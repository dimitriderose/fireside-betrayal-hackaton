import asyncio
import logging
import os
from typing import Optional, List, Dict, Any
from datetime import datetime

from models.game import (
    GameState, PlayerState, AICharacter, GameEvent, ChatMessage, Phase, GameStatus
)
from config import settings

logger = logging.getLogger(__name__)


class FirestoreService:
    """
    Async-friendly Firestore wrapper using run_in_executor to avoid
    blocking the event loop. Switch to AsyncClient once stable.
    """

    def __init__(self):
        if settings.firestore_emulator_host:
            os.environ["FIRESTORE_EMULATOR_HOST"] = settings.firestore_emulator_host
        # Lazy import so the service can be instantiated before GCP creds exist
        from google.cloud import firestore
        self.db = firestore.Client(project=settings.google_cloud_project or None)

    def _run(self, fn):
        """Run a sync Firestore call in the default thread pool."""
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(None, fn)

    # ── Collection helpers ────────────────────────────────────────────────────

    def _game_ref(self, game_id: str):
        return self.db.collection("games").document(game_id)

    def _players_ref(self, game_id: str):
        return self._game_ref(game_id).collection("players")

    def _events_ref(self, game_id: str):
        return self._game_ref(game_id).collection("events")

    def _chat_ref(self, game_id: str):
        return self._game_ref(game_id).collection("chat")

    # ── Game CRUD ─────────────────────────────────────────────────────────────

    async def create_game(
        self,
        host_player_id: str,
        difficulty: str = "normal",
        random_alignment: bool = False,
        narrator_preset: str = "classic",
        in_person_mode: bool = False,
    ) -> GameState:
        game = GameState(
            host_player_id=host_player_id,
            difficulty=difficulty,
            random_alignment=random_alignment,
            narrator_preset=narrator_preset,
            in_person_mode=in_person_mode,
        )
        data = game.model_dump()
        data["created_at"] = data["created_at"].isoformat()
        data["session"]["started_at"] = None
        await self._run(lambda: self._game_ref(game.id).set(data))
        return game

    async def get_game(self, game_id: str) -> Optional[GameState]:
        doc = await self._run(lambda: self._game_ref(game_id).get())
        if doc.exists:
            return GameState(**doc.to_dict())
        return None

    async def update_game(self, game_id: str, updates: Dict[str, Any]):
        await self._run(lambda: self._game_ref(game_id).update(updates))

    async def set_phase(self, game_id: str, phase: Phase, round: Optional[int] = None):
        updates: Dict[str, Any] = {"phase": phase.value}
        if round is not None:
            updates["round"] = round
        await self.update_game(game_id, updates)

    async def set_status(self, game_id: str, status: str):
        await self.update_game(game_id, {"status": status})

    # ── Player CRUD ───────────────────────────────────────────────────────────

    async def add_player(self, game_id: str, player_id: str, name: str) -> PlayerState:
        player = PlayerState(id=player_id, name=name)
        data = player.model_dump()
        data["joined_at"] = data["joined_at"].isoformat()
        await self._run(lambda: self._players_ref(game_id).document(player_id).set(data))
        return player

    async def get_player(self, game_id: str, player_id: str) -> Optional[PlayerState]:
        doc = await self._run(lambda: self._players_ref(game_id).document(player_id).get())
        if doc.exists:
            return PlayerState(**doc.to_dict())
        return None

    async def get_all_players(self, game_id: str) -> List[PlayerState]:
        docs = await self._run(lambda: list(self._players_ref(game_id).order_by("joined_at").stream()))
        return [PlayerState(**d.to_dict()) for d in docs]

    async def get_alive_players(self, game_id: str) -> List[PlayerState]:
        players = await self.get_all_players(game_id)
        return [p for p in players if p.alive]

    async def update_player(self, game_id: str, player_id: str, updates: Dict[str, Any]):
        await self._run(lambda: self._players_ref(game_id).document(player_id).update(updates))

    async def set_player_connected(self, game_id: str, player_id: str, connected: bool):
        await self.update_player(game_id, player_id, {"connected": connected})

    async def set_player_ready(self, game_id: str, player_id: str):
        await self.update_player(game_id, player_id, {"ready": True})

    async def eliminate_by_character(self, game_id: str, character_name: str) -> bool:
        """Mark the player (or AI) with the given character name as dead."""
        players = await self.get_all_players(game_id)
        for p in players:
            if p.character_name == character_name:
                await self.update_player(game_id, p.id, {"alive": False})
                return True
        # Check AI character
        game = await self.get_game(game_id)
        if game and game.ai_character and game.ai_character.name == character_name:
            await self.update_game(game_id, {"ai_character.alive": False})
            return True
        return False

    # ── Votes ─────────────────────────────────────────────────────────────────

    async def cast_vote(self, game_id: str, voter_id: str, target_character: str):
        await self.update_player(game_id, voter_id, {"voted_for": target_character})

    async def get_vote_tally(self, game_id: str) -> Dict[str, int]:
        """Return {character_name: vote_count} for all non-null votes."""
        players = await self.get_all_players(game_id)
        tally: Dict[str, int] = {}
        for p in players:
            if p.voted_for:
                tally[p.voted_for] = tally.get(p.voted_for, 0) + 1
        return tally

    async def clear_votes(self, game_id: str):
        players = await self.get_all_players(game_id)
        for p in players:
            if p.voted_for:
                await self.update_player(game_id, p.id, {"voted_for": None})

    # ── Night actions ─────────────────────────────────────────────────────────

    async def set_night_action(self, game_id: str, player_id: str, target: str):
        await self.update_player(game_id, player_id, {"night_action": target})

    async def get_night_actions(self, game_id: str) -> Dict[str, str]:
        """Return {player_id: target_character} for all players with night actions.
        Keyed by player_id (not role) to avoid silent overwrites if two players share a role."""
        players = await self.get_all_players(game_id)
        return {p.id: p.night_action for p in players if p.night_action and p.role}

    async def clear_night_actions(self, game_id: str):
        players = await self.get_all_players(game_id)
        for p in players:
            if p.night_action:
                await self.update_player(game_id, p.id, {"night_action": None})

    # ── AI character ──────────────────────────────────────────────────────────

    async def set_ai_character(self, game_id: str, ai_char: AICharacter):
        await self.update_game(game_id, {"ai_character": ai_char.model_dump()})

    async def get_ai_character(self, game_id: str) -> Optional[AICharacter]:
        game = await self.get_game(game_id)
        if game and game.ai_character:
            return game.ai_character
        return None

    # ── Events (append-only audit log) ───────────────────────────────────────

    async def log_event(self, game_id: str, event: GameEvent):
        data = event.model_dump()
        data["timestamp"] = data["timestamp"].isoformat()
        await self._run(lambda: self._events_ref(game_id).document(event.id).set(data))

    async def get_events(
        self, game_id: str, round: Optional[int] = None, visible_only: bool = False
    ) -> List[GameEvent]:
        ref = self._events_ref(game_id)
        if round is not None:
            ref = ref.where("round", "==", round)
        if visible_only:
            ref = ref.where("visible_in_game", "==", True)
        docs = await self._run(lambda: list(ref.order_by("timestamp").stream()))
        return [GameEvent(**d.to_dict()) for d in docs]

    # ── Chat messages ─────────────────────────────────────────────────────────

    async def add_chat_message(self, game_id: str, message: ChatMessage):
        data = message.model_dump()
        data["timestamp"] = data["timestamp"].isoformat()
        await self._run(lambda: self._chat_ref(game_id).document(message.id).set(data))

    async def get_chat_messages(self, game_id: str, limit: int = 50) -> List[ChatMessage]:
        docs = await self._run(
            lambda: self._chat_ref(game_id).order_by("timestamp").limit_to_last(limit).get()
        )
        return [ChatMessage(**d.to_dict()) for d in docs]

    # ── Atomic resolution guards ────────────────────────────────────────────

    async def try_set_resolving(self, game_id: str, field: str) -> bool:
        """Atomically check+set a boolean resolving flag on the game document.

        Uses a Firestore transaction so that only one caller wins when
        concurrent requests race (e.g. two simultaneous last-votes).

        Args:
            game_id: The game document ID.
            field: The boolean field name, e.g. 'vote_resolving' or 'night_resolving'.

        Returns:
            True if this caller acquired the lock (field was False/missing and is now True).
            False if another caller already holds it.
        """
        from google.cloud import firestore as _firestore

        @_firestore.transactional
        def _txn(transaction):
            ref = self._game_ref(game_id)
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return False
            data = snapshot.to_dict()
            if data.get(field, False):
                return False  # Already resolving
            transaction.update(ref, {field: True})
            return True

        transaction = self.db.transaction()
        return await self._run(lambda: _txn(transaction))

    async def clear_resolving(self, game_id: str, field: str) -> None:
        """Clear a resolving flag back to False."""
        await self.update_game(game_id, {field: False})

    # ── Transactional critical paths ──────────────────────────────────────────

    async def start_game_transactional(self, game_id: str) -> bool:
        """Atomically check status==LOBBY and set IN_PROGRESS.

        Returns True if the transition succeeded, False if the game was
        not in LOBBY state (already started or finished).
        """
        from google.cloud import firestore as _firestore

        @_firestore.transactional
        def _txn(transaction):
            ref = self._game_ref(game_id)
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return False
            data = snapshot.to_dict()
            if data.get("status") != GameStatus.LOBBY.value:
                return False
            transaction.update(ref, {"status": GameStatus.IN_PROGRESS.value})
            return True

        transaction = self.db.transaction()
        return await self._run(lambda: _txn(transaction))

    async def eliminate_character_transactional(self, game_id: str, character_name: str) -> bool:
        """Atomically verify a character is alive and mark them as dead.

        Handles both human players (subcollection) and AI characters
        (fields on game document).

        Returns True if the character was found alive and eliminated.
        """
        from google.cloud import firestore as _firestore

        # First try human players
        players = await self.get_all_players(game_id)
        for p in players:
            if p.character_name == character_name:
                @_firestore.transactional
                def _txn_player(transaction, pid=p.id):
                    ref = self._players_ref(game_id).document(pid)
                    snapshot = ref.get(transaction=transaction)
                    if not snapshot.exists:
                        return False
                    data = snapshot.to_dict()
                    if not data.get("alive", False):
                        return False  # Already dead
                    transaction.update(ref, {"alive": False})
                    return True

                transaction = self.db.transaction()
                return await self._run(lambda: _txn_player(transaction))

        # Try AI characters
        game = await self.get_game(game_id)
        if not game:
            return False

        for ai_field in ["ai_character", "ai_character_2"]:
            ai = getattr(game, ai_field, None)
            if ai and ai.name == character_name:
                @_firestore.transactional
                def _txn_ai(transaction, field=ai_field):
                    ref = self._game_ref(game_id)
                    snapshot = ref.get(transaction=transaction)
                    if not snapshot.exists:
                        return False
                    data = snapshot.to_dict()
                    ai_data = data.get(field)
                    if not ai_data or not ai_data.get("alive", False):
                        return False
                    transaction.update(ref, {f"{field}.alive": False})
                    return True

                transaction = self.db.transaction()
                return await self._run(lambda: _txn_ai(transaction))

        return False

    # ── Ghost messages (Ghost Council — dead players only) ─────────────────

    def _ghost_ref(self, game_id: str):
        return self._game_ref(game_id).collection("ghost_messages")

    async def add_ghost_message(self, game_id: str, message: ChatMessage):
        data = message.model_dump()
        data["timestamp"] = data["timestamp"].isoformat()
        await self._run(lambda: self._ghost_ref(game_id).document(message.id).set(data))

    async def get_ghost_messages(self, game_id: str, limit: int = 50) -> List[ChatMessage]:
        docs = await self._run(
            lambda: self._ghost_ref(game_id).order_by("timestamp").limit_to_last(limit).get()
        )
        return [ChatMessage(**d.to_dict()) for d in docs]


_firestore_service: Optional["FirestoreService"] = None


def get_firestore_service() -> "FirestoreService":
    """Lazy singleton — initialised on first call, not at import time.
    This prevents credential errors from crashing the app before FastAPI boots.
    Use as a FastAPI dependency: Depends(get_firestore_service)
    """
    global _firestore_service
    if _firestore_service is None:
        _firestore_service = FirestoreService()
    return _firestore_service


# Convenience alias for direct imports (backwards-compatible)
firestore_service = get_firestore_service

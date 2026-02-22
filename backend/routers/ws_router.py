"""
WebSocket Hub — real-time multiplayer connection management.

URL: /ws/{game_id}?playerId={player_id}

Connection flow:
  1. Accept connection → validate game + player exist
  2. Mark player connected in Firestore
  3. Send private "connected" message with full game state snapshot
  4. Broadcast "player_joined" to all other players
  5. Message loop (handle_message dispatcher)
  6. On disconnect: mark disconnected, broadcast "player_left"

Client → server message types handled here:
  ping          — keep-alive heartbeat → responds with "pong"
  ready         — player ready in lobby
  message       — free-form chat (stored; Narrator picks it up in P0-5)
  vote          — vote for a character (day_vote phase only)
  night_action  — Seer / Healer / Drunk action (night phase only)
  hunter_revenge — Hunter's revenge kill (after Hunter elimination)

Phase auto-advance (vote phase only):
  When all alive human players have submitted their vote,
  the hub auto-tallies votes, broadcasts elimination, and advances
  to the next phase (NIGHT or GAME_OVER).

Night auto-advance is deferred to the Narrator Agent (P0-5)
to keep the coordinator role in one place.
"""
import json
import logging
from typing import Dict, Optional, Any, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from models.game import Phase, Role, GameStatus, ChatMessage
from services.firestore_service import get_firestore_service

# Games whose vote tally is currently being resolved.
# Guards against double-advance when two players vote simultaneously.
# Safe without a Lock because asyncio is single-threaded: no await between
# the membership test and the add(), so no interleaving is possible.
_resolving_votes: Set[str] = set()

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# ── Role description cards (sent privately at game start) ─────────────────────

ROLE_DESCRIPTIONS: Dict[str, str] = {
    "villager": (
        "You are a Villager of Thornwood. Survive the night and identify "
        "the Shapeshifter hiding among you. Vote wisely during the day."
    ),
    "seer": (
        "You are the Seer. Each night you may investigate one character "
        "to learn whether they are the Shapeshifter."
    ),
    "healer": (
        "You are the Healer. Each night you may protect one character "
        "from elimination. You cannot protect yourself."
    ),
    "hunter": (
        "You are the Hunter. If you are eliminated — by vote or by night — "
        "you immediately drag one other character to their doom."
    ),
    "drunk": (
        "You believe you are the Seer, but something is wrong with your visions. "
        "Your investigations always return the WRONG answer."
    ),
    "shapeshifter": (
        "You are the Shapeshifter. Blend in, sow suspicion, and eliminate the "
        "villagers one by one before they unmask you."
    ),
}


# ── Connection Manager ─────────────────────────────────────────────────────────

class ConnectionManager:
    """
    Tracks active WebSocket connections per game.
    Safe for asyncio single-threaded event loop (no extra locking needed).
    """

    def __init__(self):
        # {game_id: {player_id: WebSocket}}
        self._games: Dict[str, Dict[str, WebSocket]] = {}

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def connect(self, game_id: str, player_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._games.setdefault(game_id, {})[player_id] = ws
        logger.debug(
            f"[{game_id}] {player_id} connected ({self.count(game_id)} total)"
        )

    def disconnect(self, game_id: str, player_id: str) -> None:
        game_conns = self._games.get(game_id, {})
        game_conns.pop(player_id, None)
        if not game_conns:
            self._games.pop(game_id, None)

    def count(self, game_id: str) -> int:
        return len(self._games.get(game_id, {}))

    def is_connected(self, game_id: str, player_id: str) -> bool:
        return player_id in self._games.get(game_id, {})

    # ── Sending ────────────────────────────────────────────────────────────────

    async def send_to(
        self, game_id: str, player_id: str, message: Dict
    ) -> None:
        """Send a private message to a single player."""
        ws = self._games.get(game_id, {}).get(player_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.warning(
                    f"[{game_id}] send_to {player_id} failed: {exc}"
                )
                self.disconnect(game_id, player_id)

    async def broadcast(
        self,
        game_id: str,
        message: Dict,
        exclude: Optional[str] = None,
    ) -> None:
        """Broadcast a message to all connected players in a game."""
        for pid, ws in list(self._games.get(game_id, {}).items()):
            if pid == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.warning(
                    f"[{game_id}] broadcast to {pid} failed: {exc}"
                )
                self.disconnect(game_id, pid)

    # ── High-level game event helpers ──────────────────────────────────────────

    async def broadcast_game_start(
        self, game_id: str, assignments: list
    ) -> None:
        """
        Called by game_router after role assignment.
        Broadcasts phase_change → NIGHT, then sends private role cards.
        """
        await self.broadcast(game_id, {
            "type": "phase_change",
            "phase": Phase.NIGHT.value,
        })
        for a in assignments:
            await self.send_to(game_id, a["player_id"], {
                "type": "role",
                "role": a["role"],
                "characterName": a["character_name"],
                "characterIntro": a["character_intro"],
                "description": ROLE_DESCRIPTIONS.get(a["role"], ""),
            })

    async def broadcast_phase_change(
        self, game_id: str, phase: Phase
    ) -> None:
        await self.broadcast(game_id, {
            "type": "phase_change",
            "phase": phase.value,
        })

    async def broadcast_elimination(
        self,
        game_id: str,
        character_name: str,
        was_traitor: bool,
        role: Optional[str],
        needs_hunter_revenge: bool = False,
        tally: Optional[Dict] = None,
    ) -> None:
        await self.broadcast(game_id, {
            "type": "elimination",
            "characterName": character_name,
            "wasTraitor": was_traitor,
            "role": role,
            "triggerHunterRevenge": needs_hunter_revenge,
            "tally": tally or {},
        })

    async def broadcast_game_over(
        self,
        game_id: str,
        winner: str,
        reason: str,
        character_reveals: list,
    ) -> None:
        await self.broadcast(game_id, {
            "type": "game_over",
            "winner": winner,
            "reason": reason,
            "characterReveals": character_reveals,
        })

    async def broadcast_transcript(
        self,
        game_id: str,
        speaker: str,
        text: str,
        source: str = "player",
        phase: Optional[str] = None,
        round_num: Optional[int] = None,
    ) -> None:
        """Broadcast a dialogue line (player chat or narrator speech)."""
        msg: Dict[str, Any] = {
            "type": "transcript",
            "speaker": speaker,
            "text": text,
            "source": source,
        }
        if phase:
            msg["phase"] = phase
        if round_num is not None:
            msg["round"] = round_num
        await self.broadcast(game_id, msg)

    async def broadcast_audio(
        self, game_id: str, pcm_base64: str
    ) -> None:
        """Broadcast a PCM audio chunk (narrator voice via Gemini Live)."""
        await self.broadcast(game_id, {
            "type": "audio",
            "data": pcm_base64,
            "sampleRate": 24000,
        })


# Module-level singleton — imported by game_router, narrator, and traitor agent
manager = ConnectionManager()


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

@router.websocket("/ws/{game_id}")
async def websocket_endpoint(
    ws: WebSocket,
    game_id: str,
    playerId: str = Query(..., description="Player UUID from join response"),
):
    fs = get_firestore_service()

    # ── Validate game and player ───────────────────────────────────────────────
    game = await fs.get_game(game_id)
    if not game:
        await ws.close(code=4404, reason="Game not found")
        return
    player = await fs.get_player(game_id, playerId)
    if not player:
        await ws.close(code=4403, reason="Player not found in this game")
        return

    # ── Accept and register ────────────────────────────────────────────────────
    await manager.connect(game_id, playerId, ws)
    await fs.set_player_connected(game_id, playerId, connected=True)

    # Refresh player (character_name is set after game start)
    player = await fs.get_player(game_id, playerId)
    alive_players = await fs.get_alive_players(game_id)
    ai_char = await fs.get_ai_character(game_id)

    # Private "connected" message with game snapshot
    await manager.send_to(game_id, playerId, {
        "type": "connected",
        "playerId": playerId,
        "characterName": player.character_name,
        "gameState": {
            "phase": game.phase.value,
            "round": game.round,
            "status": game.status.value,
            "characterCast": game.character_cast,
            "players": [p.to_public() for p in alive_players],
            "aiCharacter": (
                {"name": ai_char.name, "alive": ai_char.alive}
                if ai_char else None
            ),
        },
    })

    # Broadcast presence to everyone else (use character name only)
    if player.character_name:
        await manager.broadcast(game_id, {
            "type": "player_joined",
            "characterName": player.character_name,
            "count": manager.count(game_id),
        }, exclude=playerId)

    # ── Message loop ───────────────────────────────────────────────────────────
    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_to(game_id, playerId, {
                    "type": "error",
                    "message": "Invalid JSON",
                    "code": "PARSE_ERROR",
                })
                continue

            msg_type = data.get("type", "")
            await _handle_message(game_id, playerId, msg_type, data, fs)

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(game_id, playerId)
        await fs.set_player_connected(game_id, playerId, connected=False)
        player_refresh = await fs.get_player(game_id, playerId)
        # Use character_name if assigned (in-game), fall back to player name (lobby)
        if player_refresh:
            char_name = player_refresh.character_name or player_refresh.name
        else:
            char_name = playerId
        await manager.broadcast(game_id, {
            "type": "player_left",
            "characterName": char_name,
            "count": manager.count(game_id),
        })


# ── Message dispatcher ─────────────────────────────────────────────────────────

async def _handle_message(
    game_id: str,
    player_id: str,
    msg_type: str,
    data: Dict,
    fs,
) -> None:
    if msg_type == "ping":
        await manager.send_to(game_id, player_id, {"type": "pong"})

    elif msg_type == "ready":
        await _on_ready(game_id, player_id, fs)

    elif msg_type == "message":
        await _on_chat(game_id, player_id, data, fs)

    elif msg_type == "vote":
        await _on_vote(game_id, player_id, data, fs)

    elif msg_type == "night_action":
        await _on_night_action(game_id, player_id, data, fs)

    elif msg_type == "hunter_revenge":
        await _on_hunter_revenge(game_id, player_id, data, fs)

    else:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": f"Unknown message type: '{msg_type}'",
            "code": "UNKNOWN_TYPE",
        })


# ── Handlers ──────────────────────────────────────────────────────────────────

async def _on_ready(game_id: str, player_id: str, fs) -> None:
    game = await fs.get_game(game_id)
    if game and game.status == GameStatus.LOBBY:
        await fs.set_player_ready(game_id, player_id)
        player = await fs.get_player(game_id, player_id)
        await manager.broadcast(game_id, {
            "type": "player_ready",
            "characterName": player.character_name if player else player_id,
        })


async def _on_chat(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    text = str(data.get("text", "")).strip()[:500]
    if not text:
        return

    game = await fs.get_game(game_id)
    player = await fs.get_player(game_id, player_id)
    if not player:
        return

    if game and game.status == GameStatus.IN_PROGRESS and not player.alive:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Eliminated players cannot send messages",
            "code": "PLAYER_ELIMINATED",
        })
        return

    speaker = player.character_name or player_id
    if game:
        msg = ChatMessage(
            speaker=speaker,
            speaker_player_id=player_id,
            text=text,
            source="player",
            phase=game.phase,
            round=game.round,
        )
        await fs.add_chat_message(game_id, msg)

    await manager.broadcast_transcript(
        game_id,
        speaker=speaker,
        text=text,
        source="player",
        phase=game.phase.value if game else None,
        round_num=game.round if game else None,
    )


async def _on_vote(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    game = await fs.get_game(game_id)
    if not game or game.phase != Phase.DAY_VOTE:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Votes can only be cast during the day vote phase",
            "code": "WRONG_PHASE",
        })
        return

    player = await fs.get_player(game_id, player_id)
    if not player or not player.alive:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Eliminated players cannot vote",
            "code": "PLAYER_ELIMINATED",
        })
        return

    target = str(data.get("target", "")).strip()
    if not target:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Vote target is required",
            "code": "MISSING_TARGET",
        })
        return

    # Validate target is an alive character
    alive_players = await fs.get_alive_players(game_id)
    ai_char = await fs.get_ai_character(game_id)
    alive_chars = {p.character_name for p in alive_players}
    if ai_char and ai_char.alive:
        alive_chars.add(ai_char.name)

    if target not in alive_chars:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": f"'{target}' is not a valid alive character",
            "code": "INVALID_TARGET",
        })
        return

    # Prevent changing a vote once cast
    if player.voted_for is not None:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "You have already voted this round",
            "code": "VOTE_ALREADY_CAST",
        })
        return

    await fs.cast_vote(game_id, player_id, target)

    # Broadcast updated vote map
    all_players = await fs.get_all_players(game_id)
    votes_map = {
        p.character_name: p.voted_for
        for p in all_players
        if p.alive and p.character_name
    }
    tally = await fs.get_vote_tally(game_id)
    await manager.broadcast(game_id, {
        "type": "vote_update",
        "votes": votes_map,
        "tally": tally,
    })

    # Auto-advance when all alive humans have voted
    voted_count = sum(1 for p in all_players if p.alive and p.voted_for)
    alive_count = sum(1 for p in all_players if p.alive)
    if voted_count >= alive_count and game_id not in _resolving_votes:
        await _resolve_vote_and_advance(game_id, fs)


async def _resolve_vote_and_advance(game_id: str, fs) -> None:
    """Tally, eliminate, check win condition, advance phase.

    Protected by _resolving_votes set so concurrent calls from simultaneous
    last votes cannot fire this twice for the same game.
    """
    if game_id in _resolving_votes:
        return
    _resolving_votes.add(game_id)
    try:
        from agents.game_master import game_master

        tally_result = await game_master.tally_votes(game_id)

        if tally_result["result"] == "no_votes":
            logger.warning(f"[{game_id}] No votes cast — skipping to NIGHT")
            next_phase = await game_master.advance_phase(game_id)
            await manager.broadcast_phase_change(game_id, next_phase)
            return

        eliminated = tally_result["eliminated"]
        elim_result = await game_master.eliminate_character(game_id, eliminated)

        await manager.broadcast_elimination(
            game_id,
            character_name=eliminated,
            was_traitor=elim_result["was_traitor"],
            role=elim_result["role"],
            needs_hunter_revenge=elim_result["needs_hunter_revenge"],
            tally=tally_result["tally"],
        )

        win = await game_master.check_win_condition(game_id)
        if win:
            await _end_game(game_id, win["winner"], win["reason"], fs)
            return

        next_phase = await game_master.advance_phase(game_id)
        await manager.broadcast_phase_change(game_id, next_phase)
    finally:
        _resolving_votes.discard(game_id)


async def _on_night_action(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    game = await fs.get_game(game_id)
    if not game or game.phase != Phase.NIGHT:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Night actions can only be submitted during the night phase",
            "code": "WRONG_PHASE",
        })
        return

    player = await fs.get_player(game_id, player_id)
    if not player or not player.alive:
        return

    if player.role not in {Role.SEER, Role.HEALER, Role.DRUNK}:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Your role has no night action",
            "code": "NO_NIGHT_ACTION",
        })
        return

    target = str(data.get("target", "")).strip()
    if not target:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Night action target is required",
            "code": "MISSING_TARGET",
        })
        return

    # Validate target is alive
    alive_players = await fs.get_alive_players(game_id)
    ai_char = await fs.get_ai_character(game_id)
    alive_chars = {p.character_name for p in alive_players}
    if ai_char and ai_char.alive:
        alive_chars.add(ai_char.name)

    if target not in alive_chars:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": f"'{target}' is not a valid alive character",
            "code": "INVALID_TARGET",
        })
        return

    if player.role == Role.HEALER and target == player.character_name:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "The Healer cannot protect themselves",
            "code": "INVALID_SELF_TARGET",
        })
        return

    await fs.set_night_action(game_id, player_id, target)
    await manager.send_to(game_id, player_id, {
        "type": "night_action_received",
        "action": data.get("action", ""),
        "target": target,
    })


async def _on_hunter_revenge(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    from agents.game_master import game_master

    player = await fs.get_player(game_id, player_id)
    # Hunter must be eliminated (alive=False) and hold the HUNTER role
    if not player or player.role != Role.HUNTER or player.alive:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Only an eliminated Hunter can use hunter_revenge",
            "code": "NOT_HUNTER",
        })
        return

    target = str(data.get("target", "")).strip()
    if not target or target == player.character_name:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Invalid hunter revenge target",
            "code": "INVALID_TARGET",
        })
        return

    result = await game_master.execute_hunter_revenge(
        game_id,
        hunter_character=player.character_name,
        target_character=target,
    )

    await manager.broadcast(game_id, {
        "type": "hunter_revenge",
        "hunterCharacter": player.character_name,
        "targetCharacter": target,
        "targetWasTraitor": result["was_traitor"],
    })

    win = await game_master.check_win_condition(game_id)
    if win:
        await _end_game(game_id, win["winner"], win["reason"], fs)
        return

    next_phase = await game_master.advance_phase(game_id)
    await manager.broadcast_phase_change(game_id, next_phase)


async def _end_game(
    game_id: str, winner: str, reason: str, fs
) -> None:
    await fs.set_status(game_id, GameStatus.FINISHED.value)
    all_players = await fs.get_all_players(game_id)
    ai_char = await fs.get_ai_character(game_id)

    reveals = [
        {
            "characterName": p.character_name,
            "playerName": p.name,
            "role": p.role.value if p.role else "villager",
            "alive": p.alive,
        }
        for p in all_players
    ]
    if ai_char:
        reveals.append({
            "characterName": ai_char.name,
            "playerName": "AI",
            "role": "shapeshifter",
            "alive": ai_char.alive,
        })

    await manager.broadcast_game_over(
        game_id,
        winner=winner,
        reason=reason,
        character_reveals=reveals,
    )
    logger.info(f"[{game_id}] Game over — winner: {winner}")

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
  ping            — keep-alive heartbeat → responds with "pong"
  ready           — player ready in lobby
  message         — free-form chat (stored; Narrator picks it up in P0-5)
  vote            — vote for a character (day_vote phase only)
  night_action    — Seer / Healer / Drunk action (night phase only)
  hunter_revenge  — Hunter's revenge kill (after Hunter elimination)
  spectator_clue  — eliminated player submits a 1-word clue (day_discussion only, once per game)

Phase auto-advance (vote phase only):
  When all alive human players have submitted their vote,
  the hub auto-tallies votes, broadcasts elimination, and advances
  to the next phase (NIGHT or GAME_OVER).

Night auto-advance is deferred to the Narrator Agent (P0-5)
to keep the coordinator role in one place.
"""
import asyncio
import json
import logging
from typing import Dict, Optional, Any, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from models.game import Phase, Role, GameStatus, ChatMessage
from services.firestore_service import get_firestore_service
from agents.narrator_agent import narrator_manager

# Games whose vote tally is currently being resolved.
# Guards against double-advance when two players vote simultaneously.
# Safe without a Lock because asyncio is single-threaded: no await between
# the membership test and the add(), so no interleaving is possible.
_resolving_votes: Set[str] = set()

# Tracks which (game_id, player_id) pairs have already submitted a spectator clue.
# Prevents double-submission without touching Firestore — resets on server restart
# (acceptable for hackathon: if the server restarts mid-game, the clue limit resets).
_spectator_clues_sent: Set[str] = set()

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
            "round": 1,
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
        self, game_id: str, phase: Phase, round: Optional[int] = None
    ) -> None:
        if round is None:
            from services import firestore_service as _fs
            game = await _fs.get_game(game_id)
            round = game.round if game else 0
        await self.broadcast(game_id, {
            "type": "phase_change",
            "phase": phase.value,
            "round": round,
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
        timeline: Optional[list] = None,
    ) -> None:
        await self.broadcast(game_id, {
            "type": "game_over",
            "winner": winner,
            "reason": reason,
            "characterReveals": character_reveals,
            "timeline": timeline or [],
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
            # Frontend sends { type, data: { ... } }; unwrap inner payload for handlers
            inner_data = data.get("data") if isinstance(data.get("data"), dict) else {}
            await _handle_message(game_id, playerId, msg_type, inner_data, fs)

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

    elif msg_type == "quick_reaction":
        await _on_quick_reaction(game_id, player_id, data, fs)

    elif msg_type == "spectator_clue":
        await _on_spectator_clue(game_id, player_id, data, fs)

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

    # Forward chat to narrator during DAY_DISCUSSION so it can react
    if game:
        await narrator_manager.forward_player_message(
            game_id, speaker, text, game.phase.value
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
            logger.warning(f"[{game_id}] No votes cast — advancing to ELIMINATION then narrator will proceed to NIGHT")
            next_phase = await game_master.advance_phase(game_id)
            await manager.broadcast_phase_change(game_id, next_phase)
            # Tell narrator to narrate the deadlock and call advance_phase → NIGHT
            # (handle_advance_phase will fire trigger_night_selection when it reaches NIGHT)
            await narrator_manager.send_phase_event(game_id, "no_elimination", {
                "tally": tally_result.get("tally", {}),
            })
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

        # Advance to ELIMINATION phase — narrator will narrate then call advance_phase
        next_phase = await game_master.advance_phase(game_id)
        await manager.broadcast_phase_change(game_id, next_phase)

        await narrator_manager.send_phase_event(game_id, "elimination", {
            "character": eliminated,
            "was_traitor": elim_result["was_traitor"],
            "role": elim_result["role"],
            "tally": tally_result.get("tally", {}),
        })
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

    # Check if all role-players have now submitted — if so, resolve night
    all_players_fresh = await fs.get_all_players(game_id)
    night_role_players = [
        p for p in all_players_fresh
        if p.alive and p.role in {Role.SEER, Role.HEALER, Role.DRUNK}
    ]
    all_acted = all(p.night_action for p in night_role_players)
    if all_acted:
        await _resolve_night_and_notify_narrator(game_id, fs)


async def _resolve_night_and_notify_narrator(game_id: str, fs) -> None:
    """
    Resolve all night actions, broadcast the results, then hand off to the
    Narrator Agent which will narrate the outcome and call advance_phase.
    """
    from agents.game_master import game_master

    night_result = await game_master.resolve_night(game_id)
    killed = night_result.get("killed")

    if killed:
        # eliminate_character logs the event and returns metadata.
        # resolve_night already called fs.eliminate_by_character() so the DB update
        # is idempotent; by_vote=False ensures the event log is correct.
        elim_result = await game_master.eliminate_character(game_id, killed, by_vote=False)

        await manager.broadcast_elimination(
            game_id,
            character_name=killed,
            was_traitor=elim_result["was_traitor"],
            role=elim_result["role"],
            needs_hunter_revenge=night_result.get("hunter_triggered", False),
        )

        win = await game_master.check_win_condition(game_id)
        if win:
            await _end_game(game_id, win["winner"], win["reason"], fs)
            return

    # Deliver seer/drunk investigation result privately
    seer_result = night_result.get("seer_result")
    if seer_result:
        investigating_player_id = seer_result.get("investigating_player_id")
        if investigating_player_id:
            is_shapeshifter = seer_result["is_shapeshifter"]
            target_char = seer_result["character"]
            result_text = (
                f"{target_char} IS the Shapeshifter!"
                if is_shapeshifter
                else f"{target_char} is NOT the Shapeshifter."
            )
            await manager.send_to(game_id, investigating_player_id, {
                "type": "seer_result",
                "character": target_char,
                "isShapeshifter": is_shapeshifter,
                "text": result_text,
            })

    # Tell narrator what happened — it will narrate then call advance_phase
    await narrator_manager.send_phase_event(game_id, "night_resolved", {
        "eliminated": killed,
        "protected": night_result.get("protected"),
        "hunter_triggered": night_result.get("hunter_triggered", False),
    })


async def _on_hunter_revenge(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    from agents.game_master import game_master

    # Reject if game is already finished (e.g. duplicate message during epilogue)
    game = await fs.get_game(game_id)
    if not game or game.status != GameStatus.IN_PROGRESS:
        return

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

    await narrator_manager.send_phase_event(game_id, "hunter_revenge", {
        "hunter": player.character_name,
        "target": target,
    })

    win = await game_master.check_win_condition(game_id)
    if win:
        await _end_game(game_id, win["winner"], win["reason"], fs)
        return

    next_phase = await game_master.advance_phase(game_id)
    await manager.broadcast_phase_change(game_id, next_phase)
    # ELIMINATION → NIGHT: fire traitor night selection for the new round
    if next_phase == Phase.NIGHT:
        from agents.traitor_agent import trigger_night_selection
        asyncio.create_task(trigger_night_selection(game_id))


async def _on_quick_reaction(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    """
    Quick-reaction shortcut during DAY_DISCUSSION.
    Sends a preset line as a regular chat message so all clients + narrator see it.
    """
    game = await fs.get_game(game_id)
    if not game or game.phase != Phase.DAY_DISCUSSION:
        return

    player = await fs.get_player(game_id, player_id)
    if not player or not player.alive:
        return

    reaction = str(data.get("reaction", "")).strip()
    target = str(data.get("target", "")).strip()[:80]  # cap — character names are short

    # Validate target is an alive character if required
    if reaction in ("suspect", "trust") and target:
        alive_players = await fs.get_alive_players(game_id)
        ai_char = await fs.get_ai_character(game_id)
        alive_names = {p.character_name for p in alive_players}
        if ai_char and ai_char.alive:
            alive_names.add(ai_char.name)
        if target not in alive_names:
            return  # target is not a valid alive character

    # Map reaction type + optional target to a human-readable line
    if reaction == "suspect" and target:
        text = f"I suspect {target}."
    elif reaction == "trust" and target:
        text = f"I trust {target}."
    elif reaction == "agree":
        text = "I agree."
    elif reaction == "information":
        text = "I have information."
    else:
        return  # Unknown or missing required target

    speaker = player.character_name or player_id
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
        phase=game.phase.value,
        round_num=game.round,
    )

    # Forward to narrator so it can react narratively
    await narrator_manager.forward_player_message(game_id, speaker, text, game.phase.value)


async def _on_spectator_clue(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    """
    Eliminated player submits a 1-word clue during DAY_DISCUSSION.
    The narrator receives it and weaves it atmospherically into the narration.
    Each spectator may submit exactly one clue per round (tracked in-memory by round).
    """
    import re as _re

    # Only during DAY_DISCUSSION
    game = await fs.get_game(game_id)
    if not game or game.phase != Phase.DAY_DISCUSSION:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Clues can only be submitted during the discussion phase",
            "code": "WRONG_PHASE",
        })
        return

    # Only for eliminated players
    player = await fs.get_player(game_id, player_id)
    if not player or player.alive:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Only eliminated players can submit clues",
            "code": "PLAYER_NOT_SPECTATOR",
        })
        return

    # One clue per spectator per round (keyed by round so new rounds allow a new clue)
    clue_key = f"{game_id}:{player_id}:{game.round}"
    if clue_key in _spectator_clues_sent:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "You have already submitted your clue this round",
            "code": "CLUE_ALREADY_SENT",
        })
        return

    # Validate: alphabetic word only (blocks Unicode spaces and prompt injection)
    word = str(data.get("word", "")).strip()
    if not word or not _re.fullmatch(r"[a-zA-Z\-']{1,30}", word):
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Clue must be a single word (letters, hyphens, apostrophes only; max 30 chars)",
            "code": "INVALID_CLUE",
        })
        return

    word = word.lower()
    character_name = player.character_name or "an unknown spirit"

    # Attempt narrator delivery first — only lock the key if it succeeds
    try:
        await narrator_manager.send_phase_event(game_id, "spectator_clue", {
            "from": character_name,
            "word": word,
        })
    except Exception:
        logger.exception("[%s] Failed to deliver spectator clue to narrator", game_id)
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Could not deliver clue — please try again",
            "code": "NARRATOR_ERROR",
        })
        return

    _spectator_clues_sent.add(clue_key)

    # Confirm to the sender (clue is now committed)
    await manager.send_to(game_id, player_id, {
        "type": "clue_accepted",
        "word": word,
    })
    logger.info("[%s] Spectator clue from %s (round %d): '%s'", game_id, character_name, game.round, word)


def _build_timeline(events: list) -> list:
    """
    Group game events by round for the post-game reveal timeline.
    Returns list of { round: int, events: list[dict] } sorted by round.
    Hidden events (night actions, kill attempts, investigations) are included
    since this is shown AFTER the game ends.
    Round-0 (pre-game setup) events are excluded.
    """
    by_round: Dict[int, list] = {}
    for ev in events:
        r = getattr(ev, "round", None) or 0
        if r == 0:
            continue  # skip pre-game setup events
        if r not in by_round:
            by_round[r] = []
        by_round[r].append({
            "id": getattr(ev, "id", None),
            "type": getattr(ev, "type", None),
            "actor": getattr(ev, "actor", None),
            "target": getattr(ev, "target", None),
            "data": getattr(ev, "data", None) or {},
            "visible": getattr(ev, "visible_in_game", False),
        })
    return [
        {"round": r, "events": evs}
        for r, evs in sorted(by_round.items())
    ]


async def _delayed_narrator_stop(game_id: str, delay: int = 30) -> None:
    """Fire-and-forget: give the narrator time to deliver its epilogue, then stop."""
    await asyncio.sleep(delay)
    await narrator_manager.stop_game(game_id)


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

    # Build post-game reveal timeline from all events (including hidden ones)
    all_events = await fs.get_events(game_id, visible_only=False)
    timeline = _build_timeline(all_events)

    await manager.broadcast_game_over(
        game_id,
        winner=winner,
        reason=reason,
        character_reveals=reveals,
        timeline=timeline,
    )
    logger.info(f"[{game_id}] Game over — winner: {winner}")

    await narrator_manager.send_phase_event(game_id, "game_over", {
        "winner": winner,
        "reason": reason,
    })
    # Schedule narrator teardown after 30s epilogue window — non-blocking
    asyncio.create_task(_delayed_narrator_stop(game_id, delay=30))

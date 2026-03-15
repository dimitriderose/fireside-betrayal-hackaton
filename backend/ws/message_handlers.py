"""
WebSocket message dispatch and handler functions.

Contains the _dispatch_message router and all _on_* handler functions that
are not in vote_manager or night_resolver.
"""

import asyncio
import collections
import logging
import random
import time
from typing import Dict, Optional, Any, Set

from models.game import Phase, Role, GameStatus, ChatMessage
from services.firestore_service import get_firestore_service
from utils.tasks import safe_create_task
from constants import (
    ErrorCode,
    GHOST_MSG_COOLDOWN,
    MAX_SPEAKING_SECONDS,
)

logger = logging.getLogger(__name__)


# ── Input validation ─────────────────────────────────────────────────────────

def validate_chat_text(text: str) -> Optional[str]:
    """Sanitize and validate chat/reaction text.

    Returns the cleaned text, or None if the input is invalid (empty after strip).
    Truncates to 500 characters.
    """
    text = str(text).strip()
    if not text:
        return None
    return text[:500]


# ── Per-game state dicts ─────────────────────────────────────────────────────

# Tracks which (game_id, player_id, round) triples have submitted a spectator clue.
_spectator_clues_sent: Set[str] = set()

# Ghost message rate limit: per-player last-send timestamp (2s cooldown)
_ghost_msg_last: Dict[str, float] = {}
_GHOST_MSG_COOLDOWN = GHOST_MSG_COOLDOWN

# Chat message rate limit: max 10 messages per 10 seconds per player
_chat_msg_timestamps: Dict[str, collections.deque] = {}
_CHAT_MSG_MAX = 10
_CHAT_MSG_WINDOW = 10.0

# Tracks which dead players have used their Haunt action per round.
_haunts_used: Dict[str, Set[str]] = {}

# Push-to-talk: only one player may stream audio at a time per game.
_current_speaker: Dict[str, Optional[str]] = {}  # game_id -> player_id or None
_speaker_timeout_tasks: Dict[str, asyncio.Task] = {}
_MAX_SPEAKING_SECONDS = MAX_SPEAKING_SECONDS


# ── Dispatch ─────────────────────────────────────────────────────────────────

async def _handle_message(
    game_id: str,
    player_id: str,
    msg_type: str,
    data: Dict,
    fs,
) -> None:
    from ws.connection_manager import manager
    try:
        await _dispatch_message(game_id, player_id, msg_type, data, fs)
    except Exception as exc:
        from fastapi import WebSocketDisconnect
        if isinstance(exc, WebSocketDisconnect):
            raise
        logger.exception("[%s] Unhandled error in _handle_message (type=%s)", game_id, msg_type)
        try:
            await manager.send_to(game_id, player_id, {
                "type": "error", "message": "Internal server error", "code": ErrorCode.SERVER_ERROR
            })
        except Exception:
            pass


async def _dispatch_message(
    game_id: str,
    player_id: str,
    msg_type: str,
    data: Dict,
    fs,
) -> None:
    from ws.connection_manager import manager
    from ws.vote_manager import _on_vote, _on_in_person_vote_frame
    from ws.night_resolver import _on_night_action, _on_hunter_revenge

    if msg_type not in ("ping", "sync"):
        logger.info("[%s] dispatch: %s -> %s", game_id, player_id, msg_type)

    if msg_type == "ping":
        await manager.send_to(game_id, player_id, {"type": "pong"})

    elif msg_type == "sync":
        game = await fs.get_game(game_id)
        await manager.send_to(game_id, player_id, {
            "type": "sync_ack",
            "phase": game.phase.value if game else "setup",
            "round": game.round if game else 0,
        })

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

    elif msg_type == "ghost_message":
        await _on_ghost_message(game_id, player_id, data, fs)

    elif msg_type == "haunt_action":
        await _on_haunt_action(game_id, player_id, data, fs)

    elif msg_type == "raise_hand":
        await _on_raise_hand(game_id, player_id, data, fs)

    elif msg_type == "in_person_vote_frame":
        await _on_in_person_vote_frame(game_id, player_id, data, fs)

    elif msg_type == "start_speaking":
        await _on_start_speaking(game_id, player_id, fs)

    elif msg_type == "stop_speaking":
        await _on_stop_speaking(game_id, player_id, fs)

    else:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": f"Unknown message type: '{msg_type}'",
            "code": "UNKNOWN_TYPE",
        })


# ── Handlers ──────────────────────────────────────────────────────────────────

async def _on_ready(game_id: str, player_id: str, fs) -> None:
    from ws.connection_manager import manager
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
    from ws.connection_manager import manager, _all_ai_chars, _alive_ai_names
    from ws.conversation import get_tracker, AffectiveSignals
    from agents.narrator_agent import narrator_manager

    # Rate limit: max 10 chat messages per 10 seconds per player
    rate_key = f"{game_id}:{player_id}"
    now = time.time()
    dq = _chat_msg_timestamps.setdefault(rate_key, collections.deque())
    # Purge timestamps older than the window
    while dq and dq[0] <= now - _CHAT_MSG_WINDOW:
        dq.popleft()
    if len(dq) >= _CHAT_MSG_MAX:
        from ws.connection_manager import manager as _mgr
        await _mgr.send_to(game_id, player_id, {
            "type": "error",
            "message": "You are sending messages too quickly. Please slow down.",
            "code": "RATE_LIMITED",
        })
        return
    dq.append(now)

    text = validate_chat_text(data.get("text", ""))
    if not text:
        logger.warning("[%s] _on_chat: empty text after validation, dropping", game_id)
        return
    logger.info("[%s] _on_chat from %s: %r", game_id, player_id, text[:80])

    game = await fs.get_game(game_id)
    player = await fs.get_player(game_id, player_id)
    if not player:
        logger.warning("[%s] _on_chat: player %s not found, dropping", game_id, player_id)
        return

    # Silently drop messages from finished games
    if game and game.status == GameStatus.FINISHED:
        logger.info("[%s] _on_chat: game finished, dropping", game_id)
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
    logger.info("[%s] Chat broadcast: %s says %r", game_id, speaker, text[:80])

    # Pacing + affective signals (DAY_DISCUSSION only)
    pacing: Optional[str] = None
    affective: Optional[Dict[str, Any]] = None

    if game and game.phase == Phase.DAY_DISCUSSION:
        try:
            alive_players, last_vote_tally = await asyncio.gather(
                fs.get_alive_players(game_id),
                fs.get_vote_tally(game_id),
            )
            game_fresh = await fs.get_game(game_id)
        except Exception:
            logger.warning("[%s] Could not fetch data for pacing signals; skipping", game_id, exc_info=True)
            alive_players, last_vote_tally, game_fresh = [], {}, None

        alive_chars = [p.character_name for p in alive_players]
        if game_fresh:
            alive_chars.extend(_alive_ai_names(game_fresh))

        tracker = get_tracker(game_id)
        tracker.add_message(player_id, speaker, text, alive_chars)
        pacing = tracker.get_pacing_signal()

        ai_char = game_fresh.ai_character if game_fresh else None
        game_state_dict: Dict[str, Any] = {
            "round": game.round,
            "total_players": len(game.character_cast),
            "players": {p.character_name: {"alive": True} for p in alive_players},
            "ai_character": {"name": ai_char.name if ai_char and ai_char.alive else None},
            "last_vote_result": last_vote_tally or {},
        }
        if game_fresh:
            for ac in _all_ai_chars(game_fresh):
                if ac.alive:
                    game_state_dict["players"][ac.name] = {"alive": True}

        affective = AffectiveSignals.compute(game_state_dict, tracker)

    # Sanitize player text before embedding in narrator prompt
    safe_text = text.replace("[", "(").replace("]", ")")

    # Forward chat to narrator during DAY_DISCUSSION
    if game and game.phase == Phase.DAY_DISCUSSION:
        await narrator_manager.forward_player_message(
            game_id, speaker, safe_text, game.phase.value,
            pacing=pacing,
            affective=affective,
        )


async def _on_quick_reaction(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    from ws.connection_manager import manager, _all_ai_chars, _alive_ai_names
    from ws.conversation import get_tracker, AffectiveSignals
    from agents.narrator_agent import narrator_manager

    game = await fs.get_game(game_id)
    if not game or game.phase != Phase.DAY_DISCUSSION:
        return

    player = await fs.get_player(game_id, player_id)
    if not player or not player.alive:
        return

    reaction = str(data.get("reaction", "")).strip()
    if not reaction or reaction not in ("suspect", "trust", "agree", "information"):
        return
    raw_target = data.get("target", "") or ""
    target = validate_chat_text(raw_target) if raw_target else ""
    if target:
        target = target[:80]

    # Validate target is an alive character if required
    if reaction in ("suspect", "trust") and target:
        alive_players = await fs.get_alive_players(game_id)
        alive_names = {p.character_name for p in alive_players}
        alive_names.update(_alive_ai_names(game))
        if target not in alive_names:
            return

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
        return

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

    # Pacing + affective signals (same path as _on_chat)
    try:
        alive_players, last_vote_tally = await asyncio.gather(
            fs.get_alive_players(game_id),
            fs.get_vote_tally(game_id),
        )
        game_fresh = await fs.get_game(game_id)
    except Exception:
        logger.warning("[%s] Could not fetch data for quick_reaction signals; skipping", game_id, exc_info=True)
        alive_players, last_vote_tally, game_fresh = [], {}, None

    alive_chars = [p.character_name for p in alive_players]
    if game_fresh:
        alive_chars.extend(_alive_ai_names(game_fresh))

    tracker = get_tracker(game_id)
    tracker.add_message(player_id, speaker, text, alive_chars)
    pacing = tracker.get_pacing_signal()

    ai_char = game_fresh.ai_character if game_fresh else None
    game_state_dict: Dict[str, Any] = {
        "round": game.round,
        "total_players": len(game.character_cast),
        "players": {p.character_name: {"alive": True} for p in alive_players},
        "ai_character": {"name": ai_char.name if ai_char and ai_char.alive else None},
        "last_vote_result": last_vote_tally or {},
    }
    if game_fresh:
        for ac in _all_ai_chars(game_fresh):
            if ac.alive:
                game_state_dict["players"][ac.name] = {"alive": True}

    affective = AffectiveSignals.compute(game_state_dict, tracker)

    # Forward to narrator with pacing + affective context
    await narrator_manager.forward_player_message(
        game_id, speaker, text, game.phase.value,
        pacing=pacing,
        affective=affective,
    )


async def _on_spectator_clue(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    import re as _re
    from ws.connection_manager import manager
    from agents.narrator_agent import narrator_manager

    game = await fs.get_game(game_id)
    if not game or game.phase != Phase.DAY_DISCUSSION:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Clues can only be submitted during the discussion phase",
            "code": ErrorCode.WRONG_PHASE,
        })
        return

    player = await fs.get_player(game_id, player_id)
    if not player or player.alive:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Only eliminated players can submit clues",
            "code": "PLAYER_NOT_SPECTATOR",
        })
        return

    # One clue per spectator per round
    clue_key = f"{game_id}:{player_id}:{game.round}"
    if clue_key in _spectator_clues_sent:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "You have already submitted your clue this round",
            "code": "CLUE_ALREADY_SENT",
        })
        return

    word = str(data.get("word", "")).strip()
    if not word or not _re.fullmatch(r"[a-zA-Z\-']{1,30}", word):
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Clue must be a single word (letters, hyphens, apostrophes only; max 30 chars)",
            "code": ErrorCode.INVALID_CLUE,
        })
        return

    word = word.lower()
    character_name = player.character_name or "an unknown spirit"

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
            "code": ErrorCode.NARRATOR_ERROR,
        })
        return

    _spectator_clues_sent.add(clue_key)

    await manager.send_to(game_id, player_id, {
        "type": "clue_accepted",
        "word": word,
    })
    logger.info("[%s] Spectator clue from %s (round %d): '%s'", game_id, character_name, game.round, word)


async def _on_haunt_action(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    from models.game import GameEvent
    from ws.connection_manager import manager, _alive_ai_names

    game = await fs.get_game(game_id)
    if not game or game.phase != Phase.NIGHT:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Haunt actions can only be used during the night phase",
            "code": ErrorCode.WRONG_PHASE,
        })
        return

    if game.status != GameStatus.IN_PROGRESS:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Game is not in progress",
            "code": "GAME_NOT_ACTIVE",
        })
        return

    player = await fs.get_player(game_id, player_id)
    if not player or player.alive:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Only eliminated players can use haunt actions",
            "code": "PLAYER_NOT_DEAD",
        })
        return

    haunt_key = f"{game_id}:{game.round}"
    if player_id in _haunts_used.get(haunt_key, set()):
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "You have already used your haunt action this round",
            "code": "HAUNT_ALREADY_USED",
        })
        return

    target = str(data.get("target", "")).strip()
    if not target:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Invalid haunt target",
            "code": ErrorCode.INVALID_TARGET,
        })
        return

    alive_players = await fs.get_alive_players(game_id)
    alive_names = {p.character_name for p in alive_players}
    alive_names.update(_alive_ai_names(game))
    if target not in alive_names:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": f"{target} is not an alive character",
            "code": "TARGET_NOT_ALIVE",
        })
        return

    event = GameEvent(
        type="ghost_accuse",
        round=game.round,
        phase=Phase.NIGHT,
        actor=player.character_name,
        target=target,
        data={},
        visible_in_game=False,
    )
    await fs.log_event(game_id, event)

    _haunts_used.setdefault(haunt_key, set()).add(player_id)

    await manager.send_to(game_id, player_id, {
        "type": "haunt_confirmed",
        "target": target,
        "action": "accuse",
    })
    logger.info("[%s] Ghost accuse from %s (round %d): target=%s",
                game_id, player.character_name, game.round, target)


# ── Ghost Council (dead player chat) ─────────────────────────────────────────

async def broadcast_to_dead(game_id: str, message: Dict) -> None:
    """Broadcast a message to all dead players only."""
    fs = get_firestore_service()
    from ws.connection_manager import manager
    all_players = await fs.get_all_players(game_id)
    dead_ids = {p.id for p in all_players if not p.alive}

    game_conns = manager._games.get(game_id, {})
    for pid in list(game_conns.keys()):
        if pid in dead_ids:
            ctrl_q = manager._ctrl_queues.get(game_id, {}).get(pid)
            if ctrl_q is not None:
                ctrl_q.put_nowait(message)


async def _on_ghost_message(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    from ws.connection_manager import manager, _all_ai_chars

    text = str(data.get("text", "")).strip()[:500]
    if not text:
        return

    now = time.time()
    rate_key = f"{game_id}:{player_id}"
    if now - _ghost_msg_last.get(rate_key, 0) < _GHOST_MSG_COOLDOWN:
        return
    _ghost_msg_last[rate_key] = now

    game = await fs.get_game(game_id)
    if not game or game.status != GameStatus.IN_PROGRESS:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Ghost messages can only be sent during an active game",
            "code": "WRONG_STATUS",
        })
        return

    player = await fs.get_player(game_id, player_id)
    if not player or player.alive:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Only dead players can send ghost messages",
            "code": "PLAYER_NOT_DEAD",
        })
        return

    speaker = player.character_name or player_id

    msg = ChatMessage(
        speaker=speaker,
        speaker_player_id=player_id,
        text=text,
        source="ghost",
        phase=game.phase,
        round=game.round,
    )
    await fs.add_ghost_message(game_id, msg)

    await broadcast_to_dead(game_id, {
        "type": "ghost_message",
        "speaker": speaker,
        "text": text,
        "timestamp": msg.timestamp.isoformat(),
    })

    logger.info("[%s] Ghost message from %s: %r", game_id, speaker, text[:80])

    # Trigger AI ghost responses from dead AI characters
    try:
        dead_ai_chars = []
        for ai_char in _all_ai_chars(game):
            if not ai_char.alive:
                dead_ai_chars.append(ai_char)

        if dead_ai_chars and random.random() < 0.3:
            safe_create_task(
                _trigger_ghost_ai_responses(game_id, dead_ai_chars),
                name=f"ghost-ai-{game_id}",
                game_id=game_id,
            )
    except Exception:
        logger.exception("[%s] Failed to trigger ghost AI responses", game_id)


async def _trigger_ghost_ai_responses(game_id: str, dead_ai_chars: list) -> None:
    """Generate and broadcast ghost dialog from dead AI characters."""
    from agents.traitor_agent import generate_ghost_dialog
    fs = get_firestore_service()

    for ai_char in dead_ai_chars:
        try:
            game = await fs.get_game(game_id)
            if not game:
                return
            fs_field = "ai_character"
            if game.ai_character_2 and game.ai_character_2.name == ai_char.name:
                fs_field = "ai_character_2"

            result = await generate_ghost_dialog(game_id, ai_char, fs_field)
            dialog = result.get("dialog", "")
            if not dialog or dialog == "...":
                continue

            msg = ChatMessage(
                speaker=ai_char.name,
                text=dialog,
                source="ai_ghost",
                phase=game.phase,
                round=game.round,
            )
            await fs.add_ghost_message(game_id, msg)

            await broadcast_to_dead(game_id, {
                "type": "ghost_message",
                "speaker": ai_char.name,
                "text": dialog,
                "timestamp": msg.timestamp.isoformat(),
            })

            await asyncio.sleep(2)
        except Exception:
            logger.exception("[%s] Ghost dialog failed for %s", game_id, ai_char.name)


async def _on_raise_hand(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    from ws.connection_manager import manager
    from ws.conversation import get_hand_queue
    from agents.narrator_agent import narrator_manager

    game = await fs.get_game(game_id)
    if not game or game.phase != Phase.DAY_DISCUSSION:
        return

    player = await fs.get_player(game_id, player_id)
    if not player or not player.alive:
        return

    character_name = player.character_name
    if not character_name:
        return

    hand_queue = get_hand_queue(game_id)
    newly_added = hand_queue.raise_hand(character_name)

    if newly_added:
        await manager.broadcast(game_id, {
            "type": "hand_raised",
            "characterName": character_name,
            "queueLength": len(hand_queue.queue),
        })
        try:
            await narrator_manager.send_phase_event(game_id, "hand_raised", {
                "character": character_name,
                "queue": hand_queue.queue[:],
            })
        except Exception:
            logger.error("[%s] Failed to notify narrator of hand_raised for %s", game_id, character_name, exc_info=True)
    else:
        try:
            pos = hand_queue.queue.index(character_name) + 1
        except ValueError:
            pos = 0
        await manager.send_to(game_id, player_id, {
            "type": "hand_raise_ack",
            "characterName": character_name,
            "queuePosition": pos,
            "alreadyQueued": True,
        })


async def _on_start_speaking(game_id: str, player_id: str, fs) -> None:
    """Player requests the speaking slot (push-to-talk)."""
    from ws.connection_manager import manager
    from agents.narrator_agent import narrator_manager

    current = _current_speaker.get(game_id)
    if current and current != player_id:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Another player is currently speaking. Please wait.",
            "code": "SPEAKER_BUSY",
        })
        return

    # Claim the lock IMMEDIATELY before any await to prevent TOCTOU race
    _current_speaker[game_id] = player_id

    game = await fs.get_game(game_id)
    speaking_phases = {Phase.DAY_DISCUSSION, Phase.SEANCE}
    if not game or game.phase not in speaking_phases:
        _current_speaker[game_id] = None
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "You can only speak during the discussion or seance phase.",
            "code": ErrorCode.WRONG_PHASE,
        })
        return

    player = await fs.get_player(game_id, player_id)

    # During SEANCE: only dead players can speak
    if game.phase == Phase.SEANCE:
        if not player:
            _current_speaker[game_id] = None
            return
        if player.alive:
            _current_speaker[game_id] = None
            await manager.send_to(game_id, player_id, {
                "type": "error",
                "message": "The spirits are speaking... listen.",
                "code": "SEANCE_LIVING_BLOCKED",
            })
            return
    else:
        # Normal DAY_DISCUSSION: only alive players can speak
        if not player or not player.alive:
            _current_speaker[game_id] = None
            if player and not player.alive:
                await manager.send_to(game_id, player_id, {
                    "type": "error",
                    "message": "Eliminated players cannot speak.",
                    "code": "PLAYER_DEAD",
                })
            return

    speaker_name = player.character_name or player_id
    logger.info("[%s] %s (%s) started speaking", game_id, speaker_name, player_id)

    await manager.broadcast(game_id, {
        "type": "speaker_changed",
        "speaker": speaker_name,
        "playerId": player_id,
    })

    phase_str = "seance" if game.phase == Phase.SEANCE else "day_discussion"
    voice_label = f"[GHOST VOICE] Spirit of {speaker_name}" if game.phase == Phase.SEANCE else f"[VOICE] {speaker_name}"
    await narrator_manager.forward_player_message(
        game_id, speaker_name,
        f"{voice_label} is now speaking via microphone.",
        phase_str,
    )

    # Schedule auto-release after MAX_SPEAKING_SECONDS
    old_timeout = _speaker_timeout_tasks.pop(game_id, None)
    if old_timeout and not old_timeout.done():
        old_timeout.cancel()

    async def _auto_release_speaker():
        await asyncio.sleep(_MAX_SPEAKING_SECONDS)
        if _current_speaker.get(game_id) == player_id:
            logger.info("[%s] Auto-releasing speaker %s after %ds", game_id, speaker_name, _MAX_SPEAKING_SECONDS)
            _current_speaker[game_id] = None
            await manager.broadcast(game_id, {
                "type": "speaker_changed",
                "speaker": None,
                "playerId": None,
            })

    _speaker_timeout_tasks[game_id] = safe_create_task(
        _auto_release_speaker(),
        name=f"speaker-timeout-{game_id}",
        game_id=game_id,
    )


async def _on_stop_speaking(game_id: str, player_id: str, fs) -> None:
    """Player releases the speaking slot."""
    from ws.connection_manager import manager

    current = _current_speaker.get(game_id)
    if current != player_id:
        return

    player = await fs.get_player(game_id, player_id)
    speaker_name = player.character_name if player else player_id
    logger.info("[%s] %s (%s) stopped speaking", game_id, speaker_name, player_id)

    _current_speaker[game_id] = None

    timeout = _speaker_timeout_tasks.pop(game_id, None)
    if timeout and not timeout.done():
        timeout.cancel()

    await manager.broadcast(game_id, {
        "type": "speaker_changed",
        "speaker": None,
        "playerId": None,
    })


# ── Cleanup ──────────────────────────────────────────────────────────────────

def cleanup_game_handlers(game_id: str) -> None:
    """Clean up handler state for a game (called on game end)."""
    for key in [k for k in _haunts_used if k.startswith(f"{game_id}:")]:
        _haunts_used.pop(key, None)
    for key in [k for k in _ghost_msg_last if k.startswith(f"{game_id}:")]:
        _ghost_msg_last.pop(key, None)
    for key in [k for k in _chat_msg_timestamps if k.startswith(f"{game_id}:")]:
        _chat_msg_timestamps.pop(key, None)
    for key in [k for k in _spectator_clues_sent if k.startswith(f"{game_id}:")]:
        _spectator_clues_sent.discard(key)
    _current_speaker.pop(game_id, None)
    speaker_timeout = _speaker_timeout_tasks.pop(game_id, None)
    if speaker_timeout and not speaker_timeout.done():
        speaker_timeout.cancel()

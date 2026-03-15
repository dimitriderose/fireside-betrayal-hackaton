"""
WebSocket Hub — thin routing shell.

All logic has been moved to the `ws/` package. This module defines the
FastAPI router + websocket endpoints and re-exports symbols for backward
compatibility so that existing imports like:

    from routers.ws_router import manager
    from routers.ws_router import start_phase_timers
    from routers.ws_router import _cancel_narrator_timeout

continue to work without modification.
"""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from models.game import Phase
from services.firestore_service import get_firestore_service
from config import settings

# ── Re-exports for backward compatibility ─────────────────────────────────────
# narrator_agent.py, game_router.py, traitor_agent.py, scene_agent.py all
# import symbols from this module. We re-export from the ws/ package here.

from ws.connection_manager import (              # noqa: F401
    ConnectionManager,
    manager,
    ROLE_DESCRIPTIONS,
    _all_ai_chars,
    _alive_ai_names,
)

from ws.conversation import (                    # noqa: F401
    ConversationTracker,
    AffectiveSignals,
    HandRaiseQueue,
    get_tracker,
    reset_tracker,
    get_hand_queue,
    drain_hand_queue,
)

from ws.phase_timers import (                    # noqa: F401
    start_phase_timers,
    MIN_DISCUSSION_SECONDS,
    _phase_timer_start_times,
    _discussion_warning_tasks,
    _cancel_narrator_timeout,
    _schedule_narrator_timeout,
    _cancel_night_action_timeout,
    _vote_timeout_tasks,
    _schedule_timer_fallback,
)

from ws.vote_manager import (                    # noqa: F401
    _resolving_votes,
    _resolve_vote_and_advance,
)

from ws.night_resolver import (                  # noqa: F401
    _resolving_nights,
    _resolve_night_and_notify_narrator,
)

from ws.message_handlers import (                # noqa: F401
    _handle_message,
    _dispatch_message,
    _current_speaker,
    _speaker_timeout_tasks,
    broadcast_to_dead,
)

from ws.game_lifecycle import (                  # noqa: F401
    _end_game,
    _build_timeline,
    _delayed_narrator_stop,
    _check_seance_trigger,
    _cancel_seance_timeout,
)

from agents.narrator_agent import narrator_manager  # noqa: F401 — used by audio WS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


# ── Main WebSocket endpoint ──────────────────────────────────────────────────

@router.websocket("/ws/{game_id}")
async def websocket_endpoint(
    ws: WebSocket,
    game_id: str,
    playerId: str = Query(..., description="Player UUID from join response"),
    lastSeq: int = Query(0, description="Last received sequence number for replay"),
):
    # CORS validation on WebSocket upgrade
    origin = ws.headers.get("origin", "")
    allowed = list(settings.allowed_origins) + ([settings.extra_origin] if settings.extra_origin else [])
    if origin and not settings.debug and origin not in allowed:
        await ws.close(code=4403, reason="Origin not allowed")
        return

    fs = get_firestore_service()

    # Validate game and player
    game = await fs.get_game(game_id)
    if not game:
        await ws.close(code=4404, reason="Game not found")
        return
    player = await fs.get_player(game_id, playerId)
    if not player:
        await ws.close(code=4403, reason="Player not found in this game")
        return

    # Accept and register
    await manager.connect(game_id, playerId, ws)
    await fs.set_player_connected(game_id, playerId, connected=True)

    # Refresh player AND game (character_name / phase set after game start)
    game = await fs.get_game(game_id)
    player = await fs.get_player(game_id, playerId)
    all_players = await fs.get_all_players(game_id)
    ai_char = await fs.get_ai_character(game_id)

    # Private "connected" message with game snapshot
    ai_char_2 = getattr(game, 'ai_character_2', None)
    await manager.send_to(game_id, playerId, {
        "type": "connected",
        "playerId": playerId,
        "characterName": player.character_name,
        "role": player.role.value if player.role else None,
        "alive": player.alive,
        "gameState": {
            "phase": game.phase.value,
            "round": game.round,
            "status": game.status.value,
            "characterCast": game.character_cast,
            "players": [p.to_public() for p in all_players],
            "aiCharacter": (
                {"name": ai_char.name, "alive": ai_char.alive}
                if ai_char else None
            ),
            "aiCharacter2": (
                {"name": ai_char_2.name, "alive": ai_char_2.alive}
                if ai_char_2 else None
            ),
            "inPersonMode": game.in_person_mode,
        },
    })

    # Replay missed reliable events
    missed = manager.get_events_since(game_id, lastSeq)
    if missed:
        logger.info(f"[{game_id}] replaying {len(missed)} events (lastSeq={lastSeq}) to {playerId}")
    for entry in missed:
        if "target" in entry and entry["target"] != playerId:
            continue
        await manager.send_to(game_id, playerId, entry["msg"])

    # Send per-player candidate list if we're in a phase that needs it
    if game.phase in (Phase.NIGHT, Phase.DAY_VOTE) and player.alive and player.character_name:
        all_names = [p.character_name for p in all_players if p.character_name and p.alive]
        all_names.extend(_alive_ai_names(game))
        candidates = [n for n in all_names if n != player.character_name]
        msg_type = "night_targets" if game.phase == Phase.NIGHT else "vote_candidates"
        await manager.send_to(game_id, playerId, {
            "type": msg_type,
            "candidates": candidates,
        })

    # Broadcast presence to everyone else
    if player.character_name:
        await manager.broadcast(game_id, {
            "type": "player_joined",
            "characterName": player.character_name,
            "count": manager.count(game_id),
        }, exclude=playerId)

    # Message loop
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
            inner_data = data.get("data") if isinstance(data.get("data"), dict) else {}
            await _handle_message(game_id, playerId, msg_type, inner_data, fs)

    except WebSocketDisconnect as e:
        logger.info("[%s] %s disconnected: code=%s", game_id, playerId, e.code)
    except RuntimeError as e:
        logger.warning("[%s] %s WS RuntimeError: %s", game_id, playerId, e)
    finally:
        is_current = manager.is_current_ws(game_id, playerId, ws)
        manager.disconnect(game_id, playerId, ws=ws)
        if is_current:
            await fs.set_player_connected(game_id, playerId, connected=False)
            # Release speaker lock if this player held it
            if _current_speaker.get(game_id) == playerId:
                _current_speaker[game_id] = None
                await manager.broadcast(game_id, {
                    "type": "speaker_changed",
                    "speaker": None,
                    "playerId": None,
                })
            player_refresh = await fs.get_player(game_id, playerId)
            if player_refresh:
                char_name = player_refresh.character_name or player_refresh.name
            else:
                char_name = playerId
            await manager.broadcast(game_id, {
                "type": "player_left",
                "characterName": char_name,
                "count": manager.count(game_id),
            })


# ── Dedicated audio WebSocket endpoint ────────────────────────────────────────

@router.websocket("/ws/audio/{game_id}")
async def audio_websocket(
    ws: WebSocket,
    game_id: str,
    playerId: str = Query(..., description="Player UUID"),
):
    """Dedicated WebSocket for player mic audio (binary PCM frames)."""
    # CORS validation on WebSocket upgrade
    origin = ws.headers.get("origin", "")
    allowed = list(settings.allowed_origins) + ([settings.extra_origin] if settings.extra_origin else [])
    if origin and not settings.debug and origin not in allowed:
        await ws.close(code=4403, reason="Origin not allowed")
        return

    await ws.accept()
    logger.info("[%s] Audio WS connected: %s", game_id, playerId)

    fs = get_firestore_service()
    player = await fs.get_player(game_id, playerId)
    if not player:
        logger.warning("[%s] Audio WS: player %s not found, closing", game_id, playerId)
        await ws.close(code=1008, reason="Player not found")
        return

    speaker_name = player.character_name or playerId

    try:
        while True:
            msg = await ws.receive()
            # Fix 4: Handle both binary (audio) and text (JSON control) messages
            if "bytes" in msg and msg["bytes"] is not None:
                raw = msg["bytes"]
                # Fix 3: Skip keepalive pings (1-byte frames)
                if len(raw) <= 1:
                    continue
                if _current_speaker.get(game_id) != playerId:
                    continue
                await narrator_manager.forward_player_audio(game_id, raw, speaker=speaker_name)
            elif "text" in msg and msg["text"] is not None:
                try:
                    data = json.loads(msg["text"])
                    if data.get("type") == "end_of_speech":
                        # Fix 4: Signal Gemini that the player stopped speaking
                        await narrator_manager.signal_end_of_speech(game_id, speaker_name)
                except (json.JSONDecodeError, Exception) as e:
                    logger.debug("[%s] Audio WS text parse error: %s", game_id, e)
    except WebSocketDisconnect:
        logger.info("[%s] Audio WS disconnected: %s", game_id, playerId)
    except RuntimeError:
        logger.info("[%s] Audio WS runtime error: %s", game_id, playerId)
    finally:
        # Fix 2: Do NOT clear speaker lock here — the game WS manages speaker state
        logger.debug("[%s] Audio WS cleanup for %s", game_id, playerId)

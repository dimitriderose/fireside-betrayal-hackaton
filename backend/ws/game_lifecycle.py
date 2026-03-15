"""
Game lifecycle — end game, build timeline, seance logic, delayed narrator stop.
"""

import asyncio
import logging
from typing import Dict, Optional

from models.game import Phase, GameStatus
from services.firestore_service import get_firestore_service
from utils.tasks import safe_create_task, cancel_game_tasks
from constants import SEANCE_DURATION

logger = logging.getLogger(__name__)


# ── Seance state ─────────────────────────────────────────────────────────────

_SEANCE_DURATION = SEANCE_DURATION
_seance_timeout_tasks: Dict[str, asyncio.Task] = {}


# ── Timeline builder ─────────────────────────────────────────────────────────

def _build_timeline(events: list) -> list:
    """
    Group game events by round for the post-game reveal timeline.
    Returns list of { round: int, events: list[dict] } sorted by round.
    """
    by_round: Dict[int, list] = {}
    for ev in events:
        r = getattr(ev, "round", None) or 0
        if r == 0:
            continue
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


# ── Delayed narrator stop ───────────────────────────────────────────────────

async def _delayed_narrator_stop(game_id: str, delay: int = 30) -> None:
    """Fire-and-forget: give the narrator time to deliver its epilogue, then stop."""
    from agents.narrator_agent import narrator_manager
    await asyncio.sleep(delay)
    await narrator_manager.stop_game(game_id)
    try:
        from agents.audio_recorder import clear_recorder
        clear_recorder(game_id)
    except Exception:
        pass


# ── Seance logic ─────────────────────────────────────────────────────────────

async def _check_seance_trigger(game_id: str) -> bool:
    """
    Check if a seance should be triggered after an elimination.
    Condition: dead_count >= total_count / 2 and seance hasn't been used yet.
    Returns True if seance was triggered.
    """
    from ws.connection_manager import manager
    from agents.narrator_agent import narrator_manager

    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if not game or game.seance_used:
        return False

    all_players = await fs.get_all_players(game_id)
    total_count = len(game.character_cast)
    dead_human = sum(1 for p in all_players if not p.alive)
    dead_ai = sum(
        1 for ai in [game.ai_character, game.ai_character_2]
        if ai and not ai.alive
    )
    dead_count = dead_human + dead_ai

    if dead_count < 2 or dead_count < total_count // 2:
        return False

    # Trigger seance
    await fs.update_game(game_id, {"seance_used": True})
    await fs.set_phase(game_id, Phase.SEANCE)

    dead_names = [p.character_name for p in all_players if not p.alive]
    for ai in [game.ai_character, game.ai_character_2]:
        if ai and not ai.alive:
            dead_names.append(ai.name)

    await manager.broadcast_phase_change(game_id, Phase.SEANCE)

    await manager.broadcast(game_id, {
        "type": "timer_start",
        "phase": "seance",
        "timer_seconds": _SEANCE_DURATION,
    })

    await narrator_manager.send_phase_event(game_id, "seance_triggered", {
        "dead_characters": dead_names,
    })

    _cancel_seance_timeout(game_id)
    _seance_timeout_tasks[game_id] = safe_create_task(
        _seance_timeout(game_id, _SEANCE_DURATION),
        name=f"seance-timeout-{game_id}",
        game_id=game_id,
    )

    logger.info("[%s] Seance triggered — %d dead of %d total, ghosts: %s",
                game_id, dead_count, total_count, dead_names)
    return True


async def _seance_timeout(game_id: str, delay: int) -> None:
    """Hard backstop: force-close seance after delay seconds."""
    await asyncio.sleep(delay)
    _seance_timeout_tasks.pop(game_id, None)
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if game and game.phase == Phase.SEANCE:
        logger.info("[%s] Seance timeout — force-closing after %ds", game_id, delay)
        from ws.message_handlers import _current_speaker
        _current_speaker[game_id] = None
        from ws.connection_manager import manager
        await manager.broadcast(game_id, {
            "type": "speaker_changed",
            "speaker": None,
            "playerId": None,
        })
        from agents.narrator_agent import handle_advance_phase
        await handle_advance_phase(game_id)


def _cancel_seance_timeout(game_id: str) -> None:
    """Cancel a pending seance timeout."""
    task = _seance_timeout_tasks.pop(game_id, None)
    if task and not task.done():
        task.cancel()


# ── End game ─────────────────────────────────────────────────────────────────

async def _end_game(
    game_id: str, winner: str, reason: str, fs
) -> None:
    from ws.connection_manager import manager, _all_ai_chars
    from ws.conversation import remove_tracker, remove_hand_queue
    from ws.phase_timers import cleanup_game_timers
    from ws.message_handlers import cleanup_game_handlers
    from agents.narrator_agent import narrator_manager

    await fs.update_game(game_id, {"status": GameStatus.FINISHED.value, "winner": winner})
    all_players = await fs.get_all_players(game_id)
    game_end = await fs.get_game(game_id)
    ai_char = game_end.ai_character if game_end else await fs.get_ai_character(game_id)

    reveals = [
        {
            "characterName": p.character_name,
            "playerName": p.name,
            "role": p.role.value if p.role else "villager",
            "alive": p.alive,
        }
        for p in all_players
    ]
    all_ais = _all_ai_chars(game_end) if game_end else ([ai_char] if ai_char else [])
    for ac in all_ais:
        ai_reveal_role = "shapeshifter" if getattr(ac, "is_traitor", True) else ac.role.value
        reveals.append({
            "characterName": ac.name,
            "playerName": "AI",
            "role": ai_reveal_role,
            "alive": ac.alive,
            "isAI": True,
            "isTraitor": getattr(ac, "is_traitor", True),
        })

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

    # Atmospheric scene for game-over screen
    _go_scene = {
        "villagers": "game_over_villagers",
        "shapeshifter": "game_over_shapeshifter",
        "tanner": "game_over_tanner",
    }
    from agents.scene_agent import trigger_scene_image
    safe_create_task(
        trigger_scene_image(game_id, _go_scene.get(winner, "game_over_shapeshifter")),
        name=f"scene-game_over-{game_id}",
        game_id=game_id,
    )

    await narrator_manager.send_phase_event(game_id, "game_over", {
        "winner": winner,
        "reason": reason,
    })

    # Clean up scene cache to prevent memory leak
    from routers.game_router import _scene_cache
    _scene_cache.pop(game_id, None)

    # Clean up per-game state (but NOT sender tasks — they need to flush game_over to clients)
    remove_tracker(game_id)
    remove_hand_queue(game_id)
    cleanup_game_timers(game_id)
    cleanup_game_handlers(game_id)
    _cancel_seance_timeout(game_id)

    # Brief yield to let sender tasks flush the game_over message to clients
    await asyncio.sleep(0.5)
    cancel_game_tasks(game_id)

    try:
        from agents.traitor_agent import clear_difficulty_adapter
        clear_difficulty_adapter(game_id)
    except Exception:
        pass

    # Log strategy data — fire-and-forget
    try:
        from agents.strategy_logger import log_game_strategy
        game_state = await fs.get_game(game_id)
        safe_create_task(
            log_game_strategy(
                game_id=game_id,
                winner=winner,
                all_events=all_events,
                ai_character_name=ai_char.name if ai_char else None,
                difficulty=game_state.difficulty.value if game_state else "normal",
                player_count=len(all_players),
                final_round=game_state.round if game_state else 0,
            ),
            name=f"strategy-log-{game_id}",
            game_id=game_id,
        )
    except Exception:
        logger.warning("[%s] Could not schedule strategy logging", game_id, exc_info=True)

    # Broadcast narrator highlight reel
    try:
        from agents.audio_recorder import get_recorder
        reel = get_recorder(game_id).get_highlight_reel()
        if reel:
            await manager.broadcast(game_id, {"type": "highlight_reel", "segments": reel})
    except Exception:
        logger.warning("[%s] Could not broadcast highlight reel", game_id, exc_info=True)

    # Schedule narrator teardown after 30s epilogue window
    safe_create_task(
        _delayed_narrator_stop(game_id, delay=30),
        name=f"narrator-stop-{game_id}",
        game_id=game_id,
    )

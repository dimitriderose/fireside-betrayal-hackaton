"""
Phase timer management — narrator timeouts, discussion warnings, night action
timeouts, vote timeouts, and safety fallbacks.

All timer state dicts and scheduling/cancellation functions live here.
"""

import asyncio
import logging
import time
from typing import Dict, Any

from models.game import Phase
from services.firestore_service import get_firestore_service
from utils.tasks import safe_create_task
from constants import (
    NARRATOR_TIMEOUT_DELAYS,
    MIN_DISCUSSION_SECONDS as _MIN_DISCUSSION_SECONDS,
    NIGHT_ACTION_TIMEOUT,
    TIMER_FALLBACK_DELAY,
    VOTE_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


# ── State dicts ──────────────────────────────────────────────────────────────

# Narrator phase safety timeouts
_narrator_timeout_tasks: Dict[str, asyncio.Task] = {}

# Timeout durations per narrator-controlled phase (seconds)
_NARRATOR_TIMEOUT_DELAYS = NARRATOR_TIMEOUT_DELAYS

# Discussion warning tasks — sends narrator a wrap-up prompt before timeout
_discussion_warning_tasks: Dict[str, asyncio.Task] = {}

# Minimum discussion time — narrator cannot advance before this many seconds
MIN_DISCUSSION_SECONDS = _MIN_DISCUSSION_SECONDS

# Tracks when interactive timers actually started (after narrator's opening narration)
_phase_timer_start_times: Dict[str, float] = {}

# Safety fallback tasks — auto-start timers if narrator doesn't call start_phase_timer
_timer_fallback_tasks: Dict[str, asyncio.Task] = {}
_TIMER_FALLBACK_DELAY = TIMER_FALLBACK_DELAY

# Night action timeout
_night_action_timeout_tasks: Dict[str, asyncio.Task] = {}
_NIGHT_ACTION_TIMEOUT = NIGHT_ACTION_TIMEOUT

# Vote timeout tasks
_vote_timeout_tasks: Dict[str, asyncio.Task] = {}


# ── Discussion timeout helper ────────────────────────────────────────────────

def _discussion_timeout(alive_count: int) -> int:
    """Scale discussion duration by number of alive players."""
    if alive_count >= 7:
        return 240   # 4 min
    if alive_count >= 5:
        return 180   # 3 min
    return 120       # 2 min


# ── Discussion warning ───────────────────────────────────────────────────────

async def _discussion_warning(game_id: str, delay: int) -> None:
    """Send the narrator a wrap-up prompt before the hard timeout fires."""
    await asyncio.sleep(delay)
    _discussion_warning_tasks.pop(game_id, None)
    from agents.narrator_agent import narrator_manager
    session = narrator_manager._sessions.get(game_id)
    if session:
        await session.send(
            "[TIME WARNING] 30 seconds remain. Begin wrapping up the discussion "
            "and transition to voting. Call generate_vote_context, create summaries, "
            "then call advance_phase."
        )
        logger.info("[%s] Discussion 30s warning sent to narrator", game_id)


# ── Narrator phase timeout ───────────────────────────────────────────────────

async def _narrator_phase_timeout(game_id: str, expected_phase: Phase, delay: int) -> None:
    """Safety net: force-advance if narrator hasn't called advance_phase in time."""
    await asyncio.sleep(delay)
    _narrator_timeout_tasks.pop(game_id, None)
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if game and game.phase == expected_phase:
        logger.warning(
            "[%s] Narrator timeout fired — force-advancing from %s after %ds",
            game_id, expected_phase.value, delay,
        )
        from agents.narrator_agent import handle_advance_phase
        await handle_advance_phase(game_id)


def _schedule_narrator_timeout(game_id: str, phase: Phase) -> None:
    """Schedule a safety timeout for a narrator-controlled phase."""
    _cancel_narrator_timeout(game_id)
    delay = _NARRATOR_TIMEOUT_DELAYS.get(phase)
    if delay:
        _narrator_timeout_tasks[game_id] = safe_create_task(
            _narrator_phase_timeout(game_id, phase, delay),
            name=f"narrator-timeout-{game_id}",
            game_id=game_id,
        )


def _cancel_narrator_timeout(game_id: str) -> None:
    """Cancel a pending narrator timeout (called on successful advance)."""
    task = _narrator_timeout_tasks.pop(game_id, None)
    if task and not task.done():
        task.cancel()


# ── Night action timeout ─────────────────────────────────────────────────────

async def _night_action_timeout(game_id: str, delay: int) -> None:
    """Auto-resolve night if not all players have submitted actions in time."""
    await asyncio.sleep(delay)
    _night_action_timeout_tasks.pop(game_id, None)
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if game and game.phase == Phase.NIGHT:
        logger.warning(
            "[%s] Night action timeout fired — auto-resolving after %ds",
            game_id, delay,
        )
        from ws.night_resolver import _resolve_night_and_notify_narrator
        await _resolve_night_and_notify_narrator(game_id, fs)


def _schedule_night_action_timeout(game_id: str) -> None:
    _cancel_night_action_timeout(game_id)
    _night_action_timeout_tasks[game_id] = safe_create_task(
        _night_action_timeout(game_id, _NIGHT_ACTION_TIMEOUT),
        name=f"night-action-timeout-{game_id}",
        game_id=game_id,
    )


def _cancel_night_action_timeout(game_id: str) -> None:
    task = _night_action_timeout_tasks.pop(game_id, None)
    if task and not task.done():
        task.cancel()


# ── Vote timeout ─────────────────────────────────────────────────────────────

async def _vote_timeout(game_id: str, fs, delay: int = VOTE_TIMEOUT_SECONDS) -> None:
    """Auto-advance day_vote phase after `delay` seconds if not already resolved."""
    await asyncio.sleep(delay)
    _vote_timeout_tasks.pop(game_id, None)
    game = await fs.get_game(game_id)
    if game and game.phase == Phase.DAY_VOTE:
        logger.info("[%s] Vote timeout fired — auto-advancing phase", game_id)
        from ws.vote_manager import _resolve_vote_and_advance
        await _resolve_vote_and_advance(game_id, fs)


# ── Phase timer start (called by narrator after opening narration) ────────────

async def start_phase_timers(game_id: str) -> Dict[str, Any]:
    """
    Start the interactive phase timer. Called by narrator's start_phase_timer tool
    after its opening narration. Schedules the appropriate timers and broadcasts
    timer_start to clients.
    """
    # Cancel safety fallback — narrator called in time
    fallback = _timer_fallback_tasks.pop(game_id, None)
    if fallback and not fallback.done():
        fallback.cancel()

    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if not game:
        return {"error": "Game not found"}

    phase = game.phase
    _phase_timer_start_times[game_id] = time.time()

    timer_seconds = 0

    if phase == Phase.DAY_DISCUSSION:
        alive = await fs.get_alive_players(game_id)
        timer_seconds = _discussion_timeout(len(alive))
        # Schedule narrator safety timeout with scaled duration
        _cancel_narrator_timeout(game_id)
        _narrator_timeout_tasks[game_id] = safe_create_task(
            _narrator_phase_timeout(game_id, phase, timer_seconds),
            name=f"narrator-timeout-discussion-{game_id}",
            game_id=game_id,
        )
        # Schedule 30s warning to narrator before hard timeout
        warn_task = _discussion_warning_tasks.pop(game_id, None)
        if warn_task and not warn_task.done():
            warn_task.cancel()
        if timer_seconds > 30:
            _discussion_warning_tasks[game_id] = safe_create_task(
                _discussion_warning(game_id, timer_seconds - 30),
                name=f"discussion-warning-{game_id}",
                game_id=game_id,
            )

    elif phase == Phase.NIGHT:
        timer_seconds = _NIGHT_ACTION_TIMEOUT
        _schedule_night_action_timeout(game_id)

    elif phase == Phase.DAY_VOTE:
        timer_seconds = VOTE_TIMEOUT_SECONDS
        _cancel_narrator_timeout(game_id)  # Cancel narrator timeout — vote timeout handles this
        existing = _vote_timeout_tasks.pop(game_id, None)
        if existing and not existing.done():
            existing.cancel()
        _vote_timeout_tasks[game_id] = safe_create_task(
            _vote_timeout(game_id, fs),
            name=f"vote-timeout-{game_id}",
            game_id=game_id,
        )

    # Broadcast timer_start to all clients so they can show the countdown
    if timer_seconds > 0:
        from ws.connection_manager import manager
        await manager.broadcast(game_id, {
            "type": "timer_start",
            "phase": phase.value,
            "timer_seconds": timer_seconds,
        })

    logger.info("[%s] Phase timers started for %s (%ds)", game_id, phase.value, timer_seconds)
    return {"result": "timers_started", "phase": phase.value, "timer_seconds": timer_seconds}


# ── Timer fallback ───────────────────────────────────────────────────────────

async def _timer_start_fallback(game_id: str) -> None:
    """Safety net: auto-start phase timers if narrator doesn't call start_phase_timer."""
    await asyncio.sleep(_TIMER_FALLBACK_DELAY)
    _timer_fallback_tasks.pop(game_id, None)
    logger.warning("[%s] Timer fallback fired — narrator didn't call start_phase_timer within %ds", game_id, _TIMER_FALLBACK_DELAY)
    await start_phase_timers(game_id)


def _schedule_timer_fallback(game_id: str) -> None:
    """Schedule a safety fallback that auto-starts phase timers."""
    existing = _timer_fallback_tasks.pop(game_id, None)
    if existing and not existing.done():
        existing.cancel()
    _timer_fallback_tasks[game_id] = safe_create_task(
        _timer_start_fallback(game_id),
        name=f"timer-fallback-{game_id}",
        game_id=game_id,
    )


# ── Cleanup ──────────────────────────────────────────────────────────────────

def cleanup_game_timers(game_id: str) -> None:
    """Cancel and remove all timer state for a game (called on game end)."""
    _phase_timer_start_times.pop(game_id, None)

    timeout_task = _vote_timeout_tasks.pop(game_id, None)
    if timeout_task and not timeout_task.done():
        timeout_task.cancel()

    fallback = _timer_fallback_tasks.pop(game_id, None)
    if fallback and not fallback.done():
        fallback.cancel()

    _cancel_night_action_timeout(game_id)
    _cancel_narrator_timeout(game_id)

    warn = _discussion_warning_tasks.pop(game_id, None)
    if warn and not warn.done():
        warn.cancel()

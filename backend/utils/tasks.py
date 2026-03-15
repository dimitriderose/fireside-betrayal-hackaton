"""
Safe asyncio task management for Fireside: Betrayal.

Provides a wrapper around asyncio.create_task that:
- Logs exceptions from fire-and-forget tasks instead of silently swallowing them
- Tracks tasks per game_id for bulk cancellation on game cleanup
- Tracks tasks per player for cancellation on disconnect
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# game_id -> list of tracked tasks
_game_tasks: dict[str, list[asyncio.Task]] = {}

# game_id -> player_id -> list of tracked tasks
_player_tasks: dict[str, dict[str, list[asyncio.Task]]] = {}


def safe_create_task(
    coro,
    *,
    name: str | None = None,
    game_id: str | None = None,
    player_id: str | None = None,
) -> asyncio.Task:
    """Create an asyncio task with exception logging and optional tracking.

    Args:
        coro: The coroutine to run.
        name: Human-readable task name for logging.
        game_id: If provided, track task for bulk cancellation via cancel_game_tasks().
        player_id: If provided (along with game_id), track for cancel_player_tasks().
    """
    task = asyncio.create_task(coro, name=name)

    def _done_callback(t: asyncio.Task):
        # Clean up from tracking lists
        if game_id:
            game_list = _game_tasks.get(game_id)
            if game_list:
                try:
                    game_list.remove(t)
                except ValueError:
                    pass
            if player_id:
                player_map = _player_tasks.get(game_id)
                if player_map:
                    player_list = player_map.get(player_id)
                    if player_list:
                        try:
                            player_list.remove(t)
                        except ValueError:
                            pass

        # Log unhandled exceptions (don't log cancellations)
        if not t.cancelled():
            exc = t.exception()
            if exc:
                logger.exception(
                    "Background task '%s' failed (game=%s, player=%s)",
                    t.get_name() or name or "unnamed",
                    game_id or "?",
                    player_id or "?",
                    exc_info=exc,
                )

    task.add_done_callback(_done_callback)

    # Track per-game
    if game_id:
        _game_tasks.setdefault(game_id, []).append(task)

    # Track per-player
    if game_id and player_id:
        _player_tasks.setdefault(game_id, {}).setdefault(player_id, []).append(task)

    return task


def cancel_game_tasks(game_id: str) -> int:
    """Cancel all tracked tasks for a game. Returns count of cancelled tasks."""
    cancelled = 0
    for task in _game_tasks.pop(game_id, []):
        if not task.done():
            task.cancel()
            cancelled += 1
    _player_tasks.pop(game_id, None)
    if cancelled:
        logger.info("[%s] Cancelled %d background tasks on game cleanup", game_id, cancelled)
    return cancelled


def cancel_player_tasks(game_id: str, player_id: str) -> int:
    """Cancel all tracked tasks for a specific player. Returns count of cancelled tasks."""
    cancelled = 0
    player_map = _player_tasks.get(game_id)
    if player_map:
        for task in player_map.pop(player_id, []):
            if not task.done():
                task.cancel()
                cancelled += 1
        # Also remove from game-level list
        game_list = _game_tasks.get(game_id)
        if game_list:
            _game_tasks[game_id] = [t for t in game_list if not t.done()]
    if cancelled:
        logger.info("[%s] Cancelled %d tasks for player %s on disconnect", game_id, cancelled, player_id)
    return cancelled

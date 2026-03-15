"""
ws package — WebSocket hub split into focused modules.

Re-exports all public symbols so existing imports like
    from routers.ws_router import manager
continue to work via ws_router.py's backward-compat imports.
"""

from ws.connection_manager import (
    ConnectionManager,
    manager,
    ROLE_DESCRIPTIONS,
    _all_ai_chars,
    _alive_ai_names,
)

from ws.conversation import (
    ConversationTracker,
    AffectiveSignals,
    HandRaiseQueue,
    get_tracker,
    reset_tracker,
    remove_tracker,
    get_hand_queue,
    drain_hand_queue,
    remove_hand_queue,
)

from ws.phase_timers import (
    start_phase_timers,
    MIN_DISCUSSION_SECONDS,
    _phase_timer_start_times,
    _discussion_warning_tasks,
    _cancel_narrator_timeout,
    _schedule_narrator_timeout,
    _schedule_timer_fallback,
    _cancel_night_action_timeout,
    _schedule_night_action_timeout,
    _NARRATOR_TIMEOUT_DELAYS,
    _vote_timeout_tasks,
    cleanup_game_timers,
)

from ws.vote_manager import (
    _on_vote,
    _resolve_vote_and_advance,
    _on_in_person_vote_frame,
    _resolving_votes,
)

from ws.night_resolver import (
    _on_night_action,
    _resolve_night_and_notify_narrator,
    _on_hunter_revenge,
    _resolving_nights,
)

from ws.message_handlers import (
    _handle_message,
    _dispatch_message,
    _current_speaker,
    _speaker_timeout_tasks,
    broadcast_to_dead,
    cleanup_game_handlers,
)

from ws.game_lifecycle import (
    _end_game,
    _build_timeline,
    _delayed_narrator_stop,
    _check_seance_trigger,
    _cancel_seance_timeout,
    _seance_timeout_tasks,
)

__all__ = [
    # connection_manager
    "ConnectionManager", "manager", "ROLE_DESCRIPTIONS",
    "_all_ai_chars", "_alive_ai_names",
    # conversation
    "ConversationTracker", "AffectiveSignals", "HandRaiseQueue",
    "get_tracker", "reset_tracker", "remove_tracker",
    "get_hand_queue", "drain_hand_queue", "remove_hand_queue",
    # phase_timers
    "start_phase_timers", "MIN_DISCUSSION_SECONDS",
    "_phase_timer_start_times", "_discussion_warning_tasks",
    "_cancel_narrator_timeout", "_schedule_narrator_timeout",
    "_cancel_night_action_timeout", "_schedule_night_action_timeout",
    "_NARRATOR_TIMEOUT_DELAYS", "_vote_timeout_tasks",
    "_schedule_timer_fallback", "cleanup_game_timers",
    # vote_manager
    "_on_vote", "_resolve_vote_and_advance", "_on_in_person_vote_frame",
    "_resolving_votes",
    # night_resolver
    "_on_night_action", "_resolve_night_and_notify_narrator",
    "_on_hunter_revenge", "_resolving_nights",
    # message_handlers
    "_handle_message", "_dispatch_message", "_current_speaker",
    "_speaker_timeout_tasks", "broadcast_to_dead", "cleanup_game_handlers",
    # game_lifecycle
    "_end_game", "_build_timeline", "_delayed_narrator_stop",
    "_check_seance_trigger", "_cancel_seance_timeout", "_seance_timeout_tasks",
]

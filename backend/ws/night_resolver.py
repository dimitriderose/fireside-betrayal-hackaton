"""
Night action handling — submitting night actions, resolving night outcomes,
and hunter revenge.
"""

import asyncio
import logging
from typing import Dict, Set

from models.game import Phase, Role, GameStatus
from services.firestore_service import get_firestore_service
from utils.tasks import safe_create_task
from utils.game_utils import get_alive_character_names
from constants import ErrorCode, NIGHT_ROLE_SET

logger = logging.getLogger(__name__)

# Kept for backward-compatible imports (ws_router, ws/__init__)
_resolving_nights: Set[str] = set()


async def _on_night_action(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    from ws.connection_manager import manager

    game = await fs.get_game(game_id)
    if not game or game.phase != Phase.NIGHT:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Night actions can only be submitted during the night phase",
            "code": ErrorCode.WRONG_PHASE,
        })
        return

    player = await fs.get_player(game_id, player_id)
    if not player or not player.alive:
        return

    if player.role not in NIGHT_ROLE_SET:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Your role has no night action",
            "code": "NO_NIGHT_ACTION",
        })
        return

    target = str(data.get("target", "")).strip()

    # Shapeshifter can skip their kill by sending target="skip"
    if player.role == Role.SHAPESHIFTER and target == "skip":
        await fs.set_night_action(game_id, player_id, "skip")
        await manager.send_to(game_id, player_id, {
            "type": "night_action_received",
            "action": "skip",
            "target": "skip",
        })
        logger.info("[%s] Shapeshifter %s chose to skip kill", game_id, player.character_name)
        # Check if all role-players have submitted
        all_players_fresh = await fs.get_all_players(game_id)
        night_role_players = [
            p for p in all_players_fresh
            if p.alive and p.role in NIGHT_ROLE_SET
        ]
        all_acted = all(p.night_action for p in night_role_players)
        if all_acted:
            safe_create_task(
                _resolve_night_and_notify_narrator(game_id, fs),
                name=f"resolve-night-{game_id}",
                game_id=game_id,
            )
        return

    if not target:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Night action target is required",
            "code": "MISSING_TARGET",
        })
        return

    # Validate target is alive
    alive_players = await fs.get_alive_players(game_id)
    alive_chars = set(get_alive_character_names(game, alive_players))

    if target not in alive_chars:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": f"'{target}' is not a valid alive character",
            "code": ErrorCode.INVALID_TARGET,
        })
        return

    # No role can target themselves during the night
    if target == player.character_name:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "You cannot target yourself",
            "code": ErrorCode.INVALID_SELF_TARGET,
        })
        return

    # Human shapeshifter: create night_target event (same format as AI traitor)
    if player.role == Role.SHAPESHIFTER:
        import uuid
        from models.game import GameEvent
        await fs.log_event(game_id, GameEvent(
            id=str(uuid.uuid4()),
            type="night_target",
            round=game.round,
            phase=Phase.NIGHT,
            actor=player.character_name,
            target=target,
            visible_in_game=False,
        ))

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
        if p.alive and p.role in NIGHT_ROLE_SET
    ]
    all_acted = all(p.night_action for p in night_role_players)
    if all_acted:
        # Fire-and-forget: do NOT await inline — that blocks the submitting
        # player's WS receive loop
        safe_create_task(
            _resolve_night_and_notify_narrator(game_id, fs),
            name=f"resolve-night-{game_id}",
            game_id=game_id,
        )


async def _resolve_night_and_notify_narrator(game_id: str, fs) -> None:
    """
    Resolve all night actions, broadcast the results, then hand off to the
    Narrator Agent which will narrate the outcome and call advance_phase.
    """
    from ws.phase_timers import _cancel_night_action_timeout
    _cancel_night_action_timeout(game_id)

    # Concurrency guard — use Firestore transaction instead of in-memory set
    acquired = await fs.try_set_resolving(game_id, "night_resolving")
    if not acquired:
        logger.warning("[%s] Night resolution already in progress — skipping duplicate", game_id)
        return

    try:
        from agents.game_master import game_master
        from agents.narrator_agent import narrator_manager
        from ws.connection_manager import manager
        from ws.game_lifecycle import _end_game

        night_result = await game_master.resolve_night(game_id)
        killed = night_result.get("killed")

        if killed:
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

        # Record caught_lie signal if Seer correctly identified the Shapeshifter
        try:
            from agents.traitor_agent import get_difficulty_adapter
            game_for_signal = await fs.get_game(game_id)
            if game_for_signal:
                night_events = await fs.get_events(game_id, round=game_for_signal.round)
                for ev in night_events:
                    if (ev.type == "night_investigation"
                            and not ev.data.get("is_drunk")
                            and ev.data.get("result") is True):
                        adapter = get_difficulty_adapter(game_id, game_for_signal.difficulty.value)
                        adapter.record_signal("caught_lie")
                        break
        except Exception:
            logger.warning("[%s] Could not check seer result for caught_lie signal", game_id, exc_info=True)

        # Tell narrator what happened
        await narrator_manager.send_phase_event(game_id, "night_resolved", {
            "eliminated": killed,
            "protected": night_result.get("protected"),
            "hunter_triggered": night_result.get("hunter_triggered", False),
        })
    finally:
        await fs.clear_resolving(game_id, "night_resolving")


async def _on_hunter_revenge(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    from agents.game_master import game_master
    from agents.narrator_agent import narrator_manager
    from ws.connection_manager import manager
    from ws.game_lifecycle import _end_game

    # Reject if game is already finished
    game = await fs.get_game(game_id)
    if not game or game.status != GameStatus.IN_PROGRESS:
        return

    player = await fs.get_player(game_id, player_id)
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
            "code": ErrorCode.INVALID_TARGET,
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
    # ELIMINATION -> NIGHT: fire traitor night selection for the new round
    if next_phase == Phase.NIGHT:
        from agents.traitor_agent import trigger_all_night_actions
        safe_create_task(
            trigger_all_night_actions(game_id),
            name=f"night-actions-{game_id}",
            game_id=game_id,
        )

"""
Vote handling — casting votes, resolving tallies, and auto-advancing phases.
Also handles in-person camera vote frames.
"""

import asyncio
import logging
from typing import Dict, Set, Optional

from models.game import Phase, Role, GameStatus
from services.firestore_service import get_firestore_service
from utils.tasks import safe_create_task
from utils.game_utils import alive_ai_names, get_alive_character_names
from constants import ErrorCode

logger = logging.getLogger(__name__)

# Kept for backward-compatible imports (ws_router, ws/__init__)
_resolving_votes: Set[str] = set()


async def _on_vote(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    from ws.connection_manager import manager

    game = await fs.get_game(game_id)
    if not game or game.phase != Phase.DAY_VOTE:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Votes can only be cast during the day vote phase",
            "code": ErrorCode.WRONG_PHASE,
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

    # Prevent self-voting
    if target == player.character_name:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "You cannot vote for yourself",
            "code": ErrorCode.SELF_VOTE,
        })
        return

    # Validate target is an alive character
    alive_players = await fs.get_alive_players(game_id)
    alive_chars = set(get_alive_character_names(game, alive_players))

    if target not in alive_chars:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": f"'{target}' is not a valid alive character",
            "code": ErrorCode.INVALID_TARGET,
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
    if voted_count >= alive_count:
        # Cancel vote timeout — we're resolving now, no need for the timer
        from ws.phase_timers import _vote_timeout_tasks
        timeout_task = _vote_timeout_tasks.pop(game_id, None)
        if timeout_task and not timeout_task.done():
            timeout_task.cancel()
        await _resolve_vote_and_advance(game_id, fs)


async def _capture_individual_votes(game_id: str, fs) -> Dict[str, str]:
    """Capture the per-character vote map BEFORE tally_votes clears AI votes."""
    from utils.game_utils import all_ai_chars as _all_ai

    all_players_pre = await fs.get_all_players(game_id)
    individual_votes = {
        p.character_name: p.voted_for
        for p in all_players_pre
        if p.alive and p.voted_for and p.character_name
    }
    game_pre = await fs.get_game(game_id)
    if game_pre:
        for ai in _all_ai(game_pre):
            if ai.alive and ai.voted_for:
                individual_votes[ai.name] = ai.voted_for
    return individual_votes


async def _handle_elimination(
    game_id: str,
    fs,
    eliminated: str,
    elim_result: Dict,
    tally_result: Dict,
    individual_votes: Dict,
    is_tie: bool,
) -> bool:
    """Broadcast elimination, record difficulty signals, check win, advance phase.

    Returns True if the game ended (caller should return early).
    """
    from agents.game_master import game_master
    from agents.narrator_agent import narrator_manager
    from ws.connection_manager import manager
    from ws.game_lifecycle import _end_game

    # Tanner solo win
    if elim_result.get("role") == Role.TANNER.value:
        await manager.broadcast_elimination(
            game_id,
            character_name=eliminated,
            was_traitor=False,
            role=Role.TANNER.value,
            needs_hunter_revenge=False,
            tally=tally_result.get("tally", {}),
            individual_votes=individual_votes,
            is_tie=is_tie,
        )
        await _end_game(game_id, "tanner", "The Tanner outsmarted the village — voted out exactly as planned!", fs)
        return True

    await manager.broadcast_elimination(
        game_id,
        character_name=eliminated,
        was_traitor=elim_result["was_traitor"],
        role=elim_result["role"],
        needs_hunter_revenge=elim_result["needs_hunter_revenge"],
        tally=tally_result["tally"],
        individual_votes=individual_votes,
        is_tie=is_tie,
    )

    # Record dynamic difficulty signals based on vote outcome
    try:
        from agents.traitor_agent import get_difficulty_adapter
        game_for_adapter = await fs.get_game(game_id)
        if game_for_adapter:
            adapter = get_difficulty_adapter(game_id, game_for_adapter.difficulty.value)
            tally_vals = tally_result.get("tally", {})
            if elim_result["was_traitor"]:
                adapter.record_signal("correct_accusation")
            else:
                adapter.record_signal("wrong_elimination")
                votes_with_value = [v for v in tally_vals.values() if v > 0]
                if len(votes_with_value) == 1:
                    adapter.record_signal("unanimous_wrong_vote")
                game_for_signal = await fs.get_game(game_id)
                ai_traitor_for_vote = next(
                    (ai for ai in [game_for_signal.ai_character, game_for_signal.ai_character_2]
                     if ai and ai.is_traitor),
                    None
                ) if game_for_signal else None
                if ai_traitor_for_vote:
                    ai_votes = tally_vals.get(ai_traitor_for_vote.name, 0)
                    top_votes = max(tally_vals.values(), default=0)
                    if ai_votes > 0 and top_votes - ai_votes <= 1:
                        adapter.record_signal("close_vote_against_ai")
                    elif ai_votes == 0:
                        adapter.record_signal("ai_unquestioned")
            adapter.lock_round_fragment()
    except Exception:
        logger.warning("[%s] Could not record difficulty adaptation signal", game_id, exc_info=True)

    win = await game_master.check_win_condition(game_id)
    if win:
        await _end_game(game_id, win["winner"], win["reason"], fs)
        return True

    # Advance to ELIMINATION phase — narrator will narrate then call advance_phase
    next_phase = await game_master.advance_phase(game_id)
    await manager.broadcast_phase_change(game_id, next_phase)

    await narrator_manager.send_phase_event(game_id, "elimination", {
        "character": eliminated,
        "was_traitor": elim_result["was_traitor"],
        "role": elim_result["role"],
        "tally": tally_result.get("tally", {}),
    })
    return False


async def _handle_tie(game_id: str, fs, tally_result: Dict) -> None:
    """Handle the case when no votes were cast — advance phase with no elimination."""
    from agents.game_master import game_master
    from agents.narrator_agent import narrator_manager
    from ws.connection_manager import manager

    logger.warning(f"[{game_id}] No votes cast — advancing to ELIMINATION then narrator will proceed to NIGHT")
    next_phase = await game_master.advance_phase(game_id)
    await manager.broadcast_phase_change(game_id, next_phase)
    await narrator_manager.send_phase_event(game_id, "no_elimination", {
        "tally": tally_result.get("tally", {}),
    })


async def _resolve_vote_and_advance(game_id: str, fs) -> None:
    """Tally, eliminate, check win condition, advance phase.

    Protected by a Firestore transactional flag (vote_resolving) so
    concurrent calls from simultaneous last votes cannot fire this twice.
    """
    # Atomically acquire the resolving lock via Firestore transaction
    acquired = await fs.try_set_resolving(game_id, "vote_resolving")
    if not acquired:
        logger.info("[%s] Vote resolution already in progress — skipping duplicate", game_id)
        return

    # Cancel any pending vote timeout — we're resolving now
    from ws.phase_timers import _vote_timeout_tasks
    timeout_task = _vote_timeout_tasks.pop(game_id, None)
    if timeout_task and not timeout_task.done():
        timeout_task.cancel()

    try:
        from agents.game_master import game_master
        from ws.connection_manager import manager
        from utils.game_utils import all_ai_chars as _all_ai

        # Poll for AI votes (they're set asynchronously via Gemini calls)
        for _ in range(5):  # up to 5s max
            game_vote_check = await fs.get_game(game_id)
            if not game_vote_check:
                break
            all_ai_voted = all(
                ai.voted_for for ai in _all_ai(game_vote_check)
                if ai.alive
            )
            if all_ai_voted:
                break
            await asyncio.sleep(1)

        individual_votes = await _capture_individual_votes(game_id, fs)
        tally_result = await game_master.tally_votes(game_id)

        if tally_result["result"] == "no_votes":
            await _handle_tie(game_id, fs, tally_result)
            return

        eliminated = tally_result["eliminated"]
        elim_result = await game_master.eliminate_character(game_id, eliminated)
        is_tie = tally_result["result"] == "tie"

        await _handle_elimination(
            game_id, fs, eliminated, elim_result, tally_result,
            individual_votes, is_tie,
        )
    finally:
        await fs.clear_resolving(game_id, "vote_resolving")


async def _on_in_person_vote_frame(
    game_id: str, player_id: str, data: Dict, fs
) -> None:
    """
    Host submits a camera frame for hand-count voting.
    data: { characterName: str, imageData: str (base64 JPEG) }
    """
    from ws.connection_manager import manager

    game = await fs.get_game(game_id)
    if not game or game.phase != Phase.DAY_VOTE or not game.in_person_mode:
        return

    # Only the host may submit camera frames
    player = await fs.get_player(game_id, player_id)
    if not player or player.id != game.host_player_id:
        await manager.send_to(game_id, player_id, {
            "type": "error",
            "message": "Only the host can submit camera vote frames.",
            "code": "NOT_HOST",
        })
        return

    character_name = data.get("characterName", "").strip()
    image_b64 = data.get("imageData", "")

    if not character_name or not image_b64:
        return

    try:
        from agents.camera_vote import count_raised_hands
        result = await count_raised_hands(image_b64)
    except Exception:
        result = {"hand_count": 0, "confidence": "low"}

    hand_count = result["hand_count"]
    confidence = result["confidence"]

    if confidence == "low":
        await manager.send_to(game_id, player_id, {
            "type": "camera_vote_fallback",
            "characterName": character_name,
            "reason": "Camera image unclear — please use phone voting for this round.",
        })
        logger.info("[%s] Camera vote fallback for '%s' (low confidence)", game_id, character_name)
        return

    # Cap hand_count to number of alive players
    all_players_for_cap = await fs.get_all_players(game_id)
    alive_cap = sum(1 for p in all_players_for_cap if p.alive)
    game_for_cap = await fs.get_game(game_id)
    if game_for_cap:
        alive_cap += len(alive_ai_names(game_for_cap))
    hand_count = min(hand_count, alive_cap)

    await manager.broadcast(game_id, {
        "type": "camera_vote_result",
        "characterName": character_name,
        "handCount": hand_count,
        "confidence": confidence,
    })

    # Persist votes to Firestore
    all_players = await fs.get_all_players(game_id)
    unvoted = [p for p in all_players if p.alive and p.voted_for is None]
    assigned = 0
    for p in unvoted:
        if assigned >= hand_count:
            break
        await fs.cast_vote(game_id, p.id, character_name)
        assigned += 1

    # Broadcast updated tally
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

    logger.info(
        "[%s] Camera vote for '%s': %d hands (confidence=%s), assigned %d votes",
        game_id, character_name, hand_count, confidence, assigned,
    )

    # Auto-advance if all alive humans have now voted
    voted_count = sum(1 for p in all_players if p.alive and p.voted_for)
    alive_count = sum(1 for p in all_players if p.alive)
    if voted_count >= alive_count:
        await _resolve_vote_and_advance(game_id, fs)

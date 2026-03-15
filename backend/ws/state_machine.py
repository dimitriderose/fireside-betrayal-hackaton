"""
Phase transition validation for Fireside: Betrayal.

Defines which phase transitions are legal and provides a validation
function that logs warnings on invalid transitions.
"""

import logging
from typing import Dict, Set

from models.game import Phase

logger = logging.getLogger(__name__)

# Maps each phase to the set of phases it may transition to.
#
# NOTE: SEANCE transitions bypass game_master.advance_phase() by design.
# _check_seance_trigger() in narrator_agent.py calls fs.set_phase(SEANCE) directly
# because seance is conditional (dead_count >= 2 AND >= total/2) and fires from
# the ELIMINATION narrator callback, not from the fixed phase cycle.
# The SEANCE -> DAY_DISCUSSION path goes through game_master.advance_phase() normally.
ALLOWED_TRANSITIONS: Dict[Phase, Set[Phase]] = {
    Phase.SETUP:          {Phase.NIGHT},
    Phase.NIGHT:          {Phase.DAY_DISCUSSION, Phase.SEANCE},
    Phase.DAY_DISCUSSION: {Phase.DAY_VOTE},
    Phase.DAY_VOTE:       {Phase.ELIMINATION},
    Phase.ELIMINATION:    {Phase.NIGHT, Phase.SEANCE, Phase.GAME_OVER},
    Phase.SEANCE:         {Phase.DAY_DISCUSSION},
}


def validate_transition(current: Phase, target: Phase, actor: str) -> bool:
    """Check if a phase transition is allowed.

    Args:
        current: The current phase.
        target:  The desired next phase.
        actor:   Human-readable label for who/what is requesting the transition
                 (used in log messages).

    Returns:
        True if the transition is valid, False otherwise.
    """
    allowed = ALLOWED_TRANSITIONS.get(current)
    if allowed is None:
        logger.warning(
            "Invalid transition: %s has no outgoing transitions (actor=%s, target=%s)",
            current.value, actor, target.value,
        )
        return False

    if target not in allowed:
        logger.warning(
            "Invalid transition: %s -> %s not allowed (actor=%s, allowed=%s)",
            current.value, target.value, actor,
            [p.value for p in allowed],
        )
        return False

    return True

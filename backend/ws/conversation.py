"""
Conversation tracking and affective signal computation.

Tracks message flow during DAY_DISCUSSION to inform narrator pacing,
and computes emotional context signals for narrator tone adjustment.
"""

import time
from typing import Dict, List, Optional, Any, Set


# ── Conversation pacing tracker ───────────────────────────────────────────────

class ConversationTracker:
    """
    Tracks message flow during DAY_DISCUSSION to inform narrator pacing.
    One instance per active game, keyed in _trackers below.
    reset_round() is called by the narrator agent when entering DAY_DISCUSSION.
    """

    def __init__(self):
        self.messages: List[Dict[str, Any]] = []   # {player_id, character_name, timestamp, text}
        self.last_message_time: float = 0.0
        self.silence_prompted: Set[str] = set()    # player_ids already prompted this round
        self.repeated_accusations: Dict[str, int] = {}  # character_name -> accusation count
        self.alive_characters: List[str] = []      # updated on each add_message call

    def add_message(
        self,
        player_id: str,
        character_name: str,
        text: str,
        alive_characters: Optional[List[str]] = None,
    ) -> None:
        if alive_characters is not None:
            self.alive_characters = alive_characters

        now = time.time()
        self.messages.append({
            "player_id": player_id,
            "character_name": character_name,
            "timestamp": now,
            "text": text,
        })
        self.last_message_time = now
        if len(self.messages) > 100:
            self.messages = self.messages[-100:]

        # Crude accusation tracking: message mentions a character name + "suspect"
        for name in self.alive_characters:
            if name.lower() in text.lower() and "suspect" in text.lower():
                self.repeated_accusations[name] = self.repeated_accusations.get(name, 0) + 1

    def get_pacing_signal(self) -> str:
        """Return a pacing directive string for the narrator."""
        now = time.time()
        silence_duration = now - self.last_message_time if self.last_message_time else 0.0
        recent_window = [m for m in self.messages if now - m["timestamp"] < 30]
        msg_rate = len(recent_window)  # messages in last 30 seconds

        if silence_duration > 45:
            return "PACE_PUSH — Long silence. Intervene narratively to advance discussion."
        elif silence_duration > 30:
            return "PACE_NUDGE — Discussion stalling. Gentle narrative prompt."
        elif msg_rate > 10:
            return "PACE_HOT — Rapid debate. Let it breathe. Do NOT interrupt."
        elif any(count > 3 for count in self.repeated_accusations.values()):
            return "PACE_CIRCULAR — Same accusations repeating. Nudge toward voting."
        else:
            return "PACE_NORMAL — Healthy discussion flow. No intervention needed."

    def reset_round(self) -> None:
        self.messages.clear()
        self.last_message_time = time.time()  # anchor to now so we don't trigger immediate PACE_PUSH
        self.silence_prompted.clear()
        self.repeated_accusations.clear()
        # alive_characters is refreshed from add_message on the first message of the round


class AffectiveSignals:
    """
    Compute emotional context signals from game state for narrator tone adjustment.
    These signals adjust the narrator's DELIVERY, not its CONTENT.
    """

    @staticmethod
    def compute(
        game_state: Dict[str, Any],
        conversation_tracker: ConversationTracker,
    ) -> Dict[str, Any]:
        signals: Dict[str, Any] = {}

        # 1. Vote closeness (only present after a round with a vote)
        if game_state.get("last_vote_result"):
            votes = game_state["last_vote_result"]
            top_two = sorted(votes.values(), reverse=True)[:2]
            if len(top_two) >= 2:
                margin = top_two[0] - top_two[1]
                signals["vote_tension"] = "HIGH" if margin <= 1 else "MEDIUM" if margin <= 2 else "LOW"
            if votes:
                # unanimous = only one candidate received any votes (not a split)
                signals["unanimous"] = len([v for v in votes.values() if v > 0]) == 1

        # 2. Debate intensity from pacing signal
        pacing = conversation_tracker.get_pacing_signal()
        signals["debate_intensity"] = "HOT" if "HOT" in pacing else "CALM"

        # 3. Round progression toward endgame
        current_round = game_state.get("round", 1)
        total_players = game_state.get("total_players", 5)
        signals["late_game"] = current_round >= (total_players - 2)

        # 4. Elimination stakes
        alive_count = sum(
            1 for p in game_state.get("players", {}).values() if p.get("alive")
        )
        signals["endgame_imminent"] = alive_count <= 3

        # 5. AI exposure risk — narrator uses for tone, never for content
        ai_name = game_state.get("ai_character", {}).get("name") if game_state.get("ai_character") else None
        accusations_against_ai = sum(
            1
            for m in conversation_tracker.messages
            if ai_name
            and ai_name.lower() in m.get("text", "").lower()
            and "suspect" in m.get("text", "").lower()
        )
        signals["ai_heat"] = (
            "HOT" if accusations_against_ai >= 3
            else "WARM" if accusations_against_ai >= 1
            else "COLD"
        )

        return signals


# ── Hand-raise queue (large group conversation structure) ────────────────────

class HandRaiseQueue:
    """
    Tracks players who want to speak, in order of hand-raise.
    Active during DAY_DISCUSSION; most useful for large groups (7+ players).
    Cleared at the start of each new DAY_DISCUSSION round.
    """

    def __init__(self):
        self.queue: List[str] = []  # character names in raise-hand order

    def raise_hand(self, character_name: str) -> bool:
        """Add character to queue. Returns True if newly added, False if already queued."""
        if character_name not in self.queue:
            self.queue.append(character_name)
            return True
        return False

    def drain(self) -> None:
        """Clear the queue (called on phase transition to new DAY_DISCUSSION round)."""
        self.queue.clear()


# Per-game conversation trackers — keyed by game_id, in-process only.
_trackers: Dict[str, ConversationTracker] = {}

# Per-game hand-raise queues — keyed by game_id, in-process only.
_hand_queues: Dict[str, HandRaiseQueue] = {}


def get_tracker(game_id: str) -> ConversationTracker:
    """Return (or create) the ConversationTracker for this game."""
    if game_id not in _trackers:
        _trackers[game_id] = ConversationTracker()
    return _trackers[game_id]


def reset_tracker(game_id: str) -> None:
    """Reset the ConversationTracker for a new DAY_DISCUSSION round."""
    tracker = _trackers.get(game_id)
    if tracker:
        tracker.reset_round()


def remove_tracker(game_id: str) -> None:
    """Remove the ConversationTracker for a game (cleanup)."""
    _trackers.pop(game_id, None)


def get_hand_queue(game_id: str) -> HandRaiseQueue:
    """Return (or create) the HandRaiseQueue for this game."""
    if game_id not in _hand_queues:
        _hand_queues[game_id] = HandRaiseQueue()
    return _hand_queues[game_id]


def drain_hand_queue(game_id: str) -> None:
    """Reset the HandRaiseQueue for a new DAY_DISCUSSION round."""
    queue = _hand_queues.get(game_id)
    if queue:
        queue.drain()


def remove_hand_queue(game_id: str) -> None:
    """Remove the HandRaiseQueue for a game (cleanup)."""
    _hand_queues.pop(game_id, None)

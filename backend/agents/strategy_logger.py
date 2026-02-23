"""
Competitor Intelligence — §12.3.18

Post-game strategy logging + cross-game intelligence aggregation.

Flow:
  1. _end_game fires asyncio.create_task(log_game_strategy(...))
  2. log_game_strategy() stores per-game data in ai_strategy_logs/{game_id}
  3. After logging, _refresh_meta_strategy() is scheduled:
       - fetches recent logs, aggregates patterns
       - calls Gemini to produce a 200-word strategy brief
       - stores in ai_meta_strategy/latest and updates in-process cache
  4. _build_system() in traitor_agent reads get_intelligence_brief() (sync)
     and appends the brief when available

Min-games guard: augmentation only activates after MIN_GAMES = 20.
Difficulty level always takes precedence (brief only INFORMs strategy).
"""
import asyncio
import logging
from collections import Counter
from typing import Optional, Any

from config import settings
from services.firestore_service import get_firestore_service

logger = logging.getLogger(__name__)

_MIN_GAMES = 20  # minimum games before augmentation activates

# In-process cache — updated after each game ends; persisted to Firestore
_intelligence_brief: str = ""


def get_intelligence_brief() -> str:
    """Sync accessor for the in-process meta-strategy brief.
    Returns "" until at least MIN_GAMES have been played.
    """
    return _intelligence_brief


async def load_brief_from_firestore() -> None:
    """Pre-load any existing brief from Firestore at app startup."""
    global _intelligence_brief
    try:
        fs = get_firestore_service()
        doc = await fs._run(
            lambda: fs.db.collection("ai_meta_strategy").document("latest").get()
        )
        if doc.exists:
            data = doc.to_dict()
            if data.get("games_analyzed", 0) >= _MIN_GAMES:
                _intelligence_brief = data.get("brief", "")
                logger.info(
                    "Intelligence brief loaded from Firestore (%d games, catch_rate=%.0f%%)",
                    data["games_analyzed"],
                    data.get("catch_rate", 0) * 100,
                )
    except Exception:
        logger.warning("Could not load intelligence brief from Firestore", exc_info=True)


async def log_game_strategy(
    game_id: str,
    winner: str,
    all_events: list,
    ai_character_name: Optional[str],
    difficulty: str,
    player_count: int,
    final_round: int,
) -> None:
    """
    Store structured strategy data for this game.
    Called fire-and-forget (asyncio.create_task) from _end_game.
    """
    try:
        fs = get_firestore_service()
        ai_caught = winner == "villagers"

        # Round when AI was caught (if applicable)
        round_caught = None
        if ai_caught and ai_character_name:
            for e in all_events:
                if e.type == "elimination" and e.target == ai_character_name:
                    round_caught = e.round
                    break

        # Exposure signals — moments suspicion concentrated on the AI
        exposure_signals = []
        if ai_caught and ai_character_name:
            for e in all_events:
                if e.type in ("vote", "accusation") and e.target == ai_character_name:
                    exposure_signals.append({
                        "round": e.round,
                        "type": e.type,
                        "actor": e.actor or "",
                        "reason": (e.narration or "")[:100],
                    })

        # Classify AI's deception moves as successful or failed
        successful_moves = []
        failed_moves = []
        if ai_character_name:
            ai_actions = [e for e in all_events if e.actor == ai_character_name]
            for action in ai_actions:
                if action.type == "accusation":
                    target = action.target
                    # Was the target subsequently eliminated?
                    later_elim = next(
                        (e for e in all_events
                         if e.type == "elimination" and e.target == target
                         and e.timestamp > action.timestamp),
                        None,
                    )
                    entry = {
                        "type": "deflection_accusation",
                        "description": (
                            f"Accused {target}, who was then eliminated"
                            if later_elim
                            else f"Accused {target}, village didn't follow"
                        ),
                        "round": action.round,
                    }
                    (successful_moves if later_elim else failed_moves).append(entry)

        from google.cloud import firestore as _fstore
        log_data = {
            "game_id": game_id,
            "difficulty": difficulty,
            "player_count": player_count,
            "ai_caught": ai_caught,
            "round_caught": round_caught,
            "total_rounds": final_round,
            "ai_character": ai_character_name or "",
            "exposure_signals": exposure_signals,
            "successful_moves": successful_moves,
            "failed_moves": failed_moves,
            "timestamp": _fstore.SERVER_TIMESTAMP,
        }
        await fs._run(
            lambda: fs.db.collection("ai_strategy_logs").document(game_id).set(log_data)
        )
        logger.info(
            "[%s] Strategy log stored (ai_caught=%s, difficulty=%s, round_caught=%s)",
            game_id, ai_caught, difficulty, round_caught,
        )

        # Trigger meta-strategy refresh after each game (replaces daily Cloud Function)
        asyncio.create_task(_refresh_meta_strategy(fs))

    except Exception:
        logger.warning("[%s] Strategy logging failed", game_id, exc_info=True)


async def _refresh_meta_strategy(fs) -> None:
    """
    Aggregate recent strategy logs and regenerate the meta-strategy brief.
    Replaces the daily Cloud Function aggregator for the hackathon build.
    """
    global _intelligence_brief
    try:
        docs = await fs._run(
            lambda: list(
                fs.db.collection("ai_strategy_logs")
                .order_by("timestamp", direction="DESCENDING")
                .limit(100)
                .stream()
            )
        )
        logs = [d.to_dict() for d in docs]

        if len(logs) < _MIN_GAMES:
            logger.info(
                "Only %d strategy logs — skipping meta-strategy generation (need %d)",
                len(logs), _MIN_GAMES,
            )
            return

        total = len(logs)
        caught_count = sum(1 for l in logs if l.get("ai_caught"))
        catch_rate = caught_count / total

        all_successes = []
        for log in logs:
            all_successes.extend(log.get("successful_moves", []))
        success_types = Counter(s["type"] for s in all_successes)

        avg_rounds_caught = (
            sum(l.get("round_caught") or 0 for l in logs if l.get("ai_caught"))
            / max(caught_count, 1)
        )

        brief = await _generate_brief(total, catch_rate, success_types, avg_rounds_caught)
        if not brief:
            return

        _intelligence_brief = brief

        from google.cloud import firestore as _fstore
        await fs._run(
            lambda: fs.db.collection("ai_meta_strategy").document("latest").set({
                "brief": brief,
                "games_analyzed": total,
                "catch_rate": catch_rate,
                "generated_at": _fstore.SERVER_TIMESTAMP,
            })
        )
        logger.info(
            "Meta-strategy brief updated (%d games, catch_rate=%.0f%%)",
            total, catch_rate * 100,
        )
    except Exception:
        logger.warning("Meta-strategy refresh failed", exc_info=True)


async def _generate_brief(
    total: int,
    catch_rate: float,
    success_types: Counter,
    avg_rounds_caught: float,
) -> Optional[str]:
    """Call Gemini to produce a 200-word meta-strategy brief."""
    if not settings.gemini_api_key:
        return None
    try:
        from google import genai
        from google.genai import types as gtypes

        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = (
            f"Analyze these AI Shapeshifter strategy statistics from {total} social "
            f"deduction games (Mafia/Werewolf variant):\n\n"
            f"Overall catch rate: {catch_rate:.0%}\n"
            f"Average rounds survived before being caught: {avg_rounds_caught:.1f}\n"
            f"Most successful deception move types: {dict(success_types.most_common(5))}\n\n"
            "Generate a concise strategy brief (max 200 words) for an AI playing as the "
            "secret Shapeshifter. Format as actionable bullet-point advice:\n"
            "- What to AVOID (patterns that get caught)\n"
            "- What WORKS (successful deception strategies)\n"
            "- TIMING (when to be aggressive vs passive)\n"
        )
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=settings.traitor_model,
                contents=prompt,
                config=gtypes.GenerateContentConfig(
                    max_output_tokens=300,
                    temperature=0.3,
                ),
            ),
        )
        text = (response.text or "").strip()
        return text or None
    except Exception:
        logger.warning("Meta-strategy Gemini brief generation failed", exc_info=True)
        return None

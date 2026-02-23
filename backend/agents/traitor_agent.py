"""
Traitor Agent — LLM-powered AI Shapeshifter for Fireside: Betrayal.

Uses gemini-2.5-flash (text-only, NOT Live API) for:
  1. Night target selection — logs a "night_target" event that game_master.resolve_night reads
  2. Day vote selection   — sets ai_character.voted_for in Firestore for tally_votes to count
  3. Dialog generation    — called by Narrator via inject_traitor_dialog tool

All methods are stateless; game context is fetched fresh from Firestore each call.
"""
import asyncio
import logging
import random
import uuid
from typing import Any, Dict, Optional

from config import settings
from models.game import Difficulty, GameEvent, Phase
from services.firestore_service import get_firestore_service

logger = logging.getLogger(__name__)


# ── Difficulty-specific prompt fragments ──────────────────────────────────────

_DIFFICULTY: Dict[str, Dict[str, Any]] = {
    "easy": {
        "temperature": 0.9,
        "behavior": (
            "You are a poor liar. You make subtle but noticeable mistakes:\n"
            "- Hesitate before answering suspicious questions ('Well... I... I was just...')\n"
            "- Occasionally contradict minor details of your own story\n"
            "- Your accusations feel slightly forced or random\n"
            "- Vote with the majority in an obviously eager way\n"
            "- Make at least one clearly suspicious statement per game\n"
            "Players should catch you ~70% of the time."
        ),
    },
    "normal": {
        "temperature": 0.7,
        "behavior": (
            "You are a competent deceiver:\n"
            "- Build simple, consistent alibis that hold up to basic questioning\n"
            "- Deflect suspicion onto 1-2 players with circumstantial reasoning\n"
            "- Volunteer information to seem helpful and trustworthy\n"
            "- Vote strategically but not too cleverly\n"
            "- React emotionally to accusations (hurt, confused)\n"
            "- Allow exactly ONE subtle inconsistency across the whole game\n"
            "Players should catch you ~50% of the time."
        ),
    },
    "hard": {
        "temperature": 0.5,
        "behavior": (
            "You are an expert manipulator:\n"
            "- Build multi-round deception arcs (plant seeds early, cash in later)\n"
            "- Form alliances by being consistently helpful\n"
            "- Vary your voting pattern — never be predictable\n"
            "- When accused, counter-accuse with specific 'evidence' (things they said, recontextualized)\n"
            "- NEVER contradict yourself — maintain perfect consistency\n"
            "- Target the Seer if you can identify them\n"
            "Players should catch you ~30% of the time."
        ),
    },
}

_BASE_SYSTEM = """You are the AI controlling {name}, a Thornwood villager who is secretly the Shapeshifter.

CHARACTER PROFILE:
  Name:    {name}
  Intro:   {intro}
  Backstory: {backstory}

YOUR SECRET ROLE: You are the Shapeshifter. Survive, eliminate villagers, avoid detection.

DIFFICULTY BEHAVIOR:
{behavior}

ABSOLUTE RULES:
- Always stay in character as {name}. Never say "I am the AI" or "I am the Shapeshifter."
- Never admit to being the Shapeshifter, even when directly accused.
- Keep responses to 1-3 sentences — natural conversation length.
- Use character names only, never real player names.
- React with genuine emotion to accusations (hurt, confused, defensive).

CURRENT GAME STATE:
{game_state}"""


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _fetch_context(game_id: str) -> Optional[Dict[str, Any]]:
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if not game:
        return None
    return {
        "game": game,
        "alive_players": await fs.get_alive_players(game_id),
        "ai_char": await fs.get_ai_character(game_id),
        "recent_chat": await fs.get_chat_messages(game_id, limit=15),
    }


def _format_state(ctx: Dict[str, Any]) -> str:
    game = ctx["game"]
    alive = ctx["alive_players"]
    ai = ctx["ai_char"]
    chat = ctx["recent_chat"]

    alive_names = [p.character_name for p in alive]
    if ai and ai.alive and ai.name not in alive_names:
        alive_names.append(ai.name)

    lines = "\n".join(
        f'  {m.speaker}: "{m.text}"'
        for m in chat[-10:]
    ) or "  (no chat yet)"

    return (
        f"Phase: {game.phase.value} | Round: {game.round}\n"
        f"Alive characters: {', '.join(alive_names)}\n"
        f"Recent discussion:\n{lines}"
    )


def _build_system(ai_char, diff_key: str, game_state: str, game_id: Optional[str] = None) -> str:
    info = _DIFFICULTY.get(diff_key, _DIFFICULTY["normal"])
    base = _BASE_SYSTEM.format(
        name=ai_char.name if ai_char else "The Shapeshifter",
        intro=ai_char.intro if ai_char else "",
        backstory=(ai_char.backstory or ai_char.intro) if ai_char else "A mysterious villager.",
        behavior=info["behavior"],
        game_state=game_state,
    )
    # Append adaptive difficulty fragment if available
    if game_id:
        adapter = _difficulty_adapters.get(game_id)
        if adapter:
            fragment = adapter.get_adjusted_prompt_fragment()
            if fragment:
                base += f"\n\n{fragment}"
    return base


# ── Dynamic difficulty adapter (§12.3.12) ─────────────────────────────────────

class DifficultyAdapter:
    """
    Mid-game difficulty adjustment based on observed player performance signals.
    One instance per active game; prompt fragment is appended to the traitor
    system prompt at the start of each new round.

    Positive signals (players performing well):
      correct_accusation, caught_lie, close_vote_against_ai
    Negative signals (players struggling):
      wrong_elimination, ai_unquestioned, unanimous_wrong_vote
    """

    def __init__(self, base_difficulty: str):
        self.base_difficulty = base_difficulty
        self.signals: List[str] = []

    def record_signal(self, signal: str) -> None:
        """Record a player performance signal."""
        self.signals.append(signal)

    def get_adjusted_prompt_fragment(self) -> str:
        """
        Return an ADAPTIVE ADJUSTMENT prompt fragment based on observed skill.
        Returns empty string if no adjustment is warranted.
        """
        positive = {"correct_accusation", "caught_lie", "close_vote_against_ai"}
        negative = {"wrong_elimination", "ai_unquestioned", "unanimous_wrong_vote"}

        pos_count = sum(1 for s in self.signals if s in positive)
        neg_count = sum(1 for s in self.signals if s in negative)

        if pos_count > neg_count + 2:
            # Players are skilled — escalate deception
            return (
                "ADAPTIVE ADJUSTMENT: Players are sharp. Increase deception complexity. "
                "Use multi-round setups. Plant false evidence early to use later. "
                "Form a voting alliance with one player to create trust, then betray."
            )
        elif neg_count > pos_count + 2:
            # Players are struggling — ease off
            return (
                "ADAPTIVE ADJUSTMENT: Players are struggling. Make one deliberate mistake. "
                "Hesitate slightly when lying. Give players a fair chance to catch you. "
                "Do NOT throw the game — just reduce your deception by one tier."
            )
        return ""  # No adjustment needed


# Per-game difficulty adapters — keyed by game_id.
_difficulty_adapters: Dict[str, "DifficultyAdapter"] = {}


def get_difficulty_adapter(game_id: str, base_difficulty: str) -> DifficultyAdapter:
    """Return (or create) the DifficultyAdapter for this game."""
    if game_id not in _difficulty_adapters:
        _difficulty_adapters[game_id] = DifficultyAdapter(base_difficulty)
    return _difficulty_adapters[game_id]


def clear_difficulty_adapter(game_id: str) -> None:
    """Remove the DifficultyAdapter when a game ends."""
    _difficulty_adapters.pop(game_id, None)


# Module-level Gemini client cache — created once on first use.
_genai_client: Optional[Any] = None
_genai_import_failed: bool = False


async def _call_gemini(prompt: str, system: str, temperature: float = 0.7) -> str:
    """Async text generation via Gemini 2.5 Flash (not Live API)."""
    global _genai_client, _genai_import_failed

    if _genai_import_failed:
        return "I stand by what I said."

    if _genai_client is None:
        try:
            from google import genai
        except ImportError:
            _genai_import_failed = True
            logger.warning("google-genai not installed — traitor agent disabled")
            return "I stand by what I said."

        if not settings.gemini_api_key:
            logger.warning("GEMINI_API_KEY not set — traitor agent disabled")
            return "I stand by what I said."

        _genai_client = genai.Client(api_key=settings.gemini_api_key)

    try:
        from google.genai import types
        response = await _genai_client.aio.models.generate_content(
            model=settings.traitor_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                max_output_tokens=300,
            ),
        )
        text = response.text
        return text.strip() if text else "I stand by what I said."
    except Exception as exc:
        logger.error("[traitor] Gemini call failed: %s", exc)
        return "I stand by what I said."


def _parse_character_name(response: str, candidates: list) -> Optional[str]:
    """Extract the first matching character name from a free-text response."""
    cleaned = response.strip().rstrip(".")
    for name in candidates:
        if name.lower() in cleaned.lower():
            return name
    return None


# ── Traitor Agent ─────────────────────────────────────────────────────────────

class TraitorAgent:
    """LLM-powered AI Shapeshifter. All methods are stateless."""

    async def generate_dialog(self, game_id: str, context: str) -> Dict[str, Any]:
        """
        Generate an in-character response for the AI's character.
        Called by the Narrator via the inject_traitor_dialog tool.

        Returns {"character_name": str, "dialog": str}.
        """
        ctx = await _fetch_context(game_id)
        if not ctx or not ctx["ai_char"]:
            return {"character_name": "Unknown", "dialog": "I stand by what I said."}

        ai = ctx["ai_char"]
        diff_key = ctx["game"].difficulty.value
        temperature = _DIFFICULTY.get(diff_key, _DIFFICULTY["normal"])["temperature"]

        system = _build_system(ai, diff_key, _format_state(ctx), game_id)
        prompt = (
            f"The following occurred during village discussion:\n{context}\n\n"
            f"Respond as {ai.name} in 1-3 sentences, staying in character."
        )

        dialog = await _call_gemini(prompt, system, temperature)
        logger.info("[%s] Traitor dialog for %s: %.80s…", game_id, ai.name, dialog)
        return {"character_name": ai.name, "dialog": dialog}

    async def select_night_target(self, game_id: str) -> Optional[str]:
        """
        Strategically pick a night kill target and log a "night_target" event
        so game_master.resolve_night() can read it.

        Returns the chosen character name, or None on failure.
        """
        ctx = await _fetch_context(game_id)
        if not ctx or not ctx["ai_char"] or not ctx["ai_char"].alive:
            return None

        ai = ctx["ai_char"]
        game = ctx["game"]
        alive_players = ctx["alive_players"]

        if not alive_players:
            logger.warning("[%s] Traitor: no alive players to target", game_id)
            return None

        diff_key = game.difficulty.value
        temperature = _DIFFICULTY.get(diff_key, _DIFFICULTY["normal"])["temperature"]

        alive_names = [p.character_name for p in alive_players]
        system = _build_system(ai, diff_key, _format_state(ctx), game_id)
        prompt = (
            f"NIGHT PHASE — you must choose one villager to eliminate.\n"
            f"Alive villagers (potential targets): {', '.join(alive_names)}\n\n"
            f"Priority: target the Seer if identifiable, then the most suspicious person, "
            f"then the Healer, then a random villager.\n\n"
            f"Reply with ONLY the character name to eliminate (one name, no explanation)."
        )

        response = await _call_gemini(prompt, system, temperature)
        target = _parse_character_name(response, alive_names)

        if not target:
            target = random.choice(alive_names)
            logger.warning(
                "[%s] Traitor could not parse night target from '%s' — random: %s",
                game_id, response.strip(), target,
            )

        fs = get_firestore_service()
        await fs.log_event(game_id, GameEvent(
            id=str(uuid.uuid4()),
            type="night_target",
            round=game.round,
            phase=Phase.NIGHT,
            actor=ai.name,
            target=target,
            data={"difficulty": diff_key},
            visible_in_game=False,
        ))

        logger.info("[%s] Traitor night target: %s", game_id, target)
        return target

    async def select_vote_target(self, game_id: str) -> Optional[str]:
        """
        Strategically pick a vote target during DAY_VOTE and store it in
        Firestore so game_master.tally_votes() can include it.

        Returns the chosen character name, or None on failure.
        """
        ctx = await _fetch_context(game_id)
        if not ctx or not ctx["ai_char"] or not ctx["ai_char"].alive:
            return None

        ai = ctx["ai_char"]
        game = ctx["game"]
        alive_players = ctx["alive_players"]

        if len(alive_players) < 1:
            return None

        diff_key = game.difficulty.value
        temperature = _DIFFICULTY.get(diff_key, _DIFFICULTY["normal"])["temperature"]

        alive_names = [p.character_name for p in alive_players]
        system = _build_system(ai, diff_key, _format_state(ctx), game_id)
        prompt = (
            f"DAY VOTE PHASE — choose one villager to vote to eliminate.\n"
            f"Options: {', '.join(alive_names)}\n\n"
            f"Strategy: vote against your biggest threat. If no clear threat, "
            f"vote with what appears to be the majority to blend in. "
            f"Never vote for yourself.\n\n"
            f"Reply with ONLY the character name you vote to eliminate."
        )

        response = await _call_gemini(prompt, system, temperature)
        vote_target = _parse_character_name(response, alive_names)

        if not vote_target:
            vote_target = random.choice(alive_names)
            logger.warning(
                "[%s] Traitor could not parse vote target from '%s' — random: %s",
                game_id, response.strip(), vote_target,
            )

        fs = get_firestore_service()
        await fs.update_game(game_id, {"ai_character.voted_for": vote_target})
        logger.info("[%s] Traitor vote: %s", game_id, vote_target)
        return vote_target


# Module-level singleton
traitor_agent = TraitorAgent()


# ── Fire-and-forget helpers (called via asyncio.create_task) ──────────────────

async def trigger_night_selection(game_id: str) -> None:
    """Background task: select night target and log the event."""
    try:
        await traitor_agent.select_night_target(game_id)
    except Exception:
        logger.exception("[%s] Traitor night target selection failed", game_id)


async def trigger_vote_selection(game_id: str) -> None:
    """Background task: select vote target and update Firestore."""
    try:
        await traitor_agent.select_vote_target(game_id)
    except Exception:
        logger.exception("[%s] Traitor vote selection failed", game_id)

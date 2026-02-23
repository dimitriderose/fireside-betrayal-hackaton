"""
Role Assignment Agent — deterministic role shuffling with optional LLM character generation.

Responsibilities:
- Shuffle and assign roles to human players based on player count + difficulty
- Generate unique character identities via LLM (falls back to static cast on failure)
- Set up the AI character (Shapeshifter)
- Apply difficulty-based role adjustments (Drunk replacement on Easy)

Called once by the game router when the host starts the game.
"""
import asyncio
import json
import logging
import random
import re
from typing import Any, Dict, List, Optional

from config import settings
from models.game import Role, Difficulty, AICharacter, ROLE_DISTRIBUTION
from services.firestore_service import get_firestore_service

logger = logging.getLogger(__name__)


# ── Fallback static character cast (used when LLM generation fails) ───────────
# 8 characters support up to 7 human players + 1 AI (max game size).
_FALLBACK_CAST: List[Dict[str, str]] = [
    {
        "name": "Blacksmith Garin",
        "intro": "The broad-shouldered smith hammers at his forge, sparks dancing in the dark.",
        "personality_hook": "proud of his work, quick to anger when accused of dishonesty",
    },
    {
        "name": "Merchant Elara",
        "intro": "The traveling merchant counts her coins by candlelight, eyes darting to the door.",
        "personality_hook": "deflects personal questions with talk of distant trade routes",
    },
    {
        "name": "Scholar Theron",
        "intro": "The old scholar peers at ancient texts, muttering about omens in the stars.",
        "personality_hook": "speaks in riddles and half-finished thoughts",
    },
    {
        "name": "Herbalist Mira",
        "intro": "The herbalist tends her garden of strange flowers, humming a melody no one recognizes.",
        "personality_hook": "trusts no one since the last harvest festival went wrong",
    },
    {
        "name": "Brother Aldric",
        "intro": "The chapel keeper lights the evening candles, his prayers a whisper against the wind.",
        "personality_hook": "claims divine insight but contradicts himself under pressure",
    },
    {
        "name": "Innkeeper Bram",
        "intro": "The innkeeper pours ale with a steady hand, but his eyes follow everyone who enters.",
        "personality_hook": "remembers everything said in his tavern, volunteers details selectively",
    },
    {
        "name": "Huntress Reva",
        "intro": "The huntress sharpens her arrows by firelight, her wolf-hound growling at shadows.",
        "personality_hook": "blunt to the point of rudeness, refuses to soften accusations",
    },
    {
        "name": "Miller Oswin",
        "intro": "The old miller keeps his wheel turning day and night, watching the river for signs only he understands.",
        "personality_hook": "speaks rarely but always at the most uncomfortable moment",
    },
]


# ── Genre seed for LLM character generation ───────────────────────────────────
GENRE_SEEDS: Dict[str, Dict[str, Any]] = {
    "fantasy_village": {
        "setting": "a remote village surrounded by dark forests",
        "occupations": [
            "blacksmith", "herbalist", "scholar", "merchant", "innkeeper",
            "huntress", "chapel keeper", "weaver", "miller", "shepherd",
            "midwife", "cartographer", "beekeeper", "tanner", "brewer",
        ],
        "tone": "medieval low fantasy",
    }
    # Future genres (P3) would add entries here
}


# ── Gemini client cache (independent instance for character generation) ────────
# NOTE: traitor_agent.py also maintains its own module-level client — they are
# separate instances, not a shared cache. Both use the same api_key.
_genai_client: Optional[Any] = None
_genai_unavailable: bool = False  # True when import fails or API key is absent


async def _call_gemini_json(prompt: str) -> Optional[str]:
    """Return raw text from a single Gemini generate_content call, or None on failure."""
    global _genai_client, _genai_unavailable

    if _genai_unavailable:
        return None

    if _genai_client is None:
        try:
            from google import genai
        except ImportError:
            _genai_unavailable = True
            logger.warning("[proc-chars] google-genai not installed — using fallback cast")
            return None

        if not settings.gemini_api_key:
            _genai_unavailable = True  # prevent repeated re-entry on every game start
            logger.warning("[proc-chars] GEMINI_API_KEY not set — using fallback cast")
            return None

        _genai_client = genai.Client(api_key=settings.gemini_api_key)

    try:
        from google.genai import types
        response = await _genai_client.aio.models.generate_content(
            model=settings.traitor_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=1.0,
                max_output_tokens=1200,
            ),
        )
        return response.text.strip() if response.text else None
    except Exception as exc:
        logger.error("[proc-chars] Gemini call failed: %s", exc)
        return None


class RoleAssigner:
    """
    Assigns roles and character identities to all game participants.
    Called once when the host triggers game start.

    ROLE_DISTRIBUTION is keyed by total character count (humans + 1 AI).
    Minimum: 3 total = 2 humans + 1 AI.
    Maximum: 8 total = 7 humans + 1 AI.
    """

    MIN_HUMANS = 2
    MAX_HUMANS = 7

    async def _generate_character_cast(
        self, n_total: int, genre: str = "fantasy_village"
    ) -> List[Dict[str, str]]:
        """
        Generate n_total unique characters via Gemini.
        Returns a list of dicts: {name, intro, personality_hook}.
        Falls back to a shuffled slice of _FALLBACK_CAST on any failure.
        """
        seed = GENRE_SEEDS.get(genre, GENRE_SEEDS["fantasy_village"])
        fallback_names = ", ".join(c["name"] for c in _FALLBACK_CAST)

        prompt = (
            f"Generate exactly {n_total} unique story characters for a social deduction game "
            f"set in {seed['setting']}. Tone: {seed['tone']}.\n\n"
            f"For each character, provide:\n"
            f"- name: A first name + occupation title "
            f"(e.g., \"Blacksmith Garin\", \"Herbalist Mira\"). "
            f"Choose occupations from this list or invent similar ones: "
            f"{', '.join(seed['occupations'])}.\n"
            f"- intro: One atmospheric sentence introducing them (max 20 words).\n"
            f"- personality_hook: One behavioral trait that creates roleplay opportunity "
            f"(e.g., \"speaks in riddles\", \"trusts no one since the last harvest\").\n\n"
            f"Rules:\n"
            f"- All names must be unique and fantasy-appropriate.\n"
            f"- Mix genders evenly.\n"
            f"- Each intro should hint at something suspicious OR trustworthy (not both).\n"
            f"- Do NOT reuse these names: {fallback_names}.\n\n"
            f"Return ONLY a valid JSON array with no markdown fences:\n"
            f'[{{"name": "...", "intro": "...", "personality_hook": "..."}}]'
        )

        raw = await _call_gemini_json(prompt)

        if raw:
            # Strip optional markdown code fences (handles ```json or ``` with any language tag)
            text = raw.strip()
            if text.startswith("```"):
                text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
                text = re.sub(r"\n?```$", "", text.strip())
            try:
                characters: List[Dict[str, str]] = json.loads(text)
                if (
                    isinstance(characters, list)
                    and len(characters) >= n_total
                    and all(
                        isinstance(c, dict)
                        and c.get("name")
                        and c.get("intro")
                        and c.get("personality_hook")
                        for c in characters[:n_total]
                    )
                ):
                    logger.info("[proc-chars] LLM generated %d characters", n_total)
                    return characters[:n_total]
                else:
                    logger.warning(
                        "[proc-chars] LLM returned %d characters (expected %d) or missing required fields — using fallback",
                        len(characters) if isinstance(characters, list) else 0,
                        n_total,
                    )
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("[proc-chars] JSON parse failed: %s — using fallback", exc)

        # Fallback: return a shuffled slice of the static cast
        fallback = list(_FALLBACK_CAST)
        random.shuffle(fallback)
        result = fallback[:n_total]
        if len(result) < n_total:
            raise RuntimeError(
                f"_FALLBACK_CAST has only {len(_FALLBACK_CAST)} entries but {n_total} are required. "
                "Expand _FALLBACK_CAST to support larger player counts."
            )
        return result

    async def assign_roles(self, game_id: str) -> Dict[str, Any]:
        """
        Shuffle and persist roles + character identities for all participants.

        Steps:
          1. Load game + all joined players from Firestore.
          2. Select role distribution by total character count + difficulty.
          3. Remove shapeshifter slot → gives exact n_human non-traitor roles.
          4. Shuffle roles; generate (or fallback) character cast.
          5. Assign one role + one character to each human player (persist).
          6. Assign the remaining cast character to the AI (persist).
          7. Store character_cast (names) and generated_characters (full data) on the game.

        Returns:
        {
            "assignments": [
                {
                    "player_id": str,
                    "player_name": str,
                    "role": str,
                    "character_name": str,
                    "character_intro": str,
                    "personality_hook": str,
                },
                ...
            ],
            "ai_character": {"name": str, "intro": str, "personality_hook": str},
            "character_cast": [str, ...],
        }

        Raises ValueError on invalid player count or missing game.
        """
        fs = get_firestore_service()
        game = await fs.get_game(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")

        players = sorted(await fs.get_all_players(game_id), key=lambda p: p.joined_at)
        n_human = len(players)

        if n_human < self.MIN_HUMANS:
            raise ValueError(
                f"Need at least {self.MIN_HUMANS} human players to start; got {n_human}."
            )
        if n_human > self.MAX_HUMANS:
            raise ValueError(
                f"Too many players: {n_human} (maximum is {self.MAX_HUMANS})."
            )

        n_total = n_human + 1  # +1 for the AI Shapeshifter
        if n_total not in ROLE_DISTRIBUTION:
            raise ValueError(
                f"No role distribution defined for {n_total} total characters "
                f"({n_human} humans + 1 AI). Supported totals: {sorted(ROLE_DISTRIBUTION)}."
            )

        # ── Build human role list ──────────────────────────────────────────────
        roles: List[str] = list(ROLE_DISTRIBUTION[n_total])

        # Apply difficulty: replace Drunk with Villager on Easy
        if game.difficulty == Difficulty.EASY and "drunk" in roles:
            roles[roles.index("drunk")] = "villager"

        # Remove the shapeshifter slot — it belongs to the AI, never a human
        if "shapeshifter" not in roles:
            raise ValueError(
                f"ROLE_DISTRIBUTION[{n_total}] has no 'shapeshifter' entry — data integrity error."
            )
        roles.remove("shapeshifter")
        # `roles` now has exactly n_human entries
        random.shuffle(roles)

        # ── Generate character cast (LLM with static fallback) ─────────────────
        cast = await self._generate_character_cast(n_total)
        random.shuffle(cast)
        # cast[0 .. n_human-1] → human players
        # cast[n_human]        → AI character

        # ── Assign roles and characters to human players (parallel writes) ─────
        assignments: List[Dict[str, Any]] = []
        player_updates = []
        for i, player in enumerate(players):
            role = roles[i]
            character = cast[i]
            hook = character.get("personality_hook", "")
            player_updates.append(fs.update_player(game_id, player.id, {
                "role": role,
                "character_name": character["name"],
                "character_intro": character["intro"],
                "personality_hook": hook,
            }))
            assignments.append({
                "player_id": player.id,
                "player_name": player.name,
                "role": role,
                "character_name": character["name"],
                "character_intro": character["intro"],
                "personality_hook": hook,
            })
        await asyncio.gather(*player_updates)

        # ── Set up the AI character ────────────────────────────────────────────
        ai_slot = cast[n_human]
        hook = ai_slot.get("personality_hook", "")
        ai_char = AICharacter(
            name=ai_slot["name"],
            intro=ai_slot["intro"],
            role=Role.SHAPESHIFTER,
            alive=True,
            backstory=hook,
            personality_hook=hook,
        )

        # ── Store AI character + full cast in a single Firestore write ─────────
        # Merging into one update_game call eliminates the crash window between
        # set_ai_character and the subsequent update_game call.
        character_cast = [c["name"] for c in cast[:n_total]]
        await fs.update_game(game_id, {
            "ai_character": ai_char.model_dump(),
            "character_cast": character_cast,
            "generated_characters": cast,
        })

        logger.info(
            "[%s] Roles assigned to %d humans (difficulty=%s). "
            "Roles: %s. AI character: %s (Shapeshifter).",
            game_id, n_human, game.difficulty.value,
            [a["role"] for a in assignments], ai_char.name,
        )

        return {
            "assignments": assignments,
            "ai_character": {
                "name": ai_char.name,
                "intro": ai_char.intro,
                "personality_hook": ai_char.personality_hook,
            },
            "character_cast": character_cast,
        }


# Module-level singleton
role_assigner = RoleAssigner()

"""
Role Assignment Agent — Pure deterministic Python, no LLM.

Responsibilities:
- Shuffle and assign roles to human players based on player count + difficulty
- Assign character names and intros from the hardcoded Thornwood fantasy cast
- Set up the AI character (Shapeshifter)
- Apply difficulty-based role adjustments (Drunk replacement on Easy)

Called once by the game router when the host starts the game.
"""
import random
import logging
from typing import Dict, Any, List

from models.game import Role, Difficulty, AICharacter, ROLE_DISTRIBUTION
from services.firestore_service import get_firestore_service

logger = logging.getLogger(__name__)


# ── Thornwood character cast ───────────────────────────────────────────────────
# 8 characters support up to 7 human players + 1 AI (max game size).
CHARACTER_CAST: List[Dict[str, str]] = [
    {
        "name": "Blacksmith Garin",
        "intro": "The broad-shouldered smith hammers at his forge, sparks dancing in the dark.",
    },
    {
        "name": "Merchant Elara",
        "intro": "The traveling merchant counts her coins by candlelight, eyes darting to the door.",
    },
    {
        "name": "Scholar Theron",
        "intro": "The old scholar peers at ancient texts, muttering about omens in the stars.",
    },
    {
        "name": "Herbalist Mira",
        "intro": "The herbalist tends her garden of strange flowers, humming a melody no one recognizes.",
    },
    {
        "name": "Brother Aldric",
        "intro": "The chapel keeper lights the evening candles, his prayers a whisper against the wind.",
    },
    {
        "name": "Innkeeper Bram",
        "intro": "The innkeeper pours ale with a steady hand, but his eyes follow everyone who enters.",
    },
    {
        "name": "Huntress Reva",
        "intro": "The huntress sharpens her arrows by firelight, her wolf-hound growling at shadows.",
    },
    {
        "name": "Miller Oswin",
        "intro": "The old miller keeps his wheel turning day and night, watching the river for signs only he understands.",
    },
]


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

    async def assign_roles(self, game_id: str) -> Dict[str, Any]:
        """
        Shuffle and persist roles + character identities for all participants.

        Steps:
          1. Load game + all joined players from Firestore.
          2. Select role distribution by total character count + difficulty.
          3. Remove shapeshifter slot → gives exact n_human non-traitor roles.
          4. Shuffle roles; shuffle character cast.
          5. Assign one role + one character to each human player (persist).
          6. Assign the remaining cast character to the AI (persist).
          7. Store character_cast list on the game document.

        Returns:
        {
            "assignments": [
                {
                    "player_id": str,
                    "player_name": str,
                    "role": str,
                    "character_name": str,
                    "character_intro": str,
                },
                ...
            ],
            "ai_character": {"name": str, "intro": str},
            "character_cast": [str, ...],
        }

        Raises ValueError on invalid player count or missing game.
        """
        fs = get_firestore_service()
        game = await fs.get_game(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")

        players = await fs.get_all_players(game_id)
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
        roles.remove("shapeshifter")
        # `roles` now has exactly n_human entries
        random.shuffle(roles)

        # ── Shuffle character cast ─────────────────────────────────────────────
        cast = list(CHARACTER_CAST)  # copy; do not mutate the module constant
        random.shuffle(cast)
        # cast[0 .. n_human-1] → human players
        # cast[n_human]        → AI character

        # ── Assign roles and characters to human players ───────────────────────
        assignments: List[Dict[str, Any]] = []
        for i, player in enumerate(players):
            role = roles[i]
            character = cast[i]
            await fs.update_player(game_id, player.id, {
                "role": role,
                "character_name": character["name"],
                "character_intro": character["intro"],
            })
            assignments.append({
                "player_id": player.id,
                "player_name": player.name,
                "role": role,
                "character_name": character["name"],
                "character_intro": character["intro"],
            })

        # ── Set up the AI character ────────────────────────────────────────────
        ai_slot = cast[n_human]
        ai_char = AICharacter(
            name=ai_slot["name"],
            intro=ai_slot["intro"],
            role=Role.SHAPESHIFTER,
            alive=True,
        )
        await fs.set_ai_character(game_id, ai_char)

        # ── Store the full character cast on the game document ─────────────────
        character_cast = [cast[i]["name"] for i in range(n_total)]
        await fs.update_game(game_id, {"character_cast": character_cast})

        logger.info(
            f"[{game_id}] Roles assigned to {n_human} humans "
            f"(difficulty={game.difficulty.value}). "
            f"Roles: {[a['role'] for a in assignments]}. "
            f"AI character: {ai_char.name} (Shapeshifter)."
        )

        return {
            "assignments": assignments,
            "ai_character": {"name": ai_char.name, "intro": ai_char.intro},
            "character_cast": character_cast,
        }


# Module-level singleton
role_assigner = RoleAssigner()

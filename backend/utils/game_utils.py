"""
Shared game utility functions — deduplicates logic across ws/ and agents/ modules.

Functions:
  all_ai_chars(game)              — list of non-None AI characters
  alive_ai_names(game)            — names of alive AI characters
  get_alive_character_names(game, players) — combined alive human + AI names
  build_candidate_pool(game, alive_players, exclude) — vote/night target lists
"""
from typing import List, Optional


def all_ai_chars(game) -> list:
    """Return list of non-None AI characters from a game object."""
    return [c for c in [game.ai_character, getattr(game, 'ai_character_2', None)] if c]


def alive_ai_names(game) -> List[str]:
    """Return names of alive AI characters."""
    return [c.name for c in all_ai_chars(game) if c.alive]


def get_alive_character_names(game, players) -> List[str]:
    """
    Build a combined list of alive character names (human players + AI characters).

    Args:
        game:    Game object with ai_character / ai_character_2 fields.
        players: List of alive player objects (each must have .character_name).

    Returns:
        List of alive character name strings.
    """
    names = [p.character_name for p in players if p.character_name]
    names.extend(alive_ai_names(game))
    return names


def build_candidate_pool(
    game, alive_players, exclude: Optional[str] = None
) -> List[str]:
    """
    Build a vote/night target candidate list from alive characters, optionally
    excluding one name (typically the acting player's own character).

    Args:
        game:           Game object.
        alive_players:  List of alive player objects.
        exclude:        Character name to exclude from the list (e.g. self).

    Returns:
        List of candidate character name strings.
    """
    names = get_alive_character_names(game, alive_players)
    if exclude:
        names = [n for n in names if n != exclude]
    return names

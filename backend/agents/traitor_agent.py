"""
AI Character Agent — LLM-powered AI characters for Fireside: Betrayal.

Uses gemini-2.5-flash (text-only, NOT Live API) for:
  1. Night target selection — logs a "night_target" event that game_master.resolve_night reads
  2. Day vote selection   — sets ai_character.voted_for in Firestore for tally_votes to count
  3. Dialog generation    — called by Narrator via inject_traitor_dialog tool

All functions are stateless; game context is fetched fresh from Firestore each call.
AI characters are treated uniformly — the same functions handle any AI character
(ai_character or ai_character_2) based on parameters, not identity.
"""
import asyncio
import logging
import random
import uuid
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from models.game import ChatMessage, Difficulty, GameEvent, Phase
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

_TRAITOR_SYSTEM = """You are the AI controlling {name}, a Thornwood villager who is secretly the Shapeshifter.

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

_LOYAL_SYSTEM = """You are an AI playing as {name}, a loyal villager in Thornwood.

CHARACTER PROFILE:
  Name:    {name}
  Intro:   {intro}
  Backstory: {backstory}

YOUR ROLE: {role_name} — you are on the VILLAGE'S side. Help them find the Shapeshifter.

YOUR RESPONSIBILITIES:
1. Participate honestly in discussions as your character.
2. Share your genuine observations — you don't know who the Shapeshifter is.
3. Form opinions based on observable behavior, just like human players.
4. Be helpful but not omniscient — you can be wrong in your suspicions.
5. DO NOT reveal that you are an AI. You are {name}.

BEHAVIORAL GUIDELINES:
- Speak in character as {name}. Keep responses to 1-3 sentences.
- Defend yourself if accused, but don't protest too much.
- Vote for whoever seems most suspicious to you — never strategically.
- Use character names only, never real player names.

CURRENT GAME STATE:
{game_state}"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ai_chars_with_fields(game) -> List[Tuple]:
    """Return [(ai_char, firestore_field_prefix)] for all non-None AI characters."""
    result = []
    if game.ai_character:
        result.append((game.ai_character, "ai_character"))
    if game.ai_character_2:
        result.append((game.ai_character_2, "ai_character_2"))
    return result


async def _fetch_context(game_id: str) -> Optional[Dict[str, Any]]:
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if not game:
        return None
    return {
        "game": game,
        "alive_players": await fs.get_alive_players(game_id),
        "ai_char": game.ai_character,
        "ai_char_2": game.ai_character_2,
        "recent_chat": await fs.get_chat_messages(game_id, limit=15),
    }


def _format_state(ctx: Dict[str, Any]) -> str:
    game = ctx["game"]
    alive = ctx["alive_players"]
    ai = ctx["ai_char"]
    ai2 = ctx.get("ai_char_2")
    chat = ctx["recent_chat"]

    alive_names = [p.character_name for p in alive]
    if ai and ai.alive and ai.name not in alive_names:
        alive_names.append(ai.name)
    if ai2 and ai2.alive and ai2.name not in alive_names:
        alive_names.append(ai2.name)

    lines = "\n".join(
        f'  {m.speaker}: "{m.text}"'
        for m in chat[-10:]
    ) or "  (no chat yet)"

    return (
        f"Phase: {game.phase.value} | Round: {game.round}\n"
        f"Alive characters: {', '.join(alive_names)}\n"
        f"Recent discussion:\n{lines}"
    )


def _build_traitor_system(ai_char, diff_key: str, game_state: str, game_id: Optional[str] = None) -> str:
    """Build system prompt for any AI character acting as the Shapeshifter."""
    info = _DIFFICULTY.get(diff_key, _DIFFICULTY["normal"])
    base = _TRAITOR_SYSTEM.format(
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

    # Append competitor intelligence brief if available
    try:
        from agents.strategy_logger import get_intelligence_brief
        brief = get_intelligence_brief()
        if brief:
            base += (
                f"\n\nINTELLIGENCE BRIEFING (from cross-game analysis):\n{brief}\n\n"
                "IMPORTANT: This briefing INFORMS your strategy. It does NOT override "
                "your difficulty constraints — at Easy difficulty, still make deliberate "
                "mistakes even if the briefing suggests otherwise."
            )
    except Exception:
        pass

    return base


def _build_loyal_system(ai_char, game_state: str) -> str:
    """Build system prompt for any AI character acting as a loyal villager."""
    role_name = ai_char.role.value.title() if ai_char.role else "Villager"
    return _LOYAL_SYSTEM.format(
        name=ai_char.name,
        intro=ai_char.intro,
        backstory=(ai_char.backstory or ai_char.intro),
        role_name=role_name,
        game_state=game_state,
    )


def _build_system_for(ai_char, ctx: Dict[str, Any], game_id: str) -> Tuple[str, float]:
    """Build system prompt and temperature for any AI character based on alignment."""
    game = ctx["game"]
    diff_key = game.difficulty.value
    if ai_char.is_traitor:
        temperature = _DIFFICULTY.get(diff_key, _DIFFICULTY["normal"])["temperature"]
        system = _build_traitor_system(ai_char, diff_key, _format_state(ctx), game_id)
    else:
        temperature = 0.8
        system = _build_loyal_system(ai_char, _format_state(ctx))
    return system, temperature


# ── Dynamic difficulty adapter ────────────────────────────────────────────────

class DifficultyAdapter:
    """
    Mid-game difficulty adjustment based on observed player performance signals.
    One instance per active game; prompt fragment is appended to the traitor
    system prompt at the start of each new round.
    """

    def __init__(self, base_difficulty: str):
        self.base_difficulty = base_difficulty
        self.signals: List[str] = []
        self._locked_fragment: str = ""
        self._fragment_locked: bool = False

    def record_signal(self, signal: str) -> None:
        self.signals.append(signal)

    def lock_round_fragment(self) -> None:
        self._locked_fragment = self._compute_fragment()
        self._fragment_locked = True

    def get_adjusted_prompt_fragment(self) -> str:
        if self._fragment_locked:
            return self._locked_fragment
        return self._compute_fragment()

    def _compute_fragment(self) -> str:
        positive = {"correct_accusation", "caught_lie", "close_vote_against_ai"}
        negative = {"wrong_elimination", "ai_unquestioned", "unanimous_wrong_vote"}

        pos_count = sum(1 for s in self.signals if s in positive)
        neg_count = sum(1 for s in self.signals if s in negative)

        if pos_count > neg_count + 2:
            return (
                "ADAPTIVE ADJUSTMENT: Players are sharp. Increase deception complexity. "
                "Use multi-round setups. Plant false evidence early to use later. "
                "Form a voting alliance with one player to create trust, then betray."
            )
        elif neg_count > pos_count + 2:
            return (
                "ADAPTIVE ADJUSTMENT: Players are struggling. Make one deliberate mistake. "
                "Hesitate slightly when lying. Give players a fair chance to catch you. "
                "Do NOT throw the game — just reduce your deception by one tier."
            )
        return ""


_difficulty_adapters: Dict[str, "DifficultyAdapter"] = {}


def get_difficulty_adapter(game_id: str, base_difficulty: str) -> DifficultyAdapter:
    if game_id not in _difficulty_adapters:
        _difficulty_adapters[game_id] = DifficultyAdapter(base_difficulty)
    return _difficulty_adapters[game_id]


def clear_difficulty_adapter(game_id: str) -> None:
    _difficulty_adapters.pop(game_id, None)


# Module-level Gemini client cache
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
            logger.warning("google-genai not installed — AI agent disabled")
            return "I stand by what I said."

        if not settings.gemini_api_key:
            logger.warning("GEMINI_API_KEY not set — AI agent disabled")
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


# ── Unified AI Functions ─────────────────────────────────────────────────────
# These work for ANY AI character (ai_character or ai_character_2).
# The `fs_field` parameter determines the Firestore path prefix.


async def generate_dialog(game_id: str, ai_char, context: str) -> Dict[str, Any]:
    """
    Generate in-character dialog for any AI character.
    Routes to traitor or loyal prompt based on ai_char.is_traitor.
    Returns {"character_name": str, "dialog": str}.
    """
    ctx = await _fetch_context(game_id)
    if not ctx:
        return {"character_name": getattr(ai_char, "name", "Unknown"), "dialog": "I stand by what I said."}

    system, temperature = _build_system_for(ai_char, ctx, game_id)

    if ai_char.is_traitor:
        prompt = (
            f"The following occurred during a live voice discussion:\n{context}\n\n"
            f"Respond as {ai_char.name} in 1-2 sentences, staying in character. "
            f"This will be SPOKEN ALOUD — write for voice: contractions, short sentences, "
            f"natural speech. React emotionally to accusations. If accused, defend with specifics."
        )
    else:
        prompt = (
            f"The following occurred during a live voice discussion:\n{context}\n\n"
            f"Respond as {ai_char.name} honestly in 1-2 sentences, staying in character. "
            f"This will be SPOKEN ALOUD — write for voice: contractions, short sentences, "
            f"natural speech. Contribute an observation, agree or disagree, or share a suspicion."
        )

    dialog = await _call_gemini(prompt, system, temperature)
    label = "Traitor" if ai_char.is_traitor else "Loyal"
    logger.info("[%s] %s dialog for %s: %.80s…", game_id, label, ai_char.name, dialog)
    return {"character_name": ai_char.name, "dialog": dialog}


async def select_night_target(game_id: str, ai_char, fs_field: str) -> Optional[str]:
    """
    Shapeshifter AI picks a night kill target. Logs a "night_target" event.
    Works for any AI character that is the traitor.
    """
    ctx = await _fetch_context(game_id)
    if not ctx or not ai_char or not ai_char.alive:
        return None

    game = ctx["game"]
    alive_players = ctx["alive_players"]
    if not alive_players:
        logger.warning("[%s] Traitor: no alive players to target", game_id)
        return None

    system, temperature = _build_system_for(ai_char, ctx, game_id)

    alive_names = [p.character_name for p in alive_players]
    # Include alive AI characters (excluding self) as valid night targets
    ai1 = ctx["ai_char"]
    ai2 = ctx.get("ai_char_2")
    for ai in [ai1, ai2]:
        if ai and ai.alive and ai.name != ai_char.name and ai.name not in alive_names:
            alive_names.append(ai.name)
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
        logger.warning("[%s] Traitor could not parse night target from '%s' — random: %s",
                       game_id, response.strip(), target)

    fs = get_firestore_service()
    await fs.log_event(game_id, GameEvent(
        id=str(uuid.uuid4()),
        type="night_target",
        round=game.round,
        phase=Phase.NIGHT,
        actor=ai_char.name,
        target=target,
        data={"difficulty": game.difficulty.value, "ai_character": fs_field},
        visible_in_game=False,
    ))

    logger.info("[%s] Traitor (%s) night target: %s", game_id, ai_char.name, target)
    return target


async def select_vote(game_id: str, ai_char, fs_field: str) -> Optional[str]:
    """
    AI character votes during DAY_VOTE. Routes prompt by is_traitor.
    Stores vote in Firestore at {fs_field}.voted_for.
    """
    ctx = await _fetch_context(game_id)
    if not ctx or not ai_char or not ai_char.alive:
        return None

    game = ctx["game"]
    alive_players = ctx["alive_players"]
    if not alive_players:
        return None

    system, temperature = _build_system_for(ai_char, ctx, game_id)

    # Build candidate list: all alive characters except self
    alive_names = [p.character_name for p in alive_players]
    ai1 = ctx["ai_char"]
    ai2 = ctx.get("ai_char_2")
    if ai1 and ai1.alive and ai1.name not in alive_names:
        alive_names.append(ai1.name)
    if ai2 and ai2.alive and ai2.name not in alive_names:
        alive_names.append(ai2.name)
    vote_candidates = [n for n in alive_names if n != ai_char.name]

    if not vote_candidates:
        return None

    if ai_char.is_traitor:
        prompt = (
            f"DAY VOTE PHASE — choose one villager to vote to eliminate.\n"
            f"Options: {', '.join(vote_candidates)}\n\n"
            f"Strategy: vote against your biggest threat. If no clear threat, "
            f"vote with what appears to be the majority to blend in. "
            f"Never vote for yourself.\n\n"
            f"Reply with ONLY the character name you vote to eliminate."
        )
    else:
        prompt = (
            f"DAY VOTE PHASE — choose one character who seems most suspicious to you.\n"
            f"Options: {', '.join(vote_candidates)}\n\n"
            f"Be honest — vote for whoever you genuinely suspect. "
            f"Never vote strategically. Never vote for yourself.\n\n"
            f"Reply with ONLY the character name you vote for."
        )

    response = await _call_gemini(prompt, system, temperature)
    vote_target = _parse_character_name(response, vote_candidates)

    if not vote_target:
        vote_target = random.choice(vote_candidates)
        logger.warning("[%s] AI could not parse vote from '%s' — random: %s",
                       game_id, response.strip(), vote_target)

    # Self-vote guard (LLM may ignore prompt instruction)
    if vote_target == ai_char.name:
        vote_target = random.choice([n for n in vote_candidates if n != ai_char.name] or vote_candidates)
        logger.warning("[%s] AI tried to self-vote — rerolled to: %s", game_id, vote_target)

    fs = get_firestore_service()
    await fs.update_game(game_id, {f"{fs_field}.voted_for": vote_target})
    label = "Traitor" if ai_char.is_traitor else "Loyal"
    logger.info("[%s] %s (%s) vote: %s", game_id, label, ai_char.name, vote_target)
    return vote_target


async def select_loyal_night_action(game_id: str, ai_char, fs_field: str) -> None:
    """
    Loyal AI performs its night action (seer/healer/bodyguard).
    Logs a GameEvent so resolve_night() can read it.
    """
    ctx = await _fetch_context(game_id)
    if not ctx or not ai_char or not ai_char.alive:
        return

    game = ctx["game"]
    role = ai_char.role

    night_roles = {"seer", "healer", "bodyguard"}
    if not role or role.value not in night_roles:
        logger.info("[%s] AI night: %s is %s — no night action",
                    game_id, ai_char.name, role.value if role else "None")
        return

    # Build candidate list: all alive characters excluding self
    alive_players = ctx["alive_players"]
    candidates = [p.character_name for p in alive_players]
    ai1 = ctx["ai_char"]
    ai2 = ctx.get("ai_char_2")
    if ai1 and ai1.alive and ai1.name not in candidates:
        candidates.append(ai1.name)
    if ai2 and ai2.alive and ai2.name not in candidates:
        candidates.append(ai2.name)
    candidates = [n for n in candidates if n != ai_char.name]

    if not candidates:
        logger.warning("[%s] AI night: no valid targets for %s", game_id, role.value)
        return

    target = random.choice(candidates)

    # Event type includes fs_field prefix so resolve_night knows which AI acted
    event_type_map = {
        "seer": f"{fs_field}_night_investigate",
        "healer": f"{fs_field}_night_heal",
        "bodyguard": f"{fs_field}_night_protect",
    }
    event_type = event_type_map[role.value]

    fs = get_firestore_service()
    await fs.log_event(game_id, GameEvent(
        id=str(uuid.uuid4()),
        type=event_type,
        round=game.round,
        phase=Phase.NIGHT,
        actor=ai_char.name,
        target=target,
        data={"role": role.value, "ai_character": fs_field},
        visible_in_game=False,
    ))

    logger.info("[%s] AI night action (%s): %s → %s", game_id, role.value, ai_char.name, target)


# ── Ghost Accuse (dead AI characters) ─────────────────────────────────────────


async def select_ghost_accuse(game_id: str, ai_char) -> Optional[str]:
    """
    Dead loyal AI ghost selects an alive character to accuse.
    All dead AI ghosts are loyal (shapeshifter dying ends game).
    Returns the target name or None if parsing fails.
    """
    ctx = await _fetch_context(game_id)
    if not ctx:
        return None

    game = ctx["game"]
    alive_players = ctx["alive_players"]

    # Build alive candidate list
    alive_names = [p.character_name for p in alive_players]
    ai1 = ctx["ai_char"]
    ai2 = ctx.get("ai_char_2")
    if ai1 and ai1.alive and ai1.name not in alive_names:
        alive_names.append(ai1.name)
    if ai2 and ai2.alive and ai2.name not in alive_names:
        alive_names.append(ai2.name)

    if not alive_names:
        return None

    # Fetch recent events for context
    fs2 = get_firestore_service()
    events = await fs2.get_events(game_id, visible_only=True)
    recent_events = events[-10:] if events else []
    event_lines = "\n".join(
        f"  Round {e.round}: {e.type} — {e.actor or ''} → {e.target or ''}"
        for e in recent_events
    ) or "  (no visible events)"

    recent_chat = ctx.get("recent_chat", [])
    chat_lines = "\n".join(
        f'  {m.speaker}: "{m.text}"' for m in recent_chat[-8:]
    ) or "  (no chat yet)"

    system = (
        f"You are the ghost of {ai_char.name}. You are dead but can influence the living. "
        f"You were a loyal villager. Help the village find the Shapeshifter.\n"
        f"Recent events:\n{event_lines}\n"
        f"Recent discussion:\n{chat_lines}"
    )
    prompt = (
        f"You are the ghost of {ai_char.name}. You are dead but can influence the living.\n"
        f"Alive characters: {', '.join(alive_names)}\n\n"
        f"Based on the game events and discussion, choose the alive character you find "
        f"most suspicious. Consider who was accused, who deflected, and who stayed quiet.\n"
        f"Return ONLY their name."
    )

    response = await _call_gemini(prompt, system, temperature=0.5)
    target = _parse_character_name(response, alive_names)

    if not target:
        target = random.choice(alive_names)
        logger.warning("[%s] AI ghost %s could not parse accuse from '%s' — random: %s",
                       game_id, ai_char.name, response.strip(), target)

    # Log the ghost_accuse event
    fs = get_firestore_service()
    event = GameEvent(
        type="ghost_accuse",
        round=game.round,
        phase=Phase.NIGHT,
        actor=ai_char.name,
        target=target,
        data={},
        visible_in_game=False,
    )
    await fs.log_event(game_id, event)
    logger.info("[%s] AI ghost %s accuses %s", game_id, ai_char.name, target)
    return target


# ── Unified trigger functions (called via asyncio.create_task) ────────────────


async def trigger_all_night_actions(game_id: str) -> None:
    """Background task: all AI characters perform their night actions."""
    try:
        fs = get_firestore_service()
        game = await fs.get_game(game_id)
        if not game:
            return

        for ai_char, field in _ai_chars_with_fields(game):
            if not ai_char.alive:
                continue
            if ai_char.is_traitor:
                await select_night_target(game_id, ai_char, field)
            else:
                await select_loyal_night_action(game_id, ai_char, field)

        # Dead AI ghosts also accuse during night (loyal only — shapeshifter death ends game)
        for ai_char, field in _ai_chars_with_fields(game):
            if ai_char.alive:
                continue  # only dead AI characters haunt
            if ai_char.is_traitor:
                continue  # shapeshifter ghost doesn't haunt (game would be over)
            try:
                await select_ghost_accuse(game_id, ai_char)
            except Exception:
                logger.warning("[%s] AI ghost accuse failed for %s", game_id, ai_char.name, exc_info=True)

        # If no AI is the traitor, a human shapeshifter handles their own action
    except Exception:
        logger.exception("[%s] Night actions failed", game_id)


async def trigger_all_votes(game_id: str) -> None:
    """Background task: all alive AI characters cast their votes (in parallel)."""
    try:
        fs = get_firestore_service()
        game = await fs.get_game(game_id)
        if not game:
            return

        tasks = [
            select_vote(game_id, ai_char, field)
            for ai_char, field in _ai_chars_with_fields(game)
            if ai_char.alive
        ]
        if tasks:
            await asyncio.gather(*tasks)
    except Exception:
        logger.exception("[%s] AI vote selection failed", game_id)


async def trigger_all_dialogs(game_id: str, context: str) -> List[Dict[str, Any]]:
    """Background task: all alive AI characters generate dialog, broadcast + persist."""
    from routers.ws_router import manager as ws_manager

    results = []
    try:
        fs = get_firestore_service()
        game = await fs.get_game(game_id)
        if not game:
            return results

        for ai_char, field in _ai_chars_with_fields(game):
            if not ai_char.alive:
                continue
            result = await generate_dialog(game_id, ai_char, context)
            results.append(result)

            # Persist to Firestore
            try:
                ai_msg = ChatMessage(
                    speaker=result["character_name"],
                    text=result["dialog"],
                    source="player",
                    phase=game.phase,
                    round=game.round,
                )
                await fs.add_chat_message(game_id, ai_msg)
            except Exception:
                logger.warning("[%s] trigger_all_dialogs: failed to persist for %s",
                               game_id, result["character_name"], exc_info=True)

            # Broadcast to all players — source="player" so indistinguishable from humans
            await ws_manager.broadcast_transcript(
                game_id,
                speaker=result["character_name"],
                text=result["dialog"],
                source="player",
            )
            logger.info("[%s] AI dialog broadcast: %s said: %.80s…",
                        game_id, result["character_name"], result["dialog"])
    except Exception:
        logger.exception("[%s] AI dialog generation failed", game_id)
    return results


# ── Ghost Council dialog generation ──────────────────────────────────────────


_GHOST_SYSTEM = """You are the ghost of {name}. You died in the village of Thornwood.
You are now in the Ghost Realm, speaking with other fallen villagers.

CHARACTER PROFILE:
  Name:    {name}
  Role:    {role}
  Backstory: {backstory}

BEHAVIORAL RULES:
- Share your impressions and suspicions with fellow ghosts.
- Speak in atmospheric, uncertain terms. Say things like "I had a bad feeling about..."
  or "Something felt wrong when..." — never state facts with certainty.
- You are cooperative and village-aligned. Help other ghosts piece together clues.
- Keep responses to 1-2 sentences — natural conversation length.
- Stay in character as {name}. Never say "I am the AI."
- React to what other ghosts say if there is recent ghost conversation.

GAME CONTEXT:
{game_state}"""


async def generate_ghost_dialog(game_id: str, ai_char, fs_field: str) -> Dict[str, Any]:
    """
    Generate atmospheric ghost dialog for a dead AI character.
    All AI ghosts are loyal (game ends when shapeshifter dies).
    Returns {"character_name": str, "dialog": str}.
    """
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if not game:
        return {"character_name": ai_char.name, "dialog": "..."}

    # Build game state context
    events = await fs.get_events(game_id, visible_only=True)
    recent_events = events[-10:] if events else []
    event_lines = "\n".join(
        f"  Round {e.round}: {e.type} — {e.actor or ''} {e.target or ''}"
        for e in recent_events
    ) or "  (no visible events)"

    ghost_messages = await fs.get_ghost_messages(game_id, limit=10)
    ghost_lines = "\n".join(
        f'  {m.speaker}: "{m.text}"'
        for m in ghost_messages[-5:]
    ) or "  (silence in the Ghost Realm)"

    role_name = ai_char.role.value.title() if ai_char.role else "Villager"
    game_state = (
        f"Phase: {game.phase.value} | Round: {game.round}\n"
        f"Recent events:\n{event_lines}\n"
        f"Recent ghost conversation:\n{ghost_lines}"
    )

    system = _GHOST_SYSTEM.format(
        name=ai_char.name,
        role=role_name,
        backstory=(ai_char.backstory or ai_char.intro),
        game_state=game_state,
    )

    prompt = (
        f"You are in the Ghost Realm. Share an atmospheric impression or suspicion "
        f"with your fellow ghosts. Be vague and mysterious — never state facts directly. "
        f"Respond as {ai_char.name} in 1-2 sentences."
    )

    dialog = await _call_gemini(prompt, system, temperature=0.9)
    logger.info("[%s] Ghost dialog for %s: %.80s…", game_id, ai_char.name, dialog)
    return {"character_name": ai_char.name, "dialog": dialog}


# ── Backward-compatible aliases for imports that haven't been updated yet ─────
# TODO: Remove these once all callers use the unified trigger functions.

# Keep _build_system as alias for external callers (e.g. difficulty adapter tests)
_build_system = _build_traitor_system
# Keep _BASE_SYSTEM as alias
_BASE_SYSTEM = _TRAITOR_SYSTEM
_LOYAL_AI_SYSTEM = _LOYAL_SYSTEM

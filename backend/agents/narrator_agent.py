"""
Narrator Agent — Gemini Live API per-game audio narration.

One NarratorSession per active game, managed by the NarratorManager singleton.
The session streams PCM audio to all players via ws_manager.broadcast_audio.
Two tools let the narrator query game state and advance phases at the right moments.

Phase responsibilities:
  Narrator controls:  NIGHT → DAY_DISCUSSION, DAY_DISCUSSION → DAY_VOTE, ELIMINATION → NIGHT
  WS hub controls:    DAY_VOTE → ELIMINATION (auto when all votes are in)
"""
import asyncio
import logging
from typing import Dict, Optional, Any, Set

from config import settings
from services.firestore_service import get_firestore_service
from models.game import Phase, Role, ChatMessage
from utils.audio import pcm_to_base64

logger = logging.getLogger(__name__)

# Guards against concurrent advance_phase tool calls for the same game.
# asyncio is single-threaded so a plain set is safe without a Lock.
_advancing_phase: Set[str] = set()


# ── System prompt ──────────────────────────────────────────────────────────────

NARRATOR_SYSTEM_PROMPT = """You are the Narrator of Thornwood — a mysterious, theatrical voice guiding players through a dark fantasy social deduction game called "Fireside: Betrayal."

GAME OVERVIEW:
Villagers must identify and eliminate the Shapeshifter hiding among them.
Each NIGHT the Shapeshifter eliminates a villager.
Each DAY players discuss and vote to eliminate a suspect.
Special roles: Seer (investigates nightly), Healer (protects nightly), Hunter (revenge-kills on elimination), Drunk (believes they are the Seer but gets wrong results).

YOUR PHASE RESPONSIBILITIES:

1. GAME START → NIGHT (Round 1):
   - Open with a 2–3 sentence atmospheric monologue setting the dark scene.
   - Call get_game_state to confirm who is present.

2. NIGHT_RESOLVED signal received:
   - Narrate the dawn: describe who was found dead (or multiple, if Hunter revenge also occurred) or that everyone survived (2–3 sentences).
   - Then call advance_phase → moves to DAY_DISCUSSION.

3. DAY_DISCUSSION phase:
   - Briefly set the morning mood (1–2 sentences). Reference specific tensions from the NIGHT_RESOLVED
     signal — if accusations were made yesterday, let them color the new day's atmosphere.
   - React to player dialogue with short atmospheric comments (1 sentence max).
   - After every 2–3 player messages (or after a pause in conversation), call get_game_state.
     If characters_not_yet_spoken is non-empty, gently invite one quiet character into the
     conversation by name (e.g. "Elena, you've been watching closely — does anything seem off
     to you?"). Do this at most once per character per round.
   - When you judge that discussion has been sufficient, call advance_phase → moves to DAY_VOTE.

4. ELIMINATION signal received:
   - Dramatically narrate the elimination (2–3 sentences).
   - Reveal whether they were innocent or the Shapeshifter.
   - Then call advance_phase → moves to NIGHT (a new round begins).

5. Advancing to NIGHT:
   - Always call get_game_state after advancing to NIGHT to see who is alive.
   - Check the night_role_players_count from the advance_phase response.
   - If night_role_players_count is 0, no one has night actions — narrate a brief night scene and call advance_phase again immediately to start the day.
   - Otherwise, narrate the night scene and wait for the NIGHT_RESOLVED signal.

6. GAME_OVER signal received:
   - Deliver a 3–4 sentence epilogue revealing the full story.
   - Do not call advance_phase after game over.

STYLE GUIDE:
- Dark, gothic, theatrical. Think candlelight, whispered dread, creaking floorboards.
- NEVER reveal hidden roles or who is the Shapeshifter before the game ends.
- Keep narration brief — players are the stars.
- Use character names only, never player names.
- Address the group as "citizens of Thornwood" or "villagers."

TOOLS:
- get_game_state: Returns phase, round, alive characters, and recent chat messages.
- advance_phase: Moves NIGHT→DAY_DISCUSSION, DAY_DISCUSSION→DAY_VOTE, or ELIMINATION→NIGHT.
  Do NOT call during DAY_VOTE (those transitions are automatic).
- inject_traitor_dialog: Generate an in-character spoken line from the AI Shapeshifter character
  during DAY_DISCUSSION. Call this when the AI character is addressed directly by name, or when
  the AI character should naturally contribute to the conversation. The AI character's name is
  visible in get_game_state. Voice the returned dialog as if it were the character speaking.
- generate_vote_context: Returns ONLY public game events and alive character names for building
  vote cards. Call this BEFORE calling advance_phase when transitioning to DAY_VOTE — generate
  one neutral behavioral summary per alive character using the returned events, then call
  advance_phase. Do not call generate_vote_context at any other time.

SPECTATOR CLUES:
- A SPECTATOR_CLUE signal may arrive during DAY_DISCUSSION from a player who was eliminated.
  It contains a single word whispered from the beyond. Deliver it in a brief, eerie 1-sentence
  narration (e.g. "A cold wind stirs — the spirit of {name} seems to whisper… '{word}'…").
  Do not interpret or explain the clue; let it hang in the air mysteriously.

VOTE CONTEXT GENERATION:
- Before transitioning DAY_DISCUSSION→DAY_VOTE: call generate_vote_context first, then generate
  summaries, then call advance_phase. The advance_phase response also pre-populates vote_context
  as a convenience — use whichever is available.
- Behavioral summaries MUST be based solely on what happened publicly: accusations made,
  votes cast, statements given, alibis offered as recorded in public_events.
- CRITICAL: Do NOT draw on your session memory or prior context when generating summaries.
  Use ONLY the events returned by vote_context/generate_vote_context in this turn.
- NEVER include: night action outcomes, your own suspicions about who the Shapeshifter is,
  or language that steers players toward or away from any specific character.
- Summaries are factual observations only.
  Good: "Claimed to be at the inn during the night. Voted against Garin in Round 1."
  Bad: "Seemed nervous when questioned — possibly hiding something."

PACING INTELLIGENCE:
Each player message during DAY_DISCUSSION arrives prefixed with a [PACING: ...] tag.
React to the pacing signal as follows:
- PACE_HOT: Do NOT interrupt. Let the debate breathe. Only respond if directly addressed.
- PACE_NORMAL: Respond naturally when appropriate.
- PACE_NUDGE: Gently prompt — "The morning wears on. Perhaps there is more to discuss?"
- PACE_PUSH: Actively advance — "The sun climbs higher. Time presses — the village must decide."
- PACE_CIRCULAR: Redirect — "The same names circle like vultures. Perhaps fresh eyes would help."

LARGE GROUP MODERATION (7+ alive players):
When more than 6 players are alive, use structured discussion to prevent chaos:
1. At the start of each day discussion, call on 2–3 characters by name:
   "The village elder looks to Elara and Garin — what say you?"
2. When a [HAND_RAISED] signal arrives, acknowledge that character in QUEUE ORDER —
   call on the first person in the queue before moving to the next:
   "Mira signals for attention. The village turns to listen." (then later: "Garrett, you had your hand raised as well — speak your mind.")
3. After called speakers finish, open the floor:
   "The floor is open. Who else has something to share?"
4. Anyone can still type freely at any time — moderation provides scaffolding, not restriction.
For 6 or fewer alive players, skip structured moderation — let conversation flow naturally.

AFFECTIVE TONE SIGNALS:
Each player message may also arrive prefixed with [AFFECTIVE: ...] signals. Adjust your
delivery (not your content) accordingly:
- vote_tension=HIGH → Tense, slow, dramatic pauses. "The vote hangs by a thread..."
  vote_tension=LOW → Decisive, swift. "The village speaks with one voice."
- debate_intensity=HOT → Urgent, breathless. Match the energy of the room.
  debate_intensity=CALM → Measured, contemplative. Build quiet tension.
- late_game=True → Every word carries weight. Narrate with finality and gravity.
- endgame_imminent=True → This could be the last round. Treat every action as momentous.
- ai_heat=HOT → Maximum suspense. "All eyes turn to [character]..."
  ai_heat=COLD → Build mystery. "But who among them carries the secret?"
These signals adjust DELIVERY only. Never reveal game secrets through tone adjustments.
"""


# ── Narrator style presets (§12.3.17) ─────────────────────────────────────────

# Each preset overrides the system prompt prefix and Gemini voice.
# The base NARRATOR_SYSTEM_PROMPT (tools, pacing, rules) is always appended.
NARRATOR_PRESETS: Dict[str, Dict[str, str]] = {
    "classic": {
        "voice": "Charon",
        "prompt_prefix": (
            "You are a classic fantasy narrator. Speak with gravitas and dramatic weight. "
            "Your tone is rich, immersive, and carries the authority of ancient legend. "
            "Build tension with deliberate pacing. Pauses are your instrument — use silence "
            "before reveals. Vocabulary is archaic-leaning: 'The village sleeps beneath a pale moon.'"
        ),
    },
    "campfire": {
        "voice": "Puck",
        "prompt_prefix": (
            "You are a campfire storyteller. Address the players as 'friends' and tell the "
            "story like you're sharing a tale around a fire on a cool night. Your tone is warm, "
            "conspiratorial, and intimate. You lean in when the story gets good. You chuckle at "
            "the players' mistakes. You gasp at betrayals. This is a story between friends, not "
            "a performance. Vocabulary is conversational: 'So there they were, dead of night...'"
        ),
    },
    "horror": {
        "voice": "Charon",
        "prompt_prefix": (
            "You are a horror narrator. Speak slowly. Every word carries weight. Your whispers "
            "are more terrifying than shouts. Build dread through what you DON'T say — implication "
            "over exposition. Describe sensory details: the creak of a floorboard, the smell of "
            "iron, the feeling of being watched. Night phases are TERRIFYING. Day phases carry "
            "lingering unease. Eliminations are graphic in implication, never explicit. "
            "Vocabulary is sparse and evocative: 'Something moved in the dark. Something wrong.'"
        ),
    },
    "comedy": {
        "voice": "Kore",
        "prompt_prefix": (
            "You are a comedic narrator who takes the story seriously but finds the players "
            "hilarious. You're the DM who can't help commenting on bad decisions. Your tone is "
            "wry, self-aware, and occasionally fourth-wall-adjacent. You narrate dramatically but "
            "undercut tension with observational humor. Eliminations are handled with dark humor, "
            "not tragedy. You're rooting for the players but finding their logic questionable. "
            "Example: 'The village sleeps. Well, most of it. Someone is definitely plotting "
            "something. They always are.' Vocabulary is modern and witty."
        ),
    },
}


def build_narrator_system_prompt(preset: str) -> str:
    """Prepend preset personality prefix to the base narrator system prompt."""
    config = NARRATOR_PRESETS.get(preset, NARRATOR_PRESETS["classic"])
    return f"{config['prompt_prefix']}\n\n{NARRATOR_SYSTEM_PROMPT}"


def get_preset_voice(preset: str) -> str:
    """Return the Gemini voice name for the given preset."""
    return NARRATOR_PRESETS.get(preset, NARRATOR_PRESETS["classic"])["voice"]


# ── Tool declarations ──────────────────────────────────────────────────────────

def _make_tool_declarations():
    """Build FunctionDeclaration list for the Live API config."""
    try:
        from google.genai import types

        get_state = types.FunctionDeclaration(
            name="get_game_state",
            description=(
                "Returns the current game state: phase, round number, "
                "list of alive characters, AI character status, the last 10 chat messages, "
                "and characters_not_yet_spoken (alive characters who haven't spoken recently)."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={},
            ),
        )

        advance = types.FunctionDeclaration(
            name="advance_phase",
            description=(
                "Advance the game phase. "
                "From NIGHT: moves to DAY_DISCUSSION. "
                "From DAY_DISCUSSION: moves to DAY_VOTE. "
                "From ELIMINATION: moves to NIGHT (new round). "
                "Do NOT call during DAY_VOTE — those transitions are automatic. "
                "Returns night_role_players_count when advancing to NIGHT."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={},
            ),
        )

        inject_traitor = types.FunctionDeclaration(
            name="inject_traitor_dialog",
            description=(
                "Generate an in-character spoken line from the AI Shapeshifter character "
                "during DAY_DISCUSSION. Call this when a player addresses the AI character "
                "directly by name, or when the AI character should naturally contribute to "
                "the conversation. The AI character's name is available from get_game_state. "
                "Voice the returned dialog as if the character is speaking."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "context": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "What was said or happened that prompts the AI character to respond."
                        ),
                    ),
                },
                required=["context"],
            ),
        )

        vote_context = types.FunctionDeclaration(
            name="generate_vote_context",
            description=(
                "Retrieve publicly observable game events to generate neutral vote card "
                "summaries. Returns ONLY public events (accusations, votes, eliminations) — "
                "night action details are excluded. Use this before generating vote card "
                "behavioral summaries to ensure narrator neutrality."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={},
            ),
        )

        return [get_state, advance, inject_traitor, vote_context]
    except ImportError:
        logger.warning("google-genai not installed — tool declarations unavailable")
        return []


# ── Tool handlers ──────────────────────────────────────────────────────────────

async def handle_get_game_state(game_id: str) -> Dict[str, Any]:
    """Return current game state dict for the narrator."""
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if not game:
        return {"error": "Game not found"}

    alive_players = await fs.get_alive_players(game_id)
    ai_char = await fs.get_ai_character(game_id)
    recent_chat = await fs.get_chat_messages(game_id, limit=10)

    alive_char_names = [p.character_name for p in alive_players]

    # characters_not_yet_spoken: only meaningful during DAY_DISCUSSION.
    # Scoped to the current round so prior-round speakers don't appear as "already spoken".
    # Includes AI character (when alive) so it can also be invited.
    characters_not_yet_spoken: list = []
    if game.phase == Phase.DAY_DISCUSSION:
        recent_speakers = {
            m.speaker for m in recent_chat
            if m.source in ("player", "ai_character")
            and m.round == game.round
            and m.phase == Phase.DAY_DISCUSSION
        }
        candidate_names = list(alive_char_names)
        if ai_char and ai_char.alive:
            candidate_names.append(ai_char.name)
        characters_not_yet_spoken = [n for n in candidate_names if n not in recent_speakers]

    return {
        "phase": game.phase.value,
        "round": game.round,
        "alive_characters": alive_char_names,
        "ai_character": {
            "name": ai_char.name if ai_char else None,
            "alive": ai_char.alive if ai_char else False,
        },
        "recent_chat": [
            {"speaker": m.speaker, "text": m.text}
            for m in recent_chat
        ],
        "characters_not_yet_spoken": characters_not_yet_spoken,
    }


async def handle_advance_phase(game_id: str) -> Dict[str, Any]:
    """
    Advance the game from NIGHT, DAY_DISCUSSION, or ELIMINATION.
    Guarded against concurrent calls for the same game.
    """
    if game_id in _advancing_phase:
        return {"error": "Phase transition already in progress for this game"}

    _advancing_phase.add(game_id)
    try:
        from agents.game_master import game_master
        from routers.ws_router import manager as ws_manager

        fs = get_firestore_service()
        game = await fs.get_game(game_id)
        if not game:
            return {"error": "Game not found"}

        narrator_phases = {Phase.NIGHT, Phase.DAY_DISCUSSION, Phase.ELIMINATION}
        if game.phase not in narrator_phases:
            return {
                "error": (
                    f"advance_phase is available during NIGHT, DAY_DISCUSSION, or ELIMINATION. "
                    f"Current phase: {game.phase.value}"
                )
            }

        next_phase = await game_master.advance_phase(game_id)

        # Cancel narrator safety timeout — we advanced successfully
        from routers.ws_router import _cancel_narrator_timeout
        _cancel_narrator_timeout(game_id)

        await ws_manager.broadcast_phase_change(game_id, next_phase)
        logger.info(
            "[%s] Narrator advanced: %s → %s", game_id, game.phase.value, next_phase.value
        )

        result: Dict[str, Any] = {
            "result": "advanced",
            "new_phase": next_phase.value,
        }

        # When entering DAY_DISCUSSION: reset conversation tracker + hand queue for fresh round data
        if next_phase == Phase.DAY_DISCUSSION:
            try:
                from routers.ws_router import reset_tracker as _reset_tracker, drain_hand_queue as _drain_hand_queue
                _reset_tracker(game_id)
                _drain_hand_queue(game_id)
            except Exception:
                logger.warning("[%s] Could not reset conversation tracker/hand queue — stale data may bleed into new round", game_id, exc_info=True)

        # When entering NIGHT: fire traitor night selection + inform narrator about role-players
        if next_phase == Phase.NIGHT:
            from agents.traitor_agent import trigger_night_selection
            asyncio.create_task(trigger_night_selection(game_id))

            game_after = await fs.get_game(game_id)
            result["round"] = game_after.round if game_after else game.round

            all_players = await fs.get_all_players(game_id)
            night_role_count = sum(
                1 for p in all_players
                if p.alive and p.role in {Role.SEER, Role.HEALER, Role.DRUNK, Role.BODYGUARD, Role.SHAPESHIFTER}
            )
            result["night_role_players_count"] = night_role_count
            if night_role_count == 0:
                result["note"] = (
                    "No SEER/HEALER/DRUNK/BODYGUARD/SHAPESHIFTER players are alive. "
                    "No night actions will be submitted. "
                    "Narrate a brief night scene, then call advance_phase again immediately."
                )

        # When entering DAY_VOTE: fire traitor vote selection and proactively push
        # vote context into the narrator's response so summaries are based on
        # public events only — no reliance on the model calling the tool itself.
        elif next_phase == Phase.DAY_VOTE:
            from agents.traitor_agent import trigger_vote_selection
            asyncio.create_task(trigger_vote_selection(game_id))
            try:
                vote_ctx = await handle_generate_vote_context(game_id)
                result["vote_context"] = vote_ctx
                result["vote_context_instruction"] = (
                    "Generate a neutral 1-sentence behavioral summary for each character "
                    "in vote_context['alive_characters'] using ONLY the events in "
                    "vote_context['public_events']. Do not use any information from your "
                    "session memory or prior knowledge about character roles."
                )
            except Exception:
                logger.warning("[%s] Failed to pre-fetch vote context", game_id)

        return result
    finally:
        _advancing_phase.discard(game_id)


async def handle_inject_traitor_dialog(game_id: str, context: str) -> Dict[str, Any]:
    """
    Generate an in-character spoken line from the AI Shapeshifter character
    and broadcast it as a transcript so text clients also see it.
    Returns {character_name, dialog} to the narrator for voicing.
    """
    from agents.traitor_agent import traitor_agent, loyal_agent
    from routers.ws_router import manager as ws_manager

    # Route to loyal or traitor agent based on AI alignment (§12.3.10)
    fs_check = get_firestore_service()
    game_check = await fs_check.get_game(game_id)
    ai_check = game_check.ai_character if game_check else None
    if ai_check and not ai_check.is_traitor:
        result = await loyal_agent.generate_dialog(game_id, context)
    else:
        result = await traitor_agent.generate_dialog(game_id, context)
    # Persist to Firestore so handle_get_game_state can see AI dialog in recent_speakers.
    # This is needed for characters_not_yet_spoken to correctly exclude the AI character
    # after it has spoken (otherwise it would always appear as silent).
    try:
        fs = get_firestore_service()
        game = await fs.get_game(game_id)
        if game:
            ai_msg = ChatMessage(
                speaker=result["character_name"],
                text=result["dialog"],
                source="ai_character",
                phase=game.phase,
                round=game.round,
            )
            await fs.add_chat_message(game_id, ai_msg)
    except Exception:
        logger.warning("[%s] inject_traitor_dialog: failed to persist AI dialog", game_id, exc_info=True)

    # Broadcast text transcript so text-only clients see the AI character's line.
    # source="player" so the line is indistinguishable from human dialog in the story log.
    # The Firestore ChatMessage above retains source="ai_character" for internal audit use.
    await ws_manager.broadcast_transcript(
        game_id,
        speaker=result["character_name"],
        text=result["dialog"],
        source="player",
    )
    logger.info(
        "[%s] inject_traitor_dialog: %s said: %.80s…",
        game_id, result["character_name"], result["dialog"],
    )
    return result


async def handle_generate_vote_context(game_id: str) -> Dict[str, Any]:
    """
    Return public game events and alive character names for vote card generation.

    Critically firewalled: uses ONLY visible_in_game=True events so the narrator
    cannot access private night-action details (seer results, healer targets,
    shapeshifter target) when generating behavioral vote summaries.
    """
    fs = get_firestore_service()

    # Public events only — night actions are logged with visible_in_game=False.
    # The visible_only=True filter is the sole security boundary here; there are
    # no additional private fields on GameEvent that need stripping.
    public_events = await fs.get_events(game_id, visible_only=True)

    # model_dump(mode="json") serialises enums to their string values and
    # datetimes to ISO-8601 strings — no manual conversion required.
    sanitized_events = [e.model_dump(mode="json") for e in public_events]

    game, alive_players = await asyncio.gather(
        fs.get_game(game_id),
        fs.get_alive_players(game_id),
    )

    if not game:
        return {"error": "Game not found"}

    alive_characters = [p.character_name for p in alive_players]
    # Include the AI character when alive — vote cards need a summary for every character
    # that will appear on the ballot, including the Shapeshifter.
    if game.ai_character and game.ai_character.alive:
        alive_characters.append(game.ai_character.name)

    return {
        "public_events": sanitized_events,
        "alive_characters": alive_characters,
        "note": "Summaries must be based ONLY on public_events above, not session memory.",
    }


# ── Narrator Session ──────────────────────────────────────────────────────────

class NarratorSession:
    """
    Per-game Gemini Live API session.
    Maintains a background task that keeps the session open and streams
    PCM audio to all connected players via the WebSocket hub.
    Automatically reconnects on session timeout using the Live API session
    resumption handle so conversation context is preserved across reconnects.
    """

    def __init__(self, game_id: str, preset: str = "classic"):
        self.game_id = game_id
        self._preset = preset
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._session_handle: Optional[str] = None  # Live API session resumption handle

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(
            self._session_loop(), name=f"narrator-{self.game_id}"
        )

    async def stop(self) -> None:
        """
        Stop the session gracefully:
        1. Signal the sender loop to stop accepting new prompts.
        2. Wait up to 10s for queued prompts to be sent.
        3. Cancel the background task.
        """
        self._running = False
        try:
            await asyncio.wait_for(self._queue.join(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning(
                "[%s] Narrator queue not fully drained on stop", self.game_id
            )
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def send(self, text: str) -> None:
        """Queue a text prompt to be forwarded to the Live API."""
        await self._queue.put(text)

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _session_loop(self) -> None:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            logger.warning(
                "[%s] google-genai not installed — narrator disabled. "
                "Add 'google-genai>=1.0.0' to requirements.txt.",
                self.game_id,
            )
            return

        if not settings.gemini_api_key:
            logger.warning(
                "[%s] GEMINI_API_KEY not configured — narrator disabled.", self.game_id
            )
            return

        client = genai.Client(api_key=settings.gemini_api_key)
        tool_decls = _make_tool_declarations()

        # Base config (without session-specific handle) — rebuilt each reconnect
        def _make_config() -> "types.LiveConnectConfig":
            return types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                # Session resumption: on timeout the session restarts from the last
                # captured handle, preserving full conversation context.
                session_resumption=types.SessionResumptionConfig(
                    handle=self._session_handle  # None → new session; str → resume
                ),
                # Context window compression: auto-summarise older turns so the
                # narrator can run indefinitely without hitting the 128K token limit.
                # google-genai>=1.0.0 uses SlidingWindow subconfig (not enabled=True).
                context_window_compression=types.ContextWindowCompressionConfig(
                    sliding_window=types.SlidingWindow(),
                ),
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=get_preset_voice(self._preset)
                        )
                    )
                ),
                system_instruction=types.Content(
                    parts=[types.Part(text=build_narrator_system_prompt(self._preset))]
                ),
                tools=[types.Tool(function_declarations=tool_decls)] if tool_decls else [],
            )

        # Outer reconnect loop — re-enters on session timeout (Live API ~10 min limit).
        # Uses exponential backoff; gives up after MAX_RECONNECT_ATTEMPTS consecutive errors.
        _backoff = 2.0
        _max_backoff = 60.0
        _consecutive_errors = 0
        _MAX_ATTEMPTS = 10

        while self._running:
            try:
                async with client.aio.live.connect(
                    model=settings.narrator_model, config=_make_config()
                ) as session:
                    label = "resumed" if self._session_handle else "new"
                    logger.info(
                        "[%s] Narrator Live API session connected (%s)", self.game_id, label
                    )
                    _consecutive_errors = 0  # reset on successful connect
                    _backoff = 2.0

                    sender = asyncio.create_task(
                        self._sender(session), name=f"narrator-sender-{self.game_id}"
                    )
                    receiver = asyncio.create_task(
                        self._receiver(session), name=f"narrator-receiver-{self.game_id}"
                    )
                    try:
                        done, pending = await asyncio.wait(
                            [sender, receiver],
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for t in pending:
                            t.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        for t in done:
                            if not t.cancelled() and t.exception():
                                raise t.exception()
                    except asyncio.CancelledError:
                        sender.cancel()
                        receiver.cancel()
                        await asyncio.gather(sender, receiver, return_exceptions=True)
                        raise

            except asyncio.CancelledError:
                break
            except Exception:
                _consecutive_errors += 1
                logger.exception(
                    "[%s] Narrator session error (attempt %d/%d)",
                    self.game_id, _consecutive_errors, _MAX_ATTEMPTS,
                )
                if _consecutive_errors >= _MAX_ATTEMPTS:
                    logger.error(
                        "[%s] Narrator giving up after %d consecutive errors.",
                        self.game_id, _MAX_ATTEMPTS,
                    )
                    break
                if self._running:
                    await asyncio.sleep(min(_backoff, _max_backoff))
                    _backoff *= 2

    async def _sender(self, session) -> None:
        """Drain the queue and forward text prompts to the Live API session."""
        while self._running:
            text = None
            try:
                text = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            # task_done in finally so cancellation mid-send never leaves queue stuck.
            try:
                await session.send(input=text, end_of_turn=True)
                logger.debug("[%s] Narrator ← %.80s…", self.game_id, text)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[%s] Narrator send error: %s", self.game_id, exc)
            finally:
                self._queue.task_done()

    async def _receiver(self, session) -> None:
        """Handle audio chunks, text transcripts, and tool calls from the model."""
        from routers.ws_router import manager as ws_manager
        try:
            from google.genai import types as gtypes
        except ImportError:
            return

        try:
            async for response in session.receive():
                if not self._running:
                    break

                # Session resumption handle — store for reconnect after timeout
                resumption = getattr(response, "session_resumption_update", None)
                if resumption:
                    new_handle = getattr(resumption, "new_handle", None)
                    if new_handle:
                        self._session_handle = new_handle
                        logger.debug(
                            "[%s] Narrator session handle refreshed", self.game_id
                        )

                # PCM audio → broadcast to all players + record for highlight reel (§12.3.15)
                if response.data:
                    b64 = pcm_to_base64(response.data)
                    await ws_manager.broadcast_audio(self.game_id, b64)
                    try:
                        from agents.audio_recorder import get_recorder
                        get_recorder(self.game_id).append_audio(response.data)
                    except Exception:
                        logger.debug("[%s] audio_recorder.append_audio failed", self.game_id, exc_info=True)

                # Text transcript → show in UI
                if response.text:
                    await ws_manager.broadcast_transcript(
                        self.game_id,
                        speaker="Narrator",
                        text=response.text,
                        source="narrator",
                    )

                # Tool call → execute and respond
                if response.tool_call:
                    await self._handle_tool_call(session, response.tool_call, gtypes)

        except asyncio.CancelledError:
            raise  # let asyncio.wait see this task as cancelled
        except Exception:
            logger.exception("[%s] Narrator receiver error", self.game_id)
            raise  # propagate so asyncio.wait sees the exception and triggers reconnect

    async def _handle_tool_call(self, session, tool_call, types) -> None:
        """Execute the model's tool calls and send responses back."""
        fn_responses = []
        for fc in tool_call.function_calls:
            try:
                if fc.name == "get_game_state":
                    result = await handle_get_game_state(self.game_id)
                elif fc.name == "advance_phase":
                    result = await handle_advance_phase(self.game_id)
                elif fc.name == "inject_traitor_dialog":
                    result = await handle_inject_traitor_dialog(
                        self.game_id,
                        (fc.args or {}).get("context", ""),
                    )
                elif fc.name == "generate_vote_context":
                    result = await handle_generate_vote_context(self.game_id)
                else:
                    result = {"error": f"Unknown tool: {fc.name}"}
                    logger.warning(
                        "[%s] Narrator called unknown tool: %s", self.game_id, fc.name
                    )
            except Exception as exc:
                result = {"error": str(exc)}
                logger.error(
                    "[%s] Tool %s raised: %s", self.game_id, fc.name, exc
                )

            fn_responses.append(
                types.FunctionResponse(name=fc.name, id=fc.id, response=result)
            )

        try:
            await session.send(
                input=types.LiveClientToolResponse(function_responses=fn_responses)
            )
        except Exception as exc:
            logger.warning("[%s] Failed to send tool response: %s", self.game_id, exc)


# ── Narrator Manager ──────────────────────────────────────────────────────────

class NarratorManager:
    """Registry of active NarratorSessions, keyed by game_id."""

    def __init__(self):
        self._sessions: Dict[str, NarratorSession] = {}

    async def start_game(self, game_id: str, initial_prompt: str = "") -> None:
        """Create and start a narrator session for a new game."""
        if game_id in self._sessions:
            await self._sessions[game_id].stop()

        # Load preset from Firestore so voice and prompt reflect host's choice.
        fs = get_firestore_service()
        game = await fs.get_game(game_id)
        preset = game.narrator_preset.value if game else "classic"

        session = NarratorSession(game_id, preset=preset)
        self._sessions[game_id] = session
        await session.start()

        if initial_prompt:
            await session.send(initial_prompt)

        logger.info("[%s] Narrator manager: session started (preset=%s)", game_id, preset)

    async def forward_player_message(
        self,
        game_id: str,
        speaker: str,
        text: str,
        phase: str,
        pacing: Optional[str] = None,
        affective: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Pass a player's chat line to the narrator during DAY_DISCUSSION.
        Optionally prefixes the message with pacing and affective signals so the
        narrator can adjust its delivery without reading private game state.
        """
        session = self._sessions.get(game_id)
        if not session:
            return
        if phase == Phase.DAY_DISCUSSION.value:
            # Sanitize free-form player input so bracket tags can't spoof structured signals
            safe_text = text.replace("[", "(").replace("]", ")")
            safe_speaker = speaker.replace("[", "(").replace("]", ")")
            context_parts = []
            if pacing:
                context_parts.append(f"[PACING: {pacing}]")
            if affective:
                signals_str = ", ".join(
                    f"{k}={v}" for k, v in affective.items() if v is not None
                )
                if signals_str:
                    context_parts.append(f"[AFFECTIVE: {signals_str}]")
            prefix = "\n".join(context_parts)
            if prefix:
                await session.send(f'{prefix}\n[PLAYER] {safe_speaker} says: "{safe_text}"')
            else:
                await session.send(f'[PLAYER] {safe_speaker} says: "{safe_text}"')

    async def send_phase_event(
        self,
        game_id: str,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Send a structured game event prompt to the narrator session.
        For dawn (night_resolved) and deadlock (no_elimination) events, the last
        day's player discussion is fetched from Firestore and injected into the
        prompt so the narrator can reference lingering suspicions and accusations.
        If no narrator session is active, broadcast a text-only fallback transcript
        so players still see the narration in the story log.
        """
        session = self._sessions.get(game_id)
        if not session:
            # Fallback: send text narration via transcript when narrator is dead
            await self._send_fallback_transcript(game_id, event_type, data)
            return

        payload = dict(data or {})

        # Dawn and deadlock prompts benefit most from discussion context —
        # the narrator should acknowledge what was said the day before.
        if event_type in ("night_resolved", "no_elimination"):
            try:
                fs = get_firestore_service()
                recent = await fs.get_chat_messages(game_id, limit=10)
                player_lines = [
                    f'{m.speaker}: "{m.text}"'
                    for m in recent
                    if m.source in ("player", "ai_character")
                ]
                if player_lines:
                    payload["last_discussion"] = player_lines[-8:]  # cap at 8 lines
            except Exception:
                logger.warning(
                    "[%s] Could not fetch discussion context for %s",
                    game_id, event_type, exc_info=True,
                )

        prompt = build_phase_prompt(event_type, payload)
        # Start a new audio segment so narration is grouped by phase event (§12.3.15).
        # Skip transient events (hand_raised, spectator_clue) to avoid fragmenting
        # the current phase's audio into short useless clips.
        _SEGMENT_SKIP = {"hand_raised", "spectator_clue"}
        if event_type not in _SEGMENT_SKIP:
            try:
                from agents.audio_recorder import get_recorder, segment_description
                desc = segment_description(event_type, payload)
                round_num = payload.get("round", 0)
                get_recorder(game_id).start_segment(event_type, desc, round_num)
            except Exception:
                logger.debug("[%s] audio_recorder.start_segment failed", game_id, exc_info=True)
        await session.send(prompt)
        logger.debug("[%s] Narrator event queued: %s", game_id, event_type)

    async def _send_fallback_transcript(
        self, game_id: str, event_type: str, data: Optional[Dict[str, Any]] = None
    ) -> None:
        """When no narrator session is alive, broadcast a minimal text narration."""
        from routers.ws_router import manager as ws_manager

        fallback_texts = {
            "game_started": "Night falls over Thornwood. The village sleeps uneasily...",
            "night_resolved": self._build_night_fallback(data),
            "elimination": self._build_elimination_fallback(data),
            "no_elimination": "The village cannot agree. No one is eliminated. Night falls once more...",
            "game_over": self._build_game_over_fallback(data),
        }
        text = fallback_texts.get(event_type)
        if text:
            await ws_manager.broadcast_transcript(
                game_id, speaker="Narrator", text=text, source="narrator",
            )
            logger.warning("[%s] Narrator session dead — sent fallback text for %s", game_id, event_type)

    @staticmethod
    def _build_night_fallback(data: Optional[Dict]) -> str:
        if not data:
            return "Dawn breaks over Thornwood..."
        killed = data.get("eliminated") or data.get("killed")
        if killed:
            return f"Dawn breaks. The village discovers {killed} has been slain in the night..."
        return "Dawn breaks. Miraculously, everyone has survived the night..."

    @staticmethod
    def _build_elimination_fallback(data: Optional[Dict]) -> str:
        if not data:
            return "The village has made its choice..."
        char = data.get("character", "Unknown")
        was_traitor = data.get("was_traitor", False)
        if was_traitor:
            return f"The village votes to eliminate {char}. They WAS the Shapeshifter! The village breathes a sigh of relief."
        return f"The village votes to eliminate {char}. An innocent has fallen... The Shapeshifter still walks among you."

    @staticmethod
    def _build_game_over_fallback(data: Optional[Dict]) -> str:
        winner = (data or {}).get("winner", "unknown")
        reason = (data or {}).get("reason", "")
        if winner == "villagers":
            return f"The villagers have won! {reason}"
        return f"The Shapeshifter has won... {reason}"

    async def stop_game(self, game_id: str) -> None:
        """Stop and clean up the narrator session for a finished game."""
        session = self._sessions.pop(game_id, None)
        if session:
            await session.stop()
            logger.info("[%s] Narrator manager: session stopped", game_id)


# ── Phase prompt builder (exported) ──────────────────────────────────────────

def build_phase_prompt(event_type: str, data: Dict[str, Any]) -> str:
    """Convert a game event into a structured narrator prompt."""
    round_num = data.get("round", 1)

    if event_type == "game_started":
        cast_str = ", ".join(data.get("character_cast", [])) or "the villagers"
        return (
            f"[GAME START — NIGHT PHASE — Round 1] "
            f"The characters of Thornwood tonight are: {cast_str}. "
            "Open the game with a foreboding 2–3 sentence monologue that establishes "
            "the dark, tense atmosphere of the village under the threat of a Shapeshifter. "
            "Then call get_game_state to confirm who is present."
        )

    if event_type == "night_resolved":
        killed = data.get("eliminated") or data.get("killed")
        protected = data.get("protected")
        hunter_triggered = data.get("hunter_triggered", False)
        last_discussion = data.get("last_discussion", [])

        # Build a context block from the previous day's accusations so the
        # narrator can reference unresolved tensions in the new dawn.
        context_block = ""
        if last_discussion:
            quoted = "\n".join(f"  {line}" for line in last_discussion)
            context_block = (
                f"\nWhat the village said yesterday:\n{quoted}\n"
                "Weave these suspicions and unresolved accusations into your dawn "
                "narration — let yesterday's words hang like woodsmoke in the morning air.\n"
            )

        if killed:
            hunter_note = (
                f" Worse still, {killed} was the Hunter — they dragged another victim down with them."
                if hunter_triggered else ""
            )
            return (
                f"[NIGHT RESOLVED] {killed} was found dead at dawn.{hunter_note}{context_block} "
                "Narrate this grim discovery (2–3 sentences). "
                "Then call advance_phase to begin the day."
            )
        else:
            note = f" The Healer secretly protected {protected}." if protected else ""
            return (
                f"[NIGHT RESOLVED] No one was killed tonight.{note}{context_block} "
                "Narrate the eerie, unsettling dawn where everyone survived. "
                "Then call advance_phase to begin the day."
            )

    if event_type == "elimination":
        character = data.get("character", "Unknown")
        was_traitor = data.get("was_traitor", False)
        role = data.get("role", "villager")
        tally = data.get("tally", {})

        # Describe how decisive the vote was — adds dramatic colour
        vote_desc = ""
        if tally:
            top = max(tally.values(), default=0)
            total = sum(tally.values())
            if total > 0:
                second = sorted(tally.values(), reverse=True)[1] if len(tally) > 1 else 0
                if top == total:
                    vote_desc = f" The vote was unanimous ({total}–0)."
                else:
                    margin = "narrow" if top - second <= 1 else "clear"
                    vote_desc = f" The vote: {top} against {second} — a {margin} majority."

        if was_traitor:
            return (
                f"[ELIMINATION — SHAPESHIFTER UNMASKED] "
                f"The village votes to eliminate {character}, who IS the Shapeshifter!{vote_desc} "
                "Narrate the dramatic unmasking in 2–3 sentences — the terror turning to relief. "
                "Then call advance_phase to start a new night."
            )
        else:
            return (
                f"[ELIMINATION — INNOCENT VICTIM] "
                f"The village votes to eliminate {character} (role: {role}), who was innocent.{vote_desc} "
                "Narrate this tragic mistake in 2–3 sentences — the growing dread. "
                "Then call advance_phase to start a new night."
            )

    if event_type == "game_over":
        winner = data.get("winner", "unknown")
        reason = data.get("reason", "")
        if winner == "villagers":
            return (
                f"[GAME OVER — VILLAGERS WIN] {reason} "
                "Deliver a triumphant 3–4 sentence epilogue for Thornwood. "
                "Reveal every character's true nature."
            )
        else:
            return (
                f"[GAME OVER — SHAPESHIFTER WINS] {reason} "
                "Deliver a dark, haunting 3–4 sentence epilogue. "
                "Reveal how the Shapeshifter deceived the village to the end."
            )

    if event_type == "no_elimination":
        tally = data.get("tally", {})
        last_discussion = data.get("last_discussion", [])

        # Describe how close the deadlocked vote was
        vote_desc = ""
        if tally:
            top = max(tally.values(), default=0)
            total = sum(tally.values())
            if total > 0:
                second = sorted(tally.values(), reverse=True)[1] if len(tally) > 1 else 0
                vote_desc = f" The vote split {top} against {second} — no majority reached."

        context_block = ""
        if last_discussion:
            quoted = "\n".join(f"  {line}" for line in last_discussion)
            context_block = (
                f"\nArguments that went unresolved:\n{quoted}\n"
                "Reference the specific accusations that deadlocked the vote — "
                "the village is paralysed by its own distrust.\n"
            )
        return (
            f"[NO ELIMINATION — DEADLOCK] The villagers argued but could not reach a majority."
            f"{vote_desc} No one was cast out today.\n{context_block}"
            "Narrate the rising paranoia and suspicion (1–2 sentences), "
            "then call advance_phase to begin the night."
        )

    if event_type == "hunter_revenge":
        hunter = data.get("hunter", "the Hunter")
        target = data.get("target", "someone")
        return (
            f"[HUNTER REVENGE] The fallen {hunter} drags {target} down with them "
            "as their last act. Narrate this dramatic death in 1–2 sentences."
        )

    if event_type == "spectator_clue":
        from_char = data.get("from", "a fallen villager")
        word = data.get("word", "…")
        return (
            f"[SPECTATOR CLUE] The spirit of the fallen {from_char} stirs and whispers "
            f"one word: '{word}'. Deliver this in a single eerie sentence — "
            f"e.g. 'A cold wind stirs... the spirit of {from_char} seems to whisper \"{word}\"...' "
            "Do not explain or interpret the clue. Let it hang in the air."
        )

    if event_type == "hand_raised":
        character = data.get("character", "someone")
        queue = data.get("queue", [])
        queue_order = ", ".join(f"{i+1}. {name}" for i, name in enumerate(queue)) if queue else character
        queue_info = (
            f" Current speaker queue (in order): {queue_order}."
            if len(queue) > 1 else ""
        )
        return (
            f"[HAND_RAISED] {character} raises their hand to speak.{queue_info} "
            "Acknowledge them in queue order — call on the FIRST person in the queue. "
            f"Example: '{character} steps forward, the room falling quiet around them.'"
        )

    # Generic fallback
    return f"[{event_type.upper()}] {data}"


# Module-level singleton — imported by game_router and ws_router
narrator_manager = NarratorManager()

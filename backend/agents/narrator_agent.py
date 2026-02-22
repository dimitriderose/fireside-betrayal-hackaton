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
from models.game import Phase, Role
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
"""


# ── Tool declarations ──────────────────────────────────────────────────────────

def _make_tool_declarations():
    """Build FunctionDeclaration list for the Live API config."""
    try:
        from google.genai import types

        get_state = types.FunctionDeclaration(
            name="get_game_state",
            description=(
                "Returns the current game state: phase, round number, "
                "list of alive characters, AI character status, and the last 10 chat messages."
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

        return [get_state, advance, inject_traitor]
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

    return {
        "phase": game.phase.value,
        "round": game.round,
        "alive_characters": [p.character_name for p in alive_players],
        "ai_character": {
            "name": ai_char.name if ai_char else None,
            "alive": ai_char.alive if ai_char else False,
        },
        "recent_chat": [
            {"speaker": m.speaker, "text": m.text}
            for m in recent_chat
        ],
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
        await ws_manager.broadcast_phase_change(game_id, next_phase)
        logger.info(
            "[%s] Narrator advanced: %s → %s", game_id, game.phase.value, next_phase.value
        )

        result: Dict[str, Any] = {
            "result": "advanced",
            "new_phase": next_phase.value,
        }

        # When entering NIGHT: fire traitor night selection + inform narrator about role-players
        if next_phase == Phase.NIGHT:
            from agents.traitor_agent import trigger_night_selection
            asyncio.create_task(trigger_night_selection(game_id))

            game_after = await fs.get_game(game_id)
            result["round"] = game_after.round if game_after else game.round

            all_players = await fs.get_all_players(game_id)
            night_role_count = sum(
                1 for p in all_players
                if p.alive and p.role in {Role.SEER, Role.HEALER, Role.DRUNK}
            )
            result["night_role_players_count"] = night_role_count
            if night_role_count == 0:
                result["note"] = (
                    "No SEER/HEALER/DRUNK players are alive. "
                    "No night actions will be submitted. "
                    "Narrate a brief night scene, then call advance_phase again immediately."
                )

        # When entering DAY_VOTE: fire traitor vote selection
        elif next_phase == Phase.DAY_VOTE:
            from agents.traitor_agent import trigger_vote_selection
            asyncio.create_task(trigger_vote_selection(game_id))

        return result
    finally:
        _advancing_phase.discard(game_id)


async def handle_inject_traitor_dialog(game_id: str, context: str) -> Dict[str, Any]:
    """
    Generate an in-character spoken line from the AI Shapeshifter character
    and broadcast it as a transcript so text clients also see it.
    Returns {character_name, dialog} to the narrator for voicing.
    """
    from agents.traitor_agent import traitor_agent
    from routers.ws_router import manager as ws_manager

    result = await traitor_agent.generate_dialog(game_id, context)
    # Broadcast text transcript so text-only clients see the AI character's line
    await ws_manager.broadcast_transcript(
        game_id,
        speaker=result["character_name"],
        text=result["dialog"],
        source="ai_character",
    )
    logger.info(
        "[%s] inject_traitor_dialog: %s said: %.80s…",
        game_id, result["character_name"], result["dialog"],
    )
    return result


# ── Narrator Session ──────────────────────────────────────────────────────────

class NarratorSession:
    """
    Per-game Gemini Live API session.
    Maintains a background task that keeps the session open and streams
    PCM audio to all connected players via the WebSocket hub.
    Automatically reconnects on session timeout using the Live API session
    resumption handle so conversation context is preserved across reconnects.
    """

    def __init__(self, game_id: str):
        self.game_id = game_id
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
                            voice_name=settings.narrator_voice
                        )
                    )
                ),
                system_instruction=types.Content(
                    parts=[types.Part(text=NARRATOR_SYSTEM_PROMPT)]
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

                # PCM audio → broadcast to all players
                if response.data:
                    b64 = pcm_to_base64(response.data)
                    await ws_manager.broadcast_audio(self.game_id, b64)

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

        session = NarratorSession(game_id)
        self._sessions[game_id] = session
        await session.start()

        if initial_prompt:
            await session.send(initial_prompt)

        logger.info("[%s] Narrator manager: session started", game_id)

    async def forward_player_message(
        self, game_id: str, speaker: str, text: str, phase: str
    ) -> None:
        """Pass a player's chat line to the narrator during DAY_DISCUSSION."""
        session = self._sessions.get(game_id)
        if not session:
            return
        if phase == Phase.DAY_DISCUSSION.value:
            await session.send(f'[PLAYER] {speaker} says: "{text}"')

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
        """
        session = self._sessions.get(game_id)
        if not session:
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
        await session.send(prompt)
        logger.debug("[%s] Narrator event queued: %s", game_id, event_type)

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

    # Generic fallback
    return f"[{event_type.upper()}] {data}"


# Module-level singleton — imported by game_router and ws_router
narrator_manager = NarratorManager()

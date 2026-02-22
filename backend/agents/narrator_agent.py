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
from typing import Dict, Optional, Any

from config import settings
from services.firestore_service import get_firestore_service
from models.game import Phase, Role
from utils.audio import pcm_to_base64

logger = logging.getLogger(__name__)


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
   - Narrate the dawn: describe who was found dead or that everyone survived (2–3 sentences).
   - Then call advance_phase → moves to DAY_DISCUSSION.

3. DAY_DISCUSSION phase:
   - Briefly set the morning mood (1–2 sentences).
   - React to player dialogue with short atmospheric comments (1 sentence max).
   - When you judge that discussion has been sufficient, call advance_phase → moves to DAY_VOTE.

4. ELIMINATION signal received:
   - Dramatically narrate the elimination (2–3 sentences).
   - Reveal whether they were innocent or the Shapeshifter.
   - Then call advance_phase → moves to NIGHT (a new round begins).

5. GAME_OVER signal received:
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
                "Do NOT call during DAY_VOTE — those transitions are automatic."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={},
            ),
        )

        return [get_state, advance]
    except ImportError:
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
    If advancing to NIGHT with no role-players alive, auto-resolves night immediately.
    """
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

    # When entering a new NIGHT, check if anyone has night actions
    if next_phase == Phase.NIGHT:
        all_players = await fs.get_all_players(game_id)
        night_role_players = [
            p for p in all_players
            if p.alive and p.role in {Role.SEER, Role.HEALER, Role.DRUNK}
        ]
        if not night_role_players:
            # No role-players alive — auto-resolve night without waiting
            night_result = await game_master.resolve_night(game_id)
            result["auto_resolved_night"] = True
            result["night_killed"] = night_result.get("killed")

            if night_result.get("killed"):
                win = await game_master.check_win_condition(game_id)
                if win:
                    from routers.ws_router import _end_game
                    await _end_game(game_id, win["winner"], win["reason"], fs)
                    return {**result, "game_over": True, "winner": win["winner"]}

        game_after = await fs.get_game(game_id)
        result["round"] = game_after.round if game_after else game.round

    return result


# ── Narrator Session ──────────────────────────────────────────────────────────

class NarratorSession:
    """
    Per-game Gemini Live API session.
    Maintains a background task that keeps the session open and streams
    PCM audio to all connected players via the WebSocket hub.
    """

    def __init__(self, game_id: str):
        self.game_id = game_id
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(
            self._session_loop(), name=f"narrator-{self.game_id}"
        )

    async def stop(self) -> None:
        self._running = False
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

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
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

        try:
            async with client.aio.live.connect(
                model=settings.narrator_model, config=config
            ) as session:
                logger.info("[%s] Narrator Live API session connected", self.game_id)

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
                    for t in done:
                        if not t.cancelled() and t.exception():
                            raise t.exception()
                except asyncio.CancelledError:
                    sender.cancel()
                    receiver.cancel()
                    raise

        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("[%s] Narrator session error", self.game_id)

    async def _sender(self, session) -> None:
        """Drain the queue and forward text prompts to the Live API session."""
        while self._running:
            try:
                text = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            try:
                await session.send(input=text, end_of_turn=True)
                self._queue.task_done()
                logger.debug("[%s] Narrator ← %.80s…", self.game_id, text)
            except Exception as exc:
                logger.warning("[%s] Narrator send error: %s", self.game_id, exc)

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
            pass
        except Exception:
            logger.exception("[%s] Narrator receiver error", self.game_id)

    async def _handle_tool_call(self, session, tool_call, types) -> None:
        """Execute the model's tool calls and send responses back."""
        fn_responses = []
        for fc in tool_call.function_calls:
            try:
                if fc.name == "get_game_state":
                    result = await handle_get_game_state(self.game_id)
                elif fc.name == "advance_phase":
                    result = await handle_advance_phase(self.game_id)
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
        """Send a structured game event prompt to the narrator session."""
        session = self._sessions.get(game_id)
        if not session:
            return
        prompt = _build_phase_prompt(event_type, data or {})
        await session.send(prompt)
        logger.debug("[%s] Narrator event queued: %s", game_id, event_type)

    async def stop_game(self, game_id: str) -> None:
        """Stop and clean up the narrator session for a finished game."""
        session = self._sessions.pop(game_id, None)
        if session:
            await session.stop()
            logger.info("[%s] Narrator manager: session stopped", game_id)


# ── Phase prompt builder ──────────────────────────────────────────────────────

def _build_phase_prompt(event_type: str, data: Dict[str, Any]) -> str:
    """Convert a game event into a structured narrator prompt."""
    round_num = data.get("round", 1)

    if event_type == "game_started":
        cast_str = ", ".join(data.get("character_cast", [])) or "the villagers"
        return (
            f"[GAME START — NIGHT PHASE — Round 1] "
            f"The characters of Thornwood tonight are: {cast_str}. "
            "Open the game with a foreboding 2–3 sentence monologue that establishes "
            "the dark, tense atmosphere of the village. "
            "Then call get_game_state to confirm who is present."
        )

    if event_type == "night_resolved":
        killed = data.get("eliminated") or data.get("killed")
        protected = data.get("protected")
        if killed:
            return (
                f"[NIGHT RESOLVED] {killed} was found dead at dawn. "
                "Narrate this grim discovery (2–3 sentences). "
                "Then call advance_phase to begin the day."
            )
        else:
            note = f" The Healer secretly protected {protected}." if protected else ""
            return (
                f"[NIGHT RESOLVED] No one was killed tonight.{note} "
                "Narrate the eerie, unsettling dawn where everyone survived. "
                "Then call advance_phase to begin the day."
            )

    if event_type == "elimination":
        character = data.get("character", "Unknown")
        was_traitor = data.get("was_traitor", False)
        role = data.get("role", "villager")
        if was_traitor:
            return (
                f"[ELIMINATION — SHAPESHIFTER UNMASKED] "
                f"The village votes to eliminate {character}, who IS the Shapeshifter! "
                "Narrate the dramatic unmasking in 2–3 sentences — the terror turning to relief. "
                "Then call advance_phase to start a new night."
            )
        else:
            return (
                f"[ELIMINATION — INNOCENT VICTIM] "
                f"The village votes to eliminate {character} (role: {role}), who was innocent. "
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

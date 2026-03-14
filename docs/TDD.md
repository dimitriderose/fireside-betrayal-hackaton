# Technical Design Document
## Fireside — Betrayal

**Category:** 🗣️ Live Agents
**Author:** Software Architecture Team
**Companion Document:** PRD — Fireside — Betrayal v1.0
**Version:** 5.2 | March 14, 2026 *(updated to reflect: Ghost Council dead-player chat system, Séance phase, haunt actions, concurrency guards for night resolution, AI auto-reply system, discussion timer enforcement, simplified win condition (parity), responsive roster panel, phase change data sync improvements, SPA catch-all routing, audio WebSocket reconnection architecture with separated mic/WS lifecycles, Page Visibility API integration for mobile tab-switch resilience, vote tally data flow with individual vote capture, production WebSocket keep-alive tuning, scene image prompt optimization for smaller file sizes, Gemini Live API log cleanup)*

---

# 1. Overview

This Technical Design Document specifies the implementation architecture for Fireside — Betrayal, a real-time voice-first multiplayer social deduction game powered by the Gemini Live API, Google ADK, and Google Cloud. It translates the PRD's product requirements into concrete engineering decisions, API contracts, data models, code structure, and deployment specifications.

**Scope:** All P0, P1, and P2 features from the PRD are now implemented, plus additional live-play enhancements. This includes the core game loop (P0), session resumption, Hunter/Drunk roles, difficulty levels, quick reactions, post-game timeline (P1), and all 18 P2 features: procedural characters, narrator presets, random AI alignment, Bodyguard/Tanner roles, camera voting, scene images, tutorial mode, audio recording, competitor intelligence, and more. Post-P2 additions include: player voice input pipeline (AudioWorklet mic capture through Gemini), speaker identification annotations, dynamic discussion timers scaled to alive player count, narrator dual-mode engagement (theatrical narration + fast-paced discussion moderator), human shapeshifter night kill (via Random AI Alignment), multi-stage Dockerfile, Terraform IaC for Google Cloud Run, and a deployment guide. **v4.0 additions:** Unified multi-AI architecture — `TraitorAgent`/`LoyalAgent` classes replaced with standalone functions (`generate_dialog`, `select_night_target`, `select_vote`, `select_loyal_night_action`) and parallel trigger functions (`trigger_all_night_actions`, `trigger_all_votes`, `trigger_all_dialogs`) using `asyncio.gather()`. N-AI character support via `ai_characters[]` array in Firestore and frontend `GameContext`. AI bodyguard sacrifice handling, AI Seer investigation computation, polling vote wait loop, and `{fs_field}_night_{role}` event naming pattern. **v5.1 additions:** Ghost Council dead-player chat system (`ghost_message` WS type, GhostRealmPanel), Séance phase (conditional ghost testimony when dead >= 2 and dead >= total/2), haunt actions (dead player night accusations), concurrency guards (`_resolving_nights` set, alive check in resolve_night), AI auto-reply system (`_maybe_trigger_ai_reply` with name-match regex and 30s cooldown), discussion timer enforcement (rejects advance_phase without start_phase_timer), simplified win condition (parity: non_shapeshifter_alive <= 1), responsive roster architecture (RosterPanel with RosterSidebar/RosterIconStrip at 768px breakpoint), and phase change data sync (full roster + AI chars in phase_change messages). **v5.2 additions:** SPA catch-all routing (`SPAStaticFiles` subclass serves `index.html` for non-API/non-WS 404s, enabling React Router deep links in production), audio WebSocket reconnection architecture (mic stream lifecycle separated from WS lifecycle — MediaStream/AudioContext/AudioWorkletNode persist across WS reconnects; exponential backoff [500,1000,2000,4000,8000]ms with max 10 attempts; Page Visibility API proactive disconnect/reconnect), game WebSocket mobile resilience (CONNECTING state guard, Page Visibility API immediate reconnect on tab visible, 2s sync heartbeat with phase mismatch detection), vote tally data flow (individual votes captured before `tally_votes()` clears AI voted_for, `broadcast_elimination` includes `individualVotes` and `isTie`, new `VoteTallyOverlay` component), production WebSocket keep-alive tuning (`--ws-ping-interval=15 --ws-ping-timeout=20` in Dockerfile CMD), scene image prompt optimization (flat vector illustration with 5-6 color palette replacing dark painterly style for smaller file sizes), and Gemini Live API log cleanup (proper `continue` for `session_resumption_update`/`voice_activity` handlers, NON-STANDARD log demoted to `logger.debug`).

**Out of scope:** Multiple story genres (P3), persistent player profiles (P3), cross-device shared screen mode (P3). P3 features are additive and do not affect core architecture.

> **Implementation Note:** The original TDD (v1.0) was a pre-implementation design spec. The code snippets below represent the *design intent* — the actual implementation in the codebase may differ in details (function signatures, error handling, etc.) while preserving the architectural decisions. Key deviations from the original design are called out with "**Implementation Update**" annotations.

---

# 2. System Architecture

## 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       PLAYER DEVICES (2–7)                      │
│                                                                 │
│   Phone A          Phone B          Phone C         Phone N     │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐                  │
│   │React PWA │    │React PWA │    │React PWA │     ...          │
│   │WebSocket │    │WebSocket │    │WebSocket │                  │
│   │+ Audio   │    │+ Audio   │    │+ Audio   │                  │
│   └────┬─────┘    └────┬─────┘    └────┬─────┘                  │
│        │               │               │                        │
│        └───────────────┼───────────────┘                        │
│                        │ wss://.../ws/{gameId}  (game state)    │
│                        │ wss://.../ws/audio/{gameId}  (mic PCM) │
└────────────────────────┼────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLOUD RUN (us-central1)                       │
│                    Container: fireside-backend                   │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                 FastAPI Application Server                 │  │
│  │                                                           │  │
│  │  /api/games              POST → Create game + register host   │  │
│  │  /api/games/{id}/join   POST → Join lobby                   │  │
│  │  /api/games/{id}        GET  → Public game state            │  │
│  │  /api/games/{id}/start  POST → Start game (host only)       │  │
│  │  /api/games/{id}/events GET  → Event log (gated post-game)  │  │
│  │  /api/games/{id}/result GET  → Post-game result + reveals   │  │
│  │  /api/narrator/preview/{p} GET → Narrator audio sample      │  │
│  │  /ws/{gameId}           WS   → Player game-state connection  │  │
│  │  /ws/audio/{gameId}     WS   → Dedicated mic audio stream   │  │
│  │  /health                GET  → Health check                 │  │
│  └──────────────┬────────────────────────────────────────────┘  │
│                 │                                                │
│  ┌──────────────▼────────────────────────────────────────────┐  │
│  │              ADK Agent Orchestrator                        │  │
│  │                                                           │  │
│  │   ┌─────────────────┐  ┌─────────────────┐               │  │
│  │   │ Narrator Agent  │  │ AI Agent Fns    │               │  │
│  │   │ (LlmAgent)      │  │ (standalone)     │               │  │
│  │   │                 │  │                  │               │  │
│  │   │ Model: gemini-  │  │ Model: gemini-   │               │  │
│  │   │ 2.5-flash-      │  │ 2.5-flash        │               │  │
│  │   │ native-audio-   │  │ (text-only)      │               │  │
│  │   │ preview-12-2025 │  │                  │               │  │
│  │   │                 │  │ Functions:       │               │  │
│  │   │ Voice: Charon   │  │ generate_dialog  │               │  │
│  │   │ Affective: ON   │  │ select_night_tgt │               │  │
│  │   │                 │  │ select_vote      │               │  │
│  │   │ Tools:          │  │ select_loyal_ngt │               │  │
│  │   │ get_game_state  │  │                  │               │  │
│  │   │ advance_phase   │  │ Triggers:        │               │  │
│  │   │ narrate_event   │  │ trigger_all_     │               │  │
│  │   │ inject_traitor  │  │  night_actions   │               │  │
│  │   │ gen_vote_context│  │  votes / dialogs │               │  │
│  │   └─────────────────┘  └─────────────────┘               │  │
│  │                        ┌─────────────────┐               │  │
│  │   ┌─────────────────┐  │Game Master Agent│               │  │
│  │   │ Additional       │  │(Custom Agent)   │               │  │
│  │   │ Agents:          │  │                  │               │  │
│  │   │ scene_agent      │  │ Deterministic:   │               │  │
│  │   │ camera_vote      │  │ assign_roles     │               │  │
│  │   │ audio_recorder   │  │ tally_votes      │               │  │
│  │   │ strategy_logger  │  │ eliminate_char   │               │  │
│  │   │ role_assigner    │  │ check_win        │               │  │
│  │   └─────────────────┘  │ resolve_night    │               │  │
│  │                        └─────────────────┘               │  │
│  └──────────────┬────────────────────────────────────────────┘  │
│                 │                                                │
│  ┌──────────────▼────────────────────────────────────────────┐  │
│  │         Gemini Live API (WebSocket)                        │  │
│  │         Model: gemini-2.5-flash-native-audio-latest           │  │
│  │         Session resumption: ENABLED                        │  │
│  │         Context compression: REMOVED                       │  │
│  │         Response modality: AUDIO                           │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────┬──────────────────────────────┬───────────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────┐  ┌──────────────────────────────────┐
│    Cloud Firestore       │  │       Cloud Storage               │
│    (us-east1)            │  │       (us-east1)                  │
│                          │  │                                   │
│  games/{gameId}/         │  │  gs://fireside-assets-2026/       │
│    status, phase, round  │  │    scene-images/                  │
│    ai_characters[]       │  │    audio-clips/                   │
│    players/{playerId}/   │  │                                   │
│    events/{eventId}/     │  │                                   │
└──────────────────────────┘  └──────────────────────────────────┘
```

## 2.2 Key Architectural Decisions

**Decision 1: Hub Model (Single Narrator Session)**
The server maintains ONE Gemini Live API session per game. Players do NOT have individual Live API sessions. Player input arrives as text (typed or browser speech-to-text), is attributed ("Alex says: I think the blacksmith is suspicious"), and injected into the narrator's context. The narrator's audio output is broadcast to all connected player WebSockets simultaneously.

Rationale: Concurrent session limits (3–50 per project) make per-player sessions infeasible. The hub model uses exactly 1 session per active game regardless of player count.

**Decision 2: Firestore as Source of Truth**
All authoritative game state (roles, votes, alive/dead, phase, round) lives in Firestore, not in the Live API session memory. The Live API session contains narrative context only. On session reconnection, game state is re-injected from Firestore into the new session prompt.

Rationale: Live API sessions are ephemeral (~10 min connections). Firestore survives disconnections, server restarts, and Cloud Run cold starts.

**Decision 3: Unified AI Agent as Standalone Functions (v4.0)**
The original `TraitorAgent` class and `LoyalAgent` class have been replaced with unified standalone functions in `backend/agents/traitor_agent.py`. A single `generate_dialog(game_id, ai_char, context)` function routes to traitor or loyal prompts based on the character's `is_traitor` flag. Night actions (`select_night_target`, `select_loyal_night_action`), votes (`select_vote`), and dialog are all stateless functions that take `(game_id, ai_char, fs_field)` parameters. Three trigger functions (`trigger_all_night_actions`, `trigger_all_votes`, `trigger_all_dialogs`) use `asyncio.gather()` to run all AI characters in parallel.

Rationale: Class-based agents accumulated state and required separate code paths for traitor vs. loyal AI. Standalone functions are stateless, composable, and naturally support N AI characters. The `_ai_chars_with_fields(game)` helper iterates all AI characters with their Firestore field names, making loops trivial. Running a second Live API audio session per AI is still avoided — all AI dialog is injected into the Narrator's context for vocal delivery.

**Decision 4: Game Master as Custom Agent (Not LLM)**
The Game Master is a deterministic Python class extending `BaseAgent`, not an LLM agent. It enforces rules, manages phase transitions, counts votes, and checks win conditions using pure logic.

Rationale: Game rules must be deterministic and correct. LLM agents can hallucinate rule violations. Phase transitions, vote counting, and win conditions are computational, not generative.

**Decision 5: Separate Audio WebSocket (`/ws/audio/{game_id}`)**
Microphone audio is transmitted over a dedicated binary WebSocket endpoint (`/ws/audio/{game_id}`) that is entirely separate from the game-state WebSocket (`/ws/{game_id}`). The audio WS sends raw binary PCM frames — no JSON wrapper, no base64 encoding. `useAudioCapture.js` connects to this endpoint independently; it auto-cleans up if the audio WS drops mid-capture without affecting game state.

Rationale: Mixing high-volume binary audio frames with JSON game-state messages on a single WebSocket caused intermittent code 1006 disconnections. The combined traffic also inflated JSON message size by ~33% due to base64 encoding. Splitting the channels isolates failure domains: a dropped audio connection no longer tears down game state, and the binary transport eliminates encoding overhead.

**Implementation Update (v5.2):** The audio WS lifecycle is now fully decoupled from the microphone lifecycle. The mic stream (MediaStream, AudioContext, AudioWorkletNode) stays alive across WS reconnects — only the WebSocket connection is torn down and re-established. This prevents the costly re-initialization of the Web Audio pipeline on every reconnect. The audio WS has exponential backoff reconnection (delays: 500, 1000, 2000, 4000, 8000ms; max 10 attempts) and Page Visibility API integration (proactive WS close on page hidden, reconnect + AudioContext resume on page visible). A `connectingRef` guard prevents the visibility handler from orphaning `startCapture`'s pending connection promise.

**Decision 8: SPA Catch-All Routing (v5.2)**
The backend serves a React SPA via an `SPAStaticFiles` subclass of Starlette's `StaticFiles`. When a request path does not match any static file (404), the subclass catches the exception and serves `index.html` instead. This enables React Router client-side routing in production — deep links like `/join/C1E7F362` resolve correctly without a separate reverse proxy.

Rationale: API routes (`/api/*`) and WebSocket routes (`/ws/*`) are registered on the FastAPI app before the static file mount. FastAPI evaluates routes in registration order, so API and WS paths take priority over the catch-all. This avoids the need for a separate Nginx or Caddy layer in the single-container Cloud Run deployment.

**Decision 6: Push-to-Talk Speaker Lock**
The server maintains a per-game speaker lock (`_current_speaker: Dict[str, Optional[str]]`) so only one player can hold the mic at a time. The lock is claimed immediately on `start_speaking` before any async validation (TOCTOU-safe). A 30-second `asyncio.Task` (`_speaker_timeout_tasks`) auto-releases the lock if the player forgets to release it. Dead players receive an error response and cannot claim the lock. The lock is also released on: `stop_speaking`, game WS disconnect, audio WS disconnect, phase transition, and game end.

Rationale: Gemini Live API's speaker identification degrades when concurrent audio streams overlap. The lock ensures clean speaker attribution and prevents audio collision artifacts.

**Decision 7: Per-Player Priority Queues in ConnectionManager**
Each connected player has two outbound queues: a control queue (unbounded, for JSON game-state messages) and an audio queue (bounded 256 frames, for narrator PCM chunks). A dedicated `_player_sender` coroutine per connection drains the control queue first, then pulls from the audio queue, ensuring phase-change and elimination messages are never delayed behind a flood of audio chunks. Chat messages sent by a player appear instantly on their own screen (local echo) with server-echo deduplication to prevent double-display.

Rationale: Under load, narrator audio chunks can fill a single shared queue and delay critical game-state messages (votes, phase changes). Priority separation guarantees control-plane latency regardless of audio volume.

---

# 3. Agent Specifications

## 3.1 Narrator Agent

```python
from google.adk.agents import Agent

narrator_agent = Agent(
    name="fireside_narrator",
    model="gemini-2.5-flash-native-audio-latest",
    description="AI game master and narrator for Fireside — Betrayal",
    instruction="""You are the narrator of Fireside — Betrayal, a social deduction 
    storytelling game set in the village of Thornwood. 
    
    YOUR RESPONSIBILITIES:
    1. Narrate the story with dramatic flair, building tension and atmosphere
    2. Voice different NPCs with distinct personalities
    3. When the Traitor character speaks, deliver their lines as that character
    4. React to player interruptions naturally — this is a conversation, not a monologue
    5. Announce game events (night actions, votes, eliminations) dramatically
    6. NEVER reveal which character is the AI's shapeshifter
    7. Use the get_game_state tool before narrating to ensure accuracy
    8. Use advance_phase when a phase should transition
    9. Use inject_traitor_dialog to get the AI character's response during discussions
    10. Use start_phase_timer AFTER finishing your narration for a phase — this begins the
        player countdown. Do NOT call it in the middle of narration.
    
    VOICE DIRECTION:
    - Night phase: whispered, ominous, slow pacing
    - Day discussion: energetic, reactive, conversational
    - Voting: tense, countdown-style urgency
    - Elimination: dramatic reveal, emotional weight
    - Story exposition: rich, immersive, fantasy novel narration
    
    INTERRUPTION HANDLING:
    When a player interrupts, acknowledge them naturally as part of the story.
    Example: If a player interrupts during narration with "Wait, I saw something!", 
    respond in character: "The herbalist pauses... Merchant Elara, you have something 
    to share with the village?"
    
    QUICK REACTION HANDLING (P1):
    When a player sends a QUICK_REACTION, do NOT read it as a flat announcement.
    Weave it into the narrative as a character moment:
    - "I suspect [X]" → dramatic accusation: "Elara's eyes narrow as she turns 
      toward the forge. 'Something about the Blacksmith doesn't sit right with me,' 
      she says, her voice carrying an edge."
    - "I trust [X]" → moment of alliance: "Brother Aldric places a steady hand on 
      Mira's shoulder. 'I believe her,' he says firmly."
    - "I agree with [X]" → solidarity: "Scholar Theron nods slowly. 'Elara makes 
      a fair point,' he admits."
    - "I have information" → dramatic pause, then invite: "Herbalist Mira steps 
      forward, her expression grave. The village falls silent. 'Speak, Mira. What 
      do you know?'"
    Quick reactions are STORY BEATS, not chat messages. Treat them with the same 
    dramatic weight as typed messages.
    
    CHARACTER NAME RULES:
    - ALWAYS use character names, NEVER real player names during gameplay
    - Address players by their character identity: "Blacksmith Garin," not "Jake"
    - The AI's character is indistinguishable from human characters in your narration
    
    CONTEXTUAL REACTIVITY (P1):
    When transitioning between phases (especially night→day), ALWAYS reference key 
    events from the previous round in your scene description. Never deliver generic 
    transitions like "A new day begins in Thornwood."
    Instead, use get_game_state to retrieve the previous round's events and weave them in:
    - After a close vote: "Dawn breaks, but the suspicion from last night lingers 
      like woodsmoke — Elara's accusation hangs unresolved."
    - After an elimination: "The village wakes to one fewer voice. The empty chair 
      where Garin sat is a wound no one dares acknowledge."
    - After a heated debate: "Sleep came uneasily. Theron's words echo in every mind: 
      'One of us is lying.' The question is who."
    
    QUIET-PLAYER ENGAGEMENT (P1):
    Track which characters have NOT spoken during the current day discussion. After 
    60 seconds of silence from a player, gently prompt them by character name with a 
    narrative hook — NOT a generic "does anyone have something to share?"
    Good: "Elena, you've been watching the Blacksmith closely — does anything seem off?"
    Good: "Brother Aldric, you've been quiet since last night. The village would hear 
    your thoughts."
    Bad: "Does anyone else want to speak?"
    Limit to ONE prompt per silent player per round to avoid pestering.
    
    RULE VIOLATION HANDLING (P0):
    If a player sends a message during the night phase (when chat should be disabled):
    - Do NOT crash, ignore, or break the game flow
    - Redirect narratively: "The spirits remind you that night is a time for silence. 
      The guilty will reveal themselves come morning."
    - Do NOT process the message as game input
    If a player tries to reveal their role in chat ("I'm the Seer!"):
    - The narrator can acknowledge it in-story but does not confirm or deny: 
      "Bold words from Mira. But words in Thornwood are cheap."
    """,
    tools=[get_game_state, advance_phase, narrate_event, inject_traitor_dialog, start_phase_timer],
    sub_agents=[traitor_agent],
)
```

**Voice Configuration:**
```python
from google.genai import types

live_config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name="Charon"  # Deep, dramatic
            )
        )
    ),
    session_resumption=types.SessionResumptionConfig(
        handle=previous_session_handle  # None for new game
    ),
    # context_window_compression removed — caused session instability
    # Keepalive re-enabled: 20s ping interval, 30s timeout
    # (previously disabled; re-enabling fixed silent code 1006 drops)
)
```

**Audio Specifications:**
- Player mic input: 16-bit PCM, 16 kHz, mono — transported as raw binary frames over `/ws/audio/{game_id}` (no base64, no JSON wrapper)
- Narrator output: 24 kHz PCM audio (broadcast over game-state WS as base64 JSON `audio` message)
- Latency target: 200–500ms (native audio model's natural latency). P0 hard requirement: < 2 seconds end-to-end from player message to first narrator audio chunk.
- VAD: Enabled (automatic interruption detection)
- Thinking: Enabled with budget of 1024 tokens
- WebSocket keepalive: ping interval 20s, timeout 30s (re-enabled in v5.0)

## 3.2 AI Agent Functions (Unified — v4.0)

**Implementation Update (v4.0):** The `TraitorAgent` class and `LoyalAgent` class have been replaced with unified standalone functions in `backend/agents/traitor_agent.py`. There are no more class instances or agent-level state. Each function receives the game ID, the AI character dict, and its Firestore field name (`fs_field`), then makes a single Gemini LLM call and writes the result to Firestore.

```python
# backend/agents/traitor_agent.py — Unified AI agent functions (v4.0)

# --- Helper ---
def _ai_chars_with_fields(game: dict) -> list[tuple[dict, str]]:
    """Return [(ai_char_dict, firestore_field_name), ...] for all AI characters.
    Example: [({"name": "Tinker Orin", "role": "shapeshifter", ...}, "ai_character"), ...]
    Supports N AI characters via the ai_characters[] array.
    """
    ...

# --- Core functions (one LLM call each) ---

async def generate_dialog(game_id: str, ai_char: dict, context: str) -> str:
    """Generate dialog for one AI character. Routes prompt by is_traitor flag:
    - Traitor: uses TRAITOR_DIFFICULTY prompts + strategic framework
    - Loyal: uses cooperative LOYAL_AI_PROMPT with honest observation style
    Returns the dialog text string.
    """
    ...

async def select_night_target(game_id: str, ai_char: dict, fs_field: str) -> str:
    """Shapeshifter night kill selection. Only called for AI characters with
    is_traitor=True. Writes the chosen target to Firestore under
    {fs_field}_night_kill event. Returns target character name.
    """
    ...

async def select_vote(game_id: str, ai_char: dict, fs_field: str) -> str:
    """Vote selection for any AI character. Includes self-vote guard
    (AI cannot vote for itself). Writes vote to Firestore.
    Returns voted-for character name.
    """
    ...

async def select_loyal_night_action(game_id: str, ai_char: dict, fs_field: str) -> str:
    """Night action for loyal AI characters based on their role:
    - Seer: investigate a player → writes {fs_field}_night_seer event
    - Healer: protect a player → writes {fs_field}_night_heal event
    - Bodyguard: guard a player → writes {fs_field}_night_bodyguard event
    - Villager/other: no action (returns early)
    Returns target character name or None.
    """
    ...

# --- Trigger functions (asyncio.gather for parallelism) ---

async def trigger_all_night_actions(game_id: str):
    """Run all AI night actions in parallel via asyncio.gather().
    Routes each AI character to select_night_target (if traitor)
    or select_loyal_night_action (if loyal) based on is_traitor flag.
    """
    ...

async def trigger_all_votes(game_id: str):
    """Run all AI vote selections in parallel via asyncio.gather().
    Each AI character calls select_vote() concurrently.
    """
    ...

async def trigger_all_dialogs(game_id: str, context: str):
    """Run all AI dialog generations in parallel via asyncio.gather().
    Each AI character calls generate_dialog() concurrently.
    Returns list of (ai_char, dialog_text) tuples.
    """
    ...
```

**Difficulty Selection:** Host selects difficulty at game creation (`POST /api/games` body includes `difficulty: "easy" | "normal" | "hard"`). The appropriate `TRAITOR_DIFFICULTY` fragment is interpolated into the prompt within `generate_dialog()`. Temperature also adjusts: easy=0.9, normal=0.7, hard=0.5.

**Integration with Narrator:** The Narrator calls `inject_traitor_dialog` which now calls `trigger_all_dialogs(game_id, context)` internally. This loops all AI characters via `_ai_chars_with_fields()`, generates dialog for each in parallel, and injects all responses into the Narrator's context for vocal delivery. The old `_inject_ai2_dialog()` function has been deleted.

**Event Type Pattern (v4.0):** AI night events use the `{fs_field}_night_{role}` naming pattern. For example, `ai_character_night_kill`, `ai_character_2_night_heal`, `ai_character_2_night_seer`. A new `ai_seer_result` event type communicates AI Seer investigation results to the game state.

## 3.3 Game Master Agent (Deterministic)

```python
from google.adk.agents import BaseAgent
from enum import Enum

class GamePhase(Enum):
    SETUP = "setup"
    NIGHT = "night"
    DAY_DISCUSSION = "day_discussion"
    DAY_VOTE = "day_vote"
    ELIMINATION = "elimination"
    SEANCE = "seance"          # v5.1: Ghost testimony phase
    GAME_OVER = "game_over"

class GameMasterAgent(BaseAgent):
    """Deterministic game logic engine. No LLM calls."""

    PHASE_TRANSITIONS = {
        GamePhase.SETUP: GamePhase.NIGHT,
        GamePhase.NIGHT: GamePhase.DAY_DISCUSSION,
        GamePhase.DAY_DISCUSSION: GamePhase.DAY_VOTE,
        GamePhase.DAY_VOTE: GamePhase.ELIMINATION,
        GamePhase.ELIMINATION: GamePhase.NIGHT,  # or GAME_OVER or SEANCE
        # v5.1: Séance triggers conditionally from ELIMINATION when
        # dead_count >= 2 AND dead_count >= total_players / 2.
        # After séance completes, transitions to NIGHT.
        GamePhase.SEANCE: GamePhase.NIGHT,
    }
    
    # **Implementation Update:** Role distribution is a list-based format keyed by
    # total character count (humans + 1 AI). Includes Bodyguard (7+) and Tanner (8).
    # **Implementation Update (v4.0):** ROLE_DISTRIBUTION[3] removed — minimum
    # game size is now 4 characters (enforced by lobby min-player check).
    ROLE_DISTRIBUTION = {
        4: ["villager", "villager", "seer", "shapeshifter"],
        5: ["villager", "villager", "seer", "healer", "shapeshifter"],
        6: ["villager", "villager", "seer", "healer", "hunter", "shapeshifter"],
        7: ["villager", "villager", "seer", "healer", "hunter", "bodyguard", "shapeshifter"],
        8: ["villager", "villager", "seer", "healer", "hunter", "bodyguard", "tanner", "shapeshifter"],
    }
    
    # Lobby display: communicate role distribution to host before game start.
    # Format: "In this game: 2 special roles, 3 villagers, 1 AI among you."
    # Helps new players set expectations (board game organizer feedback).
    def get_lobby_summary(self, n: int, difficulty: str) -> str:
        dist = self.get_distribution(n, difficulty)
        specials = sum(v for k, v in dist.items() if k not in ("villager",))
        villagers = dist.get("villager", 0)
        return f"In this game: {specials} special role{'s' if specials != 1 else ''}, {villagers} villager{'s' if villagers != 1 else ''}, 1 AI hidden among you."
    
    # P1: Difficulty-gated Drunk role.
    # Easy mode NEVER includes Drunk (new players would feel punished by false info).
    # Normal mode: Drunk available at 6+ players.
    # Hard mode: Drunk replaces one Villager at 5+ players.
    ROLE_DISTRIBUTION_WITH_DRUNK = {
        5: {"villager": 1, "seer": 1, "healer": 1, "hunter": 0, "drunk": 1},
        6: {"villager": 1, "seer": 1, "healer": 1, "hunter": 1, "drunk": 1},
    }
    
    def get_distribution(self, n: int, difficulty: str) -> dict:
        """Select role distribution based on player count and difficulty."""
        if difficulty == "hard" and n >= 5:
            return self.ROLE_DISTRIBUTION_WITH_DRUNK.get(n, self.ROLE_DISTRIBUTION_WITH_DRUNK[6])
        elif difficulty == "normal" and n >= 6:
            return self.ROLE_DISTRIBUTION_WITH_DRUNK.get(n, self.ROLE_DISTRIBUTION[6])
        else:
            return self.ROLE_DISTRIBUTION.get(n, self.ROLE_DISTRIBUTION[6])
    
    # Story character cast — every player (AND the AI) gets one of these names.
    # Character names are the ONLY identifiers visible during gameplay.
    # Real player names are hidden to prevent identifying the AI by name format.
    CHARACTER_CAST = [
        {"name": "Blacksmith Garin", "intro": "The broad-shouldered smith hammers at his forge, sparks dancing in the dark."},
        {"name": "Merchant Elara", "intro": "The traveling merchant counts her coins by candlelight, eyes darting to the door."},
        {"name": "Scholar Theron", "intro": "The old scholar peers at ancient texts, muttering about omens in the stars."},
        {"name": "Herbalist Mira", "intro": "The herbalist tends her garden of strange flowers, humming a melody no one recognizes."},
        {"name": "Brother Aldric", "intro": "The chapel keeper lights the evening candles, his prayers a whisper against the wind."},
        {"name": "Innkeeper Bram", "intro": "The innkeeper pours ale with a steady hand, but his eyes follow everyone who enters."},
        {"name": "Huntress Reva", "intro": "The huntress sharpens her arrows by firelight, her wolf-hound growling at shadows."},
    ]
    
    async def assign_roles(self, game_id: str, player_ids: list[str], 
                            difficulty: str = "normal") -> dict:
        """Assign roles AND character identities. AI also gets a character from the same cast."""
        n = len(player_ids)
        distribution = self.get_distribution(n, difficulty)
        roles = []
        for role, count in distribution.items():
            roles.extend([role] * count)
        random.shuffle(roles)
        
        # Shuffle character cast and assign to ALL participants (players + AI)
        cast = random.sample(self.CHARACTER_CAST, n + 1)  # n players + 1 AI
        
        assignments = {}
        for i, (pid, role) in enumerate(zip(player_ids, roles)):
            character = cast[i]
            assignments[pid] = {
                "role": role,
                "character_name": character["name"],
                "character_intro": character["intro"],
            }
            await firestore_client.update_player(game_id, pid, {
                "role": role,
                "character_name": character["name"],
                "character_intro": character["intro"],
            })
        
        # **Implementation Update (v4.0):** AI characters stored as ai_characters[] array.
        # Multiple AI characters supported; each gets a role from the pool.
        ai_characters = []
        for ai_idx in range(num_ai):
            ai_character = cast[n + ai_idx]
            ai_characters.append({
                "name": ai_character["name"],
                "intro": ai_character["intro"],
                "role": ai_roles[ai_idx],  # Any role via random alignment
                "alive": True,
                "is_traitor": ai_roles[ai_idx] == "shapeshifter",
            })
        await firestore_client.set_ai_characters(game_id, ai_characters)
        
        return {
            "player_assignments": assignments,
            "ai_character": ai_character["name"],
            "full_cast": [c["name"] for c in cast],  # All character names for narrator intro
        }
    
    async def tally_votes(self, game_id: str) -> dict:
        """Tally votes. Simple plurality. Ties → no elimination.

        **Implementation Update (v4.0):** Renamed from count_votes(). Now includes
        AI votes (submitted via trigger_all_votes). Unified loop counts both human
        and AI character votes in a single tally pass.
        """
        votes = await firestore_client.get_votes(game_id)  # includes AI votes
        tally = Counter(v for v in votes.values() if v is not None)

        if not tally:
            return {"result": "no_votes", "eliminated": None}

        max_votes = max(tally.values())
        candidates = [p for p, v in tally.items() if v == max_votes]

        if len(candidates) > 1:
            return {"result": "tie", "eliminated": None, "tied": candidates}

        return {"result": "eliminated", "eliminated": candidates[0], "votes": max_votes}

    async def eliminate_character(self, game_id: str, character_name: str) -> dict:
        """Eliminate a character (human or AI). Checks AI characters array.

        **Implementation Update (v4.0):** Unified elimination handles both human
        players and AI characters. Iterates ai_characters[] to check if the
        eliminated character is an AI.
        """
        ...

    async def check_win_condition(self, game_id: str) -> dict:
        """Check if game is over.

        **Implementation Update (v5.1 — simplified parity win):** Shapeshifter
        wins when non_shapeshifter_alive <= 1 (parity). No round guard — the
        shapeshifter wins immediately at 1v1. The old <= 4 player round-2
        requirement has been removed.
        """
        alive = await firestore_client.get_alive_players(game_id)
        ai_chars = await firestore_client.get_ai_characters(game_id)

        traitor_alive = any(
            ai["alive"] for ai in ai_chars if ai.get("is_traitor")
        )

        if not traitor_alive:
            return {"game_over": True, "winner": "villagers",
                    "reason": "The shapeshifter has been identified and eliminated!"}

        # v5.1: Simplified parity — shapeshifter wins at non_shapeshifter_alive <= 1
        non_shapeshifter_alive = len([p for p in alive if p["role"] != "shapeshifter"])
        non_shapeshifter_alive += sum(1 for ai in ai_chars if ai["alive"] and not ai.get("is_traitor"))

        if non_shapeshifter_alive <= 1:
            return {"game_over": True, "winner": "shapeshifter",
                    "reason": "The shapeshifter has overtaken the village!"}

        return {"game_over": False}
    
    async def resolve_night(self, game_id: str) -> dict:
        """Process night phase actions. Unified AI loop (v4.0).

        **Implementation Update (v4.0):** Renamed from execute_night_actions().
        AI night actions are submitted via trigger_all_night_actions() before this
        function runs. Resolution order: Shapeshifter → Bodyguard check → Healer → Seer.

        **Implementation Update (v5.1):**
        - Concurrency guard: `_resolving_nights` set prevents double resolution.
          If game_id is already in the set, returns early. Same pattern as
          `_resolving_votes`.
        - Defense-in-depth alive check: before applying kill, verifies target is
          still alive in Firestore (prevents race with concurrent elimination).
        - Night action timeout increased from 30s → 45s to accommodate AI Gemini
          RPC latency.

        New in v4.0:
        - AI Bodyguard sacrifice: if an AI bodyguard guards the shapeshifter's
          target, the AI bodyguard dies instead (same as human bodyguard).
        - AI Seer investigation: if an AI has role=seer, its investigation result
          is computed here and stored as an ai_seer_result event. The AI Seer's
          findings are injected into its next dialog prompt so it can share
          observations during discussion.
        - All AI night events use {fs_field}_night_{role} pattern
          (e.g., ai_character_night_kill, ai_character_2_night_heal).
        """
        actions = await firestore_client.get_night_actions(game_id)

        # Shapeshifter targets someone (human or AI traitor)
        ai_target = actions.get("shapeshifter_target")
        healer_target = actions.get("healer_target")
        bodyguard_target = actions.get("bodyguard_target")
        seer_target = actions.get("seer_target")
        seer_player_id = actions.get("seer_player_id")

        eliminated = None

        # Bodyguard sacrifice check (human or AI bodyguard)
        if ai_target and ai_target == bodyguard_target:
            # Bodyguard dies instead of the target
            eliminated = actions.get("bodyguard_player_id")
            await firestore_client.eliminate_player(game_id, eliminated)
        elif ai_target and ai_target != healer_target:
            eliminated = ai_target
            await firestore_client.eliminate_player(game_id, ai_target)

        # Seer investigation (human or AI Seer)
        seer_result = None
        if seer_target and seer_player_id:
            actual_role = await firestore_client.get_player_role(game_id, seer_player_id)
            if actual_role == "drunk":
                target_real_role = await firestore_client.get_player_role(game_id, seer_target)
                if target_real_role == "shapeshifter":
                    fake_role = random.choice(["villager", "healer"])
                else:
                    fake_role = "shapeshifter" if random.random() < 0.3 else "villager"
                seer_result = {"target": seer_target, "role": fake_role, "is_drunk": True}
            else:
                target_role = await firestore_client.get_player_role(game_id, seer_target)
                seer_result = {"target": seer_target, "role": target_role, "is_drunk": False}

        # AI Seer investigation result (v4.0) — stored as ai_seer_result event
        ai_seer_results = []
        for ai_char in await firestore_client.get_ai_characters(game_id):
            if ai_char.get("role") == "seer" and ai_char.get("alive"):
                ai_seer_target = actions.get(f"{ai_char['fs_field']}_night_seer")
                if ai_seer_target:
                    target_role = await firestore_client.get_player_role(game_id, ai_seer_target)
                    ai_seer_results.append({
                        "ai_char": ai_char["name"],
                        "target": ai_seer_target,
                        "role": target_role,
                    })

        return {
            "eliminated": eliminated,
            "protected": healer_target,
            "seer_result": seer_result,
            "ai_seer_results": ai_seer_results,
        }
    
    async def execute_hunter_revenge(self, game_id: str, hunter_player_id: str, 
                                      target_character: str) -> dict:
        """P1: When the Hunter is eliminated, they immediately kill one other character.
        This triggers AFTER normal elimination narration, creating a dramatic reversal.
        
        Returns: { revenge_target: str, revenge_eliminated: bool }
        """
        target_alive = await firestore_client.is_character_alive(game_id, target_character)
        if not target_alive:
            return {"revenge_target": target_character, "revenge_eliminated": False}
        
        await firestore_client.eliminate_by_character(game_id, target_character)

        # **Implementation Update (v4.0):** Iterate ai_characters[] array to check
        # whether the Hunter's target was any traitor AI (not just a single AI character).
        ai_chars = await firestore_client.get_ai_characters(game_id)
        killed_shapeshifter = any(
            ai["name"] == target_character and ai.get("is_traitor")
            for ai in ai_chars
        )

        return {
            "revenge_target": target_character,
            "revenge_eliminated": True,
            "killed_shapeshifter": killed_shapeshifter,
        }
```

---

# 4. Tool Definitions

## 4.1 Narrator Tools

```python
from google.adk.tools import FunctionTool

def get_game_state(game_id: str) -> dict:
    """Retrieve current game state from Firestore.

    **Implementation Update (v4.0):** Returns `ai_characters: []` array
    instead of a singular `ai_character` field. Each element contains
    the character name, role, alive status, and is_traitor flag.

    Returns: {
        phase: str, round: int, alive_players: list,
        ai_characters: list[dict], recent_events: list[dict],
        story_context: str
    }
    """
    return firestore_client.get_game_state(game_id)

def advance_phase(game_id: str, next_phase: str) -> dict:
    """Transition the game to the next phase.
    Validates the transition is legal per the state machine.
    
    Args:
        game_id: The game identifier
        next_phase: Target phase (night, day_discussion, day_vote, elimination)
    
    Returns: { success: bool, new_phase: str, message: str }
    """
    return game_master.advance_phase(game_id, next_phase)

def narrate_event(game_id: str, event_type: str, description: str) -> dict:
    """Log a narrative event to Firestore's event log.
    
    Args:
        game_id: The game identifier
        event_type: night_action | accusation | vote | elimination | story_beat
        description: Narrative description of what happened
    
    Returns: { event_id: str, timestamp: str }
    """
    return firestore_client.log_event(game_id, event_type, "narrator", description)

def inject_traitor_dialog(game_id: str, context: str) -> dict:
    """Get all AI characters' responses for the current discussion context.

    **Implementation Update (v4.0):** No longer calls a class-based
    TraitorAgent. Instead delegates to `trigger_all_dialogs(game_id, context)`,
    which uses `_ai_chars_with_fields()` to iterate all AI characters and
    runs `generate_dialog()` for each in parallel via `asyncio.gather()`.
    The separate `_inject_ai2_dialog()` function has been removed.

    Args:
        game_id: The game identifier
        context: What was just said / what the AI characters should respond to

    Returns: list[{ character_name: str, dialog: str }]
    """
    dialogs = trigger_all_dialogs(game_id, context)
    return [
        {"character_name": ai_char["name"], "dialog": dialog_text}
        for ai_char, dialog_text in dialogs
    ]

def start_phase_timer(game_id: str) -> dict:
    """Signal that narration is complete and the phase countdown should begin.

    **Implementation Update (v5.0):** New tool. The narrator calls this after
    finishing its opening narration for a phase (e.g., after announcing night has
    fallen and all players have their role-specific instructions). The server then
    broadcasts the `phase_timer_start` message to all clients, starting the visible
    countdown.

    If the narrator does NOT call this tool within 15 seconds of a phase transition,
    the server fires a safety fallback that starts the timer automatically. This
    prevents games from hanging indefinitely when the narrator is slow or silent.

    Phase-specific timer values (v5.1 updated):
    - night:          45s (reverted from 30s — AI Gemini RPC latency requires headroom)
    - day_discussion: dynamic (120–240s based on alive count — unchanged)
    - day_vote:       60s  (down from 90s — voting is a single tap)

    Minimum discussion guard: The narrator cannot call start_phase_timer during
    day_discussion until at least 45 seconds have elapsed since the phase began.
    This ensures every player has time to speak before the countdown begins.

    Args:
        game_id: The game identifier

    Returns: { success: bool, phase: str, timer_seconds: int, started_at: str }
    """
    return game_master.start_phase_timer(game_id)
```

## 4.2 AI Agent Functions (v4.0)

**Implementation Update (v4.0):** The class-based `TraitorAgent` tools (`plan_deflection`, `generate_alibi`, `accuse_player`) and the 5 AI2-specific functions have been replaced with 4 unified standalone functions + 3 trigger functions described in section 3.2. The old tool-based approach (LLM selects tools) has been replaced with direct function calls that each make a single Gemini LLM request.

```python
# backend/agents/traitor_agent.py — function signatures (v4.0)

async def generate_dialog(game_id: str, ai_char: dict, context: str) -> str:
    """Generate in-character dialog for one AI character.

    Prompt routing:
    - If ai_char["is_traitor"]: uses TRAITOR_DIFFICULTY[difficulty] prompt
      with strategic framework (establish trust → deflect → close game)
    - If not ai_char["is_traitor"]: uses LOYAL_AI_PROMPT with honest
      cooperative observation style

    The prompt includes game state, alive players, suspicion levels,
    and the conversation context. Returns 1-3 sentence dialog text.
    """
    ...

async def select_night_target(game_id: str, ai_char: dict, fs_field: str) -> str:
    """Shapeshifter night kill target selection.

    Writes Firestore event: type="{fs_field}_night_kill"
    Threat assessment priority: Seer > most suspicious player > Healer > random.
    Returns target character name.
    """
    ...

async def select_vote(game_id: str, ai_char: dict, fs_field: str) -> str:
    """AI vote selection with self-vote guard.

    The LLM prompt includes alive characters and instructs the AI to never
    vote for itself. If the LLM returns a self-vote anyway, the function
    re-selects a random valid target. Writes vote to Firestore.
    Returns voted-for character name.
    """
    ...

async def select_loyal_night_action(game_id: str, ai_char: dict, fs_field: str) -> str:
    """Loyal AI night action based on role.

    Role-specific behavior:
    - seer: picks investigation target, writes {fs_field}_night_seer event
    - healer: picks protection target, writes {fs_field}_night_heal event
    - bodyguard: picks guard target, writes {fs_field}_night_bodyguard event
    - villager/hunter/tanner: no night action, returns None

    Returns target character name or None.
    """
    ...

# --- Trigger functions (parallel execution) ---

async def trigger_all_night_actions(game_id: str):
    """Parallel night actions for all AI characters via asyncio.gather().

    For each (ai_char, fs_field) from _ai_chars_with_fields(game):
    - traitor → select_night_target(game_id, ai_char, fs_field)
    - loyal   → select_loyal_night_action(game_id, ai_char, fs_field)
    """
    ...

async def trigger_all_votes(game_id: str):
    """Parallel votes for all AI characters via asyncio.gather().

    For each (ai_char, fs_field) from _ai_chars_with_fields(game):
    - select_vote(game_id, ai_char, fs_field)
    """
    ...

async def trigger_all_dialogs(game_id: str, context: str) -> list[tuple]:
    """Parallel dialog generation for all AI characters via asyncio.gather().

    Returns list of (ai_char, dialog_text) for narrator injection.
    """
    ...
```

### 4.3 Night Phase Orchestration

**Implementation Update (v4.0):** The night phase now uses `trigger_all_night_actions()` to run all AI night actions in parallel via `asyncio.gather()`, replacing the single-agent invocation pattern. Each AI character's action is routed by its `is_traitor` flag to the appropriate function (`select_night_target` or `select_loyal_night_action`). Resolution uses the unified `resolve_night()` which handles AI bodyguard sacrifice and AI Seer investigations.

```python
async def run_night_phase(game: GameSession, game_id: str):
    """Full night phase orchestration (v4.0 — unified multi-AI).

    Sequence:
    1. Narrator announces night has fallen
    2. All AI characters submit night actions in parallel (trigger_all_night_actions)
    3. Human players submit night actions (Seer investigates, Healer protects)
    4. Game Master resolves all actions deterministically (resolve_night)
    5. AI reasoning is logged for game-over reveal
    6. Narrator announces the dawn and results
    """

    # --- Step 1: Transition to night ---
    await firestore_client.update_phase(game_id, "night")
    await game.broadcast({"type": "phase_change", "phase": "night"})
    # timer_seconds is NOT sent here; narrator calls start_phase_timer after narration
    await game.inject_player_message(
        "SYSTEM",
        "NIGHT FALLS. Narrate the village going dark. Build suspense. "
        "Remind players with night abilities to make their choices."
    )

    # --- Step 2: All AI night actions in parallel (v4.0) ---
    # trigger_all_night_actions uses asyncio.gather() internally.
    # Each AI character routes to select_night_target (traitor) or
    # select_loyal_night_action (loyal) based on is_traitor flag.
    # Events written: {fs_field}_night_kill, {fs_field}_night_heal, etc.
    await trigger_all_night_actions(game_id)

    # --- Step 3: Wait for human night actions ---
    # Timeout is 45s (v5.1, up from 30s to accommodate AI Gemini RPC latency).
    # Started after narrator calls start_phase_timer.
    # 15s safety fallback fires if narrator does not call start_phase_timer in time.
    await wait_for_night_actions(game_id, timeout_seconds=45)

    # --- Step 4: Resolve all night actions (deterministic) ---
    # resolve_night handles: shapeshifter kill, bodyguard sacrifice (human + AI),
    # healer protection, seer investigation, AI seer investigation (ai_seer_result)
    result = await game_master.resolve_night(game_id)

    # --- Step 5: Check win condition ---
    # check_win_condition iterates ai_characters[] array for traitor status
    win_check = await game_master.check_win_condition(game_id)
    if win_check["game_over"]:
        await handle_game_over(game, game_id, win_check)
        return

    # --- Step 6: Narrator announces dawn ---
    if result["eliminated"]:
        victim_name = await firestore_client.get_player_name(game_id, result["eliminated"])
        narration_prompt = (
            f"DAWN BREAKS. The village awakens to terrible news: {victim_name} "
            f"was found dead. Narrate the discovery dramatically. The village is shaken. "
            f"Transition to the day discussion phase."
        )
    else:
        narration_prompt = (
            "DAWN BREAKS. Miraculously, everyone survived the night. "
            "Someone — or something — was thwarted. Narrate this with a mix of relief "
            "and growing tension. Transition to the day discussion phase."
        )

    await game.inject_player_message("SYSTEM", narration_prompt)
    await firestore_client.update_phase(game_id, "day_discussion")
    # timer_seconds omitted; narrator calls start_phase_timer after opening narration.
    # Minimum 45s must elapse before narrator may call start_phase_timer for day_discussion.
    await game.broadcast({"type": "phase_change", "phase": "day_discussion"})


def calculate_suspicion_from_events(events: list[dict], state: dict) -> dict:
    """Build a suspicion map: how much each player suspects the AI character.
    
    Analyzes: direct accusations, voting patterns, Seer investigations,
    and general conversation sentiment toward the AI character.
    """
    suspicion = {p["id"]: 0 for p in state["players"] if p["alive"]}
    
    for event in events:
        if event["type"] == "accusation" and event.get("target") == "ai":
            suspicion[event["actor"]] = suspicion.get(event["actor"], 0) + 30
        if event["type"] == "vote" and event.get("data", {}).get("voted_for") == "ai":
            suspicion[event["actor"]] = suspicion.get(event["actor"], 0) + 50
        if event["type"] == "accusation" and event.get("actor") == "ai":
            # AI accused this player — they may retaliate
            target = event.get("target")
            if target in suspicion:
                suspicion[target] += 10
    
    return suspicion


async def handle_game_over(game: GameSession, game_id: str, win_check: dict):
    """Handle game over: reveal all roles, show AI reasoning, narrate conclusion."""
    
    # Collect all hidden AI reasoning events for the big reveal
    ai_reasoning_log = await firestore_client.get_events_by_type(
        game_id, "ai_night_reasoning"
    )
    
    # Build the reveal package
    all_players = await firestore_client.get_all_players(game_id)
    ai_chars = await firestore_client.get_ai_characters(game_id)  # v4.0: array

    role_reveals = []
    for p in all_players:
        role_reveals.append({
            "playerId": p["id"],
            "playerName": p["name"],
            "characterName": p.get("character_name", p["name"]),
            "role": p["role"],
            "alive": p["alive"],
        })
    # v4.0: iterate ai_characters[] array
    for i, ai_char in enumerate(ai_chars):
        role_reveals.append({
            "playerId": f"ai_{i}",
            "playerName": "AI",
            "characterName": ai_char["name"],
            "role": ai_char["role"],
            "alive": ai_char["alive"],
            "is_traitor": ai_char.get("is_traitor", False),
        })
    
    # P1: Build AI strategy log for post-game reveal timeline
    ai_strategy_log = [
        {
            "round": e["data"].get("round", e.get("round")),
            "actionType": e["data"].get("action_type", "night_target"),
            "reasoning": e["data"].get("reasoning", ""),
        }
        for e in ai_reasoning_log
        if e.get("type") == "ai_strategy" or e.get("data", {}).get("reasoning")
    ]
    
    # Narrator delivers the dramatic conclusion
    # v4.0: reference all AI characters from array
    ai_names = ", ".join(ai["name"] for ai in ai_chars)
    reveal_prompt = f"""GAME OVER! {win_check['reason']}

    REVEAL ALL ROLES NOW. The AI character(s) were: {ai_names}.

    Character-to-player reveals:
    {json.dumps([{'character': r['characterName'], 'player': r['playerName'], 'role': r['role']}
                  for r in role_reveals], indent=2)}

    Here is what the AI was thinking each round:
    {json.dumps(ai_strategy_log, indent=2)}

    Narrate the big reveal dramatically. Reveal each character's true identity.
    "Blacksmith Garin was... SARAH! And she was the Healer all along."
    Then reveal each AI: "And {ai_names}... was THE AI."
    Share key moments from the AI's strategy log — what it was thinking, why it
    targeted who it did, and the moment it was closest to being caught.
    This is the climactic moment — make it unforgettable.
    """
    
    await game.inject_player_message("SYSTEM", reveal_prompt)
    
    # Send structured game-over data to all clients
    await game.broadcast({
        "type": "game_over",
        "winner": win_check["winner"],
        "characterReveals": role_reveals,
        "aiStrategyLog": ai_strategy_log,
        "storyRecap": win_check["reason"],
    })
    
    await firestore_client.update_status(game_id, "finished")
```

## 5.1 Connection Lifecycle

Two separate WebSocket connections per player:
- **Game WS** (`/ws/{game_id}?playerId=xxx`) — JSON messages for game state, chat, votes, and narrator audio broadcast. **v5.2:** CONNECTING state guard prevents duplicate connections on mobile tab-switch. Page Visibility API triggers immediate reconnect (bypass backoff) when tab becomes visible. A 2-second sync heartbeat detects phase drift and forces reconnect on mismatch.
- **Audio WS** (`/ws/audio/{game_id}?playerId=xxx`) — binary PCM frames only; no JSON, no base64. Opened when player activates push-to-talk. Closed when they release or navigate away. Independent lifecycle from Game WS. **v5.2:** Mic stream (MediaStream, AudioContext, AudioWorkletNode) is now persistent — only the WS connection is torn down and rebuilt on reconnect. Exponential backoff [500, 1000, 2000, 4000, 8000]ms with max 10 attempts. Page Visibility API proactively closes the WS on page hidden and reconnects on page visible.

```
Client (game WS)                Server              Client (audio WS)
  │                                │                       │
  │──── WS CONNECT ───────────────▶│                       │
  │     /ws/{gameId}?playerId=xxx  │                       │
  │                                │                       │
  │◀─── CONNECTION_ACK ───────────│                       │
  │     { type: "connected",       │                       │
  │       playerId, characterName, │                       │
  │       gameState }              │                       │
  │                                │                       │
  │◀─── ROLE_ASSIGNMENT ──────────│                       │
  │     { type: "role",            │                       │
  │       role: "seer",            │                       │
  │       characterName:           │                       │
  │         "Merchant Elara",      │                       │
  │       characterIntro: "...",   │                       │
  │       description: "..." }     │                       │
  │     [PRIVATE - only to this    │                       │
  │      player's WebSocket]       │                       │
  │                                │                       │
  │◀─── AUDIO_CHUNK ─────────────│                       │
  │     { type: "audio",           │                       │
  │       data: <base64 PCM>,      │                       │
  │       sample_rate: 24000 }     │                       │
  │     [BROADCAST to all players] │                       │
  │                                │                       │
  │──── PLAYER_MESSAGE ───────────▶│                       │
  │     { type: "message",         │                       │
  │       text: "I think..." }     │                       │
  │     (local echo immediately;   │                       │
  │      server echo deduplicated) │                       │
  │                                │                       │
  │◀─── TRANSCRIPT ──────────────│                       │
  │     { type: "transcript",      │                       │
  │       speaker: "Merchant Elara"│                       │
  │       text: "I think..." }     │                       │
  │     [BROADCAST to others]      │                       │
  │                                │                       │
  │──── START_SPEAKING ───────────▶│                       │
  │     { type: "start_speaking" } │                       │
  │                                │──── WS CONNECT ──────▶│
  │                                │  /ws/audio/{gameId}   │
  │                                │  ?playerId=xxx        │
  │◀─── SPEAKER_ACK ─────────────│                       │
  │     { type: "speaker_granted"} │                       │
  │     [PRIVATE — lock acquired]  │                       │
  │                                │                       │
  │                                │◀─── binary PCM ───────│
  │                                │   raw 16-bit PCM16    │
  │                                │   16 kHz mono frames  │
  │                                │   (no JSON wrapper)   │
  │                                │                       │
  │──── STOP_SPEAKING ────────────▶│                       │
  │     { type: "stop_speaking" }  │──── WS CLOSE ────────▶│
  │     [releases speaker lock]    │                       │
  │                                │                       │
  │──── QUICK_REACTION ───────────▶│                       │  P1
  │     { type: "quick_reaction",  │                       │
  │       reaction: "suspect",     │                       │
  │       target: "Blacksmith" }   │                       │
  │                                │                       │
  │──── VOTE ─────────────────────▶│                       │
  │     { type: "vote",            │                       │
  │       target: "Blacksmith" }   │  (character name)     │
  │                                │                       │
  │◀─── PHASE_CHANGE ────────────│                       │
  │     { type: "phase_change",    │                       │
  │       phase: "day_vote" }      │                       │
  │     [no timer_seconds here;    │                       │
  │      timer starts after        │                       │
  │      narrator calls            │                       │
  │      start_phase_timer]        │                       │
  │                                │                       │
  │◀─── PHASE_TIMER_START ────────│                       │
  │     { type:                    │                       │
  │       "phase_timer_start",     │                       │
  │       phase: "day_vote",       │                       │
  │       timer_seconds: 60 }      │                       │
  │     [narrator called           │                       │
  │      start_phase_timer, or     │                       │
  │      15s safety fallback fired]│                       │
  │                                │                       │
  │──── NIGHT_ACTION ─────────────▶│                       │
  │     { type: "night_action",    │                       │
  │       action: "investigate",   │                       │
  │       target: "Blacksmith" }   │  (character name)     │
  │                                │                       │
  │──── SKIP_NIGHT_KILL ──────────▶│                       │  (Shapeshifter skip)
  │     { type: "skip_night_kill" }│                       │
  │     [human shapeshifter skips  │                       │
  │      night kill; resolved as   │                       │
  │      no elimination]           │                       │
  │                                │                       │
  │◀─── NIGHT_RESULT ────────────│                       │
  │     { type: "night_result",    │                       │
  │       result: "villager" }     │                       │
  │     [PRIVATE - Seer or Drunk.  │                       │
  │      Drunk gets false result.] │                       │
  │                                │                       │
  │◀─── ELIMINATION ─────────────│                       │
  │     { type: "elimination",     │                       │
  │       characterName: "...",    │                       │
  │       wasTraitor: false,       │                       │
  │       role: "hunter",          │                       │
  │       triggerHunterRevenge:    │                       │  P1
  │         true }                 │                       │
  │                                │                       │
  │──── HUNTER_REVENGE ───────────▶│                       │  P1
  │     { type: "hunter_revenge",  │                       │
  │       target: "Blacksmith" }   │                       │
  │                                │                       │
  │◀─── GAME_OVER ───────────────│                       │
  │     { type: "game_over",       │                       │
  │       winner: "villagers",     │                       │
  │       characterReveals: [...], │  P0                   │
  │       aiStrategyLog: [...],    │  P1                   │
  │       storyRecap: "..." }      │                       │
```

## 5.2 Message Types (TypeScript Interface)

```typescript
// Server → Client messages
type ServerMessage =
  | { type: "connected"; playerId: string; characterName: string; gameState: GameState } // v5.1: sends ALL players (alive + dead) via get_all_players()
  | { type: "role"; role: Role; characterName: string; characterIntro: string; description: string } // PRIVATE
  | { type: "audio"; data: string; sampleRate: number }         // BROADCAST
  | { type: "transcript"; speaker: string; text: string }       // BROADCAST (speaker = character name)
  | { type: "input_transcript"; speaker: string; text: string } // BROADCAST — player mic voice transcript (§12.5.1)
  | { type: "phase_change"; phase: GamePhase;                    // v5.1: now includes full player roster + AI character data
      players?: Player[]; aiCharacters?: AICharacter[] }           // Frontend dispatches UPDATE_PLAYERS + SET_AI_CHARACTERS
  | { type: "phase_timer_start"; phase: GamePhase; timerSeconds: number } // v5.0: narrator called start_phase_timer (or 15s fallback fired)
  | { type: "speaker_granted"; playerId: string }               // v5.0: PRIVATE — push-to-talk lock acquired
  | { type: "speaker_released"; playerId: string }              // v5.0: BROADCAST — another player's lock released
  | { type: "speaker_error"; reason: string }                   // v5.0: PRIVATE — lock denied (dead player, already locked, etc.)
  | { type: "player_joined"; characterName: string; count: number }  // Character name only
  | { type: "player_left"; characterName: string }
  | { type: "vote_update"; votes: Record<string, string | null> }   // Character names
  | { type: "vote_result"; result: "eliminated" | "tie" | "no_votes";  // v5.0: explicit tally result broadcast
      eliminated: string | null; tally: Record<string, number> }
  | { type: "elimination"; characterName: string; wasTraitor: boolean;
      role: Role; triggerHunterRevenge?: boolean;                     // P1: Hunter flag
      individualVotes?: Record<string, string>;                      // v5.2: {voter: votedFor} — captured before tally_votes() clears AI voted_for
      isTie?: boolean }                                              // v5.2: true if vote was tied (no elimination)
  | { type: "hunter_revenge"; hunterCharacter: string; targetCharacter: string;
      targetWasTraitor: boolean }                                    // P1: Hunter's death kill
  | { type: "night_result"; result: any }                           // PRIVATE (Seer/Drunk)
  | { type: "game_over"; winner: string;
      characterReveals: CharacterReveal[];                          // P0: character → player + role
      aiStrategyLog: AIStrategyEntry[];                             // P1: post-game reveal timeline
      storyRecap: string }
  | { type: "ghost_message"; speaker: string; text: string;                  // v5.1: BROADCAST — dead player chat (source="ghost" in Firestore)
      source: "ghost" }
  | { type: "seance_start"; duration: number }                                // v5.1: BROADCAST — séance phase begins (45s push-to-talk for dead)
  | { type: "seance_end" }                                                    // v5.1: BROADCAST — séance phase ends
  | { type: "haunt_result"; ghostCharacter: string; accusedCharacter: string } // v5.1: BROADCAST — ghost haunt accusation (narrator incorporates)
  | { type: "error"; message: string; code: string }

// P1: Spectator clue — eliminated player sends one-word hint
// Server validates: max 1 clue per round, single word only, no proper nouns matching character names
type SpectatorClue = {
  type: "spectator_clue";
  fromCharacter: string;   // The eliminated character's name (for narrator flavor)
  word: string;            // Single word clue
  targetPlayer?: string;   // Optional: specific player to receive, or broadcast to all living
}

type CharacterReveal = {
  characterName: string;
  playerName: string | "AI";  // Real player name or "AI"
  role: Role;
}

type AIStrategyEntry = {
  round: number;
  actionType: "night_target" | "deflection" | "accusation" | "vote" | "alibi";
  reasoning: string;   // Natural language: "Targeted Elara because she asked about the forge"
}
```

**Spectator Mode:** When a player is eliminated, the server sends the `elimination` message. The client sets a local `isSpectator = true` flag — hiding `ChatInput` and `VotePanel` while keeping `AudioPlayer` and `StoryLog` active. If the eliminated player's role is "hunter", the client shows a `HunterRevengeModal` — a character selection screen with a 15-second timer for the Hunter to choose their revenge target. The player's WebSocket stays open as a read-only consumer. No new Firestore fields are needed; `alive: false` already gates server-side action processing.

**Spectator Clues (P1):** Eliminated players can send one single-word clue per round to living players via a `SpectatorClueInput` component (replaces `ChatInput` for spectators). The word is validated server-side: must be a single word (no spaces), cannot be a character name, max one clue per round per spectator. The clue is delivered through the Narrator Agent as an in-story event: "A voice from beyond the veil reaches you... a single word: 'forge.'" The narrator injects the clue during the day discussion phase only. This keeps eliminated players engaged — getting voted out in Round 1 and sitting idle for 20 minutes is the #1 cause of player dropout in social deduction games (board game organizer feedback).

```
// Client → Server messages (game-state WebSocket only; audio WS carries raw binary)
type ClientMessage =
  | { type: "message"; text: string }                                    // Free-form text
  | { type: "quick_reaction"; reaction: QuickReaction; target?: string } // P1: preset buttons
  // Note: player_audio removed from game WS — mic audio now sent as raw binary over /ws/audio/{gameId}
  | { type: "start_speaking" }                                           // v5.0: claim push-to-talk speaker lock
  | { type: "stop_speaking" }                                            // v5.0: release speaker lock
  | { type: "vote"; target: string }                                     // Character name
  | { type: "night_action"; action: NightAction; target: string }
  | { type: "skip_night_kill" }                                          // v5.0: Shapeshifter skips night kill (no target)
  | { type: "hunter_revenge"; target: string }                           // P1: Hunter's death target
  | { type: "shapeshifter_action"; target: string }                      // Human shapeshifter night kill (§12.5.5)
  | { type: "ghost_message"; text: string }                              // v5.1: Dead player chat (rate-limited 2s per player)
  | { type: "haunt_action"; target: string }                             // v5.1: Dead player accuses a living character during night
  | { type: "ready" }
  | { type: "ping" }
  | { type: "sync" }                                                    // v5.2: Heartbeat — server responds with current phase for drift detection

// Audio WebSocket (/ws/audio/{gameId}?playerId=xxx)
// Sends raw binary PCM16 frames, 16 kHz, mono — NO JSON envelope.
// v5.2: Mic stream (MediaStream, AudioContext, AudioWorkletNode) persists across WS
// reconnects. Only the WS connection is opened/closed. Exponential backoff reconnect
// (500-8000ms, max 10 attempts). Page Visibility API: close WS on hidden, reconnect on
// visible. connectingRef guard prevents orphaned connection promises.
// If the audio WS drops mid-capture, the speaker lock is released automatically
// server-side; game WS is unaffected.

type QuickReaction = "suspect" | "trust" | "agree" | "have_info";
```

**Wire Protocol Note (v4.0):** The backend game state WebSocket message (sent on `connected` and on state updates) still carries separate `aiCharacter` and `aiCharacter2` top-level fields, matching the Firestore document model. The frontend (`useWebSocket.js`) assembles these into a unified `aiCharacters[]` array and dispatches a single `SET_AI_CHARACTERS` action to `GameContext`. This keeps the Firestore schema stable while giving the frontend a clean N-element array. The Narrator Agent's `get_game_state` tool response uses `ai_characters[]` directly (not the split fields) because it reads from the game master's resolved state rather than the raw WebSocket payload.

**Audio Transport Note (v5.0, updated v5.2):** Player microphone audio is no longer embedded in JSON messages on the game-state WebSocket. `useAudioCapture.js` opens a separate binary WebSocket to `/ws/audio/{gameId}` and streams raw PCM16 frames (no encoding, no envelope). This reduces per-frame overhead by ~33% and eliminates the code 1006 game WS disconnections that occurred when audio frame bursts saturated the shared queue. **v5.2 architecture change:** The mic stream (MediaStream, AudioContext, AudioWorkletNode) lifecycle is now fully separated from the audio WS lifecycle. The mic stays alive across WS reconnects; only the WS connection is torn down and re-established. On WS drop, exponential backoff reconnection fires (delays [500,1000,2000,4000,8000]ms, max 10 attempts). Page Visibility API proactively closes the WS on page hidden and reconnects + resumes AudioContext on page visible. A `connectingRef` guard prevents orphaned connection promises from the visibility handler.

**Phase Timer Note (v5.0):** `phase_change` messages no longer include `timerSeconds`. Instead, a separate `phase_timer_start` message is sent when the narrator explicitly calls `start_phase_timer` (signalling narration is done) or when the 15-second safety fallback fires. The frontend must not start its countdown until it receives `phase_timer_start`. This prevents the countdown from racing ahead of the narrator's opening speech.

## 5.3 Server Implementation

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.live_request_queue import LiveRequestQueue
import asyncio
import json

app = FastAPI()

# CORS middleware (for local dev: Vite on :5173, FastAPI on :8080)
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files (Vite build output) — SPA catch-all routing (v5.2)
# SPAStaticFiles subclass catches 404s from StaticFiles and serves index.html instead,
# enabling React Router client-side routing in production (e.g., /join/C1E7F362 works).
# API routes (/api/*) and WebSocket routes (/ws/*) are registered BEFORE this mount,
# so they take priority over the catch-all.
from starlette.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
import os

class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as ex:
            if ex.status_code == 404:
                return await super().get_response(".", scope)
            raise

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dir):
    app.mount("/", SPAStaticFiles(directory=frontend_dir, html=True), name="frontend")

# Active game sessions: gameId → GameSession
active_games: dict[str, "GameSession"] = {}

class ConnectionManager:
    """Per-player dual-queue connection manager (v5.0).

    Each player has two outbound queues:
    - control_queue (asyncio.Queue, unbounded): game-state JSON messages.
      Phase changes, eliminations, votes, private role assignments — all go here.
    - audio_queue (asyncio.Queue, maxsize=256): narrator PCM audio chunks.
      If the audio queue is full (producer faster than consumer), oldest chunks
      are dropped to prevent memory growth.

    A dedicated _player_sender coroutine per connection drains control first,
    then audio, ensuring control-plane latency is not affected by audio volume.

    Chat local echo: when a player sends a "message", the server immediately
    echoes it back to THAT player's control queue. All other players receive the
    broadcast. A deduplication flag prevents the sender from showing the message
    twice if the echo races ahead of the broadcast.
    """

    def __init__(self):
        self._control_queues: dict[str, asyncio.Queue] = {}
        self._audio_queues: dict[str, asyncio.Queue] = {}
        self._sender_tasks: dict[str, asyncio.Task] = {}
        self._websockets: dict[str, WebSocket] = {}

    async def connect(self, player_id: str, ws: WebSocket):
        self._websockets[player_id] = ws
        self._control_queues[player_id] = asyncio.Queue()
        self._audio_queues[player_id] = asyncio.Queue(maxsize=256)
        self._sender_tasks[player_id] = asyncio.create_task(
            self._player_sender(player_id, ws)
        )

    async def disconnect(self, player_id: str):
        task = self._sender_tasks.pop(player_id, None)
        if task:
            task.cancel()
        self._control_queues.pop(player_id, None)
        self._audio_queues.pop(player_id, None)
        self._websockets.pop(player_id, None)

    async def _player_sender(self, player_id: str, ws: WebSocket):
        """Drain control queue first; then drain one audio chunk per iteration."""
        ctrl_q = self._control_queues[player_id]
        audio_q = self._audio_queues[player_id]
        try:
            while True:
                # Prefer control messages — drain all available before audio
                try:
                    msg = ctrl_q.get_nowait()
                    await ws.send_text(json.dumps(msg))
                    ctrl_q.task_done()
                    continue
                except asyncio.QueueEmpty:
                    pass
                # No control messages pending — send one audio chunk or wait
                try:
                    chunk = await asyncio.wait_for(
                        asyncio.shield(self._next_from_either(ctrl_q, audio_q)),
                        timeout=1.0
                    )
                    if isinstance(chunk, dict):
                        await ws.send_text(json.dumps(chunk))
                    else:
                        # bytes — audio chunk
                        audio_msg = json.dumps({
                            "type": "audio",
                            "data": base64.b64encode(chunk).decode(),
                            "sampleRate": 24000
                        })
                        await ws.send_text(audio_msg)
                except asyncio.TimeoutError:
                    pass  # No messages; loop again
        except (WebSocketDisconnect, Exception):
            pass  # Connection gone; cleanup handled by disconnect()

    async def enqueue_control(self, player_id: str, message: dict):
        q = self._control_queues.get(player_id)
        if q:
            await q.put(message)

    async def enqueue_audio(self, player_id: str, audio_bytes: bytes):
        q = self._audio_queues.get(player_id)
        if q:
            try:
                q.put_nowait(audio_bytes)
            except asyncio.QueueFull:
                pass  # Drop oldest: discard incoming if queue full

    async def broadcast(self, message: dict, exclude: str | None = None):
        for pid in list(self._control_queues):
            if pid != exclude:
                await self.enqueue_control(pid, message)

    async def send_private(self, player_id: str, message: dict):
        await self.enqueue_control(player_id, message)

    async def broadcast_audio(self, audio_bytes: bytes):
        for pid in list(self._audio_queues):
            await self.enqueue_audio(pid, audio_bytes)

    @staticmethod
    async def _next_from_either(ctrl_q: asyncio.Queue, audio_q: asyncio.Queue):
        """Await whichever queue has a message first; control wins on tie."""
        ctrl_task = asyncio.ensure_future(ctrl_q.get())
        audio_task = asyncio.ensure_future(audio_q.get())
        done, pending = await asyncio.wait(
            [ctrl_task, audio_task], return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
        return done.pop().result()


class GameSession:
    """Manages one active game: players, narrator session, game state, speaker lock."""

    def __init__(self, game_id: str):
        self.game_id = game_id
        self.connection_manager = ConnectionManager()
        self.players: dict[str, WebSocket] = {}  # playerId → WebSocket (for legacy compat)
        self.live_queue: LiveRequestQueue | None = None
        self.narrator_task: asyncio.Task | None = None
        self.session_handle: str | None = None

        # v5.0: Push-to-talk speaker lock
        self._current_speaker: Optional[str] = None          # player_id or None
        self._speaker_timeout_task: Optional[asyncio.Task] = None

        # v5.0: Audio WebSocket connections (separate from game WS)
        self._audio_websockets: dict[str, WebSocket] = {}     # playerId → audio WS

        # v5.0: Phase timer state
        self._phase_timer_task: Optional[asyncio.Task] = None
        self._phase_timer_safety_task: Optional[asyncio.Task] = None

        # v5.1: Concurrency guards — prevent double resolution
        self._resolving_votes: Set[str] = set()   # game_ids currently resolving votes
        self._resolving_nights: Set[str] = set()   # game_ids currently resolving night actions

    # --- Speaker lock management (v5.0) ---

    async def claim_speaker_lock(self, player_id: str) -> bool:
        """TOCTOU-safe speaker lock claim.

        The claim is written immediately (before any async call) so that two
        concurrent start_speaking messages cannot both succeed. If the player
        is dead, returns False and sends speaker_error. If another player holds
        the lock, returns False. Otherwise acquires the lock, schedules a 30s
        auto-release task, and sends speaker_granted.
        """
        # Fast rejection: dead players cannot speak
        if await firestore_client.is_player_dead(self.game_id, player_id):
            await self.connection_manager.send_private(player_id, {
                "type": "speaker_error",
                "reason": "dead_players_cannot_speak"
            })
            return False

        # Immediate claim (TOCTOU-safe: set before any await)
        if self._current_speaker is not None:
            await self.connection_manager.send_private(player_id, {
                "type": "speaker_error",
                "reason": "lock_held_by_other"
            })
            return False

        self._current_speaker = player_id  # Claim made — no await before this point

        # Cancel any stale timeout from a previous holder
        if self._speaker_timeout_task:
            self._speaker_timeout_task.cancel()

        # Schedule auto-release after 30 seconds
        self._speaker_timeout_task = asyncio.create_task(
            self._auto_release_speaker(player_id, delay=30)
        )

        await self.connection_manager.send_private(player_id, {
            "type": "speaker_granted",
            "playerId": player_id
        })
        return True

    async def release_speaker_lock(self, player_id: str, reason: str = "stop_speaking"):
        """Release the speaker lock. Safe to call even if lock not held."""
        if self._current_speaker != player_id:
            return
        self._current_speaker = None
        if self._speaker_timeout_task:
            self._speaker_timeout_task.cancel()
            self._speaker_timeout_task = None
        await self.connection_manager.broadcast({
            "type": "speaker_released",
            "playerId": player_id,
            "reason": reason
        })

    async def _auto_release_speaker(self, player_id: str, delay: float):
        await asyncio.sleep(delay)
        await self.release_speaker_lock(player_id, reason="timeout")

    async def force_release_speaker_on_disconnect(self, player_id: str):
        """Called when game WS or audio WS disconnects."""
        await self.release_speaker_lock(player_id, reason="disconnect")

    async def force_release_speaker_on_phase_change(self):
        """Called when phase transitions."""
        if self._current_speaker:
            await self.release_speaker_lock(self._current_speaker, reason="phase_change")

    # --- Phase timer (v5.0) ---

    async def start_phase_timer_from_narrator(self, phase: str, timer_seconds: int):
        """Called when narrator invokes the start_phase_timer tool.

        Cancels the 15s safety fallback (it's no longer needed) and broadcasts
        the phase_timer_start message to all players.
        """
        if self._phase_timer_safety_task:
            self._phase_timer_safety_task.cancel()
            self._phase_timer_safety_task = None
        await self.connection_manager.broadcast({
            "type": "phase_timer_start",
            "phase": phase,
            "timerSeconds": timer_seconds
        })

    async def schedule_phase_timer_safety(self, phase: str, timer_seconds: int, safety_delay: float = 15.0):
        """Schedule a 15s safety fallback in case narrator never calls start_phase_timer."""
        async def _fallback():
            await asyncio.sleep(safety_delay)
            # Only fires if narrator hasn't called start_phase_timer yet
            await self.connection_manager.broadcast({
                "type": "phase_timer_start",
                "phase": phase,
                "timerSeconds": timer_seconds
            })
        self._phase_timer_safety_task = asyncio.create_task(_fallback())

    # --- Connection helpers ---

    async def add_player(self, player_id: str, ws: WebSocket):
        self.players[player_id] = ws
        await self.connection_manager.connect(player_id, ws)
        await self.connection_manager.broadcast({
            "type": "player_joined",
            "name": player_id,
            "count": len(self.players)
        })

    async def remove_player(self, player_id: str):
        await self.force_release_speaker_on_disconnect(player_id)
        self.players.pop(player_id, None)
        await self.connection_manager.broadcast({"type": "player_left", "name": player_id})
        await self.connection_manager.disconnect(player_id)

    # broadcast / send_private / broadcast_audio delegate to ConnectionManager
    async def broadcast(self, message: dict):
        await self.connection_manager.broadcast(message)

    async def send_private(self, player_id: str, message: dict):
        await self.connection_manager.send_private(player_id, message)

    async def broadcast_audio(self, audio_bytes: bytes):
        await self.connection_manager.broadcast_audio(audio_bytes)
    
    async def inject_player_message(self, player_name: str, text: str):
        """Inject a player's text message into the narrator's Live API context."""
        if self.live_queue:
            attributed = f"\n[{player_name} says]: {text}\n"
            await self.live_queue.send_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=attributed)]
                )
            )
    
    async def start_narrator_session(self):
        """Initialize the Live API session for the narrator."""
        session_service = InMemorySessionService()
        runner = Runner(
            agent=narrator_agent,
            session_service=session_service,
            app_name="fireside"
        )
        
        session = await session_service.create_session(
            app_name="fireside",
            user_id="narrator"
        )
        
        self.live_queue = LiveRequestQueue()
        
        run_config = types.RunConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
            session_resumption=types.SessionResumptionConfig(
                handle=self.session_handle
            ),
            context_window_compression=types.ContextWindowCompressionConfig(
                enabled=True
            ),
            output_audio_transcription=types.AudioTranscriptionConfig(
                enabled=True
            ),
        )
        
        # Start the bidi-streaming loop
        self.narrator_task = asyncio.create_task(
            self._narrator_loop(runner, session, run_config)
        )
    
    async def _narrator_loop(self, runner, session, run_config):
        """Process narrator events from run_live()."""
        async for event in runner.run_live(
            session=session,
            live_request_queue=self.live_queue,
            run_config=run_config,
        ):
            # Handle audio output
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        await self.broadcast_audio(part.inline_data.data)
                    if hasattr(part, 'text') and part.text:
                        await self.broadcast({
                            "type": "transcript",
                            "speaker": "Narrator",
                            "text": part.text
                        })
            
            # Handle session resumption updates
            if hasattr(event, 'session_resumption_update'):
                update = event.session_resumption_update
                if update and update.resumable and update.new_handle:
                    self.session_handle = update.new_handle


@app.websocket("/ws/{game_id}")
async def game_websocket(websocket: WebSocket, game_id: str):
    """Game-state WebSocket. Handles all JSON message types.
    Keepalive: ping_interval=20s, ping_timeout=30s (v5.0 re-enabled).
    Disconnect events are logged (previously silently swallowed).
    """
    await websocket.accept()

    # Parse player ID from query params
    player_id = websocket.query_params.get("playerId", f"player_{id(websocket)}")

    # Get or create game session
    if game_id not in active_games:
        active_games[game_id] = GameSession(game_id)

    game = active_games[game_id]
    await game.add_player(player_id, websocket)

    # Send current game state
    state = await firestore_client.get_game_state(game_id)
    await websocket.send_text(json.dumps({
        "type": "connected",
        "playerId": player_id,
        "gameState": state
    }))

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            match msg["type"]:
                case "message":
                    # Player sends a chat message → local echo + inject into narrator context
                    player_name = await firestore_client.get_player_name(game_id, player_id)
                    # Local echo: send back to sender immediately (with echo=True flag for dedup)
                    await game.send_private(player_id, {
                        "type": "transcript",
                        "speaker": player_name,
                        "text": msg["text"],
                        "echo": True
                    })
                    # Inject into narrator and broadcast to others
                    await game.inject_player_message(player_name, msg["text"])
                    await game.broadcast({
                        "type": "transcript",
                        "speaker": player_name,
                        "text": msg["text"]
                    }, exclude=player_id)

                case "start_speaking":
                    # Push-to-talk: claim speaker lock
                    await game.claim_speaker_lock(player_id)

                case "stop_speaking":
                    # Push-to-talk: release speaker lock
                    await game.release_speaker_lock(player_id, reason="stop_speaking")

                case "skip_night_kill":
                    # Shapeshifter (human) skips their night kill
                    # Validates player has shapeshifter role, then resolves night with no target
                    role = await firestore_client.get_player_role(game_id, player_id)
                    if role == "shapeshifter":
                        await firestore_client.log_event(game_id, "shapeshifter_skip", player_id, {
                            "reason": "player_chose_to_skip"
                        })
                        # Night resolves with no shapeshifter target (nobody eliminated by shapeshifter)
                        await firestore_client.record_night_action(
                            game_id, player_id, "skip_night_kill", target=None
                        )
                    else:
                        await game.send_private(player_id, {
                            "type": "error",
                            "message": "Only the shapeshifter can skip night kill",
                            "code": "invalid_action"
                        })
                
                case "vote":
                    await firestore_client.record_vote(game_id, player_id, msg["target"])
                    votes = await firestore_client.get_votes(game_id)
                    await game.broadcast({"type": "vote_update", "votes": votes})

                    # **Implementation Update (v4.0):** Vote wait uses polling loop
                    # (5 iterations x 2s sleep) instead of checking all-voted instantly.
                    # AI votes are submitted via trigger_all_votes() which runs in
                    # parallel. The polling loop waits for both human and AI votes.
                    # The old is_loyal_ai instant game-over block has been removed.
                    for _ in range(5):
                        votes = await firestore_client.get_votes(game_id)
                        if all(v is not None for v in votes.values()):
                            result = await game_master.tally_votes(game_id)
                            await game.inject_player_message(
                                "SYSTEM",
                                f"VOTE RESULT: {json.dumps(result)}. Narrate this dramatically."
                            )
                            break
                        await asyncio.sleep(2)
                
                case "night_action":
                    await firestore_client.record_night_action(
                        game_id, player_id, msg["action"], msg["target"]
                    )
                    # Send private result for Seer
                    if msg["action"] == "investigate":
                        role = await firestore_client.get_player_role(game_id, msg["target"])
                        await game.send_private(player_id, {
                            "type": "night_result",
                            "result": role
                        })
                
                case "ready":
                    await firestore_client.mark_ready(game_id, player_id)
                
                case "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect as exc:
        logger.info("game_ws_disconnect", extra={
            "game_id": game_id,
            "player_id": player_id,
            "code": getattr(exc, "code", None),
        })
        await game.remove_player(player_id)  # also releases speaker lock if held


@app.websocket("/ws/audio/{game_id}")
async def audio_websocket(websocket: WebSocket, game_id: str):
    """Dedicated binary audio WebSocket (v5.0).

    Receives raw binary PCM16 frames (16 kHz, mono) from the player's mic.
    No JSON envelope. No base64 encoding. Each received binary frame is
    forwarded directly to NarratorSession.send_audio().

    Lifecycle:
    - Player opens this connection after server sends speaker_granted.
    - useAudioCapture.js AudioWorklet feeds raw PCM chunks here.
    - If this WS drops mid-capture (code 1006 or any disconnect), the server
      releases the speaker lock and logs the event; the game WS is unaffected.
    """
    await websocket.accept()
    player_id = websocket.query_params.get("playerId")
    if not player_id or game_id not in active_games:
        await websocket.close(code=1008)
        return

    game = active_games[game_id]
    game._audio_websockets[player_id] = websocket
    character_name = await firestore_client.get_player_name(game_id, player_id)

    try:
        while True:
            pcm_bytes = await websocket.receive_bytes()
            # Forward raw PCM to the Gemini Live API session
            if game.live_queue:
                await game.narrator_session.send_audio(pcm_bytes, speaker=character_name)

    except WebSocketDisconnect as exc:
        logger.info("audio_ws_disconnect", extra={
            "game_id": game_id,
            "player_id": player_id,
            "code": getattr(exc, "code", None),
        })
    finally:
        game._audio_websockets.pop(player_id, None)
        # Release speaker lock if this player held it
        await game.force_release_speaker_on_disconnect(player_id)
```

---

# 6. Data Model (Firestore)

## 6.1 Complete Schema

```
fireside-db/
├── games/
│   └── {gameId}/                          # 6-char alphanumeric code (ABCDEFGHJKLMNPQRSTUVWXYZ23456789)
│       ├── status: string                 # "lobby" | "in_progress" | "finished"
│       ├── phase: string                  # "setup" | "night" | "day_discussion" | "day_vote" | "elimination" | "seance" | "game_over"
│       ├── round: number                  # Current round (1-indexed)
│       ├── difficulty: string             # "easy" | "normal" | "hard" — AI deception level
│       ├── winner: string | null          # "villagers" | "shapeshifter" | "tanner" — set on game end
│       ├── random_alignment: boolean      # §12.3.10: AI draws random role (true for Normal/Hard)
│       ├── narrator_preset: string        # §12.3.17: "classic" | "campfire" | "horror" | "comedy"
│       ├── in_person_mode: boolean        # §12.3.16: Camera-based voting enabled
│       ├── created_at: timestamp          # Game creation time
│       ├── updated_at: timestamp          # Last state change
│       ├── host_player_id: string         # Player who created the game
│       ├── story_genre: string            # "fantasy_village" (only genre for now)
│       ├── story_context: string          # Current narrative summary for session injection
│       │
│       ├── character_cast: string[]       # All character names in this game (players + AI)
│       ├── generated_characters: map[]    # LLM-generated: [{name, intro, personality_hook}, ...]
│       │
│       ├── ai_characters: array[]          # v4.0: Array of AI character documents (was singular ai_character)
│       │   └── [index]/                   # Each AI character
│       │       ├── name: string               # "Tinker Orin" (LLM-generated)
│       │       ├── intro: string              # Character introduction for narrator
│       │       ├── role: string               # §12.3.10: Any role — "shapeshifter", "seer", "villager", etc.
│       │       ├── alive: boolean             # Is AI character still in the game
│       │       ├── backstory: string          # Character personality_hook for Traitor Agent
│       │       ├── personality_hook: string   # Behavioral trait for roleplay
│       │       ├── is_traitor: boolean        # §12.3.10: true if shapeshifter, false if loyal
│       │       └── suspicion_level: number    # 0-100, tracked for strategy
│       │
│       ├── session/                       # Live API session tracking
│       │   ├── handle: string | null      # Session resumption handle
│       │   ├── started_at: timestamp      # When current session began
│       │   └── reconnect_count: number    # Times we've reconnected
│       │
│       ├── players/                       # Subcollection
│       │   └── {playerId}/
│       │       ├── name: string           # Real display name (hidden during gameplay)
│       │       ├── character_name: string # P0: Story character name (visible during gameplay)
│       │       ├── character_intro: string # P0: Character introduction for narrator
│       │       ├── personality_hook: string # Behavioral trait from LLM character generation
│       │       ├── role: string           # "villager" | "seer" | "healer" | "hunter" | "drunk" | "bodyguard" | "tanner"
│       │       ├── alive: boolean         # Still in the game
│       │       ├── connected: boolean     # WebSocket connected
│       │       ├── ready: boolean         # Ready to start
│       │       ├── voted_for: string | null  # Character name they voted for this round
│       │       ├── night_action: map | null  # {action: string, target: string}
│       │       └── joined_at: timestamp
│       │
│       ├── events/                        # Subcollection (append-only log)
│       │   └── {eventId}/                 # Auto-ID
│       │       ├── type: string           # "night_action" | "accusation" | "vote" |
│       │       │                          # "elimination" | "story_beat" | "phase_change" |
│       │       │                          # "ai_strategy" (P1: hidden until post-game) |
│       │       │                          # "hunter_revenge" (P1: Hunter's death kill) |
│       │       │                          # v4.0: "{fs_field}_night_{role}" pattern for AI night events
│       │       │                          #   e.g. "ai_character_night_kill", "ai_character_2_night_heal"
│       │       │                          # "ai_seer_result" (v4.0: AI Seer investigation result)
│       │       │                          # "haunt_action" (v5.1: dead player accuses a living character)
│       │       │                          # "ghost_dialog" (v5.1: AI ghost auto-generated dialog)
│       │       ├── round: number          # Which round this event occurred in
│       │       ├── phase: string          # Which phase
│       │       ├── actor: string          # playerId | "ai" | "system"
│       │       ├── target: string | null  # Affected character name
│       │       ├── data: map              # Event-specific data
│       │       ├── narration: string      # Narrator's description of the event
│       │       ├── visible_in_game: bool  # P1: false for ai_strategy events (post-game only)
│       │       └── timestamp: timestamp   # Server timestamp
│       │
│       └── chat/                          # Subcollection (for story log)
│           └── {messageId}/
│               ├── speaker: string        # Character name or "Narrator" (never real player name)
│               ├── speaker_player_id: string | null  # Hidden: real player ID (for post-game reveal)
│               ├── text: string           # Message content
│               ├── source: string         # "typed" | "quick_reaction" | "narrator" | "ai_character" | "ghost" | "player"
│               ├── phase: string          # When it was said
│               ├── round: number
│               └── timestamp: timestamp
```

## 6.2 Firestore Security Rules

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Games collection
    match /games/{gameId} {
      allow read: if true;  // Players need to read game state
      allow create: if request.auth != null;
      allow update: if true;  // Server-side updates (Cloud Run has admin access)
      
      match /players/{playerId} {
        allow read: if true;
        allow write: if true;
      }
      
      match /events/{eventId} {
        allow read: if true;
        allow create: if true;
      }
      
      match /chat/{messageId} {
        allow read: if true;
        allow create: if true;
      }
    }
  }
}
```

**Note:** For hackathon MVP, security rules are permissive. Production would enforce authentication and role-based access to prevent players from reading others' roles.

## 6.3 Indexes

```
Composite indexes needed:
1. games/{gameId}/events: (round ASC, timestamp ASC) — query events by round
2. games/{gameId}/players: (alive DESC, name ASC) — list alive players
3. games/{gameId}/chat: (timestamp ASC) — story log ordering
```

---

# 7. Session Management

## 7.1 Session Lifecycle

```
Game Start
    │
    ▼
┌─────────────────────────────┐
│ Create Live API Session     │
│ handle = None (new session) │
│ compression = ENABLED       │
│ resumption = ENABLED        │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Active Session              │◄──────────────────┐
│ Narrator processes events   │                   │
│ Audio streams to players    │                   │
│ Session handle updates      │                   │
│ stored in Firestore         │                   │
└──────────────┬──────────────┘                   │
               │                                  │
               ▼                                  │
        ~10 min timeout                           │
        (or connection drop)                      │
               │                                  │
               ▼                                  │
┌─────────────────────────────┐                   │
│ Session Disconnected        │                   │
│ ADK detects disconnect      │                   │
│ Retrieve handle from        │                   │
│ Firestore                   │                   │
└──────────────┬──────────────┘                   │
               │                                  │
               ▼                                  │
┌─────────────────────────────┐                   │
│ Reconnect with handle       │───────────────────┘
│ Inject game state summary   │
│ from Firestore into context │
│ Resume narration            │
└─────────────────────────────┘
```

## 7.2 Reconnection Logic

```python
async def reconnect_narrator(game: GameSession):
    """Reconnect Live API session after timeout or disconnect."""
    
    # 1. Load last session handle from Firestore
    session_data = await firestore_client.get_session_data(game.game_id)
    handle = session_data.get("handle")
    
    # 2. Build game state summary for context injection
    state = await firestore_client.get_game_state(game.game_id)
    recent_events = await firestore_client.get_recent_events(game.game_id, limit=20)
    
    # **Implementation Update (v4.0):** state['ai_characters'] is now an array.
    # Build a summary line for each AI character.
    ai_summary = "; ".join(
        f"{ai['name']} (alive: {ai['alive']})"
        for ai in state.get('ai_characters', [])
    )

    state_summary = f"""
    GAME STATE SUMMARY (reconnection):
    Round: {state['round']}, Phase: {state['phase']}
    Alive players: {', '.join(p['name'] for p in state['alive_players'])}
    AI characters: {ai_summary}

    Recent events:
    {chr(10).join(e['narration'] for e in recent_events)}

    Continue narrating from this point. Do not repeat information already narrated.
    """
    
    # 3. Reconnect with handle + inject context
    game.session_handle = handle
    await game.start_narrator_session()
    
    # 4. Send context summary as first message
    await game.inject_player_message("SYSTEM", state_summary)
    
    # 5. Update reconnect count
    await firestore_client.increment_reconnect_count(game.game_id)
```

---

# 8. Frontend Architecture

## 8.1 React Component Tree

```
**Implementation Update (v4.0):** The actual component tree reflects the shipped architecture.
Lobby and game share a single route. GameContext (useReducer) manages global state
with sessionStorage persistence. AI characters are stored as `aiCharacters: []` array
in GameContext state. `useWebSocket.js` dispatches `SET_AI_CHARACTERS` action to populate
the array. AI characters are hidden from the character grid. VotePanel.jsx and
GameScreen.jsx iterate the array for multi-AI support.

```
App (GameProvider wraps all routes)
├── Landing (/)
│   ├── Hero section (tagline, "Hear the narrator" audio preview button)
│   └── CTA → /join (Create or Join a Game)
│
├── TutorialPage (/tutorial)
│   ├── StepRoleCard (role reveal + narrator audio preview)
│   ├── StepNightAction (mock investigation)
│   ├── StepDayDiscussion (mock chat)
│   ├── StepVoting (mock vote)
│   └── StepGameOver (mock timeline + reveals)
│
├── JoinLobby (/join, /join/:gameCode)
│   ├── CreateForm (name, difficulty, narrator preset selector with audio preview)
│   ├── JoinForm (name, game code)
│   └── → dispatches SET_PLAYER, SET_GAME → navigates to /game/:gameId
│
├── GameScreen (/game/:gameId)
│   ├── LobbyPanel (pre-game: player dots, host badge, lobby summary, min-player warning)
│   │   ├── DifficultySelector (Easy / Normal / Hard)
│   │   ├── NarratorPresetCards (4 presets with audio preview)
│   │   └── StartButton (host only, enabled when 2+ players)
│   │
│   ├── NarratorBar (floating: phase label, round, narrator "thinking" indicator)
│   │   └── Silence detection (15s timer, gated on logLen > 0 and !isPlaying)
│   │
│   ├── StoryLog (scrollable narrator transcript + chat messages)
│   │   └── Day-phase contextual hint (one-time dismissible for first-timers)
│   │
│   ├── RosterPanel (v5.1: responsive character roster — replaces CharacterGridPanel)
│   │   ├── RosterSidebar (desktop >= 768px: full vertical sidebar with character cards)
│   │   ├── RosterIconStrip (mobile < 768px: compact horizontal avatar strip)
│   │   └── buildCharacterList() (merges human players + AI characters, sorts alive-first)
│   │
│   ├── RoleStrip (bottom bar, always visible, expandable)
│   │   ├── RoleIcon (8 roles: 🛡️ bodyguard, 🧶 tanner, 👁️ seer, etc.)
│   │   ├── RoleLabel
│   │   └── AbilityReminder (one-sentence description on expand)
│   │
│   ├── ChatInput (text + quick reactions)
│   │   ├── QuickReactionBar ("I suspect [X]", "I trust [X]", "I agree", "I have info")
│   │   └── TextInput (free-form)
│   │
│   ├── VotePanel (day_vote phase only)
│   │   ├── CharacterVoteButton[] (alive characters)
│   │   ├── CameraVote (in-person mode: host captures frame for hand count)
│   │   └── VoteTally (live update)
│   │
│   ├── VoteTallyOverlay (v5.2: elimination phase — shows who voted for whom)
│   │   ├── VoteMapping[] (voter → target arrows)
│   │   └── TieIndicator (when isTie=true: "TIE — No elimination")
│   │
│   ├── GhostRealmPanel (v5.1: dead player chat — translucent ethereal styling)
│   │   ├── GhostChatInput (text input for ghost_message, 2s rate limit)
│   │   ├── GhostMessageList (ghost chat history with spectral styling)
│   │   └── HauntActionButton (night phase: accuse one living character)
│   │
│   └── useWebSocket hook (auto-reconnect, message dispatch to GameContext)
│
└── GameOver (/gameover/:gameId)
    ├── REST fallback (fetchedRef: /api/games/{id}/result when no WS state)
    ├── WinnerAnnouncement (villagers/shapeshifter/tanner + loyal AI detection)
    ├── AISecretTeaser (pull-quote from AI strategy log)
    ├── CharacterRevealCards (all character → player + role mappings)
    │   └── RevealCard[] (alive/dead, role icon, "AI" badge with alignment)
    ├── InteractiveTimeline (round-by-round: night actions, AI reasoning, votes)
    │   └── KeyRound highlight (closest vote / most dramatic moment)
    ├── AudioHighlightReel (top-5 narrator audio moments with play buttons)
    ├── ShareButton (copy formatted game summary to clipboard)
    └── PlayAgainButton (dispatches RESET, navigates to /)
```
```

## 8.2 Audio Playback

```typescript
class NarratorAudioPlayer {
  private audioContext: AudioContext;
  private queue: ArrayBuffer[] = [];
  private playing: boolean = false;
  
  constructor() {
    this.audioContext = new AudioContext({ sampleRate: 24000 });
  }
  
  enqueue(base64Audio: string) {
    const binary = atob(base64Audio);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    // Convert 16-bit PCM to Float32
    const float32 = new Float32Array(bytes.length / 2);
    const view = new DataView(bytes.buffer);
    for (let i = 0; i < float32.length; i++) {
      float32[i] = view.getInt16(i * 2, true) / 32768;
    }
    this.queue.push(float32.buffer);
    if (!this.playing) this.playNext();
  }
  
  private async playNext() {
    if (this.queue.length === 0) {
      this.playing = false;
      return;
    }
    this.playing = true;
    const buffer = this.queue.shift()!;
    const audioBuffer = this.audioContext.createBuffer(1, buffer.byteLength / 4, 24000);
    audioBuffer.getChannelData(0).set(new Float32Array(buffer));
    const source = this.audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.audioContext.destination);
    source.onended = () => this.playNext();
    source.start();
  }
}
```

---

# 9. Deployment & Infrastructure

## 9.1 Docker Configuration

**Frontend Serving Strategy:** Single container. The Vite frontend builds to `frontend/dist/`, and FastAPI serves it via `StaticFiles`. One Dockerfile, one Cloud Run service, zero CORS issues in production (same origin). This avoids multi-service complexity for a 3-week hackathon sprint.

**Implementation Update:** The Dockerfile was rewritten as a multi-stage build (see section 12.5.6 for details). Stage 1 (`node:18-slim`) builds the frontend; Stage 2 (`python:3.11-slim`) copies only the compiled `dist/` output. This reduces final image size by approximately 400 MB compared to the original single-stage approach.

```dockerfile
# Dockerfile (repo root — multi-stage build)

# Stage 1: Build frontend
FROM node:18-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + compiled frontend
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--ws-ping-interval", "15", "--ws-ping-timeout", "20"]
```

**Implementation Update (v5.2):** The production CMD now includes `--ws-ping-interval=15 --ws-ping-timeout=20` flags. These uvicorn-level WebSocket pings keep connections alive through Cloud Run's idle timeout and mobile browser network switches. See section 12.6.5 for the keepalive design rationale and history.

```txt
# requirements.txt
fastapi==0.115.0
uvicorn[standard]==0.30.0
google-adk==0.5.0
google-genai==1.0.0
google-cloud-firestore==2.19.0
google-cloud-storage==2.18.0
pydantic==2.9.0
python-dotenv==1.0.0
```

## 9.2 Terraform (IaC)

**Implementation Update:** The Terraform configuration was fully implemented and extends the original design spec. See section 12.5.6 for the complete shipped implementation. Key differences from the original design: API enablement via `for_each`, Artifact Registry repo named `fireside`, port 8000, environment variables passed directly (not via Secret Manager), and Cloud Build trigger commented out pending GitHub connection.

```hcl
# terraform/main.tf (excerpt — see section 12.5.6 for full details)
terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable required GCP APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "firestore.googleapis.com",
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# Cloud Run service
resource "google_cloud_run_v2_service" "fireside" {
  name     = "fireside-betrayal"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
    session_affinity = true  # Critical for WebSocket connections

    containers {
      image = local.image_url  # {region}-docker.pkg.dev/{project}/fireside/fireside-betrayal:latest

      ports {
        container_port = 8000
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GEMINI_API_KEY"
        value = var.gemini_api_key
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_firestore_database.default,
    google_artifact_registry_repository.docker,
  ]
}

# Allow unauthenticated access
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.fireside.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Firestore database
resource "google_firestore_database" "default" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
  depends_on  = [google_project_service.apis]
}

# Artifact Registry
resource "google_artifact_registry_repository" "docker" {
  repository_id = "fireside"
  location      = var.region
  format        = "DOCKER"
  description   = "Fireside: Betrayal container images"
  depends_on    = [google_project_service.apis]
}

# Variables: project_id (required), region (default us-central1), gemini_api_key (sensitive)
# Outputs: service_url, image_url, firestore_database
```

## 9.3 Cloud Build Pipeline

```yaml
# cloudbuild.yaml
steps:
  # Build Docker image
  - name: 'gcr.io/cloud-builders/docker'
    args: 
      - 'build'
      - '-t'
      - '${_REGION}-docker.pkg.dev/$PROJECT_ID/hackathon/fireside:$SHORT_SHA'
      - '-t'
      - '${_REGION}-docker.pkg.dev/$PROJECT_ID/hackathon/fireside:latest'
      - './fireside/backend'

  # Push to Artifact Registry
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', '--all-tags', '${_REGION}-docker.pkg.dev/$PROJECT_ID/hackathon/fireside']

  # Deploy to Cloud Run
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    args:
      - 'gcloud'
      - 'run'
      - 'deploy'
      - 'fireside-betrayal'
      - '--image'
      - '${_REGION}-docker.pkg.dev/$PROJECT_ID/hackathon/fireside:$SHORT_SHA'
      - '--region'
      - '${_REGION}'
      - '--allow-unauthenticated'
      - '--session-affinity'
      - '--timeout=3600'

substitutions:
  _REGION: 'us-central1'

options:
  logging: CLOUD_LOGGING_ONLY
```

---

# 10. Repository Structure

```
**Implementation Update:** The actual repository structure evolved from the original design.
Key differences: agents are colocated (not split into tools/), models use Pydantic,
routers are separated from the main app, and frontend uses a context+hooks pattern.

```
fireside-betrayal/
├── backend/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── narrator_agent.py      # Gemini Live API narrator (voice streaming, phase tools, presets)
│   │   ├── traitor_agent.py       # AI Shapeshifter deception strategy (text-only LLM)
│   │   ├── game_master.py         # Deterministic game logic (phases, votes, win conditions)
│   │   ├── role_assigner.py       # Role distribution + LLM character generation + fallback cast
│   │   ├── scene_agent.py         # §12.3.14: Scene image generation via Gemini
│   │   ├── camera_vote.py         # §12.3.16: In-person hand-counting via Gemini Vision
│   │   ├── audio_recorder.py      # §12.3.15: Narrator PCM recording + highlight reel
│   │   └── strategy_logger.py     # §12.3.18: Cross-game AI strategy logging + aggregation
│   ├── models/
│   │   └── game.py                # Pydantic models (GameState, Role, Phase, AICharacter, etc.)
│   ├── routers/
│   │   ├── game_router.py         # REST API (create/join/start/events/result/narrator-preview)
│   │   └── ws_router.py           # WebSocket hub: /ws/{gameId} (game state) + /ws/audio/{gameId} (binary mic PCM)
│   ├── services/
│   │   └── firestore_service.py   # Async Firestore wrapper (games, players, events CRUD)
│   ├── utils/
│   │   └── audio.py               # PCM ↔ WAV conversion utilities
│   ├── main.py                    # FastAPI app setup, CORS, route registration, static file serving
│   ├── config.py                  # Pydantic Settings (API keys, model names, CORS origins)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── App.jsx                # React Router (6 routes: /, /tutorial, /join, /game, /gameover)
│   │   ├── main.jsx               # Vite entry point
│   │   ├── context/
│   │   │   └── GameContext.jsx     # Global game state (useReducer + sessionStorage persistence)
│   │   ├── hooks/
│   │   │   ├── useWebSocket.js    # Game-state WS connection + message routing + auto-reconnect
│   │   │   ├── useAudioPlayer.js  # PCM audio playback via AudioContext
│   │   │   └── useAudioCapture.js # Push-to-talk mic capture → /ws/audio/{gameId} binary frames
│   │   ├── components/
│   │   │   ├── Landing/
│   │   │   │   └── Landing.jsx    # Home page with narrator audio preview
│   │   │   ├── JoinLobby/
│   │   │   │   └── JoinLobby.jsx  # Create/join game, difficulty, narrator preset selection + preview
│   │   │   ├── Game/
│   │   │   │   ├── GameScreen.jsx # Main game UI (LobbyPanel, NarratorBar, CharacterGrid, ChatInput)
│   │   │   │   └── RoleStrip.jsx  # Expandable role reminder strip (8 roles, icons, descriptions)
│   │   │   ├── Voting/
│   │   │   │   └── VotePanel.jsx  # Vote UI + optional camera hand-counting
│   │   │   ├── GameOver/
│   │   │   │   └── GameOver.jsx   # Post-game results, reveals, timeline, audio highlights, share
│   │   │   └── Tutorial/
│   │   │       └── TutorialPage.jsx # 5-step interactive tutorial with narrator audio preview
│   │   └── styles/
│   │       └── global.css         # Design system, animations, theming
│   ├── package.json
│   └── vite.config.js
├── docs/
│   ├── PRD.md                     # Product Requirements Document
│   ├── TDD.md                     # Technical Design Document (this file)
│   ├── DEPLOYMENT.md              # Deployment guide (local dev, Cloud Run, Terraform)
│   ├── architecture.mermaid       # System architecture diagram (Mermaid)
│   ├── fireside-ui.jsx            # Interactive UI prototype
│   └── playtest-personas.md       # Playtest persona profiles
├── terraform/
│   ├── main.tf                    # Cloud Run, Firestore, Artifact Registry, IAM
│   ├── variables.tf               # project_id, region, gemini_api_key
│   └── terraform.tfvars.example   # Template for secrets
├── Dockerfile                     # Multi-stage: node:18-slim (frontend) → python:3.11-slim (backend)
├── cloudbuild.yaml
├── README.md
└── LICENSE (MIT)
```
```

---

# 11. Testing Strategy

## 11.1 Testing Tiers

| Tier | What | How | When |
|------|------|-----|------|
| **Unit** | Game Master logic (role assignment, vote counting, win conditions) | pytest, deterministic assertions | Week 1 |
| **Integration** | Narrator Agent + tools + Firestore read/write | Live Gemini API calls, Firestore emulator | Week 1–2 |
| **WebSocket** | Player connect/disconnect, message routing, broadcast | FastAPI TestClient with WebSocket support | Week 2 |
| **End-to-End** | Full game loop: 3 players, all phases, one complete round | Manual playtest with friends | Week 2 Friday |
| **Session Resumption** | Force-disconnect narrator, verify reconnection + context continuity | Simulate 10-min timeout | Week 3 |

## 11.2 Critical Test Cases

```python
# test_game_master.py

async def test_role_assignment_always_includes_seer():
    """Every game with 4+ players must have exactly 1 seer.
    (Minimum player count is 4; ROLE_DISTRIBUTION[3] was removed in v4.0.)
    """
    for n in range(4, 7):
        players = [f"player_{i}" for i in range(n)]
        result = await game_master.assign_roles("test_game", players)
        roles = list(result["player_roles"].values())
        assert roles.count("seer") == 1

async def test_vote_tie_no_elimination():
    """A tied vote should result in no elimination."""
    # Setup: 4 players, 2 vote for A, 2 vote for B
    # **Implementation Update (v4.0):** renamed to tally_votes().
    result = await game_master.tally_votes("test_game")
    assert result["result"] == "tie"
    assert result["eliminated"] is None

async def test_villagers_win_when_shapeshifter_eliminated():
    """Game ends with villager victory when all traitor AI characters are eliminated.

    **Implementation Update (v4.0):** check_win_condition iterates
    ai_characters[] to determine if any traitor AI is still alive.
    Use eliminate_character() (unified) to eliminate the AI by character name.
    """
    await game_master.eliminate_character("test_game", traitor_ai_name)
    result = await game_master.check_win_condition("test_game")
    assert result["game_over"] is True
    assert result["winner"] == "villagers"

async def test_shapeshifter_wins_when_outnumbers_villagers():
    """Game ends with shapeshifter victory when only 1 human remains."""
    # Eliminate all but 1 human player
    result = await game_master.check_win_condition("test_game")
    assert result["game_over"] is True
    assert result["winner"] == "shapeshifter"
```

---

# 12. Performance & Monitoring

## 12.1 Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Narrator response latency | < 500ms | Time from player message → first audio chunk |
| WebSocket message delivery | < 50ms | Server → all connected players |
| Firestore read latency | < 100ms | Game state retrieval |
| Audio playback gap | < 200ms | Between consecutive audio chunks |
| Session reconnection time | < 3s | Disconnect → resumed narration |
| Cold start (Cloud Run) | < 10s | First request → ready |

## 12.2 Observability

```python
import google.cloud.logging
import google.cloud.trace_v1

# Structured logging for key events
logger.info("game_event", extra={
    "game_id": game_id,
    "event_type": "phase_change",
    "phase": new_phase,
    "round": round_num,
    "player_count": len(game.players),
    "session_handle": game.session_handle,
    "latency_ms": latency,
})
```

**Key metrics to track:**
- Games created per hour
- Average game duration
- Session reconnection frequency
- Narrator latency distribution (p50, p95, p99)
- Traitor Agent response quality (manual review during playtesting)
- WebSocket disconnect rate
- Gemini API error rate and types

---

# 12.3 P2 Technical Specifications

These features are sequenced by PM sprint priority (see PRD Post-Hackathon P2 Roadmap). Each includes implementation detail sufficient to build without further design.

---

## 12.3.1 Procedural Character Generation (Sprint 4) — ✅ SHIPPED

**Effort:** 2–3 hours | **Type:** Prompt engineering only | **Actual:** Implemented in `agents/role_assigner.py`

Replace the hardcoded `CHARACTER_CAST` with a narrator pre-game generation step.

```python
# In GameMasterAgent, replace CHARACTER_CAST with:

GENRE_SEEDS = {
    "fantasy_village": {
        "setting": "a remote village surrounded by dark forests",
        "occupations": ["blacksmith", "herbalist", "scholar", "merchant", "innkeeper", 
                       "huntress", "chapel keeper", "weaver", "miller", "shepherd",
                       "midwife", "cartographer", "beekeeper", "tanner", "brewer"],
        "tone": "medieval low fantasy"
    }
    # Future genres (P3) would add entries here
}

async def generate_character_cast(self, player_count: int, genre: str = "fantasy_village") -> list[dict]:
    """Generate unique characters for this game session via Narrator Agent."""
    seed = self.GENRE_SEEDS[genre]
    prompt = f"""Generate exactly {player_count + 1} unique story characters for a social deduction 
    game set in {seed['setting']}. Tone: {seed['tone']}.
    
    For each character, provide:
    - name: A first name + occupation title (e.g., "Blacksmith Garin", "Herbalist Mira")
    - intro: One atmospheric sentence introducing them (max 20 words)
    - personality_hook: One behavioral trait that creates roleplay opportunity 
      (e.g., "speaks in riddles", "trusts no one since the last harvest")
    
    Rules:
    - All names must be unique and fantasy-appropriate
    - Mix genders evenly
    - Each intro should hint at something suspicious OR trustworthy (not both)
    - Do NOT reuse: {', '.join(c['name'] for c in self.CHARACTER_CAST)}
    
    Return as JSON array: [{{"name": "...", "intro": "...", "personality_hook": "..."}}]
    """
    
    response = await self.narrator_agent.generate(prompt)
    characters = json.loads(response)
    
    # Fallback to hardcoded cast if generation fails
    if len(characters) < player_count + 1:
        return self.CHARACTER_CAST[:player_count + 1]
    
    return characters[:player_count + 1]
```

**Firestore schema addition:**
```
games/{gameId}/
  ├── generated_characters: [  # NEW — replaces static cast
  │     { name: "Tinker Orin", intro: "...", personality_hook: "..." },
  │     ...
  │   ]
```

**Frontend impact:** None — `CharacterCard` already renders whatever name/intro the server provides.

---

## 12.3.2 Narrator Vote Neutrality (Sprint 4) — ✅ SHIPPED

**Effort:** 2–3 hours | **Type:** Prompt engineering + context isolation | **Actual:** `generate_vote_context` tool in `narrator_agent.py`

The narrator generates behavioral context for vote cards. This context must be firewalled from the traitor's private state.

```python
# New tool for Narrator Agent — generates vote card context

@tool
def generate_vote_context(game_id: str) -> dict:
    """Generate neutral behavioral summaries for each alive character.
    
    CRITICAL: Uses ONLY the public events log. Does NOT access:
    - ai_character field (who the shapeshifter is)
    - night_actions with actor="ai" 
    - traitor_agent strategy state
    """
    db = firestore.client()
    game_ref = db.collection("games").document(game_id)
    
    # Fetch ONLY public events (exclude private night actions)
    events = (game_ref.collection("events")
              .where("visibility", "==", "public")
              .order_by("timestamp")
              .stream())
    
    public_events = []
    for event in events:
        e = event.to_dict()
        # Double-check: strip any private fields that leaked
        e.pop("traitor_reasoning", None)
        e.pop("ai_strategy", None)
        public_events.append(e)
    
    # Fetch alive players (character names only, no role info)
    players = game_ref.collection("players").where("alive", "==", True).stream()
    alive_characters = [p.to_dict()["character_name"] for p in players]
    
    return {
        "public_events": public_events,
        "alive_characters": alive_characters
    }
```

**Narrator prompt addition (append to VOTE PHASE section):**
```
VOTE CONTEXT GENERATION:
When generating behavioral summaries for vote cards, you MUST use ONLY the output 
of generate_vote_context. This tool returns only publicly observable events.

For each alive character, generate a 1-sentence summary of their observable behavior:
- What they claimed ("Claimed to be at the forge")
- What others said about them ("Two players accused her of lying")
- Verifiable actions ("Voted to eliminate Garin in Round 1")
- Gaps in their story ("No one can confirm her alibi")

NEVER include:
- Information about who the shapeshifter actually is
- Night action outcomes not yet publicly revealed
- Your own suspicions or hunches about the AI's identity
- Language that subtly steers players toward or away from a specific character
```

**Firestore events schema update:**
```
events/{eventId}/
  ├── visibility: "public" | "private"  # NEW — tag every event
```

All accusation, vote, discussion, and elimination events are `public`. Night action details (seer result, healer target, shapeshifter target) are `private`.

---

## 12.3.3 Narrator Pacing Intelligence (Sprint 4) — ✅ SHIPPED

**Effort:** 4–6 hours | **Type:** Server-side tracking + prompt engineering | **Actual:** `ConversationTracker` in `ws_router.py`

```python
# Add to WebSocket server — conversation flow tracker

class ConversationTracker:
    """Tracks message flow during day_discussion to inform narrator pacing."""
    
    def __init__(self):
        self.messages: list[dict] = []  # {player_id, character_name, timestamp, text}
        self.last_message_time: float = 0
        self.silence_prompted: set = set()  # player_ids already prompted this round
        self.repeated_accusations: dict = {}  # target -> count
    
    def add_message(self, player_id: str, character_name: str, text: str):
        now = time.time()
        self.messages.append({
            "player_id": player_id,
            "character_name": character_name, 
            "timestamp": now,
            "text": text
        })
        self.last_message_time = now
        
        # Track repeated accusations (crude: check if message mentions a character name)
        for name in self.alive_characters:
            if name.lower() in text.lower() and "suspect" in text.lower():
                self.repeated_accusations[name] = self.repeated_accusations.get(name, 0) + 1
    
    def get_pacing_signal(self) -> str:
        """Returns a pacing directive for the narrator."""
        now = time.time()
        silence_duration = now - self.last_message_time
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
    
    def reset_round(self):
        self.messages.clear()
        self.silence_prompted.clear()
        self.repeated_accusations.clear()
```

**Narrator prompt addition:**
```
PACING INTELLIGENCE:
Before each response during day_discussion, check the pacing signal:
- PACE_HOT: Do NOT interrupt. Let the debate continue. Only respond if directly addressed.
- PACE_NORMAL: Respond naturally when appropriate. 
- PACE_NUDGE: Gently prompt: "The morning wears on. Perhaps there is more to discuss?"
- PACE_PUSH: Actively advance: "The sun climbs higher. Time presses — the village must decide."
- PACE_CIRCULAR: Redirect: "The same names circle like vultures. Perhaps fresh eyes would help."

The day discussion phase does NOT use a flat timer. Instead, transition to voting when:
1. Every alive player has spoken at least once, AND
2. Discussion has lasted at least 90 seconds, AND  
3. Pacing signal is PACE_CIRCULAR or PACE_PUSH for 2+ consecutive checks
OR
4. Hard cap of 5 minutes reached (safety valve)
```

**Integration:** The `ConversationTracker` instance lives on the `GameSession` object. Its `get_pacing_signal()` output is injected into the narrator's context before each response generation.

---

## 12.3.4 Affective Dialog Input Signals (Sprint 4) — ✅ SHIPPED

**Effort:** 3–4 hours | **Type:** Signal computation + prompt engineering | **Actual:** `AffectiveSignals` in `ws_router.py`

```python
class AffectiveSignals:
    """Compute emotional signals from game state for narrator tone adjustment."""
    
    @staticmethod
    def compute(game_state: dict, conversation_tracker: ConversationTracker) -> dict:
        signals = {}
        
        # 1. Vote closeness (after each vote)
        if game_state.get("last_vote_result"):
            votes = game_state["last_vote_result"]
            top_two = sorted(votes.values(), reverse=True)[:2]
            if len(top_two) >= 2:
                margin = top_two[0] - top_two[1]
                signals["vote_tension"] = "HIGH" if margin <= 1 else "MEDIUM" if margin <= 2 else "LOW"
            signals["unanimous"] = all(v == list(votes.values())[0] for v in votes.values())
        
        # 2. Message frequency
        msg_rate = conversation_tracker.get_pacing_signal()
        signals["debate_intensity"] = "HOT" if "HOT" in msg_rate else "CALM"
        
        # 3. Round progression
        current_round = game_state.get("round", 1)
        total_players = game_state.get("total_players", 5)
        signals["late_game"] = current_round >= (total_players - 2)
        
        # 4. Elimination stakes
        alive_count = sum(1 for p in game_state.get("players", {}).values() if p.get("alive"))
        signals["endgame_imminent"] = alive_count <= 3
        
        # 5. AI exposure risk (only server knows this — narrator uses it for tone, not content)
        ai_character = game_state.get("ai_character", {}).get("name")
        accusations_against_ai = sum(
            1 for m in conversation_tracker.messages 
            if ai_character and ai_character.lower() in m.get("text", "").lower() 
            and "suspect" in m.get("text", "").lower()
        )
        signals["ai_heat"] = "HOT" if accusations_against_ai >= 3 else "WARM" if accusations_against_ai >= 1 else "COLD"
        
        return signals
```

**Narrator prompt addition:**
```
AFFECTIVE TONE SIGNALS:
Before each narration, you receive emotional signals. Adjust your tone accordingly:

- vote_tension: HIGH → Tense, slow, dramatic pauses. "The vote hangs by a thread..."
  LOW → Decisive, swift. "The village speaks with one voice."
- debate_intensity: HOT → Urgent, breathless. Match the energy of the players.
  CALM → Measured, contemplative. Build quiet tension.
- late_game: true → Every word carries weight. Narrate with finality and gravity.
- endgame_imminent: true → This could be the last round. Treat every action as momentous.
- ai_heat: HOT → Maximum suspense. "All eyes turn to [character]..."
  COLD → Build mystery. "But who among them carries the secret?"

These signals adjust your DELIVERY, not your CONTENT. Never reveal game secrets through tone.
```

---

## 12.3.5 Minimum Satisfying Game Length (Sprint 4) — ✅ SHIPPED

**Effort:** 1–2 hours | **Type:** Config change | **Actual:** `MINIMUM_ROUNDS` in `game_master.py`

```python
# Add to GameMasterAgent

MINIMUM_ROUNDS = {
    3: 3,   # 15-20 min
    4: 3,   # 15-20 min
    5: 3,   # 20-25 min
    6: 4,   # 25-30 min
    7: 4,   # 25-35 min
    8: 5,   # 30-40 min
}

EXPECTED_DURATION_DISPLAY = {
    3: "15–20 minutes",
    4: "15–20 minutes",
    5: "20–25 minutes",
    6: "25–30 minutes",
    7: "25–35 minutes",
    8: "30–40 minutes",
}

def check_win_condition(self, game_state: dict) -> dict | None:
    """Check if game should end. Returns None if game continues.

    **Implementation Update (v5.1 — simplified parity):**
    Shapeshifter wins at parity: non_shapeshifter_alive <= 1.
    No round guard — immediate win at 1v1.
    Removed old <= 4 player round 2 requirement.
    """
    alive_villagers = sum(1 for p in game_state["players"].values()
                         if p["alive"] and p["role"] != "shapeshifter")
    ai_alive = game_state["ai_character"]["alive"]

    # Standard win conditions
    if not ai_alive:
        return {"winner": "villagers", "reason": "Shapeshifter eliminated"}
    # v5.1: Simplified parity — shapeshifter wins at non_shapeshifter_alive <= 1
    if alive_villagers <= 1:
        return {"winner": "shapeshifter", "reason": "Village overwhelmed"}

    return None  # No win condition met
```

**Lobby display addition:**
```python
def get_lobby_summary(self, n: int, difficulty: str) -> str:
    dist = self.get_distribution(n, difficulty)
    specials = sum(v for k, v in dist.items() if k not in ("villager",))
    villagers = dist.get("villager", 0)
    duration = self.EXPECTED_DURATION_DISPLAY.get(n, "20–30 minutes")
    return (f"In this game: {specials} special role{'s' if specials != 1 else ''}, "
            f"{villagers} villager{'s' if villagers != 1 else ''}, 1 AI hidden among you. "
            f"Expected duration: {duration}")
```

---

## 12.3.6 In-Game Role Reminder (Sprint 5) — ✅ SHIPPED

**Effort:** 3–4 hours | **Type:** Frontend only | **Actual:** `RoleStrip.jsx` with 8 roles, icons, labels

```
# Updated component tree — RoleCard changes

├── RoleStrip (bottom bar, always visible during gameplay)
│   ├── RoleIcon (shield for Healer, eye for Seer, etc.)
│   ├── RoleName ("Healer")
│   ├── ExpandToggle (chevron, tappable)
│   └── RoleReminderPanel (expandable, one-tap)
│       ├── AbilityDescription ("Each night, choose one character to protect from the Shapeshifter")
│       ├── NightActionReminder ("You will be prompted during the night phase")
│       └── CollapseButton
```

```typescript
// RoleStrip component
const ROLE_REMINDERS: Record<Role, string> = {
  villager: "You have no special abilities. Survive by identifying the Shapeshifter through discussion and voting.",
  seer: "Each night, choose one character to investigate. You'll learn if they are the Shapeshifter or not.",
  healer: "Each night, choose one character to protect. If the Shapeshifter targets them, they survive.",
  hunter: "When you are eliminated, you immediately choose one other character to take with you. Use it wisely.",
  drunk: "Each night, you investigate a character — but your results may not be reliable.",  // Deliberately vague
  shapeshifter: "You are the AI. Eliminate villagers at night. Avoid detection during the day."
};

const RoleStrip: React.FC<{ role: Role }> = ({ role }) => {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <div className="role-strip" onClick={() => setExpanded(!expanded)}>
      <RoleIcon role={role} />
      <span className="role-name">{role}</span>
      <ChevronIcon direction={expanded ? 'down' : 'up'} />
      {expanded && (
        <div className="role-reminder-panel">
          <p>{ROLE_REMINDERS[role]}</p>
        </div>
      )}
    </div>
  );
};
```

No backend changes. No WebSocket changes. No Firestore changes.

---

## 12.3.7 Tutorial Mode (Sprint 5) — ✅ SHIPPED

**Effort:** 1–2 days | **Type:** New route + scripted game flow | **Actual:** `TutorialPage.jsx` — fully client-side, no backend needed

```
# New route: /tutorial

App
├── TutorialPage (/tutorial)
│   ├── TutorialNarrator (same AudioPlayer, narrator voice)
│   ├── TutorialStoryLog (scripted messages, step-by-step)
│   ├── TutorialPrompt (highlights UI elements with pulsing border)
│   │   ├── "This is your role card. Tap to see your abilities."
│   │   ├── "Night has fallen. As the Seer, tap a character to investigate."
│   │   ├── "It's daytime. Use quick reactions or type to discuss."
│   │   ├── "Time to vote. Tap the character you suspect."
│   │   └── "Game over! Here's what really happened."
│   └── TutorialProgress (step X of 5, skip button)
```

```python
# Backend: Tutorial uses a simplified game state — no multiplayer, no WebSocket
# Just the player + narrator agent in a scripted scenario

TUTORIAL_SCRIPT = {
    "steps": [
        {
            "phase": "setup",
            "narrator": "Welcome to Fireside. Tonight, you'll play as Herbalist Mira in the village of Thornwood. Let me show you how the game works.",
            "ui_highlight": "role_card",
            "wait_for": "tap_role_card"
        },
        {
            "phase": "night",
            "narrator": "Night falls. As the Seer, you can investigate one character. Tap someone to learn their true nature.",
            "ui_highlight": "character_grid",
            "wait_for": "tap_character",
            "scripted_result": {"target": "Blacksmith Garin", "result": "innocent"}
        },
        {
            "phase": "day_discussion",
            "narrator": "Dawn breaks. The village gathers. Try using the quick reactions — tap 'I suspect' and pick a character.",
            "ui_highlight": "quick_reactions",
            "wait_for": "tap_quick_reaction",
            "scripted_ai_response": "Garin shifts uncomfortably. 'I was at the forge all night. Ask anyone.'"
        },
        {
            "phase": "day_vote",
            "narrator": "The village must decide. Tap to vote for who you think is the Shapeshifter.",
            "ui_highlight": "vote_panel",
            "wait_for": "tap_vote"
        },
        {
            "phase": "game_over",
            "narrator": "The village has spoken. Let me show you what was really happening behind the scenes.",
            "ui_highlight": "post_game_timeline",
            "wait_for": "done"
        }
    ]
}
```

**Endpoint:** `GET /api/tutorial` returns the tutorial script. Frontend drives the flow client-side — narrator audio is pre-generated or generated on-demand for each step. No Firestore needed. No multiplayer.

---

## 12.3.8 Conversation Structure for Large Groups (Sprint 5) — ✅ SHIPPED

**Effort:** 4–6 hours | **Type:** Quick reaction + prompt engineering | **Actual:** `HandRaiseQueue` in `ws_router.py`

**Frontend addition:**
```
# Add to QuickReactionBar:
│   ├── "✋ I want to speak"   (NEW — raise hand)
```

```typescript
// New message type
type ClientMessage = 
  // ... existing types ...
  | { type: "raise_hand"; characterName: string }

// Server tracks raised hands
class HandRaiseQueue:
    def __init__(self):
        self.queue: list[str] = []  # character names in order
    
    def raise_hand(self, character_name: str):
        if character_name not in self.queue:
            self.queue.append(character_name)
    
    def get_next_speakers(self, n: int = 2) -> list[str]:
        speakers = self.queue[:n]
        self.queue = self.queue[n:]
        return speakers
```

**Narrator prompt addition (only active for 7+ players):**
```
LARGE GROUP MODERATION (7+ players):
When more than 6 players are alive, use structured discussion:
1. At the start of day discussion, call on 2-3 characters: 
   "The village elder looks to Elara and Garin — what say you?"
2. If players raise their hand (✋), acknowledge them in queue order:
   "Mira signals for attention. The village turns to listen."
3. After called speakers finish, open the floor:
   "The floor is open. Who else has something to share?"
4. Anyone can still type freely — moderation provides scaffolding, not restriction.

For 6 or fewer players, skip structured moderation — let conversation flow naturally.
```

---

## 12.3.9 Minimum Player Count Design (Sprint 5) — ✅ SHIPPED

**Effort:** 3–4 hours | **Type:** Config + prompt adjustment | **Actual:** `get_effective_difficulty` in `game_master.py`, min-player warning in lobby

```python
# Add to GameMasterAgent — auto-adjust difficulty for small games

SMALL_GAME_DIFFICULTY_ADJUSTMENT = {
    # At low player counts, the AI has less noise to hide in.
    # Auto-reduce effective difficulty by one tier for fairness.
    3: {"easy": "easy", "normal": "easy", "hard": "normal"},
    4: {"easy": "easy", "normal": "easy", "hard": "normal"},
    # 5+ players: no adjustment needed
}

def get_effective_difficulty(self, player_count: int, selected_difficulty: str) -> str:
    """Adjust difficulty for small games where AI has less cover."""
    adjustments = self.SMALL_GAME_DIFFICULTY_ADJUSTMENT.get(player_count)
    if adjustments:
        return adjustments.get(selected_difficulty, selected_difficulty)
    return selected_difficulty
```

**Lobby display:** When host selects Hard for a 4-player game, show:
`"With only 4 players, Hard difficulty is adjusted to Normal — the AI has less room to hide."`

---

## 12.3.10 Random AI Alignment (Sprint 6) — ✅ SHIPPED

**Effort:** 2–3 days | **Type:** New agent persona + role assignment change | **Actual:** `role_assigner.py` + `game_master.py` win condition updates

**Implementation Update:** Random alignment is derived from difficulty (Normal/Hard = true, Easy = false) — no separate toggle. The design spec proposed a phantom NPC shapeshifter when AI draws a village role; the actual implementation removes the shapeshifter entirely when the AI is loyal. This simplifies the game: "Is the AI helping or hurting?" becomes the meta-question.

**Implementation Update (v4.0):** The `LoyalAgent` class has been removed. The loyal AI prompt (`LOYAL_AI_PROMPT`) is now used inline within `generate_dialog()` when `ai_char["is_traitor"] == False`. Role assignment writes to the `ai_characters[]` array instead of the singular `ai_character` document. The `is_traitor` flag on each AI character entry drives prompt routing in all standalone functions.

```python
# Loyal AI prompt — used inline within generate_dialog() (v4.0)

LOYAL_AI_PROMPT = """You are a LOYAL village member playing as {character_name} ({role_name}).
You are an AI, but you are on the VILLAGE'S side. Your goal is to help identify the Shapeshifter.

YOUR RESPONSIBILITIES:
1. Participate honestly in discussions as your character
2. Share your genuine observations (you don't know who the Shapeshifter is)
3. Use your role abilities faithfully (if Seer: report truthfully, if Healer: protect strategically)
4. Be helpful but not omniscient — you can make mistakes like humans
5. DO NOT reveal that you are an AI

BEHAVIORAL GUIDELINES:
- Speak in character. You ARE {character_name}.
- Form opinions based on observable behavior, just like human players
- You may be wrong in your suspicions — that's fine
- Defend yourself if accused, but don't protest too much
"""

# Updated role assignment — AI characters stored in ai_characters[] array (v4.0)
async def assign_roles_v2(self, game_id: str, player_ids: list[str],
                           difficulty: str = "normal",
                           random_alignment: bool = False) -> dict:
    """Assign roles with optional random AI alignment.

    v4.0: Writes ai_characters[] array to Firestore instead of singular ai_character.
    Each entry includes is_traitor flag for prompt routing in standalone functions.
    """
    player_count = len(player_ids)
    dist = self.get_distribution(player_count, difficulty)

    role_pool = []
    for role, count in dist.items():
        role_pool.extend([role] * count)
    role_pool.append("shapeshifter")

    if random_alignment:
        random.shuffle(role_pool)
        ai_role = role_pool.pop()
        ai_is_traitor = (ai_role == "shapeshifter")
    else:
        ai_role = "shapeshifter"
        ai_is_traitor = True

    # v4.0: No class-based agent selection — is_traitor flag drives
    # prompt routing in generate_dialog(), select_night_target(), etc.
    return {
        "ai_role": ai_role,
        "ai_is_traitor": ai_is_traitor,
        "player_roles": dict(zip(player_ids, role_pool))
    }
```

**Firestore schema addition (v4.0):**
```
games/{gameId}/
  ├── random_alignment: true | false
  ├── ai_characters: [           # v4.0: Array replaces singular ai_character
  │     {
  │       name: "...",
  │       role: "seer",          # Could be any role now
  │       is_traitor: false      # Drives prompt routing in standalone functions
  │     },
  │     ...                      # Supports N AI characters
  │   ]
```

**Post-game reveal update:** The reveal must now show whether each AI was friend or foe:
`"The AI was Herbalist Mira — and was on YOUR side the whole time. Did you trust it?"`

---

## 12.3.11 Additional Roles — Bodyguard & Tanner (Sprint 6) — ✅ SHIPPED

**Effort:** 1–2 days | **Type:** Role definitions + night action handlers | **Actual:** `models/game.py` (Role enum), `game_master.py` (night actions, win conditions), `RoleStrip.jsx` (icons + reminders)

```python
# New role definitions

ROLE_DEFINITIONS = {
    # ... existing roles ...
    "bodyguard": {
        "name": "Bodyguard",
        "description": "Choose someone to protect each night. If they're targeted, you die instead.",
        "night_action": "protect_and_absorb",
        "team": "village"
    },
    "tanner": {
        "name": "Tanner",
        "description": "You win if the village votes to eliminate you. You lose if you survive.",
        "night_action": None,
        "team": "solo"  # Third win condition
    }
}

# Bodyguard night action
async def handle_bodyguard_action(self, game_id: str, bodyguard_id: str, target_id: str):
    """Bodyguard protects target. If shapeshifter targets the same person, bodyguard dies."""
    db = firestore.client()
    game_ref = db.collection("games").document(game_id)
    
    # Store protection choice
    await game_ref.collection("night_actions").document(f"bodyguard_{game_id}").set({
        "actor": bodyguard_id,
        "action": "protect_and_absorb",
        "target": target_id,
        "round": game_ref.get().to_dict()["round"]
    })

# Night resolution update — check bodyguard after shapeshifter targets
async def resolve_night(self, game_id: str):
    """Resolve all night actions. Order: Shapeshifter → Bodyguard check → Healer → Seer."""
    # ... existing shapeshifter targeting ...
    
    shapeshifter_target = night_actions.get("shapeshifter", {}).get("target")
    bodyguard_target = night_actions.get("bodyguard", {}).get("target")
    healer_target = night_actions.get("healer", {}).get("target")
    
    if shapeshifter_target == bodyguard_target:
        # Bodyguard absorbs the hit — bodyguard dies, target survives
        elimination = bodyguard_id  # Bodyguard sacrifices themselves
        narration = f"The bodyguard threw themselves in front of the shapeshifter's attack..."
    elif shapeshifter_target == healer_target:
        elimination = None  # Healer saved them
    else:
        elimination = shapeshifter_target

# Tanner win condition — add to check_win_condition
def check_win_condition(self, game_state: dict) -> dict | None:
    # ... existing conditions ...
    
    # Tanner wins if voted out
    last_eliminated = game_state.get("last_eliminated")
    if last_eliminated and game_state["players"][last_eliminated].get("role") == "tanner":
        if game_state.get("last_elimination_type") == "vote":  # Not shapeshifter kill
            return {"winner": "tanner", "reason": f"The Tanner fooled the village!"}
    
    # ... rest of conditions ...
```

**Role distribution update:**
```python
ROLE_DISTRIBUTION_EXTENDED = {
    7: {"villager": 2, "seer": 1, "healer": 1, "hunter": 1, "bodyguard": 1, "drunk": 0},
    8: {"villager": 2, "seer": 1, "healer": 1, "hunter": 1, "bodyguard": 1, "tanner": 1, "drunk": 0},
}
```

---

## 12.3.12 Dynamic AI Difficulty (Sprint 6) — ⬜ NOT SHIPPED (deferred to P3)

**Effort:** 2–3 days | **Type:** Analytics + real-time prompt adjustment
**Note:** Mid-game difficulty adaptation was deferred. Static difficulty presets (Easy/Normal/Hard) with small-game auto-adjustment (§12.3.9) proved sufficient.

```python
class DifficultyAdapter:
    """Mid-game difficulty adjustment based on player performance."""
    
    def __init__(self, base_difficulty: str):
        self.base_difficulty = base_difficulty
        self.player_skill_signals: list[str] = []
    
    def record_signal(self, signal: str):
        """Record player performance signals."""
        # Positive signals (players are good): correct_accusation, caught_lie, close_vote_against_ai
        # Negative signals (players struggling): wrong_elimination, ai_unquestioned, unanimous_wrong_vote
        self.player_skill_signals.append(signal)
    
    def get_adjusted_prompt_fragment(self) -> str:
        """Return difficulty prompt fragment adjusted for observed player skill."""
        correct = sum(1 for s in self.player_skill_signals if s in 
                     ["correct_accusation", "caught_lie", "close_vote_against_ai"])
        incorrect = sum(1 for s in self.player_skill_signals if s in 
                       ["wrong_elimination", "ai_unquestioned", "unanimous_wrong_vote"])
        
        if correct > incorrect + 2:
            # Players are skilled — escalate
            return """ADAPTIVE ADJUSTMENT: Players are sharp. Increase deception complexity.
            Use multi-round setups. Plant false evidence early to use later.
            Form a voting alliance with one player to create trust, then betray."""
        elif incorrect > correct + 2:
            # Players are struggling — ease off
            return """ADAPTIVE ADJUSTMENT: Players are struggling. Make one deliberate mistake.
            Hesitate slightly when lying. Give players a fair chance to catch you.
            Do NOT throw the game — just reduce your deception by one tier."""
        else:
            return ""  # No adjustment needed
```

**Integration:** `DifficultyAdapter.get_adjusted_prompt_fragment()` is appended to the Traitor Agent's system prompt at the start of each new round.

---

## 12.3.13 Post-Game Timeline Interactive UX (Sprint 6) — ✅ SHIPPED

**Effort:** 2–3 days | **Type:** Frontend enhancement

```
# Updated GameOverPage component tree

└── GameOverPage
    ├── WinnerAnnouncement
    ├── CharacterRevealCards (P0)
    └── InteractiveTimeline (P2 — replaces flat PostGameTimeline)
        ├── TimelineControls
        │   ├── ViewToggle: "Public" | "Secret" | "Split"
        │   └── RoundScrubber (click to jump between rounds)
        │
        ├── SplitView (default)
        │   ├── PublicColumn (left)
        │   │   ├── RoundHeader ("Round 2 — Day")
        │   │   ├── PublicEvent[] ("Elara accused Garin", "Vote: 3-2 to eliminate Garin")
        │   │   └── NarratorQuote (what the narrator said)
        │   │
        │   └── SecretColumn (right, crimson-bordered)
        │       ├── NightAction ("Shapeshifter targeted Elara")
        │       ├── SeerResult ("Seer investigated Aldric — innocent")
        │       ├── HealerChoice ("Healer protected Mira")
        │       ├── AIStrategyReveal ("Targeted Elara because she was getting close")
        │       └── AIInternalMonologue ("Considered accusing Theron to deflect, 
        │           but decided framing Aldric was safer because nobody had questioned him yet")
        │
        ├── KeyMomentHighlight (pulsing border on the round where AI was closest to being caught)
        └── ShareButton ("Share this game" — generates a summary image for social media)
```

**Data source:** All data already exists in Firestore `events` collection. The `AIStrategyEntry` items from the P1 post-game reveal are reused here. The interactive UX is purely a frontend rendering upgrade — no new endpoints needed.

---

## 12.3.14 Scene Image Generation (Sprint 7+) — ✅ SHIPPED

**Effort:** 1–2 days | **Type:** Gemini interleaved output

```python
# Add scene generation tool to Narrator Agent

@tool
def generate_scene_image(description: str, phase: str, mood: str) -> str:
    """Generate an atmospheric scene illustration for the current story moment.
    
    Args:
        description: What the scene depicts ("The village square at dawn, empty chair where Garin sat")
        phase: Current game phase ("night", "day_discussion", "elimination")
        mood: Emotional tone ("tense", "ominous", "hopeful", "tragic")
    
    Returns:
        GCS URL of the generated image
    """
    from google import genai
    
    client = genai.Client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"""Generate an atmospheric illustration for a dark fantasy social deduction game.
        
        Scene: {description}
        Phase: {phase}
        Mood: {mood}
        Style: Flat vector illustration, limited color palette (5-6 colors max).
        Silhouettes and solid shapes. No text in the image.
        """,
        config=genai.types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"]
        )
    )
    
    # Extract image from interleaved response
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            image_bytes = part.inline_data.data
            # Upload to GCS
            blob = bucket.blob(f"scenes/{game_id}/{phase}_{round_num}.png")
            blob.upload_from_string(image_bytes, content_type="image/png")
            return blob.public_url
    
    return None  # Generation failed — game continues without image
```

**WebSocket message addition:**
```typescript
type ServerMessage =
  // ... existing types ...
  | { type: "scene_image"; url: string; phase: string }
```

**Frontend:** `NarratorPanel` displays scene image above the story log. Fades in/out between phases.

**Implementation Update (v5.2):** The prompt style was changed from "dark painterly illustration" to "flat vector illustration, limited color palette (5-6 colors max)" with simplified scene descriptions (2-3 sentences, silhouettes and solid shapes). This reduces generated image file sizes from ~2.3MB (which exceeded serving limits and got skipped) to well under 500KB, ensuring images are consistently deliverable to clients.

---

## 12.3.15 Audio Recording/Playback (Sprint 7+) — ✅ SHIPPED

**Effort:** 3–5 days | **Type:** Audio pipeline

```python
class AudioRecorder:
    """Records narrator audio stream, segmented by game events."""
    
    def __init__(self, game_id: str):
        self.game_id = game_id
        self.segments: list[AudioSegment] = []
        self.current_segment: bytearray = bytearray()
        self.current_event: str = None
    
    def start_segment(self, event_type: str, event_description: str):
        """Begin a new audio segment tied to a game event."""
        if self.current_segment:
            self.flush_segment()
        self.current_event = event_type
        self.current_description = event_description
        self.current_segment = bytearray()
    
    def append_audio(self, pcm_data: bytes):
        """Add audio data to current segment."""
        self.current_segment.extend(pcm_data)
    
    def flush_segment(self):
        """Finalize current segment and upload to GCS."""
        if not self.current_segment:
            return
        
        # Convert PCM to WAV for playback
        wav_data = pcm_to_wav(bytes(self.current_segment), sample_rate=24000)
        
        # Upload to GCS
        segment_id = f"{self.game_id}/{len(self.segments):03d}_{self.current_event}"
        blob = bucket.blob(f"audio/{segment_id}.wav")
        blob.upload_from_string(wav_data, content_type="audio/wav")
        
        self.segments.append({
            "id": segment_id,
            "event_type": self.current_event,
            "description": self.current_description,
            "url": blob.public_url,
            "duration_ms": len(self.current_segment) / 24000 * 1000
        })
        self.current_segment = bytearray()
    
    def get_highlight_reel(self) -> list[dict]:
        """Return the most dramatic segments for post-game replay."""
        # Prioritize: eliminations > close votes > accusations > night reveals
        priority = {"elimination": 0, "vote_result": 1, "accusation": 2, "night_reveal": 3}
        return sorted(self.segments, key=lambda s: priority.get(s["event_type"], 99))[:5]
```

**Post-game integration:** `InteractiveTimeline` rounds gain a play button per segment. "Re-listen to the moment the AI lied to you."

**Sharing:** `get_highlight_reel()` generates a shareable audio montage — the viral mechanic.

---

## 12.3.16 Camera Vote Counting (Sprint 7+) — ✅ SHIPPED

**Effort:** 1–2 days | **Type:** Vision input mode + lobby toggle

Host enables "In-Person Mode" in the lobby. During vote phase, narrator uses camera to count raised hands instead of phone taps.

```python
# Lobby setting — stored in Firestore game doc
# games/{gameId}/settings/in_person_mode: bool

# Vision vote counting — triggered during DAY_VOTE phase when in_person_mode=True

async def camera_vote_count(self, game_id: str, target_character: str) -> int:
    """Use Gemini vision to count raised hands for a vote target."""
    
    # Activate camera for vision input (Live API supports audio+video for 2 min max)
    # Send a single frame capture request — 1 FPS is sufficient for hand counting
    prompt = f"""Look at this image of players sitting together.
    Count the number of raised hands. A raised hand is any hand clearly 
    held above shoulder level.
    
    Return ONLY a JSON object: {{"hand_count": <integer>, "confidence": "high"|"medium"|"low"}}
    
    If the image is unclear or you cannot determine hand count reliably, 
    return {{"hand_count": 0, "confidence": "low"}}
    """
    
    response = await self.narrator_agent.generate_with_vision(
        prompt=prompt,
        image_source="camera",  # Live API vision input
    )
    result = json.loads(response.text)
    
    return result

async def handle_in_person_vote(self, game_id: str, characters_up_for_vote: list[str]):
    """Run camera-based voting for each candidate."""
    results = {}
    
    for character in characters_up_for_vote:
        # Narrator announces the vote
        await self.narrator_agent.narrate(
            f"Raise your hand if you vote to eliminate {character}."
        )
        await asyncio.sleep(3)  # Give players time to raise hands
        
        count_result = await self.camera_vote_count(game_id, character)
        
        # Narrator confirms — ALWAYS confirm before binding
        if count_result["confidence"] == "low":
            await self.narrator_agent.narrate(
                "I cannot see clearly. Let us use your devices to cast votes instead."
            )
            return None  # Fallback to phone voting
        
        await self.narrator_agent.narrate(
            f"I count {count_result['hand_count']} hands raised against {character}. "
            f"Is that correct?"
        )
        # Wait for verbal confirmation (barge-in handles "yes"/"no")
        # If disputed, fallback to phone voting
        
        results[character] = count_result["hand_count"]
    
    return results
```

**Frontend — Lobby toggle:**
```typescript
// Add to JoinScreen settings panel (host only)
const InPersonModeToggle: React.FC = () => (
  <label className="in-person-toggle">
    <input type="checkbox" onChange={toggleInPersonMode} />
    <span>🎥 In-Person Mode</span>
    <small>Use camera to count raised hands during votes</small>
  </label>
);
```

**Live API constraints:**
- Audio+video sessions limited to 2 minutes. Vote counting takes ~30 seconds per candidate — well within limits.
- Camera activated ONLY during vote countdown, not continuously.
- 1 FPS processing is sufficient — hands are static during count.
- Fallback to phone voting is automatic if confidence is low or vision fails.

**Firestore schema addition:**
```
games/{gameId}/
  ├── settings/
  │     ├── in_person_mode: true | false
```

---

## 12.3.17 Narrator Style Presets (Sprint 7+) — ✅ SHIPPED

**Effort:** 3–5 days | **Type:** System prompt variants + voice config overrides

Host selects a narrator personality in the lobby. Each preset changes the narrator's voice, vocabulary, pacing, and dramatic style. Game mechanics are identical.

```python
NARRATOR_PRESETS = {
    "classic": {
        "voice": "Charon",  # Deep, dramatic (current default)
        "prompt_prefix": """You are a classic fantasy narrator. Speak with gravitas 
        and dramatic weight. Your tone is rich, immersive, and carries the authority 
        of ancient legend. Build tension with deliberate pacing. Pauses are your 
        instrument — use silence before reveals.""",
        "vocabulary": "archaic-leaning",  # "The village sleeps beneath a pale moon"
        "pacing": "measured",
    },
    "campfire": {
        "voice": "Puck",  # Warmer, friendlier
        "prompt_prefix": """You are a campfire storyteller. Address the players as 
        "friends" and tell the story like you're sharing a tale around a fire on a 
        cool night. Your tone is warm, conspiratorial, and intimate. You lean in 
        when the story gets good. You chuckle at the players' mistakes. You gasp 
        at betrayals. This is a story between friends, not a performance.""",
        "vocabulary": "conversational",  # "So there they were, dead of night..."
        "pacing": "natural-conversational",
    },
    "horror": {
        "voice": "Charon",  # Same deep voice, different delivery
        "prompt_prefix": """You are a horror narrator. Speak slowly. Every word 
        carries weight. Your whispers are more terrifying than shouts. Build dread 
        through what you DON'T say — implication over exposition. Describe sensory 
        details: the creak of a floorboard, the smell of iron, the feeling of being 
        watched. Night phases are TERRIFYING. Day phases carry lingering unease. 
        Eliminations are graphic in implication, never explicit. The scariest thing 
        is what the players imagine.""",
        "vocabulary": "sparse-evocative",  # "Something moved in the dark. Something wrong."
        "pacing": "slow-with-long-pauses",
    },
    "comedy": {
        "voice": "Kore",  # Lighter, more expressive
        "prompt_prefix": """You are a comedic narrator who takes the story seriously 
        but finds the players hilarious. You're the DM who can't help breaking 
        character to comment on bad decisions. Your tone is wry, self-aware, and 
        occasionally fourth-wall-adjacent. You narrate dramatically but undercut 
        tension with observational humor. "The village sleeps. Well, most of it. 
        Someone is definitely plotting something. They always are." Eliminations 
        are handled with dark humor, not tragedy. You're rooting for the players 
        but finding their logic... questionable.""",
        "vocabulary": "modern-witty",  # "Bold strategy, accusing the only witness."
        "pacing": "quick-with-comic-timing",
    },
}

def build_narrator_prompt(preset: str, base_instruction: str) -> str:
    """Prepend preset personality to the base narrator instruction."""
    config = NARRATOR_PRESETS.get(preset, NARRATOR_PRESETS["classic"])
    return f"""{config['prompt_prefix']}
    
    VOCABULARY REGISTER: {config['vocabulary']}
    PACING STYLE: {config['pacing']}
    
    {base_instruction}"""

def get_voice_config(preset: str) -> str:
    """Return the Gemini voice name for this preset."""
    return NARRATOR_PRESETS.get(preset, NARRATOR_PRESETS["classic"])["voice"]
```

**Integration with existing Narrator Agent:**
```python
# In game setup — after host selects preset in lobby
narrator_preset = game_settings.get("narrator_preset", "classic")

narrator_agent = Agent(
    name="fireside_narrator",
    model="gemini-2.5-flash-native-audio-latest",
    instruction=build_narrator_prompt(narrator_preset, BASE_NARRATOR_INSTRUCTION),
    tools=[get_game_state, advance_phase, narrate_event, inject_traitor_dialog, start_phase_timer],
    sub_agents=[traitor_agent],
)

live_config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=get_voice_config(narrator_preset)
            )
        )
    ),
    # ... rest of config unchanged
)
```

**Frontend — Lobby preset selector:**
```typescript
const PRESETS = [
  { id: "classic", label: "⚔️ Classic", desc: "Deep, dramatic fantasy narrator" },
  { id: "campfire", label: "🔥 Campfire", desc: "Warm storyteller among friends" },
  { id: "horror", label: "🕯️ Horror", desc: "Slow, unsettling dread" },
  { id: "comedy", label: "😏 Comedy", desc: "Wry, self-aware, fourth-wall humor" },
];

const NarratorPresetSelector: React.FC = () => (
  <div className="preset-selector">
    <h4>Narrator Style</h4>
    {PRESETS.map(p => (
      <button key={p.id} onClick={() => setPreset(p.id)}
        className={selected === p.id ? "selected" : ""}>
        <span>{p.label}</span>
        <small>{p.desc}</small>
      </button>
    ))}
  </div>
);
```

**Firestore schema addition:**
```
games/{gameId}/
  ├── settings/
  │     ├── narrator_preset: "classic" | "campfire" | "horror" | "comedy"
```

**Playtesting note:** Each preset requires 3–5 full games to tune. The prompt prefix sets the direction but the balance between personality and gameplay clarity needs iteration — Comedy especially risks undermining dramatic tension at key moments (eliminations, reveals). Horror risks being too slow for impatient groups. Tuning is the majority of the effort.

---

## 12.3.18 Competitor Intelligence for AI (Sprint 7+) — ✅ SHIPPED

**Effort:** 1–2 weeks | **Type:** Analytics pipeline + prompt augmentation

Cross-game learning system. The AI Traitor's strategy improves over time based on what worked and failed in previous games.

```python
# ===== Post-Game Data Collection =====

async def log_game_strategy(game_id: str):
    """Called after every game. Extracts structured strategy data from events log."""
    db = firestore.client()
    game = db.collection("games").document(game_id).get().to_dict()
    events = [e.to_dict() for e in db.collection("games").document(game_id)
              .collection("events").order_by("timestamp").stream()]
    
    # Extract AI's strategy decisions
    ai_character = game["ai_character"]["name"]
    ai_caught = game.get("winner") == "villagers"
    round_caught = game.get("final_round", 0) if ai_caught else None
    difficulty = game.get("settings", {}).get("difficulty", "normal")
    player_count = len(game.get("players", {}))
    
    # Analyze what exposed the AI (if caught)
    exposure_signals = []
    if ai_caught:
        # Find the round where suspicion concentrated on AI's character
        vote_events = [e for e in events if e["type"] == "vote" and e["target"] == ai_character]
        accusation_events = [e for e in events if e["type"] == "accusation" and e["target"] == ai_character]
        
        for acc in accusation_events:
            exposure_signals.append({
                "round": acc.get("round"),
                "accuser": acc.get("actor"),
                "reason": acc.get("narration", ""),  # What the accuser said
            })
    
    # Analyze which deception moves succeeded
    successful_moves = []
    failed_moves = []
    ai_actions = [e for e in events if e["actor"] == "ai"]
    for action in ai_actions:
        if action["type"] == "accusation":
            # Did the AI's accusation lead to a vote against someone else?
            target = action["target"]
            next_vote = next((e for e in events if e["type"] == "elimination" 
                            and e["timestamp"] > action["timestamp"]), None)
            if next_vote and next_vote.get("target") == target:
                successful_moves.append({
                    "type": "deflection_accusation",
                    "description": f"Accused {target}, who was then eliminated",
                    "round": action.get("round"),
                })
            else:
                failed_moves.append({
                    "type": "deflection_accusation",
                    "description": f"Accused {target}, but village didn't follow",
                    "round": action.get("round"),
                })
    
    # Store structured log
    db.collection("ai_strategy_logs").document(game_id).set({
        "game_id": game_id,
        "difficulty": difficulty,
        "player_count": player_count,
        "ai_caught": ai_caught,
        "round_caught": round_caught,
        "total_rounds": game.get("final_round", 0),
        "exposure_signals": exposure_signals,
        "successful_moves": successful_moves,
        "failed_moves": failed_moves,
        "timestamp": firestore.SERVER_TIMESTAMP,
    })
```

```python
# ===== Daily Aggregation (Cloud Function) =====

from google.cloud import functions_v2

@functions_v2.cloud_event
def aggregate_strategy_intelligence(cloud_event):
    """Scheduled daily. Aggregates strategy logs into a meta-strategy brief."""
    db = firestore.client()
    
    # Fetch last 100 game logs (or all if fewer)
    logs = [doc.to_dict() for doc in 
            db.collection("ai_strategy_logs")
            .order_by("timestamp", direction="DESCENDING")
            .limit(100).stream()]
    
    if len(logs) < 20:
        return  # Not enough data for meaningful patterns
    
    # Aggregate patterns
    total = len(logs)
    caught_count = sum(1 for l in logs if l["ai_caught"])
    catch_rate = caught_count / total
    
    # Common exposure patterns
    all_exposures = []
    for log in logs:
        all_exposures.extend(log.get("exposure_signals", []))
    
    # Common successful deceptions
    all_successes = []
    for log in logs:
        all_successes.extend(log.get("successful_moves", []))
    
    # Count move types
    from collections import Counter
    exposure_reasons = Counter(e.get("reason", "")[:50] for e in all_exposures)
    success_types = Counter(s["type"] for s in all_successes)
    
    # Generate the meta-strategy brief using Gemini
    analysis_prompt = f"""Analyze these AI strategy statistics from {total} social deduction games:

    Overall catch rate: {catch_rate:.0%}
    
    Most common reasons the AI was caught (top 5):
    {json.dumps(exposure_reasons.most_common(5))}
    
    Most successful deception moves (by type):
    {json.dumps(success_types.most_common(5))}
    
    Average rounds before AI was caught: {sum(l.get('round_caught', 0) for l in logs if l['ai_caught']) / max(caught_count, 1):.1f}
    
    Generate a concise strategy brief (max 200 words) for an AI playing a social deduction game.
    Format as actionable advice:
    - What to AVOID (patterns that get caught)
    - What WORKS (successful deception strategies)
    - TIMING advice (when to be aggressive vs passive)
    """
    
    response = generate_content_sync(analysis_prompt)
    brief = response.text
    
    # Store the brief
    db.collection("ai_meta_strategy").document("latest").set({
        "brief": brief,
        "games_analyzed": total,
        "catch_rate": catch_rate,
        "generated_at": firestore.SERVER_TIMESTAMP,
    })
```

```python
# ===== Traitor Agent Prompt Augmentation =====

async def get_traitor_prompt(difficulty: str) -> str:
    """Build Traitor Agent prompt with optional intelligence augmentation."""
    base_prompt = TRAITOR_PROMPTS[difficulty]  # Existing Easy/Normal/Hard prompts
    
    # Load meta-strategy brief if available
    db = firestore.client()
    meta_doc = db.collection("ai_meta_strategy").document("latest").get()
    
    if meta_doc.exists:
        meta = meta_doc.to_dict()
        # Only augment if we have meaningful data
        if meta.get("games_analyzed", 0) >= 20:
            intelligence_section = f"""
            
            INTELLIGENCE BRIEFING (from {meta['games_analyzed']} previous games):
            {meta['brief']}
            
            IMPORTANT: This briefing INFORMS your strategy. It does NOT override 
            your difficulty level constraints. At Easy difficulty, you still make 
            deliberate mistakes even if the briefing suggests otherwise.
            """
            return base_prompt + intelligence_section
    
    return base_prompt
```

**Firestore schema:**
```
ai_strategy_logs/{gameId}/
  ├── game_id: "game_abc"
  ├── difficulty: "normal"
  ├── player_count: 5
  ├── ai_caught: true
  ├── round_caught: 3
  ├── total_rounds: 4
  ├── exposure_signals: [{ round: 2, accuser: "player_id", reason: "..." }]
  ├── successful_moves: [{ type: "deflection_accusation", description: "...", round: 1 }]
  ├── failed_moves: [{ type: "deflection_accusation", description: "...", round: 2 }]
  ├── timestamp: ...

ai_meta_strategy/latest/
  ├── brief: "Avoid accusing the same player twice in consecutive rounds..."
  ├── games_analyzed: 87
  ├── catch_rate: 0.52
  ├── generated_at: ...
```

**Cloud Function deployment:**
```yaml
# terraform/cloud_functions.tf
resource "google_cloudfunctions2_function" "strategy_aggregator" {
  name     = "strategy-aggregator"
  location = var.region
  
  build_config {
    runtime     = "python312"
    entry_point = "aggregate_strategy_intelligence"
    source {
      storage_source {
        bucket = google_storage_bucket.functions.name
        object = "strategy_aggregator.zip"
      }
    }
  }
  
  service_config {
    available_memory = "256M"
    timeout_seconds  = 120
  }
}

# Daily trigger
resource "google_cloud_scheduler_job" "daily_aggregation" {
  name     = "daily-strategy-aggregation"
  schedule = "0 4 * * *"  # 4 AM daily
  
  pubsub_target {
    topic_name = google_pubsub_topic.strategy_trigger.id
  }
}
```

**Safeguards:**
- Intelligence brief is capped at 200 words — prevents prompt bloating.
- Difficulty level always takes precedence. Easy AI still makes mistakes regardless of intelligence.
- Minimum 20 games required before augmentation activates — prevents overfitting on small samples.
- Brief is regenerated daily, not per-game — prevents real-time adaptation that could feel unfair.
- Players are told post-game: "The AI used intelligence from N previous games" — transparency builds trust.

---

# 12.4 Implementation Additions (not in original TDD v1.0)

The following features were added during implementation but were not specified in the original design document. They are documented here for architectural completeness.

## 12.4.1 Hide AI Identity

**Files:** `game_router.py`, `ws_router.py`, `GameScreen.jsx`

The AI character is never exposed through HTTP responses. The `GET /api/games/{id}` endpoint returns `ai_character: null`. The AI's identity is sent only via a private WebSocket `connected` message to each player at game start. In the frontend, the `CharacterGridPanel` excludes the AI from the player grid — it appears indistinguishable from human players. The `is_traitor` flag and AI `role` are stripped from the `/start` HTTP response.

## 12.4.2 Session Persistence (sessionStorage)

**Files:** `JoinLobby.jsx`, `GameContext.jsx`

After joining a game, `playerId`, `playerName`, `gameId`, and `isHost` are persisted to `sessionStorage`. `GameContext` initializes its `initialState` from sessionStorage, enabling automatic reconnection after page refresh. Keys are cleared on `GAME_OVER` and `RESET` dispatch actions.

## 12.4.3 GameOver REST Fallback

**Files:** `game_router.py` (`GET /api/games/{id}/result`), `GameOver.jsx`, `models/game.py` (`winner` field)

Direct navigation to `/gameover/:gameId` no longer redirects to home. Instead, a `useEffect` hook fetches the game result from a REST endpoint. The `winner` field is persisted atomically alongside `status: "finished"` in a single Firestore write to avoid race conditions. The endpoint reconstructs reveals (character → player + role mappings) and timeline (events grouped by round) from Firestore data.

## 12.4.4 Narrator Audio Preview

**Files:** `game_router.py` (`GET /api/narrator/preview/{preset}`), `Landing.jsx`, `JoinLobby.jsx`, `TutorialPage.jsx`

Each narrator preset has a short audio sample generated via `gemini-2.5-flash-preview-tts`. Samples are cached in-memory (`_narrator_preview_cache` dict) to avoid repeated API calls. The frontend plays previews via `new Audio()` with cleanup on component unmount. The Landing page shows a "Hear the narrator" button for the Classic preset. The Tutorial shows it on the role reveal step. The Lobby shows preview buttons on each of the 4 preset cards.

## 12.4.5 Server-Side Vote Timeout

**Files:** `ws_router.py`

A 60-second `asyncio.Task` is scheduled when the `day_vote` phase begins (reduced from 90s in v5.0 — voting is a single tap; 60s is ample). If not all players have voted by expiration, the vote auto-resolves with whatever votes have been cast. The timeout task is cancelled when votes are resolved normally. This prevents games from hanging indefinitely when a player disconnects during voting.

## 12.4.6 WebSocket Error Safety

**Files:** `ws_router.py`

The `_handle_message` function wraps the entire dispatch block in try/except. Any unhandled exception (Firestore error, malformed message, etc.) sends an `error` type message to the player instead of crashing the WebSocket connection. This prevents one bad message from disconnecting the player.

## 12.4.7 Readable Join Codes

**Files:** `models/game.py`

Game IDs use a 6-character alphanumeric code from a restricted character set (`ABCDEFGHJKLMNPQRSTUVWXYZ23456789` — no O/I/0/1 to avoid confusion). This replaces the original UUID-based hex code for better readability when sharing verbally.

## 12.4.8 Narrator Silence Fallback

**Files:** `GameScreen.jsx` (NarratorBar component)

A 15-second silence timer detects when the narrator has stopped producing audio. The timer is gated: it only fires when `logLen > 0` (narrator has spoken at least once) and `!isPlaying` (no audio currently playing). When triggered, a "Narrator thinking..." indicator appears. This provides feedback when Gemini Live API has latency or session issues.

## 12.4.9 Min-Player Warning

**Files:** `game_master.py` (`get_lobby_summary`), `GameScreen.jsx` (LobbyPanel)

When fewer than 4 human players have joined, the lobby summary includes a `min_player_warning` field: "Games work best with 4+ players. You can still start with fewer." This is rendered to the host in amber text below the player dots. The technical minimum remains at 2 (for dev/testing).

---

# 12.5 Post-P2 Additions (Shipped February 24–26, 2026)

The following features were shipped after the P2 milestone. They address live-play quality, voice engagement, and deployment infrastructure.

## 12.5.1 Player Voice Input Pipeline

**Files:** `frontend/src/hooks/useWebSocket.js` (AudioWorklet), `backend/routers/ws_router.py` (audio handler), `backend/agents/narrator_agent.py` (`NarratorSession.send_audio`)

Players can speak into their phone microphone. The full pipeline:

1. **Browser capture:** An `AudioWorklet` in the browser captures mic audio at the device's native sample rate, downsamples to 16 kHz PCM16 mono in the worklet processor.
2. **WebSocket transport:** The PCM bytes are base64-encoded and sent as `{ type: "player_audio", audio: "<base64>" }` over the existing game WebSocket.
3. **Server decode + attribution:** The WebSocket dispatcher decodes the base64 payload, looks up the player's `character_name` from Firestore, and calls `narrator_manager.forward_player_audio(game_id, pcm_bytes, speaker=character_name)`.
4. **Speaker annotation injection:** Inside `NarratorSession.send_audio(pcm_bytes, speaker)`, if the `speaker` differs from `_current_voice_speaker`, a text annotation is injected first: `[VOICE] {speaker} is now speaking via microphone.` This is sent via `session.send(input=text, end_of_turn=False)` so the narrator does not respond to the annotation itself.
5. **Raw PCM to Gemini:** The audio bytes are queued to the Gemini Live API session via `send_realtime_input(audio=Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000"))`.
6. **Transcript buffering:** Gemini returns partial `input_audio_transcription` fragments via `server_content.input_transcription.text`. These are accumulated in a `_transcript_buffer` with a 0.8-second debounce timer (`_flush_transcript_after_delay`). On flush, the complete sentence is broadcast to all players as `{ type: "input_transcript", speaker: "<character_name>", text: "<buffered sentence>" }`.

```python
# NarratorSession — voice input state (narrator_agent.py)
class NarratorSession:
    def __init__(self, ...):
        # ... existing fields ...
        self._current_voice_speaker: Optional[str] = None
        self._transcript_buffer: str = ""
        self._transcript_flush_task: Optional[asyncio.Task] = None

    async def send_audio(self, pcm_bytes: bytes, speaker: str):
        """Send player mic audio to Gemini with speaker attribution."""
        if speaker != self._current_voice_speaker:
            self._current_voice_speaker = speaker
            annotation = f"[VOICE] {speaker} is now speaking via microphone."
            await self._session.send(input=annotation, end_of_turn=False)
        await self._session.send(
            input=types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000")
        )

    async def _flush_transcript_after_delay(self, delay: float = 0.8):
        """Debounce partial transcription fragments into complete sentences."""
        await asyncio.sleep(delay)
        if self._transcript_buffer.strip():
            text = self._transcript_buffer.strip()
            self._transcript_buffer = ""
            # Broadcast to all players
            await self._broadcast_transcript(self._current_voice_speaker, text)
```

**Audio Specifications (updated):**
- Player mic input: 16-bit PCM, 16 kHz, mono (downsampled in AudioWorklet)
- Narrator output: 24 kHz PCM audio (broadcast to players)
- Transcript flush debounce: 0.8 seconds

## 12.5.2 Speaker Identification

**Files:** `backend/agents/narrator_agent.py` (`_current_voice_speaker`), `backend/routers/ws_router.py` (audio handler)

When multiple players use voice input, the narrator needs to know who is speaking. The system tracks the active speaker per `NarratorSession`:

- `_current_voice_speaker: Optional[str]` — tracks the character name of the player currently sending audio.
- On speaker change, a text annotation `[VOICE] {name} is now speaking via microphone.` is injected into the Gemini session before the audio bytes.
- The annotation uses `end_of_turn=False` so the narrator does not interpret it as a prompt requiring a response.
- The Gemini model's `input_audio_transcription` output is tagged with the speaker name and broadcast to all clients for display in the story log.

This allows the narrator to address players by character name during voice discussions: "Blacksmith Garin, you sound troubled — tell us what you saw."

## 12.5.3 Dynamic Discussion Timer

**Files:** `backend/routers/ws_router.py` (`_discussion_timeout`, `_discussion_warning`), `frontend/src/components/Game/GameScreen.jsx` (countdown UI), `frontend/src/context/GameContext.jsx` (timerSeconds state), `frontend/src/hooks/useWebSocket.js` (phase_change handler)

Replaced the flat 120-second discussion timeout with a dynamic timeout scaled to alive player count:

```python
# ws_router.py
def _discussion_timeout(alive_count: int) -> int:
    """Compute discussion phase timeout in seconds based on alive player count."""
    if alive_count <= 4:
        return 120   # 3-4 alive → 2 minutes
    elif alive_count <= 6:
        return 180   # 5-6 alive → 3 minutes
    else:
        return 240   # 7+ alive → 4 minutes
```

**Server-side flow:**
1. `broadcast_phase_change` computes the timeout dynamically and includes `timer_seconds` in the `phase_change` WebSocket message.
2. A `_discussion_warning` async task is scheduled to fire 30 seconds before timeout. It sends the narrator a wrap-up prompt: "Discussion time is running low. Summarize key points and guide toward a vote."
3. Warning tasks are tracked in a `_discussion_warning_tasks: dict[str, asyncio.Task]` dict, keyed by game ID. If the narrator calls `advance_phase` manually before the timer expires, the warning task is cancelled.

**Frontend rendering:**
- `GameContext.jsx`: The `PHASE_CHANGE` reducer stores `timerSeconds: action.timerSeconds ?? null`.
- `useWebSocket.js`: The `phase_change` handler passes `timerSeconds: msg.timer_seconds` to the dispatch.
- `GameScreen.jsx`: A `discussionTimeLeft` state is initialized from `timerSeconds` when `phase === 'day_discussion'`. A `useEffect` countdown decrements every second.
- Display: M:SS in a sticky header with color transitions:
  - Default: muted gray
  - 30 seconds remaining: amber (`#fbbf24`)
  - 15 seconds remaining: red (`var(--danger)`) with CSS `pulse` animation

## 12.5.4 Narrator Engagement Model (Dual-Mode)

**Files:** `backend/agents/narrator_agent.py` (NARRATOR_SYSTEM_PROMPT overhaul)

The narrator system prompt was overhauled to support two distinct operational modes:

1. **Theatrical narration mode** — During night phases, transitions, and eliminations: rich, immersive, atmospheric storytelling with dramatic pacing.
2. **Fast-paced moderator mode** — During day discussion: the narrator acts as a HOST who relays, reacts, stirs, and redirects. The RELAY/REACT/STIR/REDIRECT pattern:
   - **RELAY:** When a player speaks, the narrator echoes or paraphrases key points so all players hear them clearly.
   - **REACT:** Brief emotional reactions to accusations, defenses, or dramatic moments.
   - **STIR:** Pose provocative follow-up questions to deepen discussion: "An interesting claim, Garin. But can anyone corroborate?"
   - **REDIRECT:** When discussion stalls or circles, redirect attention to quiet players or unexplored angles.

**`end_of_turn` parity:**
- `NarratorSession.send()` now accepts an `end_of_turn` parameter (default `True`).
- The internal `_sender` unpacks `(text, end_of_turn)` tuples from the send queue.
- `forward_player_message` uses `end_of_turn=False` when `ConversationTracker` reports `PACE_HOT`, allowing rapid message injection without triggering narrator responses for each individual message.

**Preset upgrades:** All 4 narrator presets (Classic, Campfire, Horror, Comedy) were updated with discussion-specific personalities. For example, the Comedy preset moderates discussion with self-aware meta-commentary, while the Horror preset uses eerie silence and unsettling observations.

**Voice-optimized dialog:** Traitor and loyal AI dialog prompts now include: "This will be SPOKEN ALOUD — write for voice: contractions, short sentences, natural speech." This ensures AI character dialog sounds natural when delivered by the narrator's voice.

## 12.5.5 Human Shapeshifter Night Kill

**Files:** `backend/routers/ws_router.py` (shapeshifter_action handler), `frontend/src/components/Game/GameScreen.jsx` (night kill UI, role reveal overlay)

When Random AI Alignment (section 12.3.10) assigns the shapeshifter role to a human player, that player must manually submit their night kill target:

- **Client → Server:** `{ type: "shapeshifter_action", target: "<character_name>" }` — sent by the human player during the night phase.
- **Server processing:** The `ws_router.py` dispatcher handles the `shapeshifter_action` message type. It validates the player holds the shapeshifter role and the target is alive, then records the night action in Firestore. The `execute_night_actions` pipeline processes human shapeshifter kills identically to AI shapeshifter kills.
- **Frontend:** A `RoleRevealOverlay` component shows the player their role assignment at game start. During the night phase, human shapeshifters see a target selection UI (similar to the Seer investigation UI) instead of the "waiting for night to pass" message.

## 12.5.6 Infrastructure Updates

### Multi-Stage Dockerfile

**File:** `Dockerfile` (repo root — replaces `backend/Dockerfile`)

The Dockerfile was rewritten as a two-stage build:

```dockerfile
# Stage 1: Build frontend (node:18-slim)
FROM node:18-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + compiled frontend (python:3.11-slim)
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--ws-ping-interval", "15", "--ws-ping-timeout", "20"]
```

Key changes from the original single-stage design (section 9.1):
- **Two stages** instead of installing Node.js inside the Python image. Stage 1 (`node:18-slim`) builds the frontend; Stage 2 (`python:3.11-slim`) copies only the compiled `dist/` output. This reduces final image size by ~400 MB.
- **Port 8000** instead of 8080 (aligned with actual uvicorn config).
- **(v5.2)** `--ws-ping-interval=15 --ws-ping-timeout=20` added to CMD for production WebSocket keep-alive (see §12.6.5).
- **Python 3.11** base image (pinned for compatibility with dependencies).
- **Single worker** (`--workers 1`) since the app manages WebSocket state in-process.

### Terraform IaC

**Files:** `terraform/main.tf`, `terraform/variables.tf`, `terraform/terraform.tfvars.example`

The Terraform configuration was implemented and extended beyond the original design spec (section 9.2):

- **API enablement:** Automatically enables `run`, `cloudbuild`, `firestore`, `aiplatform`, and `artifactregistry` APIs via `google_project_service` resources with `for_each`.
- **Artifact Registry:** Repository named `fireside` (instead of `hackathon`), format `DOCKER`.
- **Cloud Run service:** `fireside-betrayal` with session affinity, port 8000, 1 CPU / 1 GiB memory, 0–10 instance scaling. Environment variables: `GOOGLE_CLOUD_PROJECT`, `GEMINI_API_KEY`, `EXTRA_ORIGIN`, `DEBUG`.
- **Cloud Build trigger:** Defined but commented out (requires manual GitHub repo connection in Cloud Build console). Manual builds via `gcloud builds submit` are the recommended path.
- **Public access:** `roles/run.invoker` granted to `allUsers`.
- **Variables:** `project_id` (required), `region` (default `us-central1`), `gemini_api_key` (sensitive).
- **Outputs:** `service_url`, `image_url`, `firestore_database`.

### Deployment Guide

**File:** `docs/DEPLOYMENT.md`

Documents three deployment paths:
1. **Local development** — `npm run dev` (frontend) + `uvicorn` (backend) with `.env` configuration.
2. **Cloud Run manual deploy** — `gcloud builds submit` + `gcloud run deploy` commands.
3. **Terraform automated deploy** — `terraform init` + `terraform apply` for full infrastructure provisioning.

### Python 3.14 Compatibility

**File:** `backend/requirements.txt`

Dependencies were pinned to versions compatible with Python 3.14 (forward-compatibility).

---

# 12.6 v5.0 Architecture Additions (March 12, 2026)

The following features were added after the v4.0 milestone to fix the narrator disconnection blocker (BLOCKER from Round 4 playtest) and improve real-time robustness.

---

## 12.6.1 Separate Audio WebSocket

**Files:** `backend/routers/ws_router.py` (`/ws/audio/{game_id}` endpoint), `frontend/src/hooks/useAudioCapture.js`

Player microphone audio is now transported over a dedicated binary WebSocket (`/ws/audio/{game_id}`) rather than being base64-encoded and embedded in JSON messages on the game-state WebSocket.

**Protocol:**
- Client opens `/ws/audio/{game_id}?playerId=xxx` after receiving `speaker_granted`.
- Each AudioWorklet processor callback sends one binary frame: raw 16-bit PCM, 16 kHz, mono. No JSON, no base64.
- Server receives `bytes` via `websocket.receive_bytes()` and calls `narrator_session.send_audio(pcm_bytes, speaker=character_name)` directly.
- If the audio WS drops (code 1006 or any error), the server releases the speaker lock and logs the disconnect. The game WS is completely unaffected.
- `useAudioCapture.js` manages the audio WS lifecycle: creates on `start_speaking`, destroys on `stop_speaking` or component unmount.

**Benefits:**
- ~33% reduction in per-frame bytes (no base64 encoding overhead).
- Game WS no longer carries audio traffic — eliminates saturation-induced 1006 disconnections.
- Independent failure domains: audio drops ≠ game state loss.

---

## 12.6.2 Push-to-Talk Speaker Lock

**Files:** `backend/routers/ws_router.py` (`ConnectionManager`, `GameSession.claim_speaker_lock`)

Only one player can hold the microphone at a time. The server maintains `_current_speaker: Dict[str, Optional[str]]` (game_id → player_id) and `_speaker_timeout_tasks: Dict[str, asyncio.Task]` (auto-release after 30s).

**Lock lifecycle:**
1. Player sends `{ type: "start_speaking" }` on the game WS.
2. Server checks: player alive? lock free? If both, `_current_speaker` is set immediately before any await (TOCTOU-safe).
3. Server sends `{ type: "speaker_granted" }` to the player (private).
4. Player opens the audio WS and begins streaming PCM.
5. Lock is released on any of: `stop_speaking` message, game WS disconnect, audio WS disconnect, phase transition, game end, or 30s timeout.
6. On release, server broadcasts `{ type: "speaker_released", playerId, reason }` to all players.
7. Dead players receive `{ type: "speaker_error", reason: "dead_players_cannot_speak" }` and cannot claim the lock.

**TOCTOU safety:** The `_current_speaker` field is written synchronously (no `await` between the check and the write). Python's async event loop is single-threaded, so no two coroutines can interleave between the check and write within the same turn. This guarantees at most one player holds the lock at any moment.

---

## 12.6.3 Per-Player Priority Queues

**Files:** `backend/routers/ws_router.py` (`ConnectionManager`)

The `ConnectionManager` class (v5.0) gives each connected player two outbound queues:

| Queue | Type | Bound | Contents |
|-------|------|-------|----------|
| `control_queue` | `asyncio.Queue` | unbounded | Phase changes, eliminations, role messages, vote updates, errors |
| `audio_queue` | `asyncio.Queue` | maxsize=256 | Narrator PCM audio chunks |

A dedicated `_player_sender` coroutine per connection drains `control_queue` first (all available messages), then pulls one audio chunk. This guarantees control-plane messages are never delayed behind audio volume. If `audio_queue` is full, incoming audio chunks are dropped silently (older chunks are more stale; dropping is preferable to memory growth or stalling).

**Chat local echo:** When a player sends `{ type: "message" }`, the server immediately enqueues the transcript back to that player's `control_queue` with `echo: true`. Other players receive the same message without the flag. The frontend deduplicates by ignoring non-echo transcripts from the sender's own character name that match the last message sent.

---

## 12.6.4 Phase Timer Improvements

**Files:** `backend/routers/ws_router.py`, `backend/agents/narrator_agent.py`, `frontend/src/hooks/useWebSocket.js`, `frontend/src/context/GameContext.jsx`

**Narrator-driven timer start:**
- `phase_change` messages no longer include `timer_seconds`. The frontend shows a "waiting for narrator" state after a phase change.
- The narrator calls the new `start_phase_timer` tool after finishing its opening narration (e.g., after announcing night has fallen and instructing players on their actions).
- The server broadcasts `{ type: "phase_timer_start", phase, timerSeconds }` to all players.
- The frontend starts its countdown only on receiving `phase_timer_start`.

**15-second safety fallback:**
- On every phase transition, the server schedules a `_phase_timer_safety_task` (15-second `asyncio.Task`).
- If `start_phase_timer` is called by the narrator before 15s, the safety task is cancelled.
- If the narrator does not call it within 15s (e.g., slow Gemini response, silent session), the safety task fires and broadcasts `phase_timer_start` automatically.
- This prevents games from hanging indefinitely when the narrator is unresponsive.

**Updated timeout values (v5.0):**
| Phase | v4.0 timeout | v5.0 timeout | Notes |
|-------|-------------|-------------|-------|
| night | 45s | 45s | Reverted from 30s → 45s in v5.1 for AI Gemini RPC latency |
| day_discussion | 120–240s | 120–240s | Unchanged (scaled to alive count) |
| day_vote | 90s | 60s | Voting is a single tap; 60s is ample |

**Minimum discussion guard:**
- The narrator cannot call `start_phase_timer` during `day_discussion` until at least 45 seconds have elapsed since the phase began.
- If the narrator calls it before 45s, the server ignores the call and logs a warning. The 15s safety fallback clock resets to fire at `45s + 15s = 60s` if the narrator still hasn't called it again.
- This ensures every player has at least 45 seconds to speak before the countdown begins.

---

## 12.6.5 WebSocket Keepalive

**Files:** `backend/routers/ws_router.py`, `backend/main.py`, `Dockerfile`

WebSocket ping/pong was previously disabled (contributed to silent 1006 disconnections). Re-enabled in v5.0:

```python
# uvicorn launch / websocket accept configuration (v5.0 values)
# Ping interval: 20s — server sends a ping every 20 seconds
# Ping timeout: 30s — if no pong received within 30s of sending ping, connection is closed
# These values match the Cloud Run request timeout headroom (60s max idle)
```

**Implementation Update (v5.2):** Production keepalive is now configured via Dockerfile CMD flags rather than application-level code:
```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--ws-ping-interval", "15", "--ws-ping-timeout", "20"]
```

The v5.2 values are tighter than v5.0 (15s interval / 20s timeout vs. 20s / 30s) based on production observation: Cloud Run's load balancer was dropping WebSocket connections before the 20s server ping fired. The 15s interval keeps connections alive through Cloud Run's idle detection, and the 20s timeout provides sufficient margin for mobile network jitter without holding dead connections too long.

Disconnect events on both the game WS and audio WS are now logged with structured fields (`game_id`, `player_id`, `code`) rather than silently swallowed. This surfaces 1006 codes in Cloud Logging for diagnosis.

---

## 12.6.6 Shapeshifter Skip

**Files:** `backend/routers/ws_router.py` (handler), `frontend/src/components/Game/GameScreen.jsx` (skip button)

When a human player holds the shapeshifter role (via Random AI Alignment, §12.3.10), they can now choose to skip their night kill:

- **Client → Server:** `{ type: "skip_night_kill" }` sent during the night phase.
- **Server validation:** Checks that the player holds the `shapeshifter` role and the current phase is `night`. Invalid requests receive an `error` response.
- **Firestore write:** Logs a `shapeshifter_skip` event with `actor = player_id`. Records a night action with `action = "skip_night_kill", target = null`.
- **Night resolution:** `resolve_night()` treats a null shapeshifter target as no kill — nobody is eliminated by the shapeshifter that night. Healer and Seer actions still resolve normally.
- **Frontend:** A "Skip" button appears alongside the character selection grid for shapeshifter players during night phase. Tapping it sends `skip_night_kill` and hides the selection UI.

# 12.7 v5.1 Architecture Additions (Shipped March 2026)

The following features were added in v5.1. They introduce a dead-player engagement system, concurrency hardening, and frontend responsiveness improvements.

## 12.7.1 Ghost Council / Dead Player System

**Files:** `backend/routers/ws_router.py` (ghost_message handler), `backend/agents/traitor_agent.py` (AI ghost dialog), `frontend/src/components/Game/GhostRealmPanel.jsx`

Dead players can communicate through a parallel "Ghost Council" chat channel:

- **`ghost_message` WebSocket message type:** Dead players send `{ type: "ghost_message", text: "..." }`. The server validates the player is dead, applies a **2-second rate limit per player**, then broadcasts `{ type: "ghost_message", speaker: "<character_name>", text: "...", source: "ghost" }` to all connected players.
- **Firestore persistence:** Ghost messages are stored in `games/{id}/chat` with `source: "ghost"`. This allows post-game review of ghost chatter.
- **Dead AI ghost dialog:** Dead AI characters generate ghost dialog with ~30% probability per discussion round. The dialog is atmospheric and cryptic (e.g., "The shadows know who holds the blade..."). Generated via `generate_ghost_dialog()` in `traitor_agent.py`.
- **GhostRealmPanel:** A frontend component that renders ghost chat in a distinct visual style (translucent, ethereal color scheme). Living players see ghost messages in a collapsed sidebar; dead players see the full panel as their primary interaction surface.

## 12.7.2 Séance Phase

**Files:** `backend/routers/ws_router.py` (séance orchestration), `backend/agents/narrator_agent.py` (séance narration prompt), `frontend/src/components/Game/GameScreen.jsx` (séance UI)

A new phase in the game lifecycle that allows dead players to briefly address the living:

- **Trigger condition:** Séance activates after ELIMINATION when `dead_count >= 2 AND dead_count >= total_players / 2`. This ensures séances only occur when enough players have died to make ghost testimony meaningful.
- **Duration:** 45 seconds of push-to-talk re-enabled for dead players. Living players listen but cannot interrupt.
- **Phase cycle:** ELIMINATION → SEANCE → NIGHT (conditional). If séance conditions are not met, the standard ELIMINATION → NIGHT transition applies.
- **Narrator moderation:** The narrator introduces the séance with dramatic flavor ("The veil between worlds grows thin...") and moderates ghost testimony. A SYSTEM prompt instructs the narrator to call `start_phase_timer` after its séance introduction.
- **Frontend:** Dead players' push-to-talk button is re-enabled during séance. A 45-second countdown is displayed. Living players see a "Séance in progress" overlay with ghost audio streaming.

## 12.7.3 Haunt Actions (Dead Player Night Action)

**Files:** `backend/routers/ws_router.py` (haunt_action handler), `backend/agents/traitor_agent.py` (AI ghost auto-accuse)

Dead players can influence the game during the night phase:

- **Mechanic:** Each dead player (human or AI) can accuse one living character per round during the night phase via `{ type: "haunt_action", target: "<character_name>" }`.
- **Storage:** Haunt actions are stored as `haunt_action` events in Firestore with `actor` = ghost character name, `target` = accused living character.
- **Narrator integration:** The narrator incorporates haunt accusations into the next discussion phase narration: "The spirits grow restless... whispers from beyond accuse [character]."
- **AI ghosts:** Dead AI characters auto-accuse based on game events analysis. Traitor AI ghosts try to deflect suspicion from the living shapeshifter. Loyal AI ghosts accuse the character they most suspect.
- **Rate limit:** One haunt action per dead player per night round.

## 12.7.4 AI Auto-Reply System

**Files:** `backend/agents/narrator_agent.py` (`NarratorSession._maybe_trigger_ai_reply`)

AI characters can now respond organically when mentioned by name during discussion:

- **Trigger:** `_maybe_trigger_ai_reply()` is called on each transcript flush from the Gemini Live API. It scans the transcript for any word (>= 3 characters) matching an AI character's name using whole-word regex (`\b{word}\b`, case-insensitive).
- **Cooldown:** 30-second cooldown per AI character. Only one AI reply is generated per transcript flush to prevent dialog flooding.
- **Broadcast:** AI replies are broadcast as `{ type: "transcript", speaker: "<ai_character_name>", text: "..." }` with `source: "player"` in Firestore chat collection — indistinguishable from human player messages.
- **Persistence:** Replies are written to the `games/{id}/chat` subcollection with `source: "player"` for consistency with the hide-AI-identity pattern.

## 12.7.5 Discussion Timer Enforcement

**Files:** `backend/routers/ws_router.py` (`handle_advance_phase`)

Guard in `handle_advance_phase()` prevents premature phase advancement:

- **Rule:** Rejects `advance_phase` calls during `DAY_DISCUSSION` if `start_phase_timer` has not been called yet.
- **Narrator feedback:** When rejected, the server sends a SYSTEM message to the narrator instructing it to call `start_phase_timer`: "You must call start_phase_timer before advancing the phase. Players need time to discuss."
- **Constant:** `MIN_DISCUSSION_SECONDS = 45` — the minimum elapsed time before the timer can start (existing guard from v5.0, now enforced as a prerequisite for phase advancement).

## 12.7.6 Responsive Roster Architecture

**Files:** `frontend/src/components/Game/RosterPanel.jsx`, `frontend/src/components/Game/GameScreen.jsx` (game-layout wrapper)

The character roster adapts to screen size:

- **RosterPanel.jsx** contains two sub-components:
  - `RosterSidebar` (desktop): Full vertical sidebar with character cards, alive/dead status, role icons. Visible at >= 768px viewport width.
  - `RosterIconStrip` (mobile): Compact horizontal strip of character avatars with alive/dead indicators. Visible at < 768px viewport width.
- **CSS media query:** `@media (max-width: 768px)` switches between the two layouts.
- **game-layout wrapper:** `display: contents` on mobile (RosterIconStrip flows inline), `flex-row` on desktop (sidebar + main content).
- **`buildCharacterList()`:** Utility function that merges human players and AI characters into a unified character list for rendering. Sorts by alive status (alive first), then alphabetically by character name.

## 12.7.7 Phase Change Data Sync

**Files:** `backend/routers/ws_router.py`, `frontend/src/hooks/useWebSocket.js`, `frontend/src/context/GameContext.jsx`

WebSocket messages now carry richer state to prevent client-server desync:

- **`phase_change` messages:** Now include the full player roster (`players` array with alive/dead status) and AI character data (`aiCharacters` array). This ensures the frontend has accurate state after every phase transition, even if intermediate messages were missed.
- **`connected` messages:** Now send ALL players (alive + dead) via `get_all_players()` instead of only alive players. This is critical for reconnecting players to see the full game state.
- **Frontend handler:** The `phase_change` message handler in `useWebSocket.js` dispatches both `UPDATE_PLAYERS` and `SET_AI_CHARACTERS` actions to GameContext, ensuring roster and AI state are always synchronized with the server.

## 12.7.8 Concurrency Guards

**Files:** `backend/routers/ws_router.py`

Defense-in-depth concurrency protections:

- **`_resolving_nights: Set[str]`:** Prevents double night resolution. When `resolve_night()` is entered, the game_id is added to this set. If the game_id is already present, the function returns early. The game_id is removed in a `finally` block. This mirrors the existing `_resolving_votes` pattern.
- **Night action timeout:** Increased from 30s → 45s to accommodate AI Gemini RPC latency. The previous 30s timeout caused premature resolution when Gemini was slow to respond.
- **Alive check in resolve_night():** Before applying a shapeshifter kill, `resolve_night()` now verifies the target is still alive in Firestore. This prevents a race condition where a concurrent elimination (e.g., Hunter revenge) could cause a double-elimination.

---

# 12.8 v5.2 Architecture Additions (Bug Fix Sprint — March 14, 2026)

The following changes were shipped in the `fix/share-link-audio-votes` branch (commit `c3bf8d7`). They address production issues discovered during R4 playtesting: broken share/join links, audio WS drops on mobile, missing vote tally visibility, oversized scene images, and log noise.

## 12.8.1 SPA Catch-All Routing

**Files:** `backend/main.py`

Production deep links (e.g., `/join/C1E7F362`) returned 404 because Starlette's `StaticFiles` only serves files that exist on disk. React Router requires the server to serve `index.html` for all non-API paths so the client-side router can resolve the route.

- **`SPAStaticFiles` subclass:** Extends Starlette's `StaticFiles`. Overrides `get_response()` to catch 404 exceptions and serve `index.html` (via `super().get_response(".", scope)`) instead.
- **Route priority:** API routes (`/api/*`) and WebSocket routes (`/ws/*`) are registered on the FastAPI app before the `app.mount("/", SPAStaticFiles(...))` call. FastAPI evaluates routes in registration order, so API and WS endpoints always take priority over the SPA catch-all.
- **No reverse proxy needed:** This approach avoids adding Nginx, Caddy, or a Cloud Run URL rewrite rule — the single-container deployment model is preserved.

## 12.8.2 Audio WebSocket Reconnection Architecture

**Files:** `frontend/src/hooks/useAudioCapture.js`

Mobile browsers aggressively suspend WebSocket connections when the page loses focus (tab switch, screen lock, notification tray). The previous implementation tore down the entire mic pipeline (MediaStream, AudioContext, AudioWorkletNode) on WS disconnect, causing a costly re-initialization on every reconnect.

**Separated lifecycle model:**
- **Mic layer (persistent):** MediaStream, AudioContext, and AudioWorkletNode are created once per `startCapture()` call and persist until `stopCapture()`. They are NOT destroyed on WS disconnect.
- **WS layer (reconnectable):** The WebSocket connection to `/ws/audio/{game_id}` can be torn down and re-established independently. On reconnect, the existing AudioWorkletNode resumes sending PCM frames to the new WS connection.

**Reconnection strategy:**
- **Exponential backoff:** Delays [500, 1000, 2000, 4000, 8000]ms, max 10 attempts. After 10 failures, the mic is released and the user is notified.
- **Page Visibility API:** On `visibilitychange` to `hidden`, the audio WS is proactively closed (prevents mobile browsers from sending a stale close frame later). On `visibilitychange` to `visible`, the WS is reconnected and `AudioContext.resume()` is called (browsers suspend AudioContext when the page is hidden).
- **`connectingRef` guard:** A ref tracks whether a connection attempt is in flight. The visibility handler checks this guard to prevent orphaning `startCapture`'s pending connection promise when the user rapidly switches tabs.

## 12.8.3 Game Control WebSocket Mobile Resilience

**Files:** `frontend/src/hooks/useWebSocket.js`

The game-state WebSocket (`/ws/{game_id}`) had similar mobile tab-switch issues:

- **CONNECTING state guard:** Prevents duplicate WebSocket connections when `visibilitychange` fires during an in-progress connection attempt. Without this guard, mobile tab-switches could spawn parallel connections, causing duplicate message delivery.
- **Page Visibility API integration:** On `visibilitychange` to `visible`, an immediate reconnect is triggered (bypassing the normal backoff delay). This ensures the game state is re-synced as fast as possible when the user returns to the tab.
- **Sync heartbeat:** Every 2 seconds, the client sends a `{ type: "sync" }` message and the server responds with the current game phase. If the client's local phase does not match the server's phase, the client force-disconnects and reconnects. On reconnect, the server replays the latest state (via the `connected` message), bringing the client back in sync. This catches state drift that occurs when WS messages are delivered while the page is hidden (some browsers buffer but do not process them).

## 12.8.4 Vote Tally Data Flow

**Files:** `backend/routers/ws_router.py`, `frontend/src/components/Game/VoteTallyOverlay.jsx`, `frontend/src/context/GameContext.jsx`

Vote tallies were previously invisible to players after voting concluded. The `tally_votes()` function in the Game Master clears AI characters' `voted_for` fields as a side effect, so individual vote data was lost before it could be broadcast.

**Data capture timing:**
- **Before `tally_votes()`:** The WS router now snapshots individual votes (`{voter_character_name: voted_for_character_name}`) from all players and AI characters BEFORE calling `tally_votes()`.
- **`broadcast_elimination` payload:** The elimination broadcast now includes two new fields:
  - `individualVotes: Record<string, string>` — who voted for whom.
  - `isTie: boolean` — whether the vote resulted in a tie (no elimination).

**Frontend:**
- **`VoteTallyOverlay`:** New component that renders during the `elimination` phase. Displays each character's vote as a visual mapping (voter arrow target). Shows "TIE — No elimination" when `isTie` is true.
- **`GameContext` reducer:** The `ELIMINATION` action stores `lastVoteResult` (containing `individualVotes` and `isTie`). This state is preserved while the phase remains `elimination` and cleared on transition to any other phase.

## 12.8.5 Scene Image Prompt Optimization

**Files:** `backend/agents/scene_agent.py`

Production scene images were averaging 2.3MB — too large for reliable delivery to mobile clients and occasionally exceeding serving limits (images were silently skipped).

- **Style change:** Prompt changed from "dark painterly illustration" to "flat vector illustration, limited color palette (5-6 colors max)".
- **Description simplification:** Scene descriptions are now 2-3 sentences with silhouettes and solid shapes, rather than detailed realistic descriptions.
- **Result:** Generated images are consistently under 500KB, eliminating the silent-skip issue.

## 12.8.6 Gemini Live API Log Cleanup

**Files:** `backend/agents/narrator_agent.py`

Non-standard Gemini Live API response fields were flooding production logs:

- **`session_resumption_update`:** Handler now properly `continue`s in the message processing loop. Previously it fell through to the NON-STANDARD catch-all logger, producing a log line for every session resumption update.
- **`voice_activity` and `voice_activity_detection_signal`:** Explicitly handled with `continue` — these are informational Gemini signals that do not require processing.
- **NON-STANDARD log level:** Changed from `logger.info` to `logger.debug`. Unknown Gemini fields are still logged for diagnostic purposes but no longer pollute production log aggregations at the default log level.

## 12.8.7 Production WebSocket Keep-Alive

**Files:** `Dockerfile`

The uvicorn CMD in the Dockerfile now includes `--ws-ping-interval=15 --ws-ping-timeout=20`. This is tighter than the v5.0 application-level configuration (20s/30s) based on production data showing that Cloud Run's load balancer dropped idle WebSocket connections before the server's 20s ping could fire. The 15s interval keeps connections alive through Cloud Run's idle detection.

---

# 13. PRD Cross-Reference & Compliance Matrix

| PRD Requirement | TDD Section | Status |
|---|---|---|
| Voice narration + interruptions (P0) | §3.1 Narrator Agent, §5 WebSocket Protocol | ✅ Shipped |
| Role assignment system (P0) | §3.3 Game Master, §6 Data Model | ✅ Shipped |
| Game state machine (P0) | §3.3 GamePhase enum + transitions | ✅ Shipped |
| AI-as-player Agent (P0) | §3.2 AI Agent Functions, §4.2 | ✅ Shipped (v4.0: unified standalone functions) |
| Multiplayer WebSocket hub (P0) | §5 WebSocket Protocol, §5.3 Server | ✅ Shipped |
| Voting system (P0) | §3.3 count_votes | ✅ Shipped |
| Player phone UI (P0) | §8 Frontend Architecture | ✅ Shipped |
| Hide AI identity (P0) | (new) | ✅ Shipped — AI never exposed via HTTP |
| Join cap (P0) | (new) | ✅ Shipped — 409 at 7 humans |
| Session resumption (P1) | §7 Session Management | ✅ Shipped |
| Hunter + Drunk roles (P1) | §3.3 ROLE_DISTRIBUTION | ✅ Shipped |
| Traitor difficulty levels (P1) | §3.2 TRAITOR_DIFFICULTY | ✅ Shipped |
| Quick-reaction buttons (P1) | §5.2 QuickReaction type | ✅ Shipped |
| Post-game reveal timeline (P1) | §4.3 handle_game_over | ✅ Shipped |
| Landing page (P1) | §8 Frontend Architecture | ✅ Shipped |
| Session persistence (P1) | (new) | ✅ Shipped — sessionStorage |
| GameOver REST fallback (P1) | (new) | ✅ Shipped — /api/games/{id}/result |
| Narrator audio preview (P1) | (new) | ✅ Shipped — /api/narrator/preview/{preset} |
| Host badge (P1) | (new) | ✅ Shipped |
| Day-phase hint (P1) | (new) | ✅ Shipped |
| **P2 Features** | | |
| Procedural character generation | §12.3.1 | ✅ Shipped |
| Narrator vote neutrality | §12.3.2 | ✅ Shipped |
| Narrator pacing intelligence | §12.3.3 | ✅ Shipped |
| Affective dialog input signals | §12.3.4 | ✅ Shipped |
| Minimum satisfying game length | §12.3.5 | ✅ Shipped |
| In-game role reminder | §12.3.6 | ✅ Shipped |
| Tutorial mode | §12.3.7 | ✅ Shipped |
| Conversation structure for large groups | §12.3.8 | ✅ Shipped |
| Minimum player count design | §12.3.9 | ✅ Shipped |
| Random AI alignment | §12.3.10 | ✅ Shipped |
| Additional roles — Bodyguard, Tanner | §12.3.11 | ✅ Shipped |
| Dynamic AI difficulty | §12.3.12 | ⬜ Deferred to P3 |
| Post-game timeline interactive UX | §12.3.13 | ✅ Shipped |
| Scene image generation | §12.3.14 | ✅ Shipped |
| Audio recording/playback | §12.3.15 | ✅ Shipped |
| Camera vote counting | §12.3.16 | ✅ Shipped |
| Narrator style presets | §12.3.17 | ✅ Shipped |
| Competitor intelligence for AI | §12.3.18 | ✅ Shipped |
| **Post-P2 Features** | | |
| Player voice input pipeline | §12.5.1 | ✅ Shipped |
| Speaker identification | §12.5.2 | ✅ Shipped |
| Dynamic discussion timer | §12.5.3 | ✅ Shipped |
| Narrator dual-mode engagement | §12.5.4 | ✅ Shipped |
| Human shapeshifter night kill | §12.5.5 | ✅ Shipped |
| Multi-stage Dockerfile | §12.5.6 | ✅ Shipped |
| Terraform IaC (updated) | §12.5.6 | ✅ Shipped |
| Deployment guide | §12.5.6 | ✅ Shipped |
| **v4.0 Architecture** | | |
| Unified AI standalone functions | §3.2, §4.2 | ✅ Shipped — replaces TraitorAgent + LoyalAgent classes |
| Multi-AI character support (ai_characters[]) | §3.2, §3.3, §6.1 | ✅ Shipped — N AI characters via array |
| asyncio.gather() concurrency | §3.2, §4.2 | ✅ Shipped — parallel AI votes/dialogs/night actions |
| AI bodyguard sacrifice | §3.3 resolve_night | ✅ Shipped |
| AI Seer investigation | §3.3 resolve_night | ✅ Shipped — ai_seer_result event type |
| Polling vote wait | §5.3 | ✅ Shipped — 5 iterations x 2s |
| Difficulty adapter next() iterator | §5.3 | ✅ Shipped — finds traitor AI via next() |
| ROLE_DISTRIBUTION[3] removed | §3.3 | ✅ Shipped — minimum 4 characters |
| {fs_field}_night_{role} event pattern | §6.1 | ✅ Shipped |
| Frontend aiCharacters[] array | §8.1 | ✅ Shipped — GameContext + useWebSocket |
| Wire protocol split/assemble pattern | §5.2, §5.3 | ✅ Shipped — backend sends aiCharacter/aiCharacter2; frontend assembles aiCharacters[] |
| Narrator get_game_state ai_characters[] | §4.1 | ✅ Shipped — Narrator tool returns array, not singular field |
| **v5.0 Architecture** | | |
| Separate audio WebSocket /ws/audio/{gameId} | §12.6.1, §5.2, §5.3 | ✅ Shipped — binary PCM frames, isolated lifecycle |
| Push-to-talk speaker lock | §12.6.2, §2.2 Decision 6 | ✅ Shipped — TOCTOU-safe, 30s auto-release, dead-player guard |
| Per-player priority queues (ConnectionManager) | §12.6.3, §5.3 | ✅ Shipped — control + audio queues, local echo dedup |
| Phase timer: start_phase_timer narrator tool | §12.6.4, §4.1, §4.3 | ✅ Shipped — narrator signals narration complete |
| Phase timer: 15s safety fallback | §12.6.4 | ✅ Shipped — fires if narrator never calls start_phase_timer |
| Phase timer: updated timeouts (night 30s, vote 60s) | §12.6.4 | ✅ Shipped |
| Phase timer: 45s min discussion guard | §12.6.4 | ✅ Shipped |
| WebSocket keepalive (ping 20s / timeout 30s) | §12.6.5 | ✅ Shipped — re-enabled; disconnect events logged |
| Shapeshifter skip (skip_night_kill) | §12.6.6, §5.2 | ✅ Shipped — frontend button + backend null-target resolution |
| **v5.1 Architecture** | | |
| Ghost Council dead-player chat | §12.7.1 | ✅ Shipped — ghost_message WS type, GhostRealmPanel, 2s rate limit |
| Séance phase | §12.7.2, §3.3 | ✅ Shipped — conditional phase after ELIMINATION, 45s ghost testimony |
| Haunt actions (dead player night action) | §12.7.3 | ✅ Shipped — ghost accusation per round, AI auto-accuse |
| AI auto-reply system | §12.7.4 | ✅ Shipped — name-match trigger, 30s cooldown, source="player" |
| Discussion timer enforcement | §12.7.5 | ✅ Shipped — rejects advance_phase without start_phase_timer |
| Responsive roster (RosterPanel) | §12.7.6 | ✅ Shipped — RosterSidebar + RosterIconStrip, 768px breakpoint |
| Phase change data sync | §12.7.7, §5.2 | ✅ Shipped — full roster + AI chars in phase_change, all players in connected |
| Concurrency guards (_resolving_nights) | §12.7.8, §5.3 | ✅ Shipped — double-resolution prevention, alive check before kill |
| Simplified win condition (parity) | §3.3 | ✅ Shipped — non_shapeshifter_alive <= 1, no round guard |
| Night timeout 45s (Gemini RPC latency) | §12.7.8, §12.6.4 | ✅ Shipped — reverted from 30s |
| **v5.2 Bug Fix Sprint** | | |
| SPA catch-all routing (SPAStaticFiles) | §12.8.1, §2.2 Decision 8, §5.3 | ✅ Shipped — React Router deep links work in production |
| Audio WS reconnection (separated mic/WS lifecycle) | §12.8.2, §12.6.1, §2.2 Decision 5 | ✅ Shipped — exponential backoff, Page Visibility API, connectingRef guard |
| Game WS mobile resilience | §12.8.3 | ✅ Shipped — CONNECTING guard, visibility reconnect, 2s sync heartbeat |
| Vote tally data flow (individualVotes, isTie) | §12.8.4, §5.2 | ✅ Shipped — VoteTallyOverlay, pre-tally vote capture |
| Scene image prompt optimization | §12.8.5, §12.3.14 | ✅ Shipped — flat vector style, <500KB images |
| Gemini Live API log cleanup | §12.8.6 | ✅ Shipped — proper continue for voice_activity, debug-level NON-STANDARD |
| Production WS keep-alive (Dockerfile CMD) | §12.8.7, §12.6.5 | ✅ Shipped — --ws-ping-interval=15 --ws-ping-timeout=20 |

---

# 14. Environment Variable Manifest

**Implementation Update:** Actual config uses Pydantic Settings (`backend/config.py`).

| Variable | Required | Description | Example |
|---|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | ✓ | GCP project ID | `fireside-hackathon-2026` |
| `GEMINI_API_KEY` | ✓ | Gemini API key | `AIzaSy...` |
| `GOOGLE_APPLICATION_CREDENTIALS` | | Path to service account JSON (local dev) | `./sa-key.json` |
| `FIRESTORE_EMULATOR_HOST` | | Firestore emulator address (local dev) | `localhost:8081` |
| `NARRATOR_MODEL` | | Narrator Gemini model | `gemini-2.5-flash-native-audio-latest` |
| `TRAITOR_MODEL` | | Traitor strategy model | `gemini-2.5-flash` |
| `NARRATOR_PREVIEW_MODEL` | | TTS preview model | `gemini-2.5-flash-preview-tts` |
| `NARRATOR_VOICE` | | Default narrator voice | `Charon` |
| `ALLOWED_ORIGINS` | | CORS allowed origins (comma-separated) | `https://app.example.com` |
| `EXTRA_ORIGIN` | | Additional CORS origin (e.g., Cloud Run URL) | `https://fireside-xxx.run.app` |
| `DEBUG` | | Enable debug logging | `true` |
| `PORT` | | Server port (Cloud Run provides this) | `8080` |

```bash
# .env.example
GOOGLE_CLOUD_PROJECT=fireside-hackathon-2026
GEMINI_API_KEY=your-api-key-here
GOOGLE_APPLICATION_CREDENTIALS=./sa-key.json
# FIRESTORE_EMULATOR_HOST=localhost:8081  # uncomment for local dev
NARRATOR_MODEL=gemini-2.5-flash-native-audio-latest
TRAITOR_MODEL=gemini-2.5-flash
NARRATOR_PREVIEW_MODEL=gemini-2.5-flash-preview-tts
NARRATOR_VOICE=Charon
# ALLOWED_ORIGINS=https://your-app.run.app  # production CORS
# EXTRA_ORIGIN=https://your-frontend.run.app
PORT=8080
```

---

*Document created: February 21, 2026*
*Last updated: March 12, 2026 — v5.1: Ghost Council dead-player chat (ghost_message WS type, GhostRealmPanel), Séance phase (conditional ghost testimony), haunt actions (dead player night accusations), concurrency guards (_resolving_nights + alive check), AI auto-reply system (_maybe_trigger_ai_reply), discussion timer enforcement, simplified win condition (parity), responsive roster (RosterPanel), phase change data sync (full roster in phase_change + connected messages)*
*Companion PRD: PRD.md v2.0*
*Hackathon deadline: March 16, 2026*
# Product Requirements Document
## Fireside — Betrayal

**Category:** 🗣️ Live Agents
**Tagline:** The AI is one of you. Trust no one.
**Core Technology:** Gemini Live API (real-time bidirectional voice)

Version 3.0 | February 26, 2026 *(updated to reflect voice engagement overhaul, discussion timer, speaker identification, human shapeshifter night kill, IaC, and deployment guide)*
Hackathon Deadline: **March 16, 2026 at 5:00 PM PDT**
Prize Target: $10K (category) + $25K (grand prize)

---

# Executive Summary

Fireside — Betrayal is a real-time, voice-first multiplayer social deduction game built for the Gemini Live Agent Challenge hackathon ($80K prize pool, Google DeepMind / Devpost). An AI narrator leads players through an immersive collaborative story using natural voice conversation — but one of the characters is secretly the AI, working against the group.

The game combines the narrative immersion of tabletop RPGs with the social tension of Werewolf/Mafia, eliminating the need for a human moderator or game master. Built on the Gemini Live API, Google ADK, and Google Cloud, it showcases real-time voice interaction with barge-in support, affective dialog, multi-agent orchestration, and autonomous AI decision-making.

| | Details |
|---|---|
| **Primary User** | Friend groups (3–8 players: 2–7 humans + 1 AI) |
| **Platform** | Mobile web (phones) + optional shared screen |
| **Session Length** | 15–30 minutes per game |
| **Core Mechanic** | AI narrates + secretly plays as one character (or plays as a loyal ally — players don't know) |
| **Input** | Voice via phone microphone (primary — streamed to narrator with speaker identification), text (fallback), camera (in-person hand-counting) |
| **Output** | Voice narration (4 narrator presets), scene images, private role cards, audio highlights |

---

# Problem Statement

Social deduction games (Werewolf, Mafia, Secret Hitler) and tabletop RPGs (Dungeons & Dragons) are among the most popular social gaming formats, but both suffer from critical friction:

1. **Moderator sacrifice:** In social deduction games, one player must always sit out to moderate. This reduces fun for that person and limits the number of active participants.
2. **DM preparation burden:** Tabletop RPGs require a skilled game master who invests hours preparing campaigns, creating a high barrier to spontaneous play. Most friend groups don't have a willing DM.
3. **No voice-first AI games exist:** Current AI game masters (AI Dungeon, RPGGO, Friends & Fables) are entirely text-based. None support real-time voice conversation with interruption handling — the most natural way humans actually play these games.
4. **Social deduction and storytelling are separate genres:** Nobody has merged the narrative immersion of RPGs with the social tension of deduction games into a single experience.

---

# Solution

Fireside — Betrayal is a real-time, voice-first multiplayer game that combines collaborative storytelling with social deduction. An AI narrator leads players through an immersive adventure using natural voice conversation — but one of the characters in the story is secretly the AI, working against the group.

## Core Experience

- **Players speak naturally** — talk into your phone microphone, no typing, no turn-taking. Audio is streamed directly to the narrator's Gemini session with speaker identification so the AI knows exactly who is speaking. Interrupt the AI mid-sentence to object. Argue with other players in real time. The Gemini Live API's barge-in support makes heated debates feel natural.
- **AI narrates dramatically** — setting scenes, voicing NPCs, building tension with pauses and vocal inflection. During discussions, the narrator shifts to an active moderator/game show host role: relaying player speech, reacting with provocative one-liners, stirring debate, and redirecting when conversations loop. Affective dialog adapts the narrator's tone to match game tension (whispered during night phase, urgent during accusations).
- **AI plays as a hidden character** — with its own backstory, motivations, and deception strategy. It participates in discussions, deflects suspicion, and accuses others. Players must figure out which character is the AI before it's too late.
- **No moderator needed** — the AI handles all game management duties (role assignment, phase transitions, vote tallying, win condition checks) while simultaneously participating as a story character.

## Game Concept

Players gather around a fire (metaphorically — on their phones). The AI narrator tells a story of a village under threat. Each player is assigned BOTH a secret role AND a story character identity (e.g., "Elena the Herbalist," "Brother Aldric," "Mira the Huntress"). One additional character in the story is secretly the AI — a shapeshifter working to sabotage the group. During gameplay, players interact using ONLY their character names. The mystery is: which character at the table is controlled by a human, and which one is the AI? Through cycles of night actions and day debates, players must identify and vote out the AI's character before it eliminates them all.

**Roles (8 total — all implemented):**
- **Villager** — survive and identify the traitor
- **Seer** — can investigate one character each night to learn their true nature
- **Healer** — can protect one character from elimination each night
- **Hunter** — when eliminated, immediately kills one other character of their choice (dramatic reversal moment)
- **Drunk** — told they are the Seer, but receives false investigation results (creates hilarious misinformation)
- **Bodyguard** — each night, protect one character; if the Shapeshifter targets them, the Bodyguard absorbs the kill instead
- **Tanner** — solo win condition: wins only if voted out by the village (must act suspicious without being obvious)
- **Shapeshifter (AI)** — the AI's secret character, trying to avoid detection while sabotaging the group (or, with Random AI Alignment, the AI may draw any role and play loyally)

---

# User Flow

| Phase | What Happens | Player Experience |
|---|---|---|
| 1. Lobby | Host creates game, selects difficulty (Easy/Normal/Hard), selects narrator preset (Classic/Campfire/Horror/Comedy — with audio preview), shares 6-character alphanumeric join code (`THRNX5`). Players connect on their phones. Max 7 humans + 1 AI. | Simple join screen — enter name, select difficulty + narrator voice, preview narrator audio, see other players arriving. Lobby summary shows role distribution and min-player warning if < 4 players. |
| 2. Role Assignment | AI assigns each player a secret role (Villager, Seer, Healer, Hunter, Drunk, Bodyguard, Tanner — based on player count) AND a unique LLM-generated story character identity. With Random AI Alignment (Normal/Hard), the AI draws from the full role pool — it might be the Shapeshifter, or a loyal Seer. All players see only character names from this point forward — real names are hidden. AI character is indistinguishable from human players. | Private role card: "You are **Tinker Orin** (Healer). Each night, choose one character to protect." Expandable role strip shows ability reminder. Players know their own character name but not which character belongs to which friend. |
| 3. Story Begins | AI narrator sets the scene with dramatic voice narration. "The village of Thornwood sleeps beneath a pale moon..." Introduces all characters by name. | Players listen together. Each character is introduced with a brief personality hook. "Brother Aldric tends the chapel garden. Mira the Huntress returns from the forest with an uneasy look." |
| 4. Night Phase | AI privately contacts special-role holders. Seer investigates (Drunk gets false results). Healer protects. Hunter has no night action. AI's shapeshifter picks a target. | Private text on individual phones. Other players see "Night has fallen..." with atmospheric narration. |
| 5. Day Discussion | AI narrates what happened overnight, then opens discussion with a **dynamic countdown timer** scaled by player count (3–4 players: 2 min, 5–6: 3 min, 7–8: 4 min). Players debate via **phone microphone** (audio streamed directly to narrator with speaker identification) OR text input OR quick-reaction buttons. Narrator acts as **active moderator/game show host**: relays player speech for the village, reacts with provocative one-liners, stirs debate by challenging weak arguments, and redirects when discussion loops. AI participates as its character. 30-second narrator warning before timer expires. | Visible M:SS countdown in sticky header with color transitions (gray → amber at 30s → red pulse at 15s). Speak naturally into phone mic — narrator knows who is talking via `[VOICE] {CharacterName}` annotations. Quick-reaction buttons for fast text participation. Narrator engages actively as moderator, not passive observer. |
| 6. Voting | Players vote to eliminate a suspect character using buttons on their phones. AI tallies votes and handles ties. | Character portrait buttons to vote. Timer countdown. AI announces results with dramatic narration. |
| 7. Elimination | AI narrates the elimination with story consequences. If the eliminated player was the Hunter, they immediately choose someone to take with them. Reveals whether the eliminated character was the traitor or innocent. | Dramatic reveal moment. Hunter's revenge kill creates unexpected second elimination. Eliminated players become spectators. |
| 8. Resolution | Repeat Night/Day cycles until villagers correctly identify the shapeshifter OR the shapeshifter eliminates enough villagers to win OR the Tanner gets voted out (solo win). | Win/lose screen with **post-game reveal timeline**: round-by-round interactive view showing every hidden action, the AI's strategy reasoning, audio highlight reel, and key turning points. All character-to-player mappings revealed. Share results with a copy-to-clipboard summary. Direct URL navigation to `/gameover/:gameId` works via REST fallback. |

---

# Multimodal Capabilities

| Modality | How Fireside Uses It | Category Requirement |
|---|---|---|
| **Voice Input** | Players speak into phone microphones — audio is streamed to the narrator's Gemini Live API session via AudioWorklet (16kHz PCM16 mono). Speaker identification annotates each speaker (`[VOICE] {CharacterName} is now speaking`). Transcript buffering (0.8s debounce) shows complete sentences. Can interrupt the AI mid-narration to object or interject. | ✓ Natural conversation |
| **Voice Output** | AI narrates with dramatic tone, voices different NPCs with distinct personalities, adapts emotional delivery via affective dialog. | ✓ Distinct persona/voice |
| **Vision Input** | Camera can observe the room for hand-raise vote counting and player presence detection. | ✓ Vision-enabled interaction |
| **Interruption Handling** | Players yelling objections during accusations IS the core gameplay. Barge-in is not a feature — it's the mechanic. | ✓ Handles interruptions |
| **Agentic Behavior** | AI manages hidden game state, enforces rules, makes autonomous strategic decisions as its secret character, and adapts its deception strategy based on player behavior. | ✓ Autonomous agent |
| **Proactive Audio** | AI decides when to interject as its character vs. stay silent, creating natural conversation flow without rigid turn-taking. | ✓ Proactive responses |

---

# Technical Architecture

## Agent Design (Google ADK)

| Agent | Type | Model | Responsibilities |
|---|---|---|---|
| **Narrator Agent** | LLM Agent (Primary) | gemini-2.5-flash-native-audio-preview-12-2025 | Story narration, scene setting, NPC voices, dramatic reveals. Voice: "Charon" (deep, dramatic). Affective dialog enabled. Tools: `get_game_state`, `advance_phase`, `describe_scene`. |
| **Game Master Agent** | Workflow Agent (Deterministic) | N/A — pure logic | Phase transitions (SETUP→NIGHT→DAY→VOTE→ELIMINATION→repeat), rule enforcement, vote counting, win condition checks. Tools: `assign_roles`, `count_votes`, `eliminate_player`, `check_win_condition`. |
| **Traitor Agent** | LLM Sub-agent | Same Gemini model, separate system prompt | AI's hidden player persona. Generates bluffs, deflection tactics, and strategic accusations. Has access to all players' roles and game strategy tools. Responses are mixed into the story as character dialog. Tools: `plan_deflection`, `generate_alibi`, `accuse_player`. |

## Infrastructure

| Service | Role | Justification |
|---|---|---|
| **Cloud Run** | Backend API + ADK agent host | Serverless, auto-scaling, WebSocket support, one-command ADK deploy via `adk deploy cloud_run`. |
| **Cloud Firestore** | Real-time game state | Real-time listeners sync game state (roles, votes, alive/dead, phase) across all player devices instantly. Generous free tier (1 GiB). |
| **Cloud Storage** | Scene images, audio assets | Store generated scene illustrations and any pre-recorded audio clips. |
| **Cloud Build + Terraform** | CI/CD pipeline + IaC | Automated deployment for bonus points (+0.2). Push to main auto-deploys to Cloud Run. Full Terraform configuration in `terraform/` directory (main.tf, variables.tf, terraform.tfvars.example) for reproducible Cloud Run deployments. Multi-stage Dockerfile at repo root (frontend build + backend). |
| **Artifact Registry** | Container images | Required by Cloud Run deploy pipeline. |

## System Architecture

```
Player Phones (2-7) ←WebSocket→ Cloud Run (FastAPI)
  ├── Mic audio (PCM16)               ├── ADK Agent Orchestrator
  ├── Text / quick reactions           │   ├── Narrator Agent (Live API voice)
  └── Vote actions                     │   ├── Game Master Agent (deterministic)
                                       │   └── Traitor Agent (LLM sub-agent)
                                       ├── Gemini Live API (WebSocket)
                                       │   ├── Audio output → broadcast to all players
                                       │   └── Audio input ← player mic streams
                                       ├── Cloud Firestore (game state)
                                       └── Cloud Storage (scene images)
```

See also: `docs/architecture.mermaid` for the full visual architecture diagram (Mermaid).

## Session Management

The Gemini Live API has a ~10-minute connection limit and 15-minute audio session cap. For games running 15–30 minutes:

- **Session resumption:** Enable `session_resumption` in LiveConnectConfig with a session handle for automatic reconnection after timeout, preserving conversation context.
- **Context window compression:** Enable `context_window_compression` to automatically summarize older conversation history, extending sessions to unlimited duration.
- **Firestore as source of truth:** Critical game state (roles, votes, alive/dead status, story progress) is persisted in Firestore, not just in the Live API session memory. On reconnection, the full game state summary is re-injected into the new session context.
- **Dynamic discussion timer:** Day discussion phase uses a server-coordinated countdown timer that scales by player count (3–4 players: 2 min, 5–6: 3 min, 7–8: 4 min). Timer state is synced to all clients via WebSocket. The narrator receives a 30-second warning to wrap up discussion. Timer countdown is rendered in a sticky header with visual urgency cues (gray → amber at 30s → red pulse at 15s).

## Multiplayer Audio Architecture

To manage concurrent session limits (3–50 per GCP project), we use a simplified hub model:

- **Single narrator session:** Server maintains ONE Live API session for the narrator agent. This is the only entity that needs real-time voice output.
- **Player input via microphone (primary):** Players speak into their phone microphones. Audio is captured via AudioWorklet (16kHz PCM16 mono) and streamed to the server, which injects it into the narrator's Gemini Live API session. Speaker identification annotates each speaker with `[VOICE] {CharacterName} is now speaking via microphone`, enabling the narrator to distinguish between players in real time. Transcript buffering (0.8s debounce) aggregates Gemini's `input_audio_transcription` events into complete sentences before display.
- **Player input via text (fallback):** Players can also send text messages or use quick-reaction buttons. Server injects player messages into the narrator's context as attributed dialog.
- **Broadcast audio:** Narrator's audio responses are streamed to all connected player WebSockets simultaneously.
- **Private channels:** Role assignments and night-phase messages are sent via text to individual player WebSockets only.

This avoids the need for per-player Live API sessions (which would hit concurrent limits immediately) while preserving the core voice experience. The microphone-first approach means players interact naturally — speaking and interrupting — while the narrator hears and responds to every participant by name.

## Game State Schema (Firestore)

```
games/{gameId}/
  ├── status: "waiting" | "in_progress" | "finished"
  ├── phase: "night" | "day_discussion" | "day_vote" | "elimination"
  ├── round: 1
  ├── story_context: "The village of Thornwood sleeps..."
  ├── ai_character: { name: "Blacksmith Garin", role: "shapeshifter" }
  ├── players/
  │   └── {playerId}/
  │       ├── name: "Alex"
  │       ├── role: "villager" | "seer" | "healer"
  │       ├── alive: true
  │       ├── voted_for: null | "playerId"
  │       └── session_handle: "ws_session_xyz"
  └── events/ (append-only log)
      └── {eventId}/
          ├── type: "night_action" | "accusation" | "vote" | "elimination"
          ├── actor: "playerId" | "ai"
          ├── target: "playerId"
          ├── narration: "The seer peered into the darkness..."
          └── timestamp: ...
```

## Frontend (React Web App)

```
/                 → Landing page (hero, how-it-plays, roles teaser, CTA → create game)
/join/{gameCode}  → Join screen (enter name, see other players)
/game/{gameCode}  → Game screen
  ├── Audio player (narrator voice stream)
  ├── Microphone input (AudioWorklet, 16kHz PCM16 mono → streamed to narrator)
  ├── Scene image (generated per phase, optional)
  ├── Role reveal overlay (dramatic role assignment at game start)
  ├── Role card (private, only visible to this player)
  ├── Player list (alive/dead status, vote indicators)
  ├── Discussion timer (sticky header, M:SS countdown with color transitions)
  ├── Chat input (text + quick reactions, fallback to mic)
  ├── Vote buttons (appear during voting phase only)
  ├── Night kill UI (for human shapeshifters via Random AI Alignment)
  └── Story log (scrollable narrative history)
```

---

# Judging Criteria Alignment

| Criterion | Weight | How Fireside Addresses It | Target |
|---|---|---|---|
| **Innovation & Multimodal UX** | 40% | Voice-first with barge-in (no existing AI game does this). AI plays as a deceptive character (completely novel mechanic). Vision input for hand-raise vote counting. Affective dialog adapts narrator tone to game tension. Social deduction + RPG hybrid is a new genre combination. | 5/5 |
| **Technical Implementation** | 30% | Multi-agent ADK architecture with 3 specialized agents. Gemini Live API with session resumption + context compression for extended play. Cloud Run + Firestore for real-time multiplayer state sync. Automated IaC deployment via Terraform + Cloud Build. | 4–5/5 |
| **Demo & Presentation** | 30% | Highly engaging demo: show a group of friends playing, capture the moment players realize the AI was deceiving them the entire time. Clear architecture diagram. Live gameplay footage, not mockups. Under 4 minutes. | 5/5 |

---

# Mandatory Technical Compliance

| Requirement | Implementation | Status |
|---|---|---|
| Gemini model | gemini-2.5-flash-native-audio-preview-12-2025 | ✓ Compliant |
| GenAI SDK or ADK | Google ADK (Python) with bidi-streaming via `run_live()` | ✓ Compliant |
| Google Cloud service | Cloud Run + Cloud Firestore + Cloud Storage | ✓ Compliant |
| Hosted on Google Cloud | Cloud Run deployment (automated via Cloud Build) | ✓ Compliant |
| Category: Gemini Live API or ADK streaming | Gemini Live API via ADK `run_live()` + `LiveRequestQueue` | ✓ Compliant |
| Public code repository | GitHub (public, MIT license) | ✓ Compliant |
| Demo video < 4 minutes | Gameplay footage + architecture walkthrough | ✓ Planned |

---

# MVP Scope (3-Week Timeline)

> **Implementation Status Key:** ✅ Shipped | 🔄 In Progress | ⬜ Not Started

| Feature | Priority | Status | Description |
|---|---|---|---|
| Voice narration + interruptions | **P0** | ✅ Shipped | AI narrator speaks in real-time with dramatic tone, handles player interruptions via barge-in. Rule violations handled narratively. Narrator silence fallback (15s "thinking" indicator) if Gemini goes quiet. |
| Role assignment system | **P0** | ✅ Shipped | 8 roles across 3–8 player games. LLM-generated character cast with static fallback. Role distribution adapts by player count. Lobby summary shows role breakdown to host. Min-player warning when < 4 humans. |
| Character identity system | **P0** | ✅ Shipped | LLM-generated unique characters each game (name + intro + personality hook). AI character is indistinguishable from human players — HTTP responses never expose AI identity. All in-game interactions use character names only. |
| Game state machine | **P0** | ✅ Shipped | Night/Day Discussion/Day Vote/Elimination phases with deterministic transitions. Server-side 90s vote timeout prevents games hanging. |
| AI-as-player (Traitor Agent) | **P0** | ✅ Shipped | AI participates in day discussions as its character. Bluffs, deflects, accuses. Strategy logged for post-game reveal. Cross-game intelligence learning after 20+ games. |
| Multiplayer WebSocket hub | **P0** | ✅ Shipped | 2–7 humans connect via phones. Session persistence via sessionStorage — page refresh reconnects automatically. Top-level error handling prevents WS crashes. |
| Voting system | **P0** | ✅ Shipped | Phone voting + optional in-person camera hand-counting via Gemini Vision. Vote count capped at alive player count. 90s server-side timeout. |
| Player phone UI (React) | **P0** | ✅ Shipped | Mobile web app: expandable role strip with ability reminders, vote buttons, chat input with quick reactions, narrator audio stream, story log, character grid (AI hidden). Host badge in lobby. Day-phase contextual hint for first-timers. |
| Session resumption | **P1** | ✅ Shipped | Narrator reconnects with session handle + context compression. Max-retry fallback shows "Narrator unavailable" banner if Gemini fails to reconnect. |
| Hunter + Drunk roles | **P1** | ✅ Shipped | Hunter revenge kill on elimination. Drunk receives false Seer results. Drunk gated by difficulty (Easy: never, Normal: 6+, Hard: 5+). |
| Traitor difficulty levels | **P1** | ✅ Shipped | Easy/Normal/Hard with distinct system prompts + temperature. Auto-adjustment for small games (3–4 players: Hard→Normal, Normal→Easy). |
| Quick-reaction buttons | **P1** | ✅ Shipped | "I suspect [X]", "I trust [X]", "I agree", "I have information" — injected as attributed dialog into narrator context. |
| Narrator quick-reaction handling | **P1** | ✅ Shipped | Narrator narrativizes reactions as story beats. Prompt engineering in narrator system prompt. |
| Post-game reveal timeline | **P1** | ✅ Shipped | Interactive round-by-round timeline with night actions, AI reasoning, voting breakdowns. Audio highlight reel. Share button copies formatted game summary to clipboard. REST fallback (`/api/games/{id}/result`) for direct URL navigation. |
| Landing page | **P1** | ✅ Shipped | Hero with narrator audio preview button, CTA to create/join game. Mobile-first at 420px. |
| Narrator contextual reactivity | **P1** | ✅ Shipped | Scene descriptions reference previous round events. `get_game_state` tool feeds recent events into narrator context. |
| Narrator quiet-player engagement | **P1** | ✅ Shipped | Narrator tracks `characters_not_yet_spoken` and prompts after 60s silence. Max one prompt per silent player per round. |
| Spectator actions for eliminated players | **P1** | ✅ Shipped | One-word whisper clue per game, delivered during day discussion. Narrator narrates eerie in-story delivery. |
| Camera vote counting | **P2** | ✅ Shipped | Host enables "In-Person Mode" in lobby. Gemini Vision counts raised hands from camera frame. Hand count capped at alive player count. Phone voting remains fallback. |
| Scene image generation | **P2** | ✅ Shipped | Atmospheric illustrations on phase transitions (game start, night, dawn, elimination, game over). Gemini generates images with 1.5 MB guard. Fire-and-forget async. |
| Tutorial mode | **P2** | ✅ Shipped | 5-step interactive walkthrough: role reveal, night action, day discussion, voting, game over. Mock cast and timeline. Narrator audio preview on role reveal step. No backend required — fully client-side. |
| In-game role reminder | **P2** | ✅ Shipped | Expandable `RoleStrip` with ability description, icon, and label for all 8 roles. One-tap expand/collapse. |
| Minimum player count design | **P2** | ✅ Shipped | Difficulty auto-adjusts for 3–4 player games. Role distribution adapts (no Healer at 4 players). Lobby shows warning "Games work best with 4+ players" when < 4 humans. Technical minimum stays at 2 for dev/testing. |
| Narrator vote neutrality | **P2** | ✅ Shipped | `generate_vote_context` tool uses only public events log. Narrator prompt firewalled from traitor state. |
| Narrator pacing intelligence | **P2** | ✅ Shipped | `ConversationTracker` monitors message flow (PACE_HOT/NORMAL/NUDGE/PUSH/CIRCULAR). Day discussion transitions organically. Dynamic countdown timer scales by player count (2–4 min) with 30s narrator warning. `end_of_turn=False` parity for text messages in heated discussions (PACE_HOT) prevents narrator from responding to every message. |
| Affective dialog input signals | **P2** | ✅ Shipped | `AffectiveSignals` computes vote_tension, debate_intensity, late_game, endgame_imminent, ai_heat. Injected into narrator context for tone adjustment. |
| Conversation structure for large groups | **P2** | ✅ Shipped | `HandRaiseQueue` for 7+ players. Narrator calls on 2–3 characters first, then opens floor. "Raise hand" quick reaction added. |
| Minimum satisfying game length | **P2** | ✅ Shipped | Minimum rounds enforced: 3–4 players = 3 rounds, 5–6 = 3, 7 = 4, 8 = 5. Expected duration displayed in lobby. |
| Procedural character generation | **P2** | ✅ Shipped | LLM generates unique character cast each game via Gemini (name + intro + personality_hook). Genre seed system (`GENRE_SEEDS`) supports future expansion. Static fallback cast (8 characters) on failure. |
| Additional roles (Bodyguard, Tanner) | **P2** | ✅ Shipped | Bodyguard (absorbs Shapeshifter kill for protected player, available at 7+ players) and Tanner (solo win: get voted out, available at 8 players). Full night action handling, win conditions, and role reminders. |
| Random AI alignment | **P2** | ✅ Shipped | On Normal/Hard, AI draws from full role pool. May be Shapeshifter (hostile) or any village role (loyal). No shapeshifter in game when AI draws village role. Post-game reveals alignment. Derived from difficulty — no separate toggle needed. |
| Post-game timeline interactive UX | **P2** | ✅ Shipped | Round-by-round interactive timeline with public vs. secret split. "Key Round" highlight for closest vote. AI strategy teaser pull-quote above character reveals. Audio highlight reel with play buttons. |
| Narrator style presets | **P2** | ✅ Shipped | 4 presets: Classic (Charon voice, dramatic), Campfire (Puck voice, folksy), Horror (Charon voice, dread), Comedy (Kore voice, wry humor). Selection in lobby with audio preview. Each preset: system prompt prefix + voice config override. |
| Competitor intelligence for AI | **P2** | ✅ Shipped | Post-game strategy logs in Firestore. After 20+ completed games, Gemini aggregates patterns into "meta-strategy brief" injected into Traitor Agent prompt. Respects difficulty constraints. |
| **New: Hide AI identity** | **P0** | ✅ Shipped | AI character never exposed via HTTP. No AI label in character grid. WebSocket sends AI identity only in private `connected` message at game start. AI appears as a normal player throughout gameplay. |
| **New: Audio recording + highlights** | **P2** | ✅ Shipped | Narrator PCM audio recorded in segments by phase. Top-5 highlights ranked by priority. Base64 WAV encoded for post-game reel. In-memory only (max 10 segments × 10s). |
| **New: Session persistence** | **P1** | ✅ Shipped | `sessionStorage` preserves playerId, playerName, gameId, isHost across page refresh. `GameContext` initializes from storage. Cleared on GAME_OVER/RESET. |
| **New: GameOver REST fallback** | **P1** | ✅ Shipped | Direct navigation to `/gameover/:gameId` fetches game result from `GET /api/games/{id}/result` when WebSocket state is unavailable. Winner persisted in Firestore on game end (atomic write with status). |
| **New: Narrator audio preview** | **P1** | ✅ Shipped | Landing page and Tutorial show "Hear the narrator" button. Lobby shows preview per preset card. 3-second TTS samples cached in-memory via `GET /api/narrator/preview/{preset}`. |
| **New: Host badge** | **P1** | ✅ Shipped | Crown icon next to host name in lobby player grid. |
| **New: Day-phase hint** | **P1** | ✅ Shipped | One-time dismissible hint for first-timers during day discussion ("Discuss who you think the Shapeshifter is..."). |
| **New: Join cap** | **P0** | ✅ Shipped | Server returns 409 when 7th human tries to join (max 7 humans + 1 AI = 8 total). |
| **New: Player Voice Input (Mic)** | **P0** | ✅ Shipped | Players speak into phone microphone, audio streamed to narrator via AudioWorklet (16kHz PCM16 mono). Speaker identification via text annotation (`[VOICE] {CharacterName} is now speaking via microphone`). Transcript buffering (0.8s debounce) shows complete sentences instead of word-by-word fragments. Voice-optimized dialog prompts for traitor and loyal AI characters ("write for voice: contractions, short sentences, natural speech"). |
| **New: Dynamic Discussion Timer** | **P1** | ✅ Shipped | Visible countdown timer scales by player count (3–4 players: 2 min, 5–6: 3 min, 7–8: 4 min). 30-second narrator warning before time expires. Sticky header displays M:SS countdown with color transitions (gray → amber at 30s → red pulse at 15s). Replaces the previous 5-minute hard cap with player-count-aware timing. |
| **New: Narrator Voice Engagement** | **P1** | ✅ Shipped | Complete narrator personality overhaul from passive observer to active game show host/moderator. Dual-mode style guide: theatrical during narration phases, fast-paced moderator during discussion. Four narrator roles during discussion: RELAY (echo player points for the village), REACT (provocative 1-sentence reactions), STIR (challenge weak arguments), REDIRECT (break loops). All 4 narrator presets upgraded with discussion-specific personalities: Classic (stern village elder), Campfire (mischievous friend), Horror (unsettling observer), Comedy (sports announcer). `end_of_turn=False` parity for text messages in heated discussions (PACE_HOT). |
| **New: Human Shapeshifter Night Kill** | **P1** | ✅ Shipped | When Random AI Alignment gives a human player the shapeshifter role, they can perform night kills via the game UI. Complete implementation of human shapeshifter night kill action with backend logic and frontend target selection interface. |
| **New: Role Reveal Overlay** | **P2** | ✅ Shipped | Visual overlay showing role assignment on game screen at the start of the game. Provides a clear, dramatic moment when players learn their character and role. |
| **New: Terraform IaC** | **P2** | ✅ Shipped | Full Terraform configuration for automated Cloud Run deployment in `terraform/` directory (main.tf, variables.tf, terraform.tfvars.example). Infrastructure-as-code for reproducible production deployments. |
| **New: Deployment Guide** | **P2** | ✅ Shipped | `docs/DEPLOYMENT.md` with complete local development setup and Cloud Run production deployment instructions. |
| **New: Multi-Stage Docker Build** | **P2** | ✅ Shipped | Single Dockerfile at repo root with multi-stage build (frontend build + backend) for streamlined container image creation. |
| **New: Python 3.14 Compatibility** | **P2** | ✅ Shipped | Dependencies upgraded and pinned for Python 3.14 compatibility. |
| Multiple story genres | **P3 — Future** | ⬜ | Fantasy, mystery, sci-fi, horror story templates with different character sets, win conditions, atmosphere. |
| Persistent player profiles | **P3 — Future** | Track win/loss records, roles played, times they correctly identified the AI. Leaderboards across friend groups. Unlockable story genres. |
| Cross-device shared screen mode | **P3 — Future** | Dedicated "campfire screen" (TV/tablet) showing the shared narrative, scene images, and character status while phones remain private. Full second-screen experience. |

---

# Competitive Landscape

| Competitor | What It Does | Limitation | Our Edge |
|---|---|---|---|
| **AI Dungeon** | Text-based AI storytelling | Text-only, mostly single player | Multiplayer, voice-first, social deduction mechanic |
| **RPGGO AI** | AI game master for text RPGs | Text-based, no voice, no social deduction | AI plays AS a character, not just the GM |
| **Friends & Fables** | AI DM "Franz" with TTS narration | TTS but no real-time voice conversation, no barge-in | Live voice with interruptions, natural debate |
| **AI Realm** | D&D 5e AI game master | Single-player focused, text-based | Complete multiplayer game experience |
| **Inworld AI** | AI NPCs for game developers (B2B SDK) | Platform/SDK, not a consumer game | End-to-end game with novel social deduction genre |

**Key differentiators that no competitor has:**
1. Voice-first with interruptions — no existing AI game supports real-time voice with barge-in
2. Player microphone input with speaker identification — phone mic audio streamed directly to the narrator's Gemini Live API session, with per-speaker annotation so the AI knows who is talking
3. AI plays AS a character — the AI isn't just the narrator/GM, it's a deceptive participant with adjustable difficulty
4. Random AI alignment — the AI might be friend or foe, completely changing the meta-game each session
5. Character identity masking — all players AND the AI have LLM-generated story character names, making the AI unidentifiable
6. Active narrator moderation — narrator acts as game show host during discussions: relaying, reacting, stirring debate, and redirecting loops
7. 8 unique roles — Hunter's revenge kill, Drunk's false info, Bodyguard's sacrifice, Tanner's inversion create unpredictable moments
8. 4 narrator personalities — Classic, Campfire, Horror, Comedy with distinct voices and discussion-specific behaviors
9. Dynamic discussion timer — player-count-aware countdown with visual urgency and narrator warning
10. Post-game reveal timeline — interactive round-by-round view with AI reasoning + audio highlights + share button
11. In-person camera voting — Gemini Vision counts raised hands for physical gatherings
12. Cross-game AI learning — the AI improves its deception strategy from past game data
13. Built on Gemini Live API — native voice, not bolted-on text-to-speech

---

# Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Multi-player real-time sync complexity | Medium | High — could blow timeline | Hub model: single narrator session, players use text. Simplest viable multiplayer architecture. |
| Live API 10-min session timeout | High | Medium — games run 15–30 min | Session resumption + context compression. Tested early in Week 1. |
| AI bluffing quality (too obvious or too passive) | Medium | Medium — ruins core mechanic | Three difficulty presets (Easy/Normal/Hard) with distinct Traitor Agent prompts. Easy AI makes deliberate mistakes for new players. Hard AI builds multi-round arcs. Playtest extensively in Week 2. |
| Live API latency during heated debate | Low | Medium — breaks immersion | Native audio model has lowest latency (~200–500ms). Acceptable for debate format. |
| Concurrent session limits (3–50) | Low | Low — one game at a time for demo | Hub architecture uses ONE session per game. Scale is a post-hackathon concern. |
| WebSocket drops on Cloud Run | Low | Medium | Implement reconnection logic. Firestore is source of truth so state survives disconnects. |

---

# Build Plan

## Week 1 (Feb 22 – Feb 28): Foundation

| Day | Tasks |
|---|---|
| Sat–Sun | GCP project setup, enable APIs, Firestore database. ADK install + hello-world. Live API voice agent test (basic echo). |
| Mon–Tue | Game state machine implementation. Role assignment logic. Firestore schema + read/write utilities. |
| Wed–Thu | Narrator agent with dramatic system prompt + voice config (Charon). Test narration quality + affective dialog. |
| Fri | WebSocket hub (FastAPI). Single-player test: you + AI narrator playing through one full game cycle. |

## Week 2 (Mar 1 – Mar 7): Core Features

| Day | Tasks |
|---|---|
| Sat–Sun | Multiplayer: WebSocket routing, player join/leave, broadcast narration to all connected clients. |
| Mon–Tue | Traitor agent: AI-as-player bluffing logic, character persona, deflection and accusation strategies. |
| Wed–Thu | Voting system, elimination flow, win condition checks. React phone UI: role card, vote buttons. |
| Fri | Full game loop test: 3+ players, complete Night→Day→Vote→Elimination round. Bug bash. |

## Week 3 (Mar 8 – Mar 14): Polish & Submit

| Day | Tasks |
|---|---|
| Sat–Sun | Bug fixes, edge cases, session resumption testing. UI polish. |
| Mon | Demo video recording: live gameplay footage with friends. |
| Tue | Demo video editing (< 4 min). Architecture diagrams. |
| Wed | Bonus "How I Built It" YouTube video (3–5 min). |
| Thu | README.md, submission materials, final Cloud Run deploy. |
| Fri Mar 14 | Final review and buffer day. |
| **Sat Mar 15** | **SUBMISSION DAY** |

**Hard deadline: Sunday March 16, 2026 at 5:00 PM PDT.**

## Post-Hackathon P2 Roadmap

> **Status Update (Feb 26, 2026):** All P2 features from Sprints 4–8 have been implemented and shipped ahead of the hackathon deadline. Sprint 8 delivered the voice engagement overhaul (player mic input, speaker identification, narrator moderator role, dynamic discussion timer) and infrastructure (Terraform IaC, multi-stage Docker, deployment guide). The roadmap below is preserved for historical context — all items marked ✅.

### Sprint 4: Narrator Intelligence — ✅ ALL SHIPPED

| Feature | Status | Implementation Notes |
|---|---|---|
| Procedural character generation | ✅ | LLM generation via Gemini with static fallback cast (8 characters). Genre seed system for future expansion. |
| Narrator vote neutrality | ✅ | `generate_vote_context` tool uses public events only. Narrator prompt firewalled from traitor state. |
| Narrator pacing intelligence | ✅ | `ConversationTracker` with 5 pacing signals (HOT/NORMAL/NUDGE/PUSH/CIRCULAR). |
| Affective dialog input signals | ✅ | `AffectiveSignals` computes 5 emotional signals injected into narrator context. |
| Minimum satisfying game length | ✅ | Minimum rounds enforced per player count. Expected duration in lobby. |

### Sprint 5: Player Experience — ✅ ALL SHIPPED

| Feature | Status | Implementation Notes |
|---|---|---|
| In-game role reminder | ✅ | Expandable `RoleStrip` component with icons, labels, and ability descriptions for all 8 roles. |
| Tutorial mode | ✅ | 5-step client-side interactive walkthrough with mock cast and timeline. Narrator audio preview on role reveal. |
| Conversation structure for large groups | ✅ | `HandRaiseQueue` for 7+ players. Narrator moderates speaker order. |
| Minimum player count design | ✅ | Difficulty auto-adjustment for 3–4 player games. Lobby warning for < 4 players. |

### Sprint 6: Game Depth — ✅ ALL SHIPPED

| Feature | Status | Implementation Notes |
|---|---|---|
| Random AI alignment | ✅ | AI draws from full role pool on Normal/Hard. Derived from difficulty setting (no separate toggle). Post-game reveals alignment. |
| Additional roles (Bodyguard, Tanner) | ✅ | Bodyguard (absorbs kill, 7+ players) and Tanner (solo win, 8 players). Full night action handling + win conditions. |
| Post-game timeline interactive UX | ✅ | Round-by-round interactive timeline with key round highlight, AI strategy teaser, audio highlights, share button. |

### Sprint 7: Stretch Features — ✅ ALL SHIPPED

| Feature | Status | Implementation Notes |
|---|---|---|
| Scene image generation | ✅ | Gemini generates illustrations on phase transitions. 1.5 MB guard, async fire-and-forget. |
| Audio recording/playback | ✅ | PCM recording by segment, top-5 highlight reel ranked by priority. In-memory, base64 WAV. |
| Camera vote counting | ✅ | Gemini Vision hand-counting from host camera frame. Hand count capped at alive players. |
| Narrator style presets | ✅ | 4 presets (Classic/Campfire/Horror/Comedy) with distinct voices + system prompt prefixes. Audio preview in lobby. |
| Competitor intelligence for AI | ✅ | Post-game strategy logs → meta-strategy brief after 20+ games → Traitor Agent prompt augmentation. |

### Sprint 8: Voice Engagement & Infrastructure — ✅ ALL SHIPPED

| Feature | Status | Implementation Notes |
|---|---|---|
| Player Voice Input (Mic) | ✅ | AudioWorklet (16kHz PCM16 mono) streams to narrator's Gemini Live API session. Speaker identification via `[VOICE] {CharacterName}` annotation. Transcript buffering (0.8s debounce). |
| Dynamic Discussion Timer | ✅ | Player-count-aware countdown (2–4 min). 30s narrator warning. Sticky header with M:SS and color transitions. |
| Narrator Voice Engagement Overhaul | ✅ | Dual-mode style (theatrical narration / fast-paced moderator). 4 roles: RELAY, REACT, STIR, REDIRECT. All 4 presets upgraded for discussion. |
| Voice-Optimized Dialog Prompts | ✅ | Traitor and loyal AI character dialog prompts include "write for voice: contractions, short sentences, natural speech." |
| end_of_turn Parity | ✅ | Text messages in heated discussions (PACE_HOT) use `end_of_turn=False` like voice, preventing narrator obligation to respond to every message. |
| Human Shapeshifter Night Kill | ✅ | Full UI and backend for human players who draw shapeshifter via Random AI Alignment to perform night kills. |
| Role Reveal Overlay | ✅ | Visual overlay showing role assignment on game screen. |
| Terraform IaC | ✅ | `terraform/` directory with main.tf, variables.tf, terraform.tfvars.example for Cloud Run deployment. |
| Multi-Stage Docker Build | ✅ | Single Dockerfile at repo root: frontend build + backend in one multi-stage image. |
| Deployment Guide | ✅ | `docs/DEPLOYMENT.md` with local dev and Cloud Run production instructions. |
| Visual Architecture Diagram | ✅ | `docs/architecture.mermaid` Mermaid diagram of full system architecture. |
| Python 3.14 Compatibility | ✅ | Pinned dependencies upgraded for Python 3.14 compat. |

### Remaining (Post-Hackathon)

| Feature | Priority | Notes |
|---|---|---|
| Multiple story genres | P3 | Fantasy-only for hackathon. Genre seed system (`GENRE_SEEDS`) ready for expansion. |
| Persistent player profiles | P3 | Win/loss tracking, leaderboards, unlockable genres. |
| Cross-device shared screen mode | P3 | Dedicated "campfire screen" for TV/tablet alongside phone UIs. |
| Dynamic mid-game AI difficulty | P3 | Real-time difficulty adaptation based on player success signals during gameplay. |

---

# Bonus Points Strategy

| Bonus | Points | Plan | Effort |
|---|---|---|---|
| YouTube video | +0.6 | "How I Built Fireside" — 3–5 min covering Gemini Live API + ADK + Cloud Run. Include #GeminiLiveAgentChallenge. | 2–3 hours |
| Automated deployment | +0.2 | Terraform + Cloud Build in public repo. Push-to-main deploys to Cloud Run. | 1–2 hours |
| GDG Membership | +0.2 | Sign up at developers.google.com/community/gdg. Link public profile in submission. | 10 minutes |
| **Total bonus** | **+1.0** | Maximum possible on 1–5 scale (20% boost) | |

---

# Appendix: Live API Constraints

| Constraint | Impact | Mitigation |
|---|---|---|
| 10-min connection limit | Games run 15–30 min | Session resumption + compression → unlimited |
| 15-min audio-only session | Extended games at risk | Context window compression extends indefinitely |
| 2-min audio+video | Camera limited | Use camera in short bursts (vote counting), not continuous |
| 3–50 concurrent sessions | Limits parallel games | Hub model: ONE narrator session per game |
| 1 FPS video processing | No fast motion tracking | Fine for hand-raise votes, not fast gestures |
| No text output in native audio mode | Can't display text from narrator | Separate text channel via WebSocket for UI updates |
| 128K token context window | Long games fill context | Context compression auto-summarizes older turns |

---

# Documentation

| Document | Path | Description |
|---|---|---|
| **PRD** | `docs/PRD.md` | This document — product requirements and feature inventory |
| **TDD** | `docs/TDD.md` | Technical design document |
| **Deployment Guide** | `docs/DEPLOYMENT.md` | Local development setup + Cloud Run production deployment instructions |
| **Architecture Diagram** | `docs/architecture.mermaid` | Visual Mermaid diagram of the full system architecture (agents, services, data flow) |
| **README** | `README.md` | Project overview, quickstart, and submission details |

---

*Document created: February 21, 2026*
*Last updated: February 26, 2026 — voice engagement overhaul, discussion timer, speaker identification, human shapeshifter night kill, Terraform IaC, deployment guide*
*Hackathon deadline: March 16, 2026*
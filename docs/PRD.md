# Product Requirements Document
## Fireside — Betrayal

**Category:** 🗣️ Live Agents
**Tagline:** The AI is one of you. Trust no one.
**Core Technology:** Gemini Live API (real-time bidirectional voice)

Version 1.0 | February 21, 2026
Hackathon Deadline: **March 16, 2026 at 5:00 PM PDT**
Prize Target: $10K (category) + $25K (grand prize)

---

# Executive Summary

Fireside — Betrayal is a real-time, voice-first multiplayer social deduction game built for the Gemini Live Agent Challenge hackathon ($80K prize pool, Google DeepMind / Devpost). An AI narrator leads players through an immersive collaborative story using natural voice conversation — but one of the characters is secretly the AI, working against the group.

The game combines the narrative immersion of tabletop RPGs with the social tension of Werewolf/Mafia, eliminating the need for a human moderator or game master. Built on the Gemini Live API, Google ADK, and Google Cloud, it showcases real-time voice interaction with barge-in support, affective dialog, multi-agent orchestration, and autonomous AI decision-making.

| | Details |
|---|---|
| **Primary User** | Friend groups (5–10 players) |
| **Platform** | Mobile web (phones) + optional shared screen |
| **Session Length** | 15–30 minutes per game |
| **Core Mechanic** | AI narrates + secretly plays as one character |
| **Input** | Voice (primary), text (fallback), camera (stretch) |
| **Output** | Voice narration, scene images, private role cards |

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

- **Players speak naturally** — no typing, no turn-taking. Interrupt the AI mid-sentence to object. Argue with other players in real time. The Gemini Live API's barge-in support makes heated debates feel natural.
- **AI narrates dramatically** — setting scenes, voicing NPCs, building tension with pauses and vocal inflection. Affective dialog adapts the narrator's tone to match game tension (whispered during night phase, urgent during accusations).
- **AI plays as a hidden character** — with its own backstory, motivations, and deception strategy. It participates in discussions, deflects suspicion, and accuses others. Players must figure out which character is the AI before it's too late.
- **No moderator needed** — the AI handles all game management duties (role assignment, phase transitions, vote tallying, win condition checks) while simultaneously participating as a story character.

## Game Concept

Players gather around a fire (metaphorically — on their phones). The AI narrator tells a story of a village under threat. Each player is assigned BOTH a secret role AND a story character identity (e.g., "Elena the Herbalist," "Brother Aldric," "Mira the Huntress"). One additional character in the story is secretly the AI — a shapeshifter working to sabotage the group. During gameplay, players interact using ONLY their character names. The mystery is: which character at the table is controlled by a human, and which one is the AI? Through cycles of night actions and day debates, players must identify and vote out the AI's character before it eliminates them all.

**Roles:**
- **Villager** — survive and identify the traitor
- **Seer** — can investigate one character each night to learn their true nature
- **Healer** — can protect one character from elimination each night
- **Hunter** (P1) — when eliminated, immediately kills one other character of their choice (dramatic reversal moment)
- **Drunk** (P1) — told they are the Seer, but receives false investigation results (creates hilarious misinformation)
- **Shapeshifter (AI)** — the AI's secret character, trying to avoid detection while sabotaging the group

---

# User Flow

| Phase | What Happens | Player Experience |
|---|---|---|
| 1. Lobby | Host creates game, selects difficulty (Easy/Normal/Hard — controls AI deception quality), shares 4-digit join code. Players connect on their phones. | Simple join screen — enter name, select difficulty, see other players arriving. |
| 2. Role Assignment | AI assigns each player a secret role (Villager, Seer, Healer, Hunter, Drunk) AND a story character identity. AI picks its own character from the same cast. All players see only character names from this point forward — real names are hidden. | Private role card: "You are **Elena the Herbalist** (Healer). Each night, choose one character to protect." Players know their own character name but not which character belongs to which friend. |
| 3. Story Begins | AI narrator sets the scene with dramatic voice narration. "The village of Thornwood sleeps beneath a pale moon..." Introduces all characters by name. | Players listen together. Each character is introduced with a brief personality hook. "Brother Aldric tends the chapel garden. Mira the Huntress returns from the forest with an uneasy look." |
| 4. Night Phase | AI privately contacts special-role holders. Seer investigates (Drunk gets false results). Healer protects. Hunter has no night action. AI's shapeshifter picks a target. | Private text on individual phones. Other players see "Night has fallen..." with atmospheric narration. |
| 5. Day Discussion | AI narrates what happened overnight, then opens discussion. Players debate via text input OR quick-reaction buttons ("I suspect [character]", "I trust [character]", "I agree with [last speaker]"). AI participates as its character. | Chat with character names only. Quick-reaction buttons for fast participation. AI responds in character when addressed or accused. |
| 6. Voting | Players vote to eliminate a suspect character using buttons on their phones. AI tallies votes and handles ties. | Character portrait buttons to vote. Timer countdown. AI announces results with dramatic narration. |
| 7. Elimination | AI narrates the elimination with story consequences. If the eliminated player was the Hunter, they immediately choose someone to take with them. Reveals whether the eliminated character was the traitor or innocent. | Dramatic reveal moment. Hunter's revenge kill creates unexpected second elimination. Eliminated players become spectators. |
| 8. Resolution | Repeat Night/Day cycles until villagers correctly identify the shapeshifter OR the shapeshifter eliminates enough villagers to win. | Win/lose screen with **post-game reveal timeline**: round-by-round view showing every hidden action, the AI's strategy reasoning, and key turning points. All character-to-player mappings revealed. |

---

# Multimodal Capabilities

| Modality | How Fireside Uses It | Category Requirement |
|---|---|---|
| **Voice Input** | Players speak accusations, defenses, and arguments naturally. Can interrupt the AI mid-narration to object or interject. | ✓ Natural conversation |
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
| **Cloud Build + Terraform** | CI/CD pipeline + IaC | Automated deployment for bonus points (+0.2). Push to main auto-deploys to Cloud Run. |
| **Artifact Registry** | Container images | Required by Cloud Run deploy pipeline. |

## System Architecture

```
Player Phones (3-6) ←WebSocket→ Cloud Run (FastAPI)
                                    ├── ADK Agent Orchestrator
                                    │   ├── Narrator Agent (Live API voice)
                                    │   ├── Game Master Agent (deterministic)
                                    │   └── Traitor Agent (LLM sub-agent)
                                    ├── Gemini Live API (WebSocket)
                                    └── Cloud Firestore (game state)
                                        Cloud Storage (scene images)
```

## Session Management

The Gemini Live API has a ~10-minute connection limit and 15-minute audio session cap. For games running 15–30 minutes:

- **Session resumption:** Enable `session_resumption` in LiveConnectConfig with a session handle for automatic reconnection after timeout, preserving conversation context.
- **Context window compression:** Enable `context_window_compression` to automatically summarize older conversation history, extending sessions to unlimited duration.
- **Firestore as source of truth:** Critical game state (roles, votes, alive/dead status, story progress) is persisted in Firestore, not just in the Live API session memory. On reconnection, the full game state summary is re-injected into the new session context.

## Multiplayer Audio Architecture

To manage concurrent session limits (3–50 per GCP project), we use a simplified hub model:

- **Single narrator session:** Server maintains ONE Live API session for the narrator agent. This is the only entity that needs real-time voice output.
- **Player input via text:** Players send text messages or use browser-native speech-to-text. Server transcribes and injects player messages into the narrator's context as attributed dialog ("Alex says: I think the blacksmith is suspicious").
- **Broadcast audio:** Narrator's audio responses are streamed to all connected player WebSockets simultaneously.
- **Private channels:** Role assignments and night-phase messages are sent via text to individual player WebSockets only.

This avoids the need for per-player Live API sessions (which would hit concurrent limits immediately) while preserving the core voice experience.

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
  ├── Scene image (generated per phase, optional)
  ├── Role card (private, only visible to this player)
  ├── Player list (alive/dead status, vote indicators)
  ├── Chat input (text + optional browser speech-to-text)
  ├── Vote buttons (appear during voting phase only)
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

| Feature | Priority | Description |
|---|---|---|
| Voice narration + interruptions | **P0 — Must Have** | AI narrator speaks in real-time with dramatic tone, handles player interruptions via barge-in. Narrator response latency must stay under 2 seconds for conversational flow — social deduction lives on momentum and any perceivable delay between a player's accusation and the narrator's reaction kills the energy. Narrator must also handle rule violations gracefully: if a player sends messages during the night phase, the narrator redirects narratively ("The spirits remind you that night is a time for silence") rather than crashing or ignoring. |
| Role assignment system | **P0 — Must Have** | AI assigns player roles (Villager, Seer, Healer) + selects its own hidden character at game start. Role distribution scales by player count: 4 players (3 human + 1 AI) = 1 Seer + 2 Villagers + Shapeshifter (no Healer — too few eliminations for protection to matter); 5 players = 1 Seer + 1 Healer + 2 Villagers + Shapeshifter; 6 players = add Hunter (P1); 7-8 players = add Drunk (P1). The AI can inhabit any role including Shapeshifter (default), or any village role (P2 Random AI alignment). Role distribution should be communicated to the host on the lobby screen before game start: "In this game: 2 special roles, 3 villagers, 1 AI among you." This framing helps new players set expectations. |
| Character identity system | **P0 — Must Have** | Every player receives a story character name (e.g., "Elena the Herbalist") in addition to their role. The AI's shapeshifter also has a character name from the same cast. All in-game interactions use character names only — real player names are hidden during gameplay. This is fundamental: without it, the AI is instantly identifiable by name format. |
| Game state machine | **P0 — Must Have** | Night/Day Discussion/Day Vote/Elimination phases with proper transitions and rule enforcement. |
| AI-as-player (Traitor Agent) | **P0 — Must Have** | AI participates in day discussions as its character. Bluffs, deflects suspicion, and strategically accuses other players. |
| Multiplayer WebSocket hub | **P0 — Must Have** | 3–6 players connect via phones and interact in real-time through a central server. |
| Voting system | **P0 — Must Have** | Players vote on their phones, AI tallies and announces results with dramatic narration. |
| Player phone UI (React) | **P0 — Must Have** | Mobile web app: role card, vote buttons, chat input, story log on each device. |
| Session resumption | **P1 — Should Have** | Handle games longer than 10 min via session resume + context window compression. |
| Hunter + Drunk roles | **P1 — Should Have** | Two additional roles for replayability. Hunter: when eliminated, immediately kills one other character (dramatic reversal, great demo moment). Drunk: told they are the Seer but receives false investigation results (creates hilarious misinformation and self-doubt). Drunk availability is gated by difficulty — Easy mode never includes the Drunk (protects new players from feeling punished), Normal includes Drunk at 6+ players, Hard includes Drunk at 5+ players. With 5 human roles total, every game plays differently. |
| Traitor difficulty levels | **P1 — Should Have** | Host selects Easy / Normal / Hard before the game starts. Easy: AI makes occasional obvious mistakes, hesitates when lying, sometimes contradicts its own alibi — good for new players who are learning the genre (target: AI caught ~70% of games). Normal: AI is competent but beatable with careful attention (target: AI caught ~50% of games). Hard: AI builds multi-round deception arcs, creates false evidence, forms strategic voting alliances, never contradicts itself — for experienced Werewolf/Mafia players (target: AI caught ~30% of games). Display expected win rates on the difficulty selector so hosts can calibrate for fun: "Easy — most groups catch the AI. Hard — the AI usually wins." Implementation: `difficulty` parameter adjusts the Traitor Agent's system prompt complexity and temperature. |
| Quick-reaction buttons | **P1 — Should Have** | During day discussion, players can tap preset reaction buttons instead of typing: "I suspect [character]," "I trust [character]," "I agree with [last speaker]," "I have information." Reactions are injected into the narrator's context as attributed dialog, same as typed messages. Critical for casual gamers who can't type fast enough during heated debates. |
| Narrator quick-reaction handling | **P1 — Should Have** | The Narrator Agent narrativizes quick reactions as story beats, not flat announcements. "I suspect Blacksmith Garin" becomes "Elara's eyes narrow as she turns toward the forge. 'Something about the Blacksmith doesn't sit right with me.'" "I have information" triggers a dramatic pause and invitation to speak. This is a prompt engineering addition to the Narrator Agent — no new architecture. Without it, quick reactions feel like a different game from typed messages. |
| Post-game reveal timeline | **P1 — Should Have** | After game ends, show a round-by-round interactive timeline revealing: every hidden night action, the AI's strategic reasoning for each decision ("targeted Alex because the Seer was getting close"), voting patterns, and the moment the AI was closest to being caught. All character-to-player name mappings revealed. This is the "let's play again" trigger — half the fun of social deduction is the post-game debrief. Data already exists in Firestore events log; this is primarily a frontend rendering feature. |
| Landing page | **P1 — Should Have** | Atmospheric marketing page that sells the experience: hero with tagline ("One of you is an AI. Can you find it?"), how-it-plays walkthrough, AI strategy preview, role teasers, gameplay moment vignettes. Maintains game's dark campfire aesthetic. CTA flows directly into game creation. Mobile-first, same 420px constraint as game UI. |
| Narrator contextual reactivity | **P1 — Should Have** | The Narrator Agent must reference recent in-game events in scene descriptions, not just recite procedural phase transitions. If two players had a heated argument about Garin's alibi in Round 2, the Round 3 dawn description should acknowledge it: "Dawn breaks, but the suspicion from last night lingers like woodsmoke — Elara's accusation hangs unresolved." If the narrator just says "A new day begins in Thornwood" without acknowledging what happened, immersion breaks immediately. Implementation: the narrator's scene-setting prompt includes a summary of the previous round's key events (accusations, close votes, dramatic moments) pulled from the events log. This is the difference between a DM who reads the room and an AI that reads a script. DM persona (Marcus) identifies this as the make-or-break quality signal. |
| Narrator quiet-player engagement | **P1 — Should Have** | The Narrator Agent tracks which players haven't spoken during the current day discussion phase and gently prompts them by character name: "Elena, you've been watching the Blacksmith closely — does anything seem off to you?" Direct address gives shy players permission to speak without performance pressure. Critical in Round 1 when everyone is finding their feet. Should trigger after 60+ seconds of silence from a player during day discussion, max once per player per round to avoid being annoying. Board game organizer persona (Priya) identifies this as the #1 cause of new player dropout in social deduction games. |
| Spectator actions for eliminated players | **P1 — Should Have** | Eliminated players can send cryptic one-word clues to living players via the narrator ("A spirit whispers to you: 'forge'"). Keeps eliminated players engaged instead of bored. Promoted from P2 based on board game organizer feedback — getting eliminated in Round 1 and sitting idle for 20 minutes is the #1 reason casual players don't return to social deduction games. Limited to one word per round to prevent eliminated players from breaking the game. The narrator delivers the clue in-story: "A voice from beyond the veil reaches you... a single word: 'forge.'" |
| Camera vote counting | **P2 — Nice to Have** | For in-person play sessions where players are physically together, the narrator can use the shared screen's camera (or host's phone camera) to count raised hands during the vote phase instead of requiring individual phone taps. **User flow:** Host enables "In-Person Mode" in the lobby. During vote phase, narrator says "Raise your hand if you vote to eliminate Blacksmith Garin." Camera captures the room at 1 FPS (Live API vision constraint). Gemini vision counts raised hands and maps them to player positions. Narrator announces: "I count four hands raised. The village has spoken." **Scope boundaries:** This is a supplementary input mode — phone voting remains the primary mechanism and fallback. Camera counts are confirmed by narrator ("I see four hands — is that correct?") before becoming binding. Does NOT replace phone-based voting for remote play. Does NOT require player identification from camera — just hand counting. **Technical constraints:** Live API processes vision at 1 FPS with a 2-minute audio+video session limit. Vote counting should take under 30 seconds, well within limits. Camera is activated only during the vote countdown, not continuously. **Why low priority:** Only useful when all players are physically co-located, which is the minority use case. Phone voting works for both remote and in-person. This is a "wow factor" demo feature for the hackathon video, not a core gameplay need. |
| Scene image generation | **P2 — Nice to Have** | Generate atmospheric scene illustrations per story phase using interleaved output. |
| Tutorial mode | **P2 — Nice to Have** | 5-minute solo walkthrough of each phase with just the player and the AI narrator. Teaches game mechanics through narrated example before the first real game. Critical for casual gamers who've never played social deduction. |
| In-game role reminder | **P2 — Nice to Have** | Tappable role strip that expands to show a one-sentence description of the player's role abilities ("Each night, choose one character to protect from the Shapeshifter"). Casual players forget what their role does mid-game and are embarrassed to ask friends. The role strip currently shows role name + icon but not abilities. One-tap expand/collapse, non-intrusive, doesn't block gameplay. Critical for casual players (Sam persona) who've only played Werewolf once or twice. |
| Minimum player count design | **P2 — Nice to Have** | Explicit design guidance for 4-player games (3 humans + 1 AI). With only 3 human players, social deduction dynamics are compressed — everyone's behavior is highly visible, there's less noise to hide in. The AI difficulty should auto-adjust for small games (easier deception at 4 players, harder at 7+). Role distribution should also adapt: at 4 players, use only Villager + Seer + Shapeshifter (no Healer — too few eliminations). At 6+, add Healer and Hunter. Document the minimum viable game configuration and expected dynamics at each player count. |
| Narrator vote neutrality | **P2 — Nice to Have** | The behavioral context shown on vote cards ("Claimed to be at the forge — but no one can confirm") is generated by the Narrator Agent. This text must be factually neutral and based only on publicly observable events — NOT influenced by the AI Traitor's knowledge. The Narrator Agent's vote context prompt should be explicitly firewalled from the Traitor Agent's private state. If the narrator has access to who the Shapeshifter is, the behavioral summaries could be unconsciously biased for or against the AI's character. Implementation: vote context generation uses only the public events log, not the full game state. Experienced players (Alex persona) will notice if the narrator subtly steers votes. |
| Narrator pacing intelligence | **P2 — Nice to Have** | The narrator should monitor conversation flow during day discussion and adapt pacing dynamically. If two players are having a productive debate, the narrator lets it breathe. If discussion circles (repeated accusations, no new info), the narrator intervenes narratively: "The sun climbs higher. Time presses." If nobody speaks for 30+ seconds, the narrator prompts action. Replaces flat timer-based phase transitions with organic narrative pacing. DM persona (Marcus) identifies this as "80% of the DM's job." Implementation: conversation analysis based on message frequency, sentiment repetition, and time elapsed. |
| Affective dialog input signals | **P2 — Nice to Have** | Define concrete signals that trigger narrator tone changes: (1) Vote closeness — 3-2 vote triggers tense narration, 5-0 triggers relief; (2) Message frequency — rapid messages = heated debate, narrator gets urgent; (3) Round progression — later rounds escalate dramatic weight; (4) Elimination stakes — if one more elimination triggers endgame, narrator conveys finality; (5) AI exposure risk — if players are close to identifying the AI, narrator adds suspense. Map each signal to a narrator tone parameter. |
| Conversation structure for large groups | **P2 — Nice to Have** | With 7-8 players, simultaneous text creates unreadable walls. Add optional conversation moderation: narrator calls on 2-3 players first ("The village elder looks to Elara and Garin — what say you?"), then opens floor. Or add "raise hand" quick reaction. Doesn't restrict who CAN speak — provides narrative scaffolding against chaos. Board game organizer persona (Priya) identifies as critical for 6+ players. |
| Minimum satisfying game length | **P2 — Nice to Have** | Enforce minimum round counts per player count. DM persona (Marcus) notes 15 min (~2 rounds) is too short. Proposed: 4 players = 3 rounds (15-20 min), 5-6 = 3-4 rounds (20-30 min), 7-8 = 4-5 rounds (25-35 min). Game ends on win condition, not time. Session resumption (P1) must support up to 45 min. Host lobby displays expected duration by player count. |
| Procedural character generation | **P2 — Nice to Have** | Character cast is hardcoded to 7 characters. By game 3-4, intros are memorized. Narrator should procedurally generate unique characters and backstories each game. DM persona (Marcus) argues this should be P1 — "Elena the Herbalist" loses surprise when repeated. Pure prompt engineering: narrator generates cast with unique names, occupations, backstory hooks before game start. No new architecture, high replay impact. |
| Additional roles (Bodyguard, Tanner, etc.) | **P2 — Nice to Have** | More roles for larger groups (7-10 players) and deeper strategy. Bodyguard: dies protecting someone. Tanner: wins by getting voted out. Each role is a system prompt branch + night action. The replayability engine for long-term retention. |
| Random AI alignment | **P2 — Nice to Have** | The AI's role is randomized just like every human player's — sometimes it's the Shapeshifter, sometimes a loyal Villager, sometimes the Seer or Healer. Players never know if the AI is friend or foe. Completely changes the meta-game: you can't just "find the AI" anymore, you have to figure out what SIDE it's on. Requires a second agent persona (loyal AI) with cooperative behaviors, and the Traitor Agent prompt would only activate when the AI draws Shapeshifter. Most replayable version of the game — every session has a different trust dynamic. |
| Post-game timeline interactive UX | **P2 — Nice to Have** | Upgrade the post-game reveal from a flat list to an interactive split view: what happened publicly (what everyone saw) vs. what happened secretly (AI reasoning, night actions, Seer results). The "aha!" moment comes from juxtaposing the two. Data structure already supports this; this is a frontend enhancement. |
| Narrator style presets | **P2 — Nice to Have** | Allow the host to select a narrator personality preset that changes the narrator's voice, vocabulary, and dramatic style. **Presets:** (1) "Classic" — default deep dramatic fantasy narrator (current Charon voice). (2) "Campfire" — warmer, folksy storyteller who addresses players as "friends" and tells the story like a campfire tale. (3) "Horror" — slow, unsettling, whispered delivery with longer pauses and dread-building descriptions. (4) "Comedy" — lighter tone, the narrator makes wry observations, fourth-wall-adjacent humor, less dramatic weight on eliminations. **Implementation:** Each preset is a system prompt prefix + voice config override (different Gemini voice, different pacing directives, different vocabulary constraints). The game mechanics are identical — only the narrator's performance changes. Selection happens on the lobby screen alongside difficulty. **Why this exists:** Different friend groups have different vibes. A group of horror fans wants dread. A casual group wants laughs. The narrator is a performer — letting the host "cast" the narrator is low effort, high personality. **Why low priority:** The default narrator is strong enough to ship. Presets are flavor, not function. Each preset requires playtesting to ensure quality, which is time-intensive relative to impact. |
| Competitor intelligence for AI | **P2 — Nice to Have** | The AI Traitor learns from previous games to improve its deception strategy over time. **How it works:** After each game, the post-game data (AI's strategy log, whether it was caught, which deception patterns succeeded/failed, what triggered player suspicion) is stored in a cross-game analytics collection. Before each new game, the Traitor Agent's system prompt is augmented with a "lessons learned" summary: "In previous games, players caught the AI when it: accused the same player twice, stayed silent during heated debates, changed its story between rounds. Successful deceptions included: building alliances early, deflecting with humor, making one bold true accusation to build credibility." **Data pipeline:** Firestore collection `ai_strategy_logs/{gameId}` stores structured post-game data: `{strategy_used, caught: bool, round_caught, player_signals_that_exposed_ai, successful_deception_moves}`. A scheduled Cloud Function (daily or on-demand) aggregates across games and generates a "meta-strategy brief" document. The Traitor Agent's prompt loader reads the latest brief at game start. **Scope boundaries:** This does NOT make the AI unbeatable — it makes the AI more human-like over time. The insight summaries inform strategy, they don't dictate it. The AI still operates within its difficulty level constraints (Easy AI still makes mistakes even with intelligence). Players should feel like the AI is "learning their group's playstyle," which is a powerful retention hook. **Why low priority:** Requires a meaningful sample size of completed games (20+ games minimum before patterns are statistically useful). The static difficulty presets (Easy/Normal/Hard) are sufficient for the hackathon and early adoption. This is a month-2+ feature that becomes valuable once there's an active player base generating game data. |
| Multiple story genres | **P3 — Future** | Fantasy, mystery, sci-fi, horror story templates with different character sets, different win conditions, different atmosphere. Each genre changes narrator tone, character archetypes, and story structure. |
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
2. AI plays AS a character — the AI isn't just the narrator/GM, it's a deceptive participant with adjustable difficulty
3. Character identity masking — all players AND the AI have story character names, making the AI unidentifiable by format
4. Social deduction + storytelling hybrid — a completely new genre combination
5. Emergent role interactions — Hunter's revenge kill and Drunk's false information create unpredictable game moments
6. Post-game reveal timeline — see the AI's hidden strategy reasoning round-by-round
7. Built on Gemini Live API — native voice, not bolted-on text-to-speech

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

P2 features sequenced by impact × effort. Grouped into sprints assuming 1–2 week cycles post-hackathon. SA should spec TDD sections in this order.

### Sprint 4 (Week 4): Narrator Intelligence — *highest impact, lowest effort*

These are all prompt engineering changes to the Narrator Agent. No new architecture, no new endpoints, no new UI components. Just better prompts and a few server-side tracking additions.

| Feature | Effort | Why Now |
|---|---|---|
| Procedural character generation | 2–3 hours | Pure prompt change. Eliminates the #1 replay killer (memorized character intros). DM persona flagged this as borderline P1. |
| Narrator vote neutrality | 2–3 hours | Firewall narrator's vote-context prompt from traitor state. Uses existing public events log. Prevents experienced players from detecting bias. |
| Narrator pacing intelligence | 4–6 hours | Add message frequency + silence tracking to day discussion phase. Narrator prompts based on conversation flow instead of flat timer. |
| Affective dialog input signals | 3–4 hours | Map 5 concrete signals (vote closeness, message frequency, round number, elimination stakes, AI exposure risk) to narrator tone parameters. Prompt changes + light server-side signal computation. |
| Minimum satisfying game length | 1–2 hours | Add minimum round counts to GameMaster config. Display expected duration in lobby. Config change, not architecture. |

**Sprint 4 total: ~15 hours. All prompt/config. No frontend changes.**

### Sprint 5 (Week 5–6): Player Experience — *high impact, moderate effort*

These improve the experience for casual and new players. Mix of frontend components and light backend additions.

| Feature | Effort | Why Now |
|---|---|---|
| In-game role reminder | 3–4 hours | Tappable role strip expansion. Frontend-only. Casual player persona's #1 request. |
| Tutorial mode | 1–2 days | Solo walkthrough with narrator. Requires a scripted game flow (no real multiplayer). New route + simplified game state. |
| Conversation structure for large groups | 4–6 hours | "Raise hand" quick reaction + narrator calling on players. Frontend button + narrator prompt update. |
| Minimum player count design | 3–4 hours | Auto-adjust AI difficulty for small games. Role distribution table already handles roles — this adds difficulty scaling logic. |

**Sprint 5 total: ~3–4 days. Frontend + prompt changes.**

### Sprint 6 (Week 7–8): Game Depth — *high impact, higher effort*

These change gameplay mechanics and require new agent logic, new UI, and playtesting.

| Feature | Effort | Why Now |
|---|---|---|
| Random AI alignment | 2–3 days | Second agent persona (loyal AI). New system prompt branch. Changes the fundamental meta-game. Most replayable version of the game. |
| Additional roles (Bodyguard, Tanner) | 1–2 days | New role definitions, night action handlers, system prompt branches. Each role is ~4 hours. |
| Dynamic AI difficulty | 2–3 days | Mid-game difficulty adaptation based on gameplay analytics. Requires tracking player success signals and adjusting traitor prompt in real-time. |
| Post-game timeline interactive UX | 2–3 days | Split-view frontend (public vs secret). Data exists in Firestore — this is a rich frontend build. |

**Sprint 6 total: ~1.5–2 weeks. New mechanics + frontend.**

### Sprint 7+ (Month 2+): Stretch Features

| Feature | Effort | Notes |
|---|---|---|
| Scene image generation | 1–2 days | Interleaved output from Gemini. Atmospheric but not gameplay-critical. |
| Audio recording/playback | 3–5 days | Record + segment narrator audio stream. Enables sharable clips ("re-listen to the moment the AI lied to you"). Viral mechanic. |
| Camera vote counting | 1–2 days | Vision input for hand-raise counting during in-person play. Niche use case but strong hackathon demo moment. Requires "In-Person Mode" lobby toggle. |
| Narrator style presets | 3–5 days | Classic / Campfire / Horror / Comedy narrator personality presets. System prompt prefix + voice config per preset. High personality, low structural complexity — but each preset needs playtesting. |
| Competitor intelligence for AI | 1–2 weeks | Cross-game learning from post-game strategy logs. Requires 20+ completed games before patterns are useful. Daily aggregation via Cloud Function → meta-strategy brief → Traitor Agent prompt augmentation. Long-term retention feature. |

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

*Document created: February 21, 2026*
*Hackathon deadline: March 16, 2026*
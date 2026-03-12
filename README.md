# 🔥 Fireside: Betrayal

**The AI is one of you. Trust no one.**

🌐 **[Play Now](https://fireside-betrayal-vrdh6pblnq-uc.a.run.app)**

A real-time, voice-first multiplayer social deduction game where an AI narrator leads players through an immersive story — and one of the characters is secretly controlled by AI.

## What is this?

Fireside: Betrayal combines the narrative immersion of tabletop RPGs with the social tension of Werewolf/Mafia. An AI narrator runs the game while simultaneously playing as a hidden character, lying, manipulating, and fighting to survive.

- 🎭 **3–8 players** — 2+ humans + 1–2 hidden AI characters (2 humans → 2 AIs, 3+ humans → 1 AI)
- 🎙️ **Voice-first** — the AI narrates with dramatic flair, players speak through their phone mic and interrupt naturally
- 🐺 **Hidden AI players** — AI characters behave just like real players, blending in seamlessly
- 🎲 **Random AI alignment** — AI characters can draw any role, and a human can be the shapeshifter (Normal/Hard difficulty)
- 🧠 **Post-game reveal** — see exactly what the AI was thinking every round
- 🎭 **8 unique roles** — Villager, Seer, Healer, Hunter, Drunk, Bodyguard, Tanner, Shapeshifter
- 🎤 **4 narrator presets** — Classic, Campfire, Horror, Comedy — each with distinct voice and tone
- ⏱️ **15–30 minutes** per game
- 📱 **No download** — works in any mobile browser

## How it plays

1. **Gather around the fire** — Share a 6-character join code. Everyone joins on their phone.
2. **Pick a narrator** — Choose from Classic, Campfire, Horror, or Comedy narration styles. Preview each voice before starting.
3. **Roles are dealt** — Villager, Seer, Healer, Hunter, Bodyguard, Tanner... and the AI hides among you (or plays as a loyal ally — you won't know).
4. **Night falls, dawn breaks** — The Shapeshifter hunts (or bluffs by skipping the kill). The Seer investigates. The Bodyguard protects. The village debates and votes.
5. **Speak up or stay silent** — Hold the "Speak" button to take the mic during discussions. Only one player can speak at a time; the button releases automatically after 30 seconds so no one can filibuster. Dead players cannot speak. The narrator hears you, identifies your character, and relays your points to the village. A countdown timer keeps debates moving — but the timer doesn't start until the narrator has finished setting the scene.
6. **The truth is revealed** — After the game, see the AI's hidden reasoning for every lie it told, listen to audio highlights, and share your results.

## Features

| Feature | Description |
|---------|-------------|
| **Push-to-Talk Mic** | Hold "Speak" to take the mic — only one player can hold it at a time. Auto-releases after 30 seconds. Dead players' buttons are disabled with clear feedback |
| **Active Narrator Moderator** | During discussions, the narrator relays player speech, stirs the pot, challenges weak arguments, and redirects loops |
| **Phase Timers** | Timers start after the narrator finishes narrating each phase. Night action window: 30s. Vote window: 60s. Discussion requires at least 45s before the narrator can call a vote — the game waits for you, not the other way around |
| **Discussion Timer** | Visible countdown scales by player count (2–4 min). 30s warning. Color-coded urgency in header |
| **Instant Chat** | Chat messages appear immediately on your screen without waiting for a server round-trip |
| **Narrator Voice Presets** | Classic (stern village elder), Campfire (mischievous friend), Horror (unsettling observer), Comedy (sports announcer) |
| **Procedural Characters** | LLM-generated unique character cast every game — no two games feel the same |
| **Random AI Alignment** | On Normal/Hard, AI characters can be randomly assigned any role — a human might end up as the Shapeshifter |
| **Human Shapeshifter** | When Random AI Alignment gives a human the shapeshifter, they perform night kills through the game UI — or choose "No Kill Tonight" to bluff and sow confusion |
| **In-Person Camera Voting** | Host's camera counts raised hands via Gemini Vision for physical gatherings |
| **Scene Illustrations** | Atmospheric images generated on phase transitions |
| **Audio Highlights** | Post-game reel of the narrator's most dramatic moments |
| **Interactive Tutorial** | 5-step guided walkthrough for first-timers, with narrator audio preview |
| **Session Persistence** | Refresh mid-game? WebSocket reconnects automatically |
| **Spectator Clues** | Eliminated players whisper one-word hints from beyond the veil |
| **Adaptive Pacing** | Narrator reads the room — speeds up stale debates, lets heated arguments breathe |
| **AI Strategy Learning** | After 20+ games, the AI learns from past mistakes (cross-game intelligence) |

## Tech Stack

- **AI Engine:** Google Gemini Live API (real-time bidirectional voice)
- **AI Models:** gemini-2.5-flash-native-audio-latest (narrator), gemini-2.5-flash (traitor strategy), gemini-2.5-flash-preview-tts (audio previews)
- **Backend:** FastAPI + Python on Cloud Run
- **Real-time State:** Cloud Firestore
- **Frontend:** React (mobile web, Vite)
- **Infrastructure:** Terraform IaC + Cloud Build (CI/CD)
- **Container:** Multi-stage Docker (Node frontend build + Python backend)

## Architecture

```
Player Phones (2-8) ←WebSocket→ Cloud Run (FastAPI)
    │                               ├── Narrator Agent (Gemini Live API voice)
    │                               │   ├── Session resumption + context compression
    │                               │   ├── Player mic audio → speaker identification → Gemini
    │                               │   ├── Transcript buffering (0.8s debounce)
    │                               │   ├── Active moderator (relay/react/stir/redirect)
    │                               │   └── 4 narrator presets (Classic/Campfire/Horror/Comedy)
    │                               ├── AI Character Agent(s) (gemini-2.5-flash, text-only)
    │                               │   ├── 1–2 AI characters (unified handler per character)
    │                               │   ├── Difficulty-calibrated deception (Easy/Normal/Hard)
    │                               │   └── Cross-game strategy learning
    │                               ├── Game Master (deterministic Python logic)
    │                               │   ├── Role assignment + character generation
    │                               │   ├── Phase transitions + dynamic discussion timer
    │                               │   ├── Vote resolution (polling-based auto-advance)
    │                               │   └── Night action processing (AI can target AI)
    ├── 🎤 Mic (16kHz PCM16)       ├── Scene Agent (image generation)
    ├── 💬 Text chat               ├── Camera Vote Agent (vision hand-counting)
    └── 🗳️ Votes                   ├── Audio Recorder (highlight reel)
                                    ├── Gemini Live API (WebSocket)
                                    └── Cloud Firestore (game state)
```

## Documentation

| Document | Description |
|---|---|
| [Product Requirements (PRD)](docs/PRD.md) | Full product spec — roles, features, user flows, competitive landscape |
| [Technical Design (TDD)](docs/TDD.md) | Implementation spec — agents, data model, API contracts, deployment |
| [Architecture Diagram](docs/architecture.mermaid) | Visual system architecture (Mermaid) |
| [Deployment Guide](docs/DEPLOYMENT.md) | Local dev setup + Cloud Run production deploy + Terraform IaC |
| [UI Mockup](docs/fireside-ui.jsx) | Interactive React prototype — 6 screens (Landing, Join, Game, Vote, Tutorial, End) |
| [Playtest Personas](docs/playtest-personas.md) | 3 player personas with scoring history for playtesting |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/games` | Create game + register host |
| POST | `/api/games/{id}/join` | Join lobby |
| GET | `/api/games/{id}` | Public game state |
| POST | `/api/games/{id}/start` | Start game (host only) |
| GET | `/api/games/{id}/events` | Event log (gated to finished games for full log) |
| GET | `/api/games/{id}/result` | Post-game result (winner, reveals, timeline) |
| GET | `/api/narrator/preview/{preset}` | Narrator audio sample (cached) |
| WS | `/ws/{gameId}?playerId={id}` | Real-time game connection |


## Hackathon

Built for the **Gemini Live Agent Challenge** hackathon ($80K prize pool, Google DeepMind / Devpost).

- **Category:** 🗣️ Live Agents
- **Deadline:** March 16, 2026 at 5:00 PM PDT
- **Prize Target:** $10K (category) + $25K (grand prize)

## License

MIT

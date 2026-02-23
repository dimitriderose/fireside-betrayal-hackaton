# 🔥 Fireside: Betrayal

**The AI is one of you. Trust no one.**

A real-time, voice-first multiplayer social deduction game where an AI narrator leads players through an immersive story — and one of the characters is secretly controlled by AI.

## What is this?

Fireside: Betrayal combines the narrative immersion of tabletop RPGs with the social tension of Werewolf/Mafia. An AI narrator runs the game while simultaneously playing as a hidden character, lying, manipulating, and fighting to survive.

- 🎭 **3–8 players** — 2–7 humans + 1 hidden AI character
- 🎙️ **Voice-first** — the AI narrates with dramatic flair, players interrupt naturally
- 🐺 **Hidden AI player** — one character is secretly the AI, with its own deception strategy
- 🎲 **Random AI alignment** — the AI might be friend or foe (Normal/Hard difficulty)
- 🧠 **Post-game reveal** — see exactly what the AI was thinking every round
- 🎭 **8 unique roles** — Villager, Seer, Healer, Hunter, Drunk, Bodyguard, Tanner, Shapeshifter
- 🎤 **4 narrator presets** — Classic, Campfire, Horror, Comedy — each with distinct voice and tone
- ⏱️ **15–30 minutes** per game
- 📱 **No download** — works in any mobile browser

## How it plays

1. **Gather around the fire** — Share a 6-character join code. Everyone joins on their phone.
2. **Pick a narrator** — Choose from Classic, Campfire, Horror, or Comedy narration styles. Preview each voice before starting.
3. **Roles are dealt** — Villager, Seer, Healer, Hunter, Bodyguard, Tanner... and the AI hides among you (or plays as a loyal ally — you won't know).
4. **Night falls, dawn breaks** — The Shapeshifter hunts. The Seer investigates. The Bodyguard protects. The village debates and votes.
5. **The truth is revealed** — After the game, see the AI's hidden reasoning for every lie it told, listen to audio highlights, and share your results.

## Features

| Feature | Description |
|---------|-------------|
| **Narrator Voice Presets** | Classic (dramatic fantasy), Campfire (folksy warmth), Horror (dread), Comedy (wry humor) |
| **Procedural Characters** | LLM-generated unique character cast every game — no two games feel the same |
| **Random AI Alignment** | On Normal/Hard, the AI draws a random role — it could be the Shapeshifter or a loyal Seer |
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
- **AI Models:** gemini-2.5-flash-native-audio (narrator), gemini-2.5-flash (traitor strategy), gemini-2.5-flash-preview-tts (audio previews)
- **Backend:** FastAPI + Python on Cloud Run
- **Real-time State:** Cloud Firestore
- **Frontend:** React (mobile web, Vite)
- **Deployment:** Terraform + Cloud Build (CI/CD)

## Architecture

```
Player Phones (2-7) ←WebSocket→ Cloud Run (FastAPI)
                                    ├── Narrator Agent (Gemini Live API voice)
                                    │   ├── Session resumption + context compression
                                    │   ├── Affective dialog (tone adapts to game tension)
                                    │   └── 4 narrator presets (Classic/Campfire/Horror/Comedy)
                                    ├── Traitor Agent (gemini-2.5-flash, text-only)
                                    │   ├── Difficulty-calibrated deception (Easy/Normal/Hard)
                                    │   └── Cross-game strategy learning
                                    ├── Game Master (deterministic Python logic)
                                    │   ├── Role assignment + character generation
                                    │   ├── Phase transitions + win conditions
                                    │   └── Vote resolution + night action processing
                                    ├── Scene Agent (image generation)
                                    ├── Camera Vote Agent (vision hand-counting)
                                    ├── Audio Recorder (highlight reel)
                                    ├── Gemini Live API (WebSocket)
                                    └── Cloud Firestore (game state)
```

## Documentation

| Document | Description |
|---|---|
| [Product Requirements (PRD)](docs/PRD.md) | Full product spec — roles, features, user flows, competitive landscape |
| [Technical Design (TDD)](docs/TDD.md) | Implementation spec — agents, data model, API contracts, deployment |
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

# 🔥 Fireside: Betrayal

**The AI is one of you. Trust no one.**

A real-time, voice-first multiplayer social deduction game where an AI narrator leads players through an immersive story — and one of the characters is secretly controlled by AI.

## What is this?

Fireside: Betrayal combines the narrative immersion of tabletop RPGs with the social tension of Werewolf/Mafia. An AI narrator runs the game while simultaneously playing as a hidden character, lying, manipulating, and fighting to survive.

- 🎭 **4-8 players** on their phones
- 🎙️ **Voice-first** — the AI narrates with dramatic flair, players interrupt naturally
- 🐺 **Hidden AI player** — one character is secretly the AI, with its own deception strategy
- 🧠 **Post-game reveal** — see exactly what the AI was thinking every round
- ⏱️ **15-30 minutes** per game
- 📱 **No download** — works in any mobile browser

## How it plays

1. **Gather around the fire** — Share a code. Everyone joins on their phone.
2. **Roles are dealt** — Villager, Seer, Healer, Hunter... and the AI hides among you.
3. **Night falls, dawn breaks** — The Shapeshifter hunts. The Seer investigates. The village debates and votes.
4. **The truth is revealed** — After the game, see the AI's hidden reasoning for every lie it told.

## Tech Stack

- **AI Engine:** Google Gemini Live API (real-time bidirectional voice)
- **Agent Framework:** Google ADK (Agent Development Kit)
- **Backend:** FastAPI on Cloud Run
- **Real-time State:** Cloud Firestore
- **Frontend:** React (mobile web)
- **Deployment:** Terraform + Cloud Build (CI/CD)

## Architecture

```
Player Phones (4-8) ←WebSocket→ Cloud Run (FastAPI)
                                    ├── ADK Agent Orchestrator
                                    │   ├── Narrator Agent (Live API voice)
                                    │   ├── Game Master Agent (deterministic)
                                    │   └── Traitor Agent (LLM sub-agent)
                                    ├── Gemini Live API (WebSocket)
                                    └── Cloud Firestore (game state)
```

## Documentation

| Document | Description |
|---|---|
| [Product Requirements (PRD)](docs/PRD.md) | Full product spec — 8 P0, 10 P1, 18 P2, 3 P3 features |
| [Technical Design (TDD)](docs/TDD.md) | Implementation spec — 2,095 lines covering all P0/P1 |
| [UI Mockup](docs/ui-mockup.jsx) | Interactive React prototype — 6 screens (Landing, Join, Game, Vote, End) |

## Hackathon

Built for the **Gemini Live Agent Challenge** hackathon ($80K prize pool, Google DeepMind / Devpost).

- **Category:** 🗣️ Live Agents
- **Deadline:** March 16, 2026 at 5:00 PM PDT
- **Prize Target:** $10K (category) + $25K (grand prize)

## License

MIT

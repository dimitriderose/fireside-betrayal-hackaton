# Fireside: Betrayal at Thornwood — Playtest Personas

## Overview

Four gamer personas reviewed the Fireside codebase and UI across 3 rounds. The panel evaluated UX fixes incrementally as they were merged to `main`.

| Round | Composite | Delta | HEAD Commit |
|-------|-----------|-------|-------------|
| Round 1 (Baseline) | 8.4/10 | — | `c353a72` (pre-fix) |
| Round 2 (4 UX Fixes) | 9.25/10 | +0.85 | `89bf202` |
| Round 3 (Polish Branch) | 9.375/10 | +0.125 | `583624b` |

**Final Verdict:** Ship it. Zero remaining blockers.

---

## Persona Profiles

### 🎮 Alex — The Regular Gamer

| Attribute | Detail |
|-----------|--------|
| Age | 24 |
| Archetype | Regular gamer, plays 3–4 nights/week |
| Platforms | Among Us, Werewolf, Secret Hitler |
| Context | Gaming with friends on Discord; values fast lobbies, clear UI, satisfying game loops |
| What they care about | Speed of lobby setup, clarity of game state, moment-to-moment excitement |

### 🎮 Sam — The Casual Gamer

| Attribute | Detail |
|-----------|--------|
| Age | 31 |
| Archetype | Casual/infrequent gamer, plays at parties |
| Platforms | Jackbox, board games at gatherings |
| Context | Shows up to game night not knowing the rules; needs everything explained in-UI |
| What they care about | Can I figure this out without reading a manual? Is it fun even if I'm bad at it? |

### 🎮 Marcus — The Dungeon Master

| Attribute | Detail |
|-----------|--------|
| Age | 35 |
| Archetype | 7-year D&D DM, narrative-focused gamer |
| Platforms | D&D, Gloomhaven, narrative RPGs |
| Context | Evaluates games as a storytelling medium; cares about atmosphere, narrator quality, tone-setting tools for the host |
| What they care about | Does the narrator feel alive? Can the host shape the experience? Is the atmosphere immersive? |

### 🎮 Priya — The Board Game Organizer

| Attribute | Detail |
|-----------|--------|
| Age | 29 |
| Archetype | Organizes weekly game nights for 6–8 people |
| Platforms | Avalon, Blood on the Clocktower, One Night Ultimate Werewolf |
| Context | Evaluates games for group dynamics — can mixed-experience groups play together? Is setup fast enough to not lose the room? |
| What they care about | Onboarding friction for newcomers, group flow, host controls, spectator experience |

---

## Round 1 — Baseline Review

**Codebase state:** Pre-UX-fix. Original GameOver, JoinLobby, and GameScreen components.

### Scores

| Panelist | Score | Key Feedback |
|----------|-------|--------------|
| Alex | 8.5/10 | Lobby is fast, game state is clear, game-over screen is anticlimactic — "I survived all that and I just get a text banner?" Wants a bridge from game-over to the Timeline replay to see what the AI was doing. |
| Sam | 7.5/10 | Confused during first day discussion — didn't know about the quick reaction buttons (voice/touch hints). "I just sat there watching text scroll." Needs contextual onboarding hint during day phase. |
| Marcus | 9.0/10 | Narrator presets are great concept but host picks blind — no way to hear voice tone before committing. "I'm choosing the soul of the game's atmosphere based on a one-line description." Wants audio preview on narrator preset cards. Also wants sample flavor text per preset. |
| Priya | 8.5/10 | Can't tell who the host is in the lobby player grid. "When 6 people join, everyone asks 'who's the host?' in Discord." Needs a visible host badge/crown. Player ordering in lobby is non-deterministic — Firestore query has no guaranteed order. |
| **Composite** | **8.4/10** | |

### Panel Flags (Round 1)

1. **Game Over → Timeline bridge missing** — No teaser for what the AI was secretly doing. Players have no reason to click through to Timeline.
2. **Host badge missing** — No visual indicator of who created the game in the lobby player grid.
3. **Day-phase hint missing** — First-timers don't discover quick reactions (voice/touch) during discussion phase.
4. **Narrator voice preview missing** — Host picks narrator preset blind based on text description only. No audio sample.

---

## Round 2 — 4 UX Fix Branches + MUST FIX Follow-ups

**Fixes merged:** `feature/ux-gameover-timeline-bridge`, `feature/ux-host-badge`, `feature/ux-day-hint`, `feature/ux-narrator-preview` + 4 MUST FIX follow-up commits from code review.

**Key changes:**
- Game Over: AI secret teaser pull-quote with "See the full timeline →" CTA. Loyal-AI variant shows green framing ("What your ally was doing for you").
- Lobby: 👑 crown emoji on host slot, "host" label at 0.6875rem (WCAG compliant).
- GameScreen: Dismissible hint banner during day_discussion: "💬 Speak naturally — tap a reaction to highlight your point." Uses localStorage for persistence. Hidden from eliminated players.
- JoinLobby: ▶ preview button on each narrator preset card. Audio cached in component. AbortController prevents race conditions. Dedicated TTS model (`gemini-2.5-flash-preview-tts`).

### Scores

| Panelist | R1 | R2 | Delta | Key Feedback |
|----------|----|----|-------|--------------|
| Alex | 8.5 | 9.5 | +1.0 | "The AI teaser on game-over is exactly what I wanted. 'Night 2: Quietly redirected suspicion toward Rowan.' I HAVE to click through to see the full timeline now." Loyal-AI variant ("What your ally was doing for you" in green) was an unexpected emotional beat — "I voted out my own ally and now I can see everything they did to help me." |
| Sam | 7.5 | 8.5 | +1.0 | "The hint banner saved me. 'Tap a reaction to highlight your point' — I didn't know those buttons existed." Appreciated localStorage persistence so hint doesn't reappear once dismissed. Would still like the hint to auto-dismiss after first interaction with reactions. |
| Marcus | 9.0 | 9.5 | +0.5 | Audio preview is exactly right. ▶/⏹/⏳ states are clear. Caching means second click is instant. "I can now audition narrators the way I'd audition a voice actor." Still wants sample flavor text line per preset to compare personality without audio (reads faster). |
| Priya | 8.5 | 9.5 | +1.0 | Crown badge is immediately clear. "No more 'who's the host?' in Discord." Notes the `i===0` dead branch removal and WCAG font size fix from code review — "This is production-quality attention to detail." Satisfied with host identification. |
| **Composite** | **8.4** | **9.25** | **+0.85** | |

### Remaining Flags (Round 2)

1. ~~Game Over → Timeline bridge~~ → **Resolved**
2. ~~Host badge~~ → **Resolved**
3. ~~Day-phase hint~~ → **Resolved** (Sam wants auto-dismiss on phase change — nice-to-have)
4. ~~Narrator voice preview~~ → **Resolved** (Marcus wants sample text — nice-to-have)

---

## Round 3 — Polish Branch

**Fixes merged:** `fix/follow-up-polish` branch with 5 items + MUST FIX follow-up.

**Key changes:**
1. Day-hint auto-dismisses in state on phase change away from `day_discussion` (shows once per game, not every round). Explicit ✕ still writes localStorage for permanent cross-game dismissal.
2. Firestore `get_all_players()`: `order_by("joined_at")` guarantees host is contractually player slot 0.
3. Narrator preset cards: replaced `<div role="button">` wrapping `<button>` with proper dual-button accessibility structure.
4. Per-preset sample flavor text (italic, shown when selected):
   - Classic: *"The accused stands before you. Speak your defence, if you dare."*
   - Campfire: *"Pull up a log, friend. The night's young and the fire's warm."*
   - Horror: *"Something watches from beyond the treeline. It always has."*
   - Comedy: *"Congratulations — you've all survived round one. Mostly."*
5. `pcm_to_wav` moved to `utils/audio.py` (public utility, removes cross-module private import).
6. **MUST FIX:** Build-breaking syntax error (missing `)` on onClick handler), Campfire sample text revised to warm/narrative tone, sample text font size bumped to 0.6875rem.

### Scores

| Panelist | R1 | R2 | R3 | Delta (R2→R3) | Key Feedback |
|----------|----|----|----|----|--------------|
| Alex | 8.5 | 9.5 | 9.5 | — | Sample text is nice quality-of-life but doesn't change core experience. "I can read the tone before I hit play — saves me a tap if I already know I want Campfire." |
| Sam | 7.5 | 8.5 | 8.5 | — | Auto-dismiss fix matters most to him: "I would have seen that hint reappear every round and thought 'wait, I already dismissed this?'" Two-tier approach (state dismiss for this game, localStorage for permanent) is correct. |
| Marcus | 9.0 | 9.5 | **10.0** | +0.5 | "This is exactly what I asked for in Round 1." Per-preset sample text with voice-appropriate prose quality. Each line captures the exact personality of the preset. Combined with audio preview from R2, narrator selection is now: read description → see sample line → tap ▶ to hear voice → select. "As a DM who's spent 7 years setting tone for sessions, this is the most thoughtful audio design I've seen in a digital game." |
| Priya | 8.5 | 9.5 | 9.5 | — | `order_by("joined_at")` fix: "Invisible fix, essential correctness. Without it, the host badge was probabilistically correct. With it, contractually correct." Day-hint auto-dismiss is right for mixed-experience game nights. |
| **Composite** | **8.4** | **9.25** | **9.375** | **+0.125** | |

### Remaining Flags (Round 3)

**None.** All open requests from all panelists across 3 rounds have been addressed.

---

## Score Progression Summary

```
         R1      R2      R3
Alex    8.5 ──→ 9.5 ──→ 9.5
Sam     7.5 ──→ 8.5 ──→ 8.5
Marcus  9.0 ──→ 9.5 ──→ 10.0
Priya   8.5 ──→ 9.5 ──→ 9.5
─────────────────────────────
AVG     8.4     9.25    9.375
```

---

## What Each Persona Would Tell a Friend

**Alex:** "There's this AI social deduction game where the narrator actually talks. Like, full voice acting from AI. The game-over screen teases what the AI was secretly doing — you HAVE to click through to the timeline to see the whole story."

**Sam:** "I played this Werewolf-type game and I actually understood what was happening. There are little hints that pop up telling you what to do, and the narrator explains everything in voice. I didn't have to read any rules."

**Marcus:** "The narrator system is the best I've seen. You can preview each voice before the game starts, read sample dialogue, hear the tone. It's like casting a voice actor for your game night. The Classic narrator sounds like a fantasy RPG, the Campfire one sounds like a friend telling a story."

**Priya:** "Setup is fast. Share a code, everyone joins, the host has a crown so there's no confusion. It handles mixed groups well — new players get a hint banner their first round, experienced players never see it. I could run this for my whole game night group."

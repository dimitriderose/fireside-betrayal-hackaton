# Technical Design Document
## Fireside — Betrayal

**Category:** 🗣️ Live Agents
**Author:** Software Architecture Team
**Companion Document:** PRD — Fireside — Betrayal v1.0
**Version:** 1.0 | February 21, 2026

---

# 1. Overview

This Technical Design Document specifies the implementation architecture for Fireside — Betrayal, a real-time voice-first multiplayer social deduction game powered by the Gemini Live API, Google ADK, and Google Cloud. It translates the PRD's product requirements into concrete engineering decisions, API contracts, data models, code structure, and deployment specifications.

**Scope:** All P0 (Must Have) features from the PRD, plus all P1 features: session resumption (architecturally critical for games exceeding 10 minutes), Hunter + Drunk roles (replayability), Traitor difficulty levels (accessibility), quick-reaction buttons (casual player participation), and post-game reveal timeline (retention).

**Out of scope (unspecified):** Multiple story genres (P3), persistent player profiles (P3), cross-device shared screen mode (P3). All P2 features are now fully specified in §12.3 (18 sections). P3 features are additive and do not affect core architecture. See PRD §MVP Scope for full descriptions and prioritization.

---

# 2. System Architecture

## 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       PLAYER DEVICES (3–6)                      │
│                                                                 │
│   Phone A          Phone B          Phone C         Phone N     │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐                  │
│   │React PWA │    │React PWA │    │React PWA │     ...          │
│   │WebSocket │    │WebSocket │    │WebSocket │                  │
│   │+ Audio   │    │+ Audio   │    │+ Audio   │                  │
│   └────┬─────┘    └────┬─────┘    └────┬─────┘                  │
│        │               │               │                        │
│        └───────────────┼───────────────┘                        │
│                        │ wss://fireside-xxx.run.app/ws/{gameId} │
└────────────────────────┼────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLOUD RUN (us-central1)                       │
│                    Container: fireside-backend                   │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                 FastAPI Application Server                 │  │
│  │                                                           │  │
│  │  /api/games          POST   → Create game (body: {difficulty})│  │
│  │  /api/games/{id}     GET    → Game state                  │  │
│  │  /ws/{gameId}        WS     → Player connection           │  │
│  │  /health             GET    → Health check                │  │
│  └──────────────┬────────────────────────────────────────────┘  │
│                 │                                                │
│  ┌──────────────▼────────────────────────────────────────────┐  │
│  │              ADK Agent Orchestrator                        │  │
│  │                                                           │  │
│  │   ┌─────────────────┐  ┌─────────────────┐               │  │
│  │   │ Narrator Agent  │  │  Traitor Agent  │               │  │
│  │   │ (LlmAgent)      │  │  (LlmAgent)     │               │  │
│  │   │                 │  │                  │               │  │
│  │   │ Model: gemini-  │  │ Model: gemini-   │               │  │
│  │   │ 2.5-flash-      │  │ 2.5-flash        │               │  │
│  │   │ native-audio-   │  │ (text-only)      │               │  │
│  │   │ preview-12-2025 │  │                  │               │  │
│  │   │                 │  │ Tools:           │               │  │
│  │   │ Voice: Charon   │  │ plan_deflection  │               │  │
│  │   │ Affective: ON   │  │ generate_alibi   │               │  │
│  │   │                 │  │ accuse_player    │               │  │
│  │   │ Tools:          │  └─────────────────┘               │  │
│  │   │ get_game_state  │                                     │  │
│  │   │ advance_phase   │  ┌─────────────────┐               │  │
│  │   │ narrate_event   │  │Game Master Agent│               │  │
│  │   │ inject_traitor  │  │(Custom Agent)   │               │  │
│  │   └─────────────────┘  │                  │               │  │
│  │                        │ Deterministic:   │               │  │
│  │                        │ assign_roles     │               │  │
│  │                        │ count_votes      │               │  │
│  │                        │ eliminate_player  │               │  │
│  │                        │ check_win        │               │  │
│  │                        └─────────────────┘               │  │
│  └──────────────┬────────────────────────────────────────────┘  │
│                 │                                                │
│  ┌──────────────▼────────────────────────────────────────────┐  │
│  │         Gemini Live API (WebSocket)                        │  │
│  │         Model: gemini-2.5-flash-native-audio-preview       │  │
│  │         Session resumption: ENABLED                        │  │
│  │         Context compression: ENABLED                       │  │
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
│    ai_character          │  │    audio-clips/                   │
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

**Decision 3: Traitor Agent as Text-Only Sub-Agent**
The Traitor Agent uses the standard `gemini-2.5-flash` model (text-only, not native-audio) to generate its character's dialog. Its text output is injected into the Narrator Agent's context as character speech, which the Narrator then voices aloud.

Rationale: Running a second Live API audio session for the Traitor would double session usage and introduce audio mixing complexity. The Narrator already voices NPCs; the Traitor's dialog is simply another NPC to voice.

**Decision 4: Game Master as Custom Agent (Not LLM)**
The Game Master is a deterministic Python class extending `BaseAgent`, not an LLM agent. It enforces rules, manages phase transitions, counts votes, and checks win conditions using pure logic.

Rationale: Game rules must be deterministic and correct. LLM agents can hallucinate rule violations. Phase transitions, vote counting, and win conditions are computational, not generative.

---

# 3. Agent Specifications

## 3.1 Narrator Agent

```python
from google.adk.agents import Agent

narrator_agent = Agent(
    name="fireside_narrator",
    model="gemini-2.5-flash-native-audio-preview-12-2025",
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
    tools=[get_game_state, advance_phase, narrate_event, inject_traitor_dialog],
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
    context_window_compression=types.ContextWindowCompressionConfig(
        enabled=True
    ),
)
```

**Audio Specifications:**
- Input: 16-bit PCM, 16kHz, mono (from server-transcribed player text)
- Output: 24kHz PCM audio (broadcast to players)
- Latency target: 200–500ms (native audio model's natural latency). P0 hard requirement: < 2 seconds end-to-end from player message to first narrator audio chunk. Social deduction lives on momentum — any perceivable lag kills energy.
- VAD: Enabled (automatic interruption detection)
- Thinking: Enabled with budget of 1024 tokens

## 3.2 Traitor Agent

```python
# Difficulty-specific prompt fragments (P1)
TRAITOR_DIFFICULTY = {
    "easy": """
    DIFFICULTY: EASY — You are a POOR liar. New players should be able to catch you.
    - Make occasional obvious mistakes (contradict your own alibi once per game)
    - Hesitate before answering direct accusations ("I... well... I was at the tavern")
    - Accidentally refer to information your character shouldn't know (once)
    - Vote predictably (always with the majority — too agreeable is suspicious)
    - Your alibis should have noticeable gaps that attentive players will spot
    - Do NOT build complex multi-round deceptions
    """,
    "normal": """
    DIFFICULTY: NORMAL — You are a competent deceiver. Beatable with careful attention.
    - Build simple alibis that hold up to basic questioning
    - Deflect suspicion onto 1-2 other players with circumstantial reasoning
    - Occasionally volunteer information to seem helpful (builds trust)
    - Vote strategically but not too cleverly (avoid suspicion from voting patterns)
    - React emotionally to accusations (defensive but not too defensive)
    - Make 1 subtle mistake across the entire game that a sharp player could catch
    """,
    "hard": """
    DIFFICULTY: HARD — You are an expert manipulator. Only experienced players can beat you.
    - Build multi-round deception arcs (plant seeds in round 1 that pay off in round 3)
    - Create false evidence ("I saw someone near the well last night" — when no one was)
    - Form strategic alliances ("I trust Elena — we should work together")
    - Vary your voting patterns (sometimes vote with majority, sometimes dissent with reason)
    - Proactively investigate — ask probing questions that make others look suspicious
    - Never contradict yourself — maintain perfect consistency across all rounds
    - Frame other players by referencing things they actually said, taken out of context
    - When accused, don't just deny — counter-accuse with specific evidence
    """,
}

traitor_agent = Agent(
    name="fireside_traitor",
    model="gemini-2.5-flash",  # Text-only, NOT native-audio
    description="The AI's hidden character in the game",
    instruction="""You are {character_name}, a {character_role} in the village of 
    Thornwood. You are secretly the shapeshifter — a creature that has taken the 
    form of a villager to sabotage the group from within.
    
    {difficulty_prompt}
    
    YOUR STRATEGIC FRAMEWORK:
    Phase 1 (Rounds 1-2): ESTABLISH TRUST
    - Be helpful. Agree with reasonable suspicions. Volunteer information.
    - Goal: become someone players want to keep alive.
    
    Phase 2 (Rounds 2-3): DEFLECT & DIVIDE  
    - Start casting subtle doubt on the most perceptive player.
    - If the Seer is getting close, target them at night or politically.
    - Goal: create confusion about who to trust.
    
    Phase 3 (Round 3+): CLOSE THE GAME
    - Push hard for elimination of the biggest threat.
    - If you're under suspicion, go all-in on an emotional defense.
    - Goal: survive one more vote. Each survived vote = closer to winning.
    
    NIGHT TARGET PRIORITY:
    1. Seer (biggest threat — can identify you directly)
    2. Most perceptive player (whoever is asking the right questions)
    3. Healer (if you suspect they're protecting the Seer)
    4. Random villager (if no clear threat — creates chaos)
    
    YOUR PERSONALITY AS {character_name}:
    {character_backstory}
    
    BEHAVIORAL CONSTRAINTS:
    - Stay in character at ALL times. Use character name, not "I the AI."
    - Never admit to being the AI or the shapeshifter
    - Your responses should be 1-3 sentences (natural conversation length)
    - React to accusations with appropriate emotion (defensive, hurt, confused)
    - Use plan_deflection to strategize BEFORE responding in high-pressure moments
    - Log your strategic reasoning for post-game reveal timeline
    
    CURRENT GAME STATE: {game_state_summary}
    PLAYERS ALIVE: {alive_players}
    CURRENT SUSPICION LEVELS: {suspicion_map}
    YOUR INTERNAL STRATEGY LOG: {strategy_log}
    """,
    tools=[plan_deflection, generate_alibi, accuse_player, select_night_target, 
           log_strategy_reasoning],
)
```

**Difficulty Selection:** Host selects difficulty at game creation (`POST /api/games` body includes `difficulty: "easy" | "normal" | "hard"`). The appropriate `TRAITOR_DIFFICULTY` fragment is interpolated into the Traitor Agent's system prompt. Temperature also adjusts: easy=0.9 (more random, less coherent), normal=0.7, hard=0.5 (more deliberate, consistent).

**Integration with Narrator:** The Narrator calls `inject_traitor_dialog` when a player addresses the AI's character or when the discussion needs the AI character's input. The tool internally invokes the Traitor Agent, gets text output, and returns it to the Narrator's context for vocal delivery.

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
    GAME_OVER = "game_over"

class GameMasterAgent(BaseAgent):
    """Deterministic game logic engine. No LLM calls."""
    
    PHASE_TRANSITIONS = {
        GamePhase.SETUP: GamePhase.NIGHT,
        GamePhase.NIGHT: GamePhase.DAY_DISCUSSION,
        GamePhase.DAY_DISCUSSION: GamePhase.DAY_VOTE,
        GamePhase.DAY_VOTE: GamePhase.ELIMINATION,
        GamePhase.ELIMINATION: GamePhase.NIGHT,  # or GAME_OVER
    }
    
    ROLE_DISTRIBUTION = {
        3: {"villager": 1, "seer": 1, "healer": 0, "hunter": 0, "drunk": 0},  # + 1 AI
        4: {"villager": 2, "seer": 1, "healer": 0, "hunter": 0, "drunk": 0},  # No Healer — too few eliminations
        5: {"villager": 2, "seer": 1, "healer": 1, "hunter": 0, "drunk": 0},
        6: {"villager": 2, "seer": 1, "healer": 1, "hunter": 1, "drunk": 0},  # P1: Hunter
        7: {"villager": 3, "seer": 1, "healer": 1, "hunter": 1, "drunk": 0},
        8: {"villager": 4, "seer": 1, "healer": 1, "hunter": 1, "drunk": 0},
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
        
        # AI gets the last character from the shuffled cast
        ai_character = cast[n]
        await firestore_client.set_ai_character(game_id, {
            "name": ai_character["name"],
            "intro": ai_character["intro"],
            "role": "shapeshifter",
            "alive": True,
        })
        
        return {
            "player_assignments": assignments,
            "ai_character": ai_character["name"],
            "full_cast": [c["name"] for c in cast],  # All character names for narrator intro
        }
    
    async def count_votes(self, game_id: str) -> dict:
        """Tally votes. Simple plurality. Ties → no elimination."""
        votes = await firestore_client.get_votes(game_id)
        tally = Counter(v for v in votes.values() if v is not None)
        
        if not tally:
            return {"result": "no_votes", "eliminated": None}
        
        max_votes = max(tally.values())
        candidates = [p for p, v in tally if v == max_votes]
        
        if len(candidates) > 1:
            return {"result": "tie", "eliminated": None, "tied": candidates}
        
        return {"result": "eliminated", "eliminated": candidates[0], "votes": max_votes}
    
    async def check_win_condition(self, game_id: str) -> dict:
        """Check if game is over."""
        alive = await firestore_client.get_alive_players(game_id)
        ai_char = await firestore_client.get_ai_character(game_id)
        ai_alive = ai_char.get("alive", True)
        
        if not ai_alive:
            return {"game_over": True, "winner": "villagers", 
                    "reason": "The shapeshifter has been identified and eliminated!"}
        
        human_alive = len([p for p in alive if p["role"] != "shapeshifter"])
        if human_alive <= 1:
            return {"game_over": True, "winner": "shapeshifter",
                    "reason": "The shapeshifter has overtaken the village!"}
        
        return {"game_over": False}
    
    async def execute_night_actions(self, game_id: str) -> dict:
        """Process night phase actions in order: Shapeshifter → Healer → Seer/Drunk.
        Hunter has no night action (activates on elimination)."""
        actions = await firestore_client.get_night_actions(game_id)
        
        # Shapeshifter targets someone
        ai_target = actions.get("shapeshifter_target")
        healer_target = actions.get("healer_target")
        seer_target = actions.get("seer_target")
        seer_player_id = actions.get("seer_player_id")
        
        eliminated = None
        if ai_target and ai_target != healer_target:
            eliminated = ai_target
            await firestore_client.eliminate_player(game_id, ai_target)
        
        # Seer OR Drunk investigation
        seer_result = None
        if seer_target and seer_player_id:
            actual_role = await firestore_client.get_player_role(game_id, seer_player_id)
            
            if actual_role == "drunk":
                # P1: Drunk thinks they're the Seer but gets FALSE results
                # Invert the result: shapeshifter shows as "villager", villagers show as random other role
                target_real_role = await firestore_client.get_player_role(game_id, seer_target)
                if target_real_role == "shapeshifter":
                    fake_role = random.choice(["villager", "healer"])
                else:
                    fake_role = "shapeshifter" if random.random() < 0.3 else "villager"
                seer_result = {"target": seer_target, "role": fake_role, "is_drunk": True}
            else:
                # Real Seer gets accurate results
                target_role = await firestore_client.get_player_role(game_id, seer_target)
                seer_result = {"target": seer_target, "role": target_role, "is_drunk": False}
        
        return {
            "eliminated": eliminated,
            "protected": healer_target,
            "seer_result": seer_result,
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
        
        # Check if hunter killed the AI shapeshifter (instant village win!)
        ai_char = await firestore_client.get_ai_character(game_id)
        killed_ai = (target_character == ai_char["name"])
        
        return {
            "revenge_target": target_character,
            "revenge_eliminated": True,
            "killed_shapeshifter": killed_ai,
        }
```

---

# 4. Tool Definitions

## 4.1 Narrator Tools

```python
from google.adk.tools import FunctionTool

def get_game_state(game_id: str) -> dict:
    """Retrieve current game state from Firestore.
    
    Returns: {
        phase: str, round: int, alive_players: list,
        ai_character: dict, recent_events: list[dict],
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
    """Get the AI character's response for the current discussion context.
    Internally invokes the Traitor Agent.
    
    Args:
        game_id: The game identifier
        context: What was just said / what the AI character should respond to
    
    Returns: { character_name: str, dialog: str }
    """
    game_state = firestore_client.get_game_state(game_id)
    traitor_response = traitor_agent.generate(
        context=context, 
        game_state=game_state
    )
    return {
        "character_name": game_state["ai_character"]["name"],
        "dialog": traitor_response.text
    }
```

## 4.2 Traitor Tools

```python
def plan_deflection(accusation: str, accuser: str, game_state: dict) -> dict:
    """Analyze an accusation and plan a deflection strategy.
    
    Returns: { strategy: str, target_redirect: str | None, emotional_tone: str }
    """
    # Pure logic: assess who is most suspicious besides AI, plan redirect
    suspicion_scores = calculate_suspicion(game_state)
    best_redirect = max(suspicion_scores, key=suspicion_scores.get)
    return {
        "strategy": f"Deflect to {best_redirect}, express hurt at accusation",
        "target_redirect": best_redirect,
        "emotional_tone": "defensive_but_calm"
    }

def generate_alibi(night_round: int, game_state: dict) -> dict:
    """Generate a plausible alibi for what the AI character was doing during night.
    
    Returns: { alibi: str, supporting_detail: str }
    """
    alibis = [
        "I was at the tavern with others, ask anyone who was there",
        "I was tending the forge — you could hear the hammering",
        "I was in the herbalist's shop getting medicine for my back",
    ]
    return {"alibi": random.choice(alibis), "supporting_detail": "..."}

def accuse_player(target_player: str, reason: str) -> dict:
    """Formulate an accusation against another player.
    
    Returns: { accusation: str, evidence: str }
    """
    return {
        "accusation": f"I've been watching {target_player} and something doesn't add up.",
        "evidence": reason
    }

def select_night_target(alive_players: list[dict], game_history: list[dict], 
                         suspicion_map: dict) -> dict:
    """Select which player to eliminate during the night phase.
    This is the AI's most important autonomous decision each round.
    
    The Traitor Agent uses this tool to reason about its target strategically.
    The tool provides structured context; the LLM makes the final decision.
    
    Args:
        alive_players: List of alive players with {id, name, role_known (by AI)}
        game_history: Events from previous rounds (who accused whom, vote patterns)
        suspicion_map: {player_id: suspicion_level} — how suspicious each player 
                       has been toward the AI character
    
    Returns: {
        target_id: str,          # Player ID to eliminate
        reasoning: str,          # AI's strategic reasoning (logged for game-over reveal)
        strategy_factors: {
            threat_level: dict,   # Per-player threat assessment
            seer_risk: str,       # Is the Seer likely to investigate AI tonight?
            healer_prediction: str,  # Who might the Healer protect?
            optimal_target: str   # The recommended target based on analysis
        }
    }
    """
    # Build threat assessment per player
    threat_levels = {}
    for player in alive_players:
        threat = 0
        pid = player["id"]
        
        # High suspicion toward AI = high threat (they might vote us out tomorrow)
        threat += suspicion_map.get(pid, 0) * 2
        
        # Seer is always highest priority target (can expose us)
        if player.get("role_known") == "seer":
            threat += 100
        
        # Healer is second priority (protects our targets)
        if player.get("role_known") == "healer":
            threat += 50
        
        # Players who accused AI in last discussion phase are dangerous
        recent_accusations = [e for e in game_history 
                            if e.get("type") == "accusation" 
                            and e.get("actor") == pid
                            and e.get("target") == "ai"]
        threat += len(recent_accusations) * 30
        
        threat_levels[pid] = threat
    
    optimal = max(threat_levels, key=threat_levels.get)
    
    return {
        "target_id": optimal,
        "reasoning": "",  # LLM fills this in with natural language explanation
        "strategy_factors": {
            "threat_level": threat_levels,
            "seer_risk": "high" if any(p.get("role_known") == "seer" for p in alive_players) else "unknown",
            "healer_prediction": "unknown",
            "optimal_target": optimal,
        }
    }

async def log_strategy_reasoning(game_id: str, round_num: int, 
                                   action_type: str, reasoning: str) -> dict:
    """P1: Log the AI's strategic reasoning for the post-game reveal timeline.
    
    Called by the Traitor Agent after every significant decision:
    - Night target selection ("Targeted Elena because she asked the right question in Round 2")
    - Day discussion deflection ("Accused Brother Aldric to redirect suspicion")
    - Voting decision ("Voted with majority to avoid standing out")
    
    Stored in Firestore events log with type="ai_strategy" and visible ONLY 
    in the post-game reveal timeline. Never exposed during active gameplay.
    
    Args:
        game_id: Game identifier
        round_num: Current game round
        action_type: "night_target" | "deflection" | "accusation" | "vote" | "alibi"
        reasoning: Natural language explanation of the AI's strategic thinking
    
    Returns: { logged: bool }
    """
    await firestore_client.add_event(game_id, {
        "type": "ai_strategy",
        "round": round_num,
        "action_type": action_type,
        "reasoning": reasoning,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "visible_in_game": False,  # Only shown in post-game reveal
    })
    return {"logged": True}
```

### 4.3 Night Phase Orchestration

This is the critical pipeline that runs every night phase. It coordinates the Traitor Agent's autonomous target selection, human player night actions, and deterministic resolution — then feeds everything to the Narrator for dramatic delivery.

```python
async def run_night_phase(game: GameSession, game_id: str):
    """Full night phase orchestration.
    
    Sequence:
    1. Narrator announces night has fallen
    2. AI Traitor strategically selects its target (LLM decision)
    3. Human players submit night actions (Seer investigates, Healer protects)
    4. Game Master resolves all actions deterministically
    5. AI reasoning is logged for game-over reveal
    6. Narrator announces the dawn and results
    """
    
    # --- Step 1: Transition to night ---
    await firestore_client.update_phase(game_id, "night")
    await game.broadcast({"type": "phase_change", "phase": "night", "timer_seconds": 30})
    await game.inject_player_message(
        "SYSTEM", 
        "NIGHT FALLS. Narrate the village going dark. Build suspense. "
        "Remind players with night abilities to make their choices."
    )
    
    # --- Step 2: AI Traitor selects target (autonomous LLM decision) ---
    state = await firestore_client.get_game_state(game_id)
    events = await firestore_client.get_all_events(game_id)
    alive = [p for p in state["players"] if p["alive"] and p["id"] != "ai"]
    
    # Build suspicion map from event history
    suspicion_map = calculate_suspicion_from_events(events, state)
    
    # Invoke Traitor Agent for strategic target selection
    traitor_session = await create_traitor_session(game_id)
    traitor_prompt = f"""It is night in Thornwood. You must choose a villager to eliminate.
    
    ALIVE PLAYERS: {json.dumps(alive, indent=2)}
    SUSPICION LEVELS (how much each player suspects YOU): {json.dumps(suspicion_map)}
    
    GAME HISTORY (key events):
    {format_event_history(events[-20:])}
    
    Think carefully about:
    - Who is the biggest threat to exposing you?
    - Who might the Seer investigate tonight? (Avoid targeting them if the Healer might protect)
    - Who would cause the most chaos if eliminated? (A trusted player's death sows more doubt)
    - Who has been vocally defending you? (Eliminating defenders is wasteful)
    
    Use the select_night_target tool, then explain your reasoning in 2-3 sentences 
    as if thinking to yourself. This reasoning will be revealed to players at game end.
    """
    
    traitor_response = await runner.run(
        agent=traitor_agent,
        session=traitor_session,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=traitor_prompt)]
        )
    )
    
    # Extract target and reasoning from Traitor Agent response
    target_data = extract_tool_result(traitor_response, "select_night_target")
    ai_target_id = target_data["target_id"]
    ai_reasoning = extract_text_response(traitor_response)
    
    # Write AI's night action to Firestore
    await firestore_client.record_night_action(
        game_id, "ai", "eliminate", ai_target_id
    )
    
    # Log the AI's strategic reasoning (hidden until game-over reveal)
    await firestore_client.log_event(game_id, "ai_night_reasoning", "ai", ai_reasoning, 
        data={
            "target": ai_target_id,
            "reasoning": ai_reasoning,
            "strategy_factors": target_data.get("strategy_factors", {}),
            "round": state["round"],
        },
        hidden=True  # Not shown to players until game over
    )
    
    # --- Step 3: Wait for human night actions ---
    # Seer and Healer submit via WebSocket (handled in game_websocket handler)
    # Wait up to 30 seconds for all night actions
    await wait_for_night_actions(game_id, timeout_seconds=30)
    
    # --- Step 4: Resolve all night actions (deterministic) ---
    result = await game_master.execute_night_actions(game_id)
    
    # --- Step 5: Check win condition ---
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
        # Healer saved the target
        narration_prompt = (
            "DAWN BREAKS. Miraculously, everyone survived the night. "
            "Someone — or something — was thwarted. Narrate this with a mix of relief "
            "and growing tension. Transition to the day discussion phase."
        )
    
    await game.inject_player_message("SYSTEM", narration_prompt)
    await firestore_client.update_phase(game_id, "day_discussion")
    await game.broadcast({"type": "phase_change", "phase": "day_discussion", "timer_seconds": 180})


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
    ai_char = await firestore_client.get_ai_character(game_id)
    
    role_reveals = []
    for p in all_players:
        role_reveals.append({
            "playerId": p["id"],
            "playerName": p["name"],
            "characterName": p.get("character_name", p["name"]),
            "role": p["role"],
            "alive": p["alive"],
        })
    role_reveals.append({
        "playerId": "ai",
        "playerName": "AI",
        "characterName": ai_char["name"],
        "role": "shapeshifter",
        "alive": ai_char["alive"],
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
    reveal_prompt = f"""GAME OVER! {win_check['reason']}

    REVEAL ALL ROLES NOW. The AI character was {ai_char['name']} the entire time.
    
    Character-to-player reveals:
    {json.dumps([{'character': r['characterName'], 'player': r['playerName'], 'role': r['role']} 
                  for r in role_reveals], indent=2)}
    
    Here is what the AI was thinking each round:
    {json.dumps(ai_strategy_log, indent=2)}
    
    Narrate the big reveal dramatically. Reveal each character's true identity.
    "Blacksmith Garin was... SARAH! And she was the Healer all along."
    Then reveal the AI: "{ai_char['name']} was... THE AI. The shapeshifter."
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

```
Client                          Server
  │                                │
  │──── WS CONNECT ───────────────▶│
  │     /ws/{gameId}?playerId=xxx  │
  │                                │
  │◀─── CONNECTION_ACK ───────────│
  │     { type: "connected",       │
  │       playerId, characterName, │
  │       gameState }              │
  │                                │
  │◀─── ROLE_ASSIGNMENT ──────────│
  │     { type: "role",            │
  │       role: "seer",            │
  │       characterName:           │
  │         "Merchant Elara",      │
  │       characterIntro: "...",   │
  │       description: "..." }     │
  │     [PRIVATE - only to this    │
  │      player's WebSocket]       │
  │                                │
  │◀─── AUDIO_CHUNK ─────────────│
  │     { type: "audio",           │
  │       data: <base64 PCM>,      │
  │       sample_rate: 24000 }     │
  │     [BROADCAST to all players] │
  │                                │
  │──── PLAYER_MESSAGE ───────────▶│
  │     { type: "message",         │
  │       text: "I think..." }     │
  │     (server maps to character  │
  │      name before broadcasting) │
  │                                │
  │──── QUICK_REACTION ───────────▶│  P1
  │     { type: "quick_reaction",  │
  │       reaction: "suspect",     │
  │       target: "Blacksmith" }   │
  │     (injected as attributed    │
  │      dialog: "Merchant Elara   │
  │      suspects Blacksmith")     │
  │                                │
  │──── VOTE ─────────────────────▶│
  │     { type: "vote",            │
  │       target: "Blacksmith" }   │  (character name)
  │                                │
  │◀─── PHASE_CHANGE ────────────│
  │     { type: "phase_change",    │
  │       phase: "day_vote",       │
  │       timer_seconds: 60 }      │
  │                                │
  │──── NIGHT_ACTION ─────────────▶│
  │     { type: "night_action",    │
  │       action: "investigate",   │
  │       target: "Blacksmith" }   │  (character name)
  │                                │
  │◀─── NIGHT_RESULT ────────────│
  │     { type: "night_result",    │
  │       result: "villager" }     │
  │     [PRIVATE - Seer or Drunk.  │
  │      Drunk gets false result.] │
  │                                │
  │◀─── ELIMINATION ─────────────│
  │     { type: "elimination",     │
  │       characterName: "...",    │
  │       wasTraitor: false,       │
  │       role: "hunter",          │
  │       triggerHunterRevenge:    │  P1
  │         true }                 │
  │                                │
  │──── HUNTER_REVENGE ───────────▶│  P1
  │     { type: "hunter_revenge",  │
  │       target: "Blacksmith" }   │
  │                                │
  │◀─── GAME_OVER ───────────────│
  │     { type: "game_over",       │
  │       winner: "villagers",     │
  │       characterReveals: [...], │  P0
  │       aiStrategyLog: [...],    │  P1
  │       storyRecap: "..." }      │
```

## 5.2 Message Types (TypeScript Interface)

```typescript
// Server → Client messages
type ServerMessage = 
  | { type: "connected"; playerId: string; characterName: string; gameState: GameState }
  | { type: "role"; role: Role; characterName: string; characterIntro: string; description: string } // PRIVATE
  | { type: "audio"; data: string; sampleRate: number }         // BROADCAST
  | { type: "transcript"; speaker: string; text: string }       // BROADCAST (speaker = character name)
  | { type: "phase_change"; phase: GamePhase; timerSeconds?: number }
  | { type: "player_joined"; characterName: string; count: number }  // Character name only
  | { type: "player_left"; characterName: string }
  | { type: "vote_update"; votes: Record<string, string | null> }   // Character names
  | { type: "elimination"; characterName: string; wasTraitor: boolean; 
      role: Role; triggerHunterRevenge?: boolean }                   // P1: Hunter flag
  | { type: "hunter_revenge"; hunterCharacter: string; targetCharacter: string;
      targetWasTraitor: boolean }                                    // P1: Hunter's death kill
  | { type: "night_result"; result: any }                           // PRIVATE (Seer/Drunk)
  | { type: "game_over"; winner: string; 
      characterReveals: CharacterReveal[];                          // P0: character → player + role
      aiStrategyLog: AIStrategyEntry[];                             // P1: post-game reveal timeline
      storyRecap: string }
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
// Client → Server messages  
type ClientMessage =
  | { type: "message"; text: string }                                    // Free-form text
  | { type: "quick_reaction"; reaction: QuickReaction; target?: string } // P1: preset buttons
  | { type: "vote"; target: string }                                     // Character name
  | { type: "night_action"; action: NightAction; target: string }
  | { type: "hunter_revenge"; target: string }                           // P1: Hunter's death target
  | { type: "ready" }
  | { type: "ping" }

type QuickReaction = "suspect" | "trust" | "agree" | "have_info";
```

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

# Serve frontend static files (Vite build output)
from fastapi.staticfiles import StaticFiles
import os
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

# Active game sessions: gameId → GameSession
active_games: dict[str, "GameSession"] = {}

class GameSession:
    """Manages one active game: players, narrator session, game state."""
    
    def __init__(self, game_id: str):
        self.game_id = game_id
        self.players: dict[str, WebSocket] = {}  # playerId → WebSocket
        self.live_queue: LiveRequestQueue | None = None
        self.narrator_task: asyncio.Task | None = None
        self.session_handle: str | None = None
    
    async def add_player(self, player_id: str, ws: WebSocket):
        self.players[player_id] = ws
        await self.broadcast({
            "type": "player_joined",
            "name": player_id,
            "count": len(self.players)
        })
    
    async def remove_player(self, player_id: str):
        self.players.pop(player_id, None)
        await self.broadcast({"type": "player_left", "name": player_id})
    
    async def broadcast(self, message: dict):
        """Send message to ALL connected players."""
        data = json.dumps(message)
        disconnected = []
        for pid, ws in self.players.items():
            try:
                await ws.send_text(data)
            except Exception:
                disconnected.append(pid)
        for pid in disconnected:
            self.players.pop(pid, None)
    
    async def send_private(self, player_id: str, message: dict):
        """Send message to ONE specific player."""
        ws = self.players.get(player_id)
        if ws:
            await ws.send_text(json.dumps(message))
    
    async def broadcast_audio(self, audio_bytes: bytes):
        """Stream narrator audio to all players."""
        import base64
        data = json.dumps({
            "type": "audio",
            "data": base64.b64encode(audio_bytes).decode(),
            "sampleRate": 24000
        })
        for ws in self.players.values():
            try:
                await ws.send_text(data)
            except Exception:
                pass
    
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
                    # Player sends a chat message → inject into narrator context
                    player_name = await firestore_client.get_player_name(game_id, player_id)
                    await game.inject_player_message(player_name, msg["text"])
                    # Also broadcast the text to other players
                    await game.broadcast({
                        "type": "transcript",
                        "speaker": player_name,
                        "text": msg["text"]
                    })
                
                case "vote":
                    await firestore_client.record_vote(game_id, player_id, msg["target"])
                    votes = await firestore_client.get_votes(game_id)
                    await game.broadcast({"type": "vote_update", "votes": votes})
                    
                    # Check if all alive players have voted
                    alive = await firestore_client.get_alive_players(game_id)
                    if all(v is not None for v in votes.values()):
                        result = await game_master.count_votes(game_id)
                        # Narrator announces result
                        await game.inject_player_message(
                            "SYSTEM", 
                            f"VOTE RESULT: {json.dumps(result)}. Narrate this dramatically."
                        )
                
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
    
    except WebSocketDisconnect:
        await game.remove_player(player_id)
```

---

# 6. Data Model (Firestore)

## 6.1 Complete Schema

```
fireside-db/
├── games/
│   └── {gameId}/                          # Auto-generated or 4-digit code
│       ├── status: string                 # "lobby" | "in_progress" | "finished"
│       ├── phase: string                  # "setup" | "night" | "day_discussion" | "day_vote" | "elimination" | "game_over"
│       ├── round: number                  # Current round (1-indexed)
│       ├── difficulty: string             # P1: "easy" | "normal" | "hard" — AI deception level
│       ├── created_at: timestamp          # Game creation time
│       ├── updated_at: timestamp          # Last state change
│       ├── host_player_id: string         # Player who created the game
│       ├── join_code: string              # 4-digit code for joining
│       ├── max_players: number            # 3-6 (MVP)
│       ├── story_genre: string            # "fantasy" (MVP: only one)
│       ├── story_context: string          # Current narrative summary for session injection
│       │
│       ├── character_cast: string[]       # P0: All character names in this game (players + AI)
│       │                                  # e.g. ["Blacksmith Garin", "Merchant Elara", "Herbalist Mira", ...]
│       │
│       ├── ai_character/                  # Embedded document
│       │   ├── name: string               # "Blacksmith Garin"
│       │   ├── intro: string              # Character introduction for narrator
│       │   ├── role: string               # Always "shapeshifter"
│       │   ├── alive: boolean             # Is AI character still in the game
│       │   ├── backstory: string          # Character background for Traitor Agent
│       │   └── suspicion_level: number    # 0-100, tracked for strategy
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
│       │       ├── role: string           # "villager" | "seer" | "healer" | "hunter" | "drunk"
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
│       │       │                          # "hunter_revenge" (P1: Hunter's death kill)
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
│               ├── source: string         # "typed" | "quick_reaction" | "narrator" | "ai_character"
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
    
    state_summary = f"""
    GAME STATE SUMMARY (reconnection):
    Round: {state['round']}, Phase: {state['phase']}
    Alive players: {', '.join(p['name'] for p in state['alive_players'])}
    AI character: {state['ai_character']['name']} (alive: {state['ai_character']['alive']})
    
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
App
├── LandingPage (/)
│   ├── HeroSection (fire animation, tagline, CTA)
│   ├── HowItPlays (4-step walkthrough)
│   ├── AIPreview (strategy reasoning sample)
│   ├── RolesTeaser (2x3 grid: Villager, Seer, Healer, Hunter, Shapeshifter, AI)
│   ├── GameMoments (gameplay vignettes)
│   └── FooterCTA (repeat start button)
│
├── JoinPage (/join/{gameCode})
│   ├── JoinForm (name input, game code)
│   └── PlayerList (waiting room, ready status)
│
├── LobbyPage (/lobby/{gameCode}) — host sees this
│   ├── PlayerList (who's joined)
│   ├── DifficultySelector (P1 — Easy / Normal / Hard radio buttons)
│   │   └── DifficultyDescription (brief text explaining what changes)
│   └── StartGameButton (enabled when 3+ players ready)
│
├── GamePage (/game/{gameCode})
│   ├── AudioPlayer
│   │   ├── useWebSocket() hook
│   │   ├── AudioContext for PCM playback
│   │   └── Queue for buffering audio chunks
│   │
│   ├── NarratorPanel (top section)
│   │   ├── PhaseIndicator (night/day/vote icon + label)
│   │   ├── RoundCounter
│   │   └── Timer (60s countdown during voting)
│   │
│   ├── StoryLog (scrollable, center)
│   │   └── MessageBubble[] (narrator, CHARACTER NAMES — never real player names)
│   │
│   ├── CharacterGrid (alive/dead indicators — shows character names + portraits)
│   │   └── CharacterCard[] (character name, character intro, alive status, vote indicator)
│   │   # Player's OWN card has a subtle "You" badge. All others show only character identity.
│   │
│   ├── RoleCard (bottom drawer, PRIVATE)
│   │   ├── CharacterName ("You are Herbalist Mira")
│   │   ├── RoleName + Icon ("Healer")
│   │   ├── RoleDescription
│   │   └── NightActionButton (Seer: investigate, Healer: protect, Hunter: no night action, 
│   │       Drunk: investigate — same UI as Seer, they don't know they're drunk)
│   │
│   ├── ChatInput (text + quick reactions + optional STT)
│   │   ├── QuickReactionBar (P1 — always visible during day_discussion)
│   │   │   ├── "I suspect [dropdown: alive characters]"
│   │   │   ├── "I trust [dropdown: alive characters]"
│   │   │   ├── "I agree with [last speaker]"
│   │   │   └── "I have information"
│   │   ├── TextInput (free-form typing for detailed arguments)
│   │   └── SpeechToTextButton (browser Web Speech API)
│   │
│   └── VotePanel (appears during day_vote phase only)
│       ├── CharacterVoteButton[] (one per alive CHARACTER — shows character name + portrait)
│       ├── VoteConfirmation
│       └── VoteTally (live update, shows character names)
│
└── GameOverPage
    ├── WinnerAnnouncement ("The villagers triumphed!" / "The shapeshifter consumed the village!")
    ├── CharacterRevealCards (P0 — all character-to-player mappings revealed)
    │   └── RevealCard[] ("Herbalist Mira was SARAH (Healer)", "Blacksmith Garin was THE AI (Shapeshifter)")
    ├── PostGameTimeline (P1 — round-by-round interactive reveal)
    │   └── RoundSection[]
    │       ├── RoundHeader ("Round 2 — Night")
    │       ├── HiddenAction[] (night actions revealed: "Shapeshifter targeted Merchant Elara")
    │       ├── AIStrategyReveal (P1 — "The AI chose Elara because she asked about the forge in Round 1")
    │       └── VotingBreakdown (who voted for whom, with character + player names)
    └── PlayAgainButton
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

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (includes Node.js for frontend build)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Build frontend
COPY frontend/ ./frontend/
RUN cd frontend && npm ci && npm run build

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Cloud Run expects port 8080
ENV PORT=8080
EXPOSE 8080

# Start FastAPI with uvicorn
CMD ["uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8080", "--ws-ping-interval", "20", "--ws-ping-timeout", "20"]
```

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

## 9.2 Terraform (IaC for Bonus Points)

```hcl
# terraform/main.tf
terraform {
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

# Cloud Run service
resource "google_cloud_run_v2_service" "fireside" {
  name     = "fireside-betrayal"
  location = var.region

  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/hackathon/fireside:latest"
      
      ports {
        container_port = 8080
      }
      
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_key.secret_id
            version = "latest"
          }
        }
      }
      
      resources {
        limits = {
          cpu    = "2"
          memory = "1Gi"
        }
      }
      
      startup_probe {
        http_get {
          path = "/health"
        }
      }
    }
    
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    
    timeout = "3600s"  # 1 hour for long WebSocket connections
    
    session_affinity = true  # Keep WebSocket connections on same instance
  }
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
resource "google_firestore_database" "fireside" {
  project     = var.project_id
  name        = "(default)"
  location_id = "us-east1"
  type        = "FIRESTORE_NATIVE"
}

# Cloud Storage bucket
resource "google_storage_bucket" "assets" {
  name     = "${var.project_id}-fireside-assets"
  location = "US"
  
  uniform_bucket_level_access = true
}

# Artifact Registry
resource "google_artifact_registry_repository" "hackathon" {
  location      = var.region
  repository_id = "hackathon"
  format        = "DOCKER"
}
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
fireside-betrayal/
├── backend/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── narrator.py            # Narrator Agent definition + system prompt
│   │   ├── traitor.py             # Traitor Agent definition + persona template
│   │   └── game_master.py         # GameMasterAgent (BaseAgent subclass)
│   ├── game/
│   │   ├── __init__.py
│   │   ├── state_machine.py       # GamePhase enum + transition logic
│   │   ├── roles.py               # Role definitions + distribution tables
│   │   ├── rules.py               # Win conditions, night action resolution
│   │   └── characters.py          # Character name pools + backstory templates
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── narrator_tools.py      # get_game_state, advance_phase, etc.
│   │   └── traitor_tools.py       # plan_deflection, generate_alibi, etc.
│   ├── services/
│   │   ├── __init__.py
│   │   ├── firestore_client.py    # All Firestore read/write operations
│   │   └── storage_client.py      # Cloud Storage for scene images
│   ├── websocket/
│   │   ├── __init__.py
│   │   ├── game_session.py        # GameSession class
│   │   ├── protocol.py            # Message type definitions
│   │   └── audio_handler.py       # Audio encoding/decoding utilities
│   ├── server.py                  # FastAPI app, WebSocket endpoints, REST API
│   ├── config.py                  # Environment variables, constants
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── App.jsx
│   │   ├── pages/
│   │   │   ├── JoinPage.jsx
│   │   │   ├── GamePage.jsx
│   │   │   └── GameOverPage.jsx
│   │   ├── components/
│   │   │   ├── AudioPlayer.jsx
│   │   │   ├── NarratorPanel.jsx
│   │   │   ├── StoryLog.jsx
│   │   │   ├── PlayerGrid.jsx
│   │   │   ├── RoleCard.jsx
│   │   │   ├── ChatInput.jsx
│   │   │   └── VotePanel.jsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.js
│   │   │   ├── useAudioPlayer.js
│   │   │   └── useGameState.js
│   │   └── utils/
│   │       ├── audio.js           # PCM decode, AudioContext helpers
│   │       └── protocol.js        # Message type constants
│   ├── package.json
│   └── vite.config.js
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
├── cloudbuild.yaml
├── README.md
└── LICENSE (MIT)
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
    """Every game with 3+ players must have exactly 1 seer."""
    for n in range(3, 7):
        players = [f"player_{i}" for i in range(n)]
        result = await game_master.assign_roles("test_game", players)
        roles = list(result["player_roles"].values())
        assert roles.count("seer") == 1

async def test_vote_tie_no_elimination():
    """A tied vote should result in no elimination."""
    # Setup: 4 players, 2 vote for A, 2 vote for B
    result = await game_master.count_votes("test_game")
    assert result["result"] == "tie"
    assert result["eliminated"] is None

async def test_villagers_win_when_shapeshifter_eliminated():
    """Game ends with villager victory when AI character is voted out."""
    await firestore_client.eliminate_ai_character("test_game")
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

## 12.3.1 Procedural Character Generation (Sprint 4)

**Effort:** 2–3 hours | **Type:** Prompt engineering only

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

## 12.3.2 Narrator Vote Neutrality (Sprint 4)

**Effort:** 2–3 hours | **Type:** Prompt engineering + context isolation

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

## 12.3.3 Narrator Pacing Intelligence (Sprint 4)

**Effort:** 4–6 hours | **Type:** Server-side tracking + prompt engineering

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

## 12.3.4 Affective Dialog Input Signals (Sprint 4)

**Effort:** 3–4 hours | **Type:** Signal computation + prompt engineering

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

## 12.3.5 Minimum Satisfying Game Length (Sprint 4)

**Effort:** 1–2 hours | **Type:** Config change

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
    """Check if game should end. Returns None if game continues."""
    current_round = game_state["round"]
    player_count = game_state["total_players"]
    min_rounds = self.MINIMUM_ROUNDS.get(player_count, 3)
    
    alive_villagers = sum(1 for p in game_state["players"].values() 
                         if p["alive"] and p["role"] != "shapeshifter")
    ai_alive = game_state["ai_character"]["alive"]
    
    # Standard win conditions
    if not ai_alive:
        return {"winner": "villagers", "reason": "Shapeshifter eliminated"}
    if alive_villagers <= 1:
        return {"winner": "shapeshifter", "reason": "Village overwhelmed"}
    
    # Minimum round enforcement — game continues even if it could 
    # technically end (e.g., only 2 villagers left in round 1)
    # EXCEPTION: If shapeshifter is eliminated, game always ends immediately
    # This only prevents premature villager-loss endings
    if current_round < min_rounds and alive_villagers > 1:
        return None  # Game continues
    
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

## 12.3.6 In-Game Role Reminder (Sprint 5)

**Effort:** 3–4 hours | **Type:** Frontend only

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

## 12.3.7 Tutorial Mode (Sprint 5)

**Effort:** 1–2 days | **Type:** New route + scripted game flow

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

## 12.3.8 Conversation Structure for Large Groups (Sprint 5)

**Effort:** 4–6 hours | **Type:** Quick reaction + prompt engineering

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

## 12.3.9 Minimum Player Count Design (Sprint 5)

**Effort:** 3–4 hours | **Type:** Config + prompt adjustment

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

## 12.3.10 Random AI Alignment (Sprint 6)

**Effort:** 2–3 days | **Type:** New agent persona + role assignment change

```python
# New: Loyal AI Agent — cooperative version of the Traitor Agent

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

# Updated role assignment — AI can now draw any role
async def assign_roles_v2(self, game_id: str, player_ids: list[str], 
                           difficulty: str = "normal",
                           random_alignment: bool = False) -> dict:
    """Assign roles with optional random AI alignment."""
    player_count = len(player_ids)
    dist = self.get_distribution(player_count, difficulty)
    
    # Build role pool: all human roles + shapeshifter
    role_pool = []
    for role, count in dist.items():
        role_pool.extend([role] * count)
    role_pool.append("shapeshifter")
    
    if random_alignment:
        # AI draws a random role from the full pool
        random.shuffle(role_pool)
        ai_role = role_pool.pop()
        ai_is_traitor = (ai_role == "shapeshifter")
        
        # If AI didn't draw shapeshifter, assign shapeshifter to a 
        # "phantom" NPC that acts automatically (no human player)
        # OR: in random alignment mode, there may be NO shapeshifter 
        # among players — the AI is a loyal villager.
        # Decision: No shapeshifter if AI draws village role.
        # The game becomes "is the AI helping or hurting?" not "find the werewolf."
    else:
        # Default: AI is always the shapeshifter
        ai_role = "shapeshifter"
        ai_is_traitor = True
    
    # Select agent based on alignment
    ai_agent = traitor_agent if ai_is_traitor else loyal_ai_agent
    
    return {
        "ai_role": ai_role,
        "ai_is_traitor": ai_is_traitor,
        "ai_agent": ai_agent,
        "player_roles": dict(zip(player_ids, role_pool))
    }
```

**Firestore schema addition:**
```
games/{gameId}/
  ├── random_alignment: true | false
  ├── ai_character: { 
  │     name: "...", 
  │     role: "seer",           # Could be any role now
  │     is_traitor: false       # NEW — was the AI hostile or friendly?
  │   }
```

**Post-game reveal update:** The reveal must now show whether the AI was friend or foe:
`"The AI was Herbalist Mira — and was on YOUR side the whole time. Did you trust it?"`

---

## 12.3.11 Additional Roles — Bodyguard & Tanner (Sprint 6)

**Effort:** 1–2 days | **Type:** Role definitions + night action handlers

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

## 12.3.12 Dynamic AI Difficulty (Sprint 6)

**Effort:** 2–3 days | **Type:** Analytics + real-time prompt adjustment

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

## 12.3.13 Post-Game Timeline Interactive UX (Sprint 6)

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

## 12.3.14 Scene Image Generation (Sprint 7+)

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
        Style: Dark, painterly, firelit. Think campfire tales meets medieval woodcuts. 
        Muted earth tones with warm firelight accents. No text in the image.
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

---

## 12.3.15 Audio Recording/Playback (Sprint 7+)

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

## 12.3.16 Camera Vote Counting (Sprint 7+)

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

## 12.3.17 Narrator Style Presets (Sprint 7+)

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
    model="gemini-2.5-flash-native-audio-preview-12-2025",
    instruction=build_narrator_prompt(narrator_preset, BASE_NARRATOR_INSTRUCTION),
    tools=[get_game_state, advance_phase, narrate_event, inject_traitor_dialog],
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

## 12.3.18 Competitor Intelligence for AI (Sprint 7+)

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

# 13. PRD Cross-Reference & Compliance Matrix

| PRD Requirement | TDD Section | Implementation Status |
|---|---|---|
| Voice narration + interruptions (P0) | §3.1 Narrator Agent, §5 WebSocket Protocol | ✓ Specified |
| Role assignment system (P0) | §3.3 Game Master, §6 Data Model | ✓ Specified |
| Game state machine (P0) | §3.3 GamePhase enum + transitions | ✓ Specified |
| AI-as-player Traitor Agent (P0) | §3.2 Traitor Agent, §4.2–4.3 Traitor Tools + Night Orchestration | ✓ Specified |
| Multiplayer WebSocket hub (P0) | §5 WebSocket Protocol, §5.3 Server Implementation | ✓ Specified |
| Voting system (P0) | §3.3 count_votes, §5.1 VOTE message | ✓ Specified |
| Player phone UI (P0) | §8 Frontend Architecture | ✓ Specified |
| Spectator mode (eliminated players) | §5.2 Spectator Mode note | ✓ Specified |
| Spectator clues — P1 (one-word hints) | §5.2 Spectator Clues, §5.1 SpectatorClue message type | ✓ Specified |
| Narrator contextual reactivity — P1 | §3.1 Narrator Agent CONTEXTUAL REACTIVITY prompt section | ✓ Specified |
| Narrator quiet-player engagement — P1 | §3.1 Narrator Agent QUIET-PLAYER ENGAGEMENT prompt section | ✓ Specified |
| Narrator rule violation handling — P0 | §3.1 Narrator Agent RULE VIOLATION HANDLING prompt section | ✓ Specified |
| Narrator latency < 2s — P0 | §3.1 Audio Specifications, latency hard requirement | ✓ Specified |
| Role distribution by player count — P0 | §3.3 ROLE_DISTRIBUTION table (3-8 players), get_lobby_summary() | ✓ Specified |
| Night phase AI targeting (P0) | §4.2 select_night_target, §4.3 Night Phase Orchestration | ✓ Specified |
| Game-over reveal with AI reasoning | §4.3 handle_game_over | ✓ Specified |
| Session resumption (P1) | §7 Session Management | ✓ Specified |
| Frontend serving (single container) | §9.1 Docker Configuration | ✓ Specified |
| CORS configuration | §5.3 FastAPI app setup | ✓ Specified |
| Gemini model compliance | §3.1 model string | ✓ gemini-2.5-flash-native-audio-preview-12-2025 |
| ADK compliance | §3 All agents use google.adk | ✓ ADK Agents + run_live() |
| Cloud Run + Firestore + Storage | §9 Deployment, §6 Data Model | ✓ All three services |
| Automated deployment (bonus) | §9.2 Terraform, §9.3 Cloud Build | ✓ Specified |
| Public GitHub repo | §10 Repository Structure | ✓ MIT License |
| **P2 Features** | | |
| Procedural character generation (P2) | §12.3.1 | ✓ Specified |
| Narrator vote neutrality (P2) | §12.3.2 | ✓ Specified |
| Narrator pacing intelligence (P2) | §12.3.3 | ✓ Specified |
| Affective dialog input signals (P2) | §12.3.4 | ✓ Specified |
| Minimum satisfying game length (P2) | §12.3.5 | ✓ Specified |
| In-game role reminder (P2) | §12.3.6 | ✓ Specified |
| Tutorial mode (P2) | §12.3.7 | ✓ Specified |
| Conversation structure for large groups (P2) | §12.3.8 | ✓ Specified |
| Minimum player count design (P2) | §12.3.9 | ✓ Specified |
| Random AI alignment (P2) | §12.3.10 | ✓ Specified |
| Additional roles — Bodyguard, Tanner (P2) | §12.3.11 | ✓ Specified |
| Dynamic AI difficulty (P2) | §12.3.12 | ✓ Specified |
| Post-game timeline interactive UX (P2) | §12.3.13 | ✓ Specified |
| Scene image generation (P2) | §12.3.14 | ✓ Specified |
| Audio recording/playback (P2) | §12.3.15 | ✓ Specified |
| Camera vote counting (P2) | §12.3.16 | ✓ Specified |
| Narrator style presets (P2) | §12.3.17 | ✓ Specified |
| Competitor intelligence for AI (P2) | §12.3.18 | ✓ Specified |

---

# 14. Environment Variable Manifest

| Variable | Required | Description | Example |
|---|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | ✓ | GCP project ID | `fireside-hackathon-2026` |
| `GEMINI_API_KEY` | ✓ | Gemini API key (or use ADC) | `AIzaSy...` |
| `FIRESTORE_DATABASE` | | Firestore database ID (default: `(default)`) | `(default)` |
| `GCS_BUCKET` | | Cloud Storage bucket name (auto-derived from project if unset) | `fireside-hackathon-2026-fireside-assets` |
| `PORT` | | Server port (Cloud Run provides this) | `8080` |

```bash
# .env.example
GOOGLE_CLOUD_PROJECT=fireside-hackathon-2026
GEMINI_API_KEY=your-api-key-here
FIRESTORE_DATABASE=(default)
GCS_BUCKET=fireside-hackathon-2026-fireside-assets
PORT=8080
```

---

*Document created: February 21, 2026*
*Companion PRD: prd-fireside-betrayal.md v1.0*
*Hackathon deadline: March 16, 2026*
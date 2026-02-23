from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
from datetime import datetime, timezone
import uuid


def _utcnow() -> datetime:
    """Timezone-aware UTC datetime (replaces deprecated datetime.utcnow)."""
    return datetime.now(timezone.utc)


class Role(str, Enum):
    VILLAGER = "villager"
    SEER = "seer"
    HEALER = "healer"
    HUNTER = "hunter"
    DRUNK = "drunk"
    SHAPESHIFTER = "shapeshifter"
    BODYGUARD = "bodyguard"  # Absorbs shapeshifter kill targeting their protected player
    TANNER = "tanner"        # Solo win condition: get voted out by the village


class Phase(str, Enum):
    SETUP = "setup"
    NIGHT = "night"
    DAY_DISCUSSION = "day_discussion"
    DAY_VOTE = "day_vote"
    ELIMINATION = "elimination"
    GAME_OVER = "game_over"


class Difficulty(str, Enum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


class NarratorPreset(str, Enum):
    CLASSIC = "classic"    # Deep, dramatic fantasy narrator (default)
    CAMPFIRE = "campfire"  # Warm, folksy campfire storyteller
    HORROR = "horror"      # Slow, unsettling dread
    COMEDY = "comedy"      # Wry, self-aware, fourth-wall humor


class GameStatus(str, Enum):
    LOBBY = "lobby"         # waiting for players to join and ready up
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


# Role distribution keyed by TOTAL character count (human players + 1 AI Shapeshifter).
# e.g. key 3 = 2 humans + 1 AI, key 8 = 7 humans + 1 AI.
ROLE_DISTRIBUTION: Dict[int, List[str]] = {
    3: ["villager", "seer", "shapeshifter"],
    4: ["villager", "villager", "seer", "shapeshifter"],
    5: ["villager", "villager", "seer", "healer", "shapeshifter"],
    6: ["villager", "villager", "seer", "healer", "hunter", "shapeshifter"],
    7: ["villager", "villager", "seer", "healer", "hunter", "bodyguard", "shapeshifter"],
    8: ["villager", "villager", "seer", "healer", "hunter", "bodyguard", "tanner", "shapeshifter"],
}


class PlayerState(BaseModel):
    id: str
    name: str
    character_name: str = ""
    character_intro: str = ""
    personality_hook: str = ""  # Behavioral roleplay hint (e.g. "speaks in riddles")
    role: Optional[Role] = None
    alive: bool = True
    connected: bool = False
    ready: bool = False
    voted_for: Optional[str] = None
    night_action: Optional[str] = None
    session_handle: Optional[str] = None  # WebSocket session handle for reconnection
    joined_at: datetime = Field(default_factory=_utcnow)

    def to_public(self) -> Dict[str, Any]:
        """Safe representation — omits role (hidden during game)."""
        return {
            "id": self.id,
            "character_name": self.character_name,
            "alive": self.alive,
            "connected": self.connected,
            "ready": self.ready,
        }


class AICharacter(BaseModel):
    name: str
    intro: str
    role: Role = Role.SHAPESHIFTER
    alive: bool = True
    backstory: str = ""          # Behavioural roleplay hint (maps from personality_hook)
    personality_hook: str = ""   # Stored directly for API response consistency
    suspicion_level: float = 0.5  # 0.0 = invisible, 1.0 = obvious
    voted_for: Optional[str] = None  # AI's vote during DAY_VOTE phase
    is_traitor: bool = True      # False in random-alignment mode when AI drew a village role


class GameSession(BaseModel):
    handle: Optional[str] = None
    started_at: Optional[datetime] = None
    reconnect_count: int = 0


class GameState(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    status: GameStatus = GameStatus.LOBBY
    phase: Phase = Phase.SETUP
    round: int = 0
    difficulty: Difficulty = Difficulty.NORMAL
    host_player_id: str
    character_cast: List[str] = []
    generated_characters: List[Dict[str, Any]] = []  # Full cast data: name, intro, personality_hook
    ai_character: Optional[AICharacter] = None
    story_context: str = ""  # Running narrative context for the Narrator Agent
    random_alignment: bool = False  # §12.3.10: AI may draw a village role instead of shapeshifter
    narrator_preset: NarratorPreset = NarratorPreset.CLASSIC  # §12.3.17
    in_person_mode: bool = False  # §12.3.16: camera counts raised hands during vote
    session: GameSession = Field(default_factory=GameSession)
    created_at: datetime = Field(default_factory=_utcnow)


class GameEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str
    round: int
    phase: Phase
    actor: Optional[str] = None
    target: Optional[str] = None
    data: Dict[str, Any] = {}
    narration: Optional[str] = None
    visible_in_game: bool = True
    timestamp: datetime = Field(default_factory=_utcnow)


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    speaker: str           # character name (never real player name)
    speaker_player_id: Optional[str] = None  # None for narrator
    text: str
    source: str = "player"  # narrator | player | quick_reaction | system
    phase: Phase
    round: int
    timestamp: datetime = Field(default_factory=_utcnow)


# ── WebSocket message shapes ──────────────────────────────────────────────────

class WSMessage(BaseModel):
    type: str
    data: Dict[str, Any] = {}


# ── HTTP request/response models ──────────────────────────────────────────────

class CreateGameRequest(BaseModel):
    difficulty: Difficulty = Difficulty.NORMAL
    host_name: str = "Host"
    random_alignment: bool = False  # §12.3.10: AI may draw any role (including village)
    narrator_preset: NarratorPreset = NarratorPreset.CLASSIC  # §12.3.17
    in_person_mode: bool = False  # §12.3.16: camera counts raised hands during vote


class CreateGameResponse(BaseModel):
    game_id: str
    host_player_id: str


class JoinGameRequest(BaseModel):
    player_name: str


class JoinGameResponse(BaseModel):
    player_id: str
    game_id: str

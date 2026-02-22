from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime
import uuid


class Role(str, Enum):
    VILLAGER = "villager"
    SEER = "seer"
    HEALER = "healer"
    HUNTER = "hunter"
    DRUNK = "drunk"
    SHAPESHIFTER = "shapeshifter"


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


class PlayerState(BaseModel):
    id: str
    name: str
    character_name: str = ""
    character_intro: str = ""
    role: Optional[Role] = None
    alive: bool = True
    connected: bool = False
    ready: bool = False
    voted_for: Optional[str] = None
    night_action: Optional[str] = None
    joined_at: datetime = Field(default_factory=datetime.utcnow)

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
    backstory: str = ""
    suspicion_level: float = 0.5  # 0.0 = invisible, 1.0 = obvious


class GameSession(BaseModel):
    handle: Optional[str] = None
    started_at: Optional[datetime] = None
    reconnect_count: int = 0


class GameState(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    status: str = "lobby"  # lobby | in_progress | finished
    phase: Phase = Phase.SETUP
    round: int = 0
    difficulty: Difficulty = Difficulty.NORMAL
    host_player_id: str
    character_cast: List[str] = []
    ai_character: Optional[AICharacter] = None
    session: GameSession = Field(default_factory=GameSession)
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    speaker: str           # character name (never real player name)
    speaker_player_id: Optional[str] = None  # None for narrator
    text: str
    source: str = "player"  # narrator | player | quick_reaction | system
    phase: Phase
    round: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── WebSocket message shapes ──────────────────────────────────────────────────

class WSMessage(BaseModel):
    type: str
    data: Dict[str, Any] = {}


# ── HTTP request/response models ──────────────────────────────────────────────

class CreateGameRequest(BaseModel):
    difficulty: Difficulty = Difficulty.NORMAL
    host_name: str = "Host"


class CreateGameResponse(BaseModel):
    game_id: str
    host_player_id: str


class JoinGameRequest(BaseModel):
    player_name: str


class JoinGameResponse(BaseModel):
    player_id: str
    game_id: str

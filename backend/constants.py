"""
Centralized constants for Fireside: Betrayal backend.

All magic strings, timeout values, and repeated sets live here.
Import from this module instead of using raw strings.
"""

from models.game import Phase, Role


# ── WebSocket Message Types ──────────────────────────────────────────────────

class WSInbound:
    """Message types sent from client → server."""
    PING = "ping"
    SYNC = "sync"
    READY = "ready"
    MESSAGE = "message"
    VOTE = "vote"
    NIGHT_ACTION = "night_action"
    HUNTER_REVENGE = "hunter_revenge"
    QUICK_REACTION = "quick_reaction"
    SPECTATOR_CLUE = "spectator_clue"
    GHOST_MESSAGE = "ghost_message"
    HAUNT_ACTION = "haunt_action"
    RAISE_HAND = "raise_hand"
    IN_PERSON_VOTE_FRAME = "in_person_vote_frame"
    START_SPEAKING = "start_speaking"
    STOP_SPEAKING = "stop_speaking"


class WSOutbound:
    """Message types sent from server → client."""
    PONG = "pong"
    SYNC_ACK = "sync_ack"
    CONNECTED = "connected"
    PHASE_CHANGE = "phase_change"
    ROLE = "role"
    SPEAKER_CHANGED = "speaker_changed"
    ELIMINATION = "elimination"
    GAME_OVER = "game_over"
    TRANSCRIPT = "transcript"
    AUDIO = "audio"
    SCENE_IMAGE = "scene_image"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    PLAYER_READY = "player_ready"
    ERROR = "error"
    TIMER_START = "timer_start"
    VOTE_UPDATE = "vote_update"
    NIGHT_ACTION_RECEIVED = "night_action_received"
    SEER_RESULT = "seer_result"
    HUNTER_REVENGE = "hunter_revenge"
    CLUE_ACCEPTED = "clue_accepted"
    HAUNT_CONFIRMED = "haunt_confirmed"
    GHOST_MESSAGE = "ghost_message"
    HAND_RAISED = "hand_raised"
    HAND_RAISE_ACK = "hand_raise_ack"
    CAMERA_VOTE_RESULT = "camera_vote_result"
    CAMERA_VOTE_FALLBACK = "camera_vote_fallback"
    HIGHLIGHT_REEL = "highlight_reel"


# ── Firestore Event Types ────────────────────────────────────────────────────

class EventType:
    """Event type strings stored in GameEvent.type."""
    NIGHT_TARGET = "night_target"
    NIGHT_KILL_ATTEMPT = "night_kill_attempt"
    NIGHT_HEAL = "night_heal"
    NIGHT_INVESTIGATION = "night_investigation"
    AI_SEER_RESULT = "ai_seer_result"
    BODYGUARD_SACRIFICE = "bodyguard_sacrifice"
    ELIMINATION = "elimination"
    HUNTER_REVENGE = "hunter_revenge"
    GHOST_ACCUSE = "ghost_accuse"
    DEFLECTION_ACCUSATION = "deflection_accusation"


# ── Narrator Event Types ─────────────────────────────────────────────────────

class NarratorEvent:
    """Event types passed to narrator.send_phase_event()."""
    GAME_STARTED = "game_started"
    NIGHT_RESOLVED = "night_resolved"
    ELIMINATION = "elimination"
    GAME_OVER = "game_over"
    NO_ELIMINATION = "no_elimination"
    HUNTER_REVENGE = "hunter_revenge"
    SEANCE_TRIGGERED = "seance_triggered"
    GHOST_ACCUSATIONS = "ghost_accusations"
    SPECTATOR_CLUE = "spectator_clue"
    HAND_RAISED = "hand_raised"


# ── Error Codes ──────────────────────────────────────────────────────────────

class ErrorCode:
    """Error code strings sent in WS error messages."""
    PARSE_ERROR = "PARSE_ERROR"
    SERVER_ERROR = "SERVER_ERROR"
    WRONG_PHASE = "WRONG_PHASE"
    SELF_VOTE = "SELF_VOTE"
    INVALID_TARGET = "INVALID_TARGET"
    INVALID_SELF_TARGET = "INVALID_SELF_TARGET"
    INVALID_CLUE = "INVALID_CLUE"
    NARRATOR_ERROR = "NARRATOR_ERROR"


# ── Firestore Field Paths ────────────────────────────────────────────────────

class FSField:
    """Firestore document field paths used in updates."""
    # Game document
    PHASE = "phase"
    ROUND = "round"
    STATUS = "status"
    WINNER = "winner"
    SEANCE_USED = "seance_used"
    AI_CHARACTER = "ai_character"
    AI_CHARACTER_ALIVE = "ai_character.alive"
    AI_CHARACTER_VOTED_FOR = "ai_character.voted_for"
    AI_CHARACTER_2 = "ai_character_2"
    AI_CHARACTER_2_ALIVE = "ai_character_2.alive"
    AI_CHARACTER_2_VOTED_FOR = "ai_character_2.voted_for"
    VOTE_RESOLVING = "vote_resolving"
    NIGHT_RESOLVING = "night_resolving"

    # Player document
    CONNECTED = "connected"
    READY = "ready"
    ALIVE = "alive"
    VOTED_FOR = "voted_for"
    NIGHT_ACTION = "night_action"

    # Collections
    GAMES = "games"
    PLAYERS = "players"
    EVENTS = "events"
    CHAT = "chat"
    GHOST_MESSAGES = "ghost_messages"


# ── Chat Message Sources ─────────────────────────────────────────────────────

class ChatSource:
    """Source field values for ChatMessage."""
    PLAYER = "player"
    NARRATOR = "narrator"
    QUICK_REACTION = "quick_reaction"
    SYSTEM = "system"
    AI_CHARACTER = "ai_character"


# ── Timeout Constants (seconds) ──────────────────────────────────────────────

GHOST_MSG_COOLDOWN = 2.0
MIN_DISCUSSION_SECONDS = 45
MAX_SPEAKING_SECONDS = 30
NIGHT_ACTION_TIMEOUT = 45
TIMER_FALLBACK_DELAY = 15
SEANCE_DURATION = 45
VOTE_TIMEOUT_SECONDS = 60

# Narrator safety timeouts per phase
NARRATOR_TIMEOUT_DELAYS = {
    Phase.NIGHT: 60,
    Phase.ELIMINATION: 60,
}

# Discussion timeout by player count (seconds)
DISCUSSION_TIMEOUT_BY_PLAYERS = {
    7: 240,   # 7+ players: 4 min
    5: 180,   # 5-6 players: 3 min
    3: 120,   # 3-4 players: 2 min
}


# ── Role Sets ────────────────────────────────────────────────────────────────

# Roles that have a night action
NIGHT_ROLE_SET = frozenset({
    Role.SEER,
    Role.HEALER,
    Role.DRUNK,
    Role.BODYGUARD,
    Role.SHAPESHIFTER,
})

# AI night roles (text-based, no human UI)
AI_NIGHT_ROLES = frozenset({"seer", "healer", "bodyguard"})


# ── Audio Constants ──────────────────────────────────────────────────────────

AUDIO_SAMPLE_RATE_OUTPUT = 24000   # Hz, narrator output
AUDIO_SAMPLE_RATE_INPUT = 16000    # Hz, player mic input
AUDIO_MIME_INPUT = "audio/pcm;rate=16000"
MAX_PCM_BYTES = 480_000            # ~10 seconds at 24kHz 16-bit mono
MAX_STORED_SEGMENTS = 10


# ── Audio Segment Priority ───────────────────────────────────────────────────

AUDIO_SEGMENT_PRIORITY = {
    "elimination": 0,
    "game_over": 1,
    "night_resolved": 2,
    "night": 3,
    "no_elimination": 4,
    "day_discussion": 5,
    "game_started": 6,
}

AUDIO_SEGMENT_SKIP = frozenset({
    "hand_raised",
    "spectator_clue",
    "ghost_accusations",
})

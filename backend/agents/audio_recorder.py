"""
Audio Recorder — §12.3.15

Records narrator PCM audio stream, segmented by game events.
Stores WAV data in memory (no GCS for hackathon).

Integration:
  - narrator_agent._receiver feeds raw PCM bytes via get_recorder().append_audio()
  - narrator_manager.send_phase_event calls get_recorder().start_segment()
    before queuing each event prompt so narration is grouped by phase.
  - _end_game calls get_recorder().get_highlight_reel() to build the top-5
    reel, broadcasts it as a 'highlight_reel' WS message, then clear_recorder().

Segment size cap: 10s × 24000 Hz × 2 bytes/sample = 480 KB per segment.
Max stored segments: 10 (ring-buffer style, oldest dropped first).
"""
import base64
import logging
import struct
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

SAMPLE_RATE = 24000          # Gemini Live API narrator output
MAX_PCM_BYTES = 480_000      # ~10 seconds of 16-bit mono at 24 kHz
MAX_STORED_SEGMENTS = 10

# Highlight-reel priority — lower = more interesting
_PRIORITY = {
    "elimination": 0,
    "game_over": 1,
    "night_resolved": 2,
    "night": 3,
    "no_elimination": 4,   # deadlocked vote is more dramatic than routine discussion
    "day_discussion": 5,
    "game_started": 6,
}


def _pcm_to_wav(pcm_data: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw 16-bit LE mono PCM bytes in a minimal RIFF/WAV container."""
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(pcm_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, num_channels, sample_rate,
        byte_rate, block_align, bits_per_sample,
        b"data", data_size,
    )
    return header + pcm_data


def segment_description(event_type: str, data: Dict[str, Any]) -> str:
    """Human-readable segment label shown in the post-game timeline."""
    round_num = data.get("round", 0)
    round_str = f" (Round {round_num})" if round_num else ""
    char = data.get("characterName", "")
    labels: Dict[str, str] = {
        "game_started": "The game begins",
        "night": f"Night falls{round_str}",
        "night_resolved": f"Dawn breaks{round_str}",
        "day_discussion": f"Village discussion{round_str}",
        "elimination": f"Elimination of {char}{round_str}" if char else f"Elimination{round_str}",
        "no_elimination": f"No elimination{round_str}",
        "game_over": "The game ends",
    }
    return labels.get(event_type, event_type.replace("_", " ").title() + round_str)


class AudioRecorder:
    """Per-game audio recorder. Thread-unsafe but fine for single-game asyncio."""

    def __init__(self, game_id: str):
        self.game_id = game_id
        self._segments: List[Dict[str, Any]] = []
        self._current_event: str = "game_started"
        self._current_description: str = "The game begins"
        self._current_round: int = 0
        self._current_pcm: bytearray = bytearray()

    def start_segment(
        self, event_type: str, description: str, round_num: int = 0
    ) -> None:
        """Flush current segment and begin a new one for this phase event."""
        self._flush()
        self._current_event = event_type
        self._current_description = description
        self._current_round = round_num
        self._current_pcm = bytearray()

    def append_audio(self, pcm_data: bytes) -> None:
        """Accumulate raw PCM bytes into the current segment (capped at MAX_PCM_BYTES)."""
        remaining = MAX_PCM_BYTES - len(self._current_pcm)
        if remaining > 0 and pcm_data:
            self._current_pcm.extend(pcm_data[:remaining])

    def _flush(self) -> None:
        """Finalise the current segment if it contains any audio."""
        if not self._current_pcm:
            return
        self._segments.append({
            "event_type": self._current_event,
            "description": self._current_description,
            "round": self._current_round,
            "wav_bytes": _pcm_to_wav(bytes(self._current_pcm)),
        })
        # Keep a rolling window — oldest segments dropped first
        if len(self._segments) > MAX_STORED_SEGMENTS:
            self._segments.pop(0)
        self._current_pcm = bytearray()

    def get_highlight_reel(self) -> List[Dict[str, Any]]:
        """
        Flush then return up to 5 segments ranked by dramatic priority.
        Each entry: { event_type, description, round, audio_b64 }
        """
        self._flush()
        if not self._segments:
            return []

        sorted_segs = sorted(
            self._segments,
            key=lambda s: (_PRIORITY.get(s["event_type"], 99), -s["round"]),
        )
        reel = []
        for seg in sorted_segs[:5]:
            reel.append({
                "event_type": seg["event_type"],
                "description": seg["description"],
                "round": seg["round"],
                "audio_b64": base64.b64encode(seg["wav_bytes"]).decode("utf-8"),
            })
        return reel


# ── Per-game registry ──────────────────────────────────────────────────────────

_recorders: Dict[str, AudioRecorder] = {}


def get_recorder(game_id: str) -> AudioRecorder:
    """Return (or lazily create) the AudioRecorder for a game."""
    if game_id not in _recorders:
        _recorders[game_id] = AudioRecorder(game_id)
    return _recorders[game_id]


def clear_recorder(game_id: str) -> None:
    """Free in-memory audio data after the game has ended."""
    _recorders.pop(game_id, None)

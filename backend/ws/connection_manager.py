"""
WebSocket ConnectionManager — tracks active connections, sends messages, and
provides high-level game event broadcast helpers.

The module-level `manager` singleton is THE source of truth for all
WebSocket connections in the process.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any

from fastapi import WebSocket

from models.game import Phase, Role
from utils.tasks import safe_create_task, cancel_player_tasks

logger = logging.getLogger(__name__)


# ── AI character helpers (supports 1 or 2 AI characters) ─────────────────────
# Canonical implementations live in utils.game_utils; re-exported here for
# backward compatibility with existing imports across the codebase.

from utils.game_utils import all_ai_chars as _all_ai_chars  # noqa: E402
from utils.game_utils import alive_ai_names as _alive_ai_names  # noqa: E402


# ── Role description cards (sent privately at game start) ─────────────────────

ROLE_DESCRIPTIONS: Dict[str, str] = {
    "villager": (
        "You are a Villager of Thornwood. Survive the night and identify "
        "the Shapeshifter hiding among you. Vote wisely during the day."
    ),
    "seer": (
        "You are the Seer. Each night you may investigate one character "
        "to learn whether they are the Shapeshifter."
    ),
    "healer": (
        "You are the Healer. Each night you may protect one character "
        "from elimination. You cannot protect yourself."
    ),
    "hunter": (
        "You are the Hunter. If you are eliminated — by vote or by night — "
        "you immediately drag one other character to their doom."
    ),
    "drunk": (
        "You believe you are the Seer, but something is wrong with your visions. "
        "Your investigations always return the WRONG answer."
    ),
    "shapeshifter": (
        "You are the Shapeshifter. Blend in, sow suspicion, and eliminate the "
        "villagers one by one before they unmask you."
    ),
    "bodyguard": (
        "You are the Bodyguard. Choose a player to protect each night. "
        "If they are targeted by the Shapeshifter, you die in their place."
    ),
    "tanner": (
        "You are the Tanner. You win if the village votes to eliminate you. "
        "Act suspicious — but not too suspicious. You have no night action."
    ),
}


# ── Connection Manager ─────────────────────────────────────────────────────────

class ConnectionManager:
    """
    Tracks active WebSocket connections per game.
    Safe for asyncio single-threaded event loop (no extra locking needed).
    """

    def __init__(self):
        # {game_id: {player_id: WebSocket}}
        self._games: Dict[str, Dict[str, WebSocket]] = {}
        # Reliable delivery: per-game monotonic sequence counter + event buffer
        self._seq: Dict[str, int] = {}
        self._event_log: Dict[str, list] = {}
        # Per-player outgoing queues: priority (control) + audio
        self._ctrl_queues: Dict[str, Dict[str, asyncio.Queue]] = {}
        self._audio_queues: Dict[str, Dict[str, asyncio.Queue]] = {}
        self._sender_tasks: Dict[str, Dict[str, asyncio.Task]] = {}

    # ── Per-player sender ─────────────────────────────────────────────────────

    async def _player_sender(self, game_id: str, player_id: str, ws: WebSocket) -> None:
        """Drain control + audio queues for one player. Control messages have priority."""
        ctrl_q = self._ctrl_queues.get(game_id, {}).get(player_id)
        audio_q = self._audio_queues.get(game_id, {}).get(player_id)
        if not ctrl_q or not audio_q:
            return
        try:
            while True:
                # Priority: drain all pending control messages first
                while not ctrl_q.empty():
                    msg = ctrl_q.get_nowait()
                    await ws.send_json(msg)

                # Then try one audio chunk (non-blocking), fall back to waiting on either
                try:
                    msg = audio_q.get_nowait()
                    await ws.send_json(msg)
                except asyncio.QueueEmpty:
                    # Nothing in either queue — wait for the next item from either
                    ctrl_task = asyncio.ensure_future(ctrl_q.get())
                    audio_task = asyncio.ensure_future(audio_q.get())
                    try:
                        done, pending = await asyncio.wait(
                            {ctrl_task, audio_task}, return_when=asyncio.FIRST_COMPLETED
                        )
                    except asyncio.CancelledError:
                        ctrl_task.cancel()
                        audio_task.cancel()
                        raise
                    for t in pending:
                        t.cancel()
                    for t in done:
                        msg = t.result()
                        await ws.send_json(msg)
        except asyncio.CancelledError:
            pass  # Task cancelled on disconnect — clean exit
        except Exception:
            logger.warning("Player sender error for %s/%s", game_id, player_id, exc_info=True)

    # ── Reliable delivery helpers ─────────────────────────────────────────────

    def _next_seq(self, game_id: str) -> int:
        self._seq[game_id] = self._seq.get(game_id, 0) + 1
        return self._seq[game_id]

    def _buffer_event(self, game_id: str, seq: int, msg: Dict, target: Optional[str] = None) -> None:
        buf = self._event_log.setdefault(game_id, [])
        entry: Dict[str, Any] = {"seq": seq, "msg": msg}
        if target:
            entry["target"] = target
        buf.append(entry)
        if len(buf) > 100:
            self._event_log[game_id] = buf[-100:]

    def get_events_since(self, game_id: str, last_seq: int) -> list:
        """Return all buffered events with seq > last_seq."""
        return [e for e in self._event_log.get(game_id, []) if e["seq"] > last_seq]

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def connect(self, game_id: str, player_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._games.setdefault(game_id, {})[player_id] = ws
        # Set up per-player send queues and start sender task
        self._ctrl_queues.setdefault(game_id, {})[player_id] = asyncio.Queue()
        self._audio_queues.setdefault(game_id, {})[player_id] = asyncio.Queue(maxsize=256)
        self._sender_tasks.setdefault(game_id, {})[player_id] = safe_create_task(
            self._player_sender(game_id, player_id, ws),
            name=f"sender-{game_id[:8]}-{player_id[:8]}",
            game_id=game_id,
            player_id=player_id,
        )
        logger.info(
            f"[{game_id}] {player_id} connected ({self.count(game_id)} total)"
        )

    def disconnect(self, game_id: str, player_id: str, ws: WebSocket = None) -> None:
        game_conns = self._games.get(game_id, {})
        # Only remove if the disconnecting WS is the CURRENT one for this player.
        if ws is not None and game_conns.get(player_id) is not ws:
            return  # stale connection closing — leave the current one alone
        game_conns.pop(player_id, None)
        # Cancel any pending tasks (speaker timeout, night action timeout, etc.)
        cancel_player_tasks(game_id, player_id)
        # Clean up sender task and queues
        task = self._sender_tasks.get(game_id, {}).pop(player_id, None)
        if task:
            task.cancel()
        self._ctrl_queues.get(game_id, {}).pop(player_id, None)
        self._audio_queues.get(game_id, {}).pop(player_id, None)
        if not game_conns:
            self._games.pop(game_id, None)
            self._sender_tasks.pop(game_id, None)
            self._ctrl_queues.pop(game_id, None)
            self._audio_queues.pop(game_id, None)

    def count(self, game_id: str) -> int:
        return len(self._games.get(game_id, {}))

    def is_connected(self, game_id: str, player_id: str) -> bool:
        return player_id in self._games.get(game_id, {})

    def is_current_ws(self, game_id: str, player_id: str, ws: WebSocket) -> bool:
        """Check if the given WS is the current active connection for this player."""
        return self._games.get(game_id, {}).get(player_id) is ws

    # ── Sending ────────────────────────────────────────────────────────────────

    async def send_to(
        self, game_id: str, player_id: str, message: Dict
    ) -> None:
        """Send a private message to a single player (via control queue)."""
        ctrl_q = self._ctrl_queues.get(game_id, {}).get(player_id)
        if ctrl_q is not None:
            ctrl_q.put_nowait(message)
        # Fallback: no queue yet (pre-connect), send directly
        elif (ws := self._games.get(game_id, {}).get(player_id)):
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.warning(
                    f"[{game_id}] send_to {player_id} failed: {exc}"
                )
                self.disconnect(game_id, player_id)

    async def send_to_reliable(
        self, game_id: str, player_id: str, message: Dict
    ) -> None:
        """Send a private message with seq number, buffered for replay."""
        seq = self._next_seq(game_id)
        message = {**message, "seq": seq}
        self._buffer_event(game_id, seq, message, target=player_id)
        await self.send_to(game_id, player_id, message)

    async def broadcast(
        self,
        game_id: str,
        message: Dict,
        exclude: Optional[str] = None,
        reliable: bool = False,
    ) -> None:
        """Broadcast a message to all connected players via control queues (non-blocking)."""
        if reliable:
            seq = self._next_seq(game_id)
            message = {**message, "seq": seq}
            self._buffer_event(game_id, seq, message)
        for pid in list(self._games.get(game_id, {})):
            if pid == exclude:
                continue
            ctrl_q = self._ctrl_queues.get(game_id, {}).get(pid)
            if ctrl_q is not None:
                ctrl_q.put_nowait(message)

    # ── High-level game event helpers ──────────────────────────────────────────

    async def broadcast_game_start(
        self, game_id: str, assignments: list, opening_scene_b64: str = None
    ) -> None:
        """
        Called by game_router after role assignment.
        Broadcasts phase_change -> NIGHT, then sends private role cards.
        If opening_scene_b64 is provided, sends it immediately (pre-generated).
        All messages are reliable (sequenced + buffered for replay).
        """
        pids = list(self._games.get(game_id, {}).keys())
        logger.info(f"[{game_id}] broadcast_game_start -> {len(pids)} players: {pids}")
        # Fetch game data for AI character list in the phase_change broadcast
        from services.firestore_service import get_firestore_service
        fs = get_firestore_service()
        game = await fs.get_game(game_id)
        ai_chars = _all_ai_chars(game) if game else []
        ai_characters_list = [{"name": c.name, "alive": c.alive} for c in ai_chars]

        await self.broadcast(game_id, {
            "type": "phase_change",
            "phase": Phase.NIGHT.value,
            "round": 1,
            "aiCharacters": ai_characters_list,
            "aiCharacter": ai_characters_list[0] if len(ai_characters_list) > 0 else None,
            "aiCharacter2": ai_characters_list[1] if len(ai_characters_list) > 1 else None,
        }, reliable=True)
        for a in assignments:
            await self.send_to_reliable(game_id, a["player_id"], {
                "type": "role",
                "role": a["role"],
                "characterName": a["character_name"],
                "characterIntro": a["character_intro"],
                "description": ROLE_DESCRIPTIONS.get(a["role"], ""),
            })
        # Send per-player night target candidates (seer/healer/shapeshifter need these)
        await self._send_candidates(game_id, Phase.NIGHT)

        # Schedule narrator safety timeout for the initial NIGHT phase
        from ws.phase_timers import _schedule_narrator_timeout, _schedule_timer_fallback
        _schedule_narrator_timeout(game_id, Phase.NIGHT)
        # Schedule safety fallback for initial NIGHT
        _schedule_timer_fallback(game_id)

        # Send pre-generated opening scene image if available;
        # otherwise fire-and-forget generation (fallback for timeout case)
        if opening_scene_b64:
            await self.broadcast_scene_image(game_id, opening_scene_b64, "game_started")
            logger.info(f"[{game_id}] Pre-generated scene image sent with game start")
        else:
            from agents.scene_agent import trigger_scene_image
            safe_create_task(
                trigger_scene_image(game_id, "game_started"),
                name=f"scene-game_started-{game_id}",
                game_id=game_id,
            )

    async def broadcast_phase_change(
        self, game_id: str, phase: Phase, round: Optional[int] = None,
        game=None, alive_players=None,
    ) -> None:
        from services.firestore_service import get_firestore_service
        fs = get_firestore_service()

        # Use pre-fetched game data if provided, otherwise fetch from Firestore
        if game is None:
            game = await fs.get_game(game_id)
        if round is None:
            round = game.round if game else 0

        # Include ALL players (alive + dead) so roster shows dead icons
        all_players = await fs.get_all_players(game_id)

        # Build full AI character list for the broadcast (Issue 10: always include)
        ai_chars = _all_ai_chars(game) if game else []
        ai_characters_list = [{"name": c.name, "alive": c.alive} for c in ai_chars]

        msg: dict = {
            "type": "phase_change",
            "phase": phase.value,
            "round": round,
            "players": [p.to_public() for p in all_players],
            "aiCharacters": ai_characters_list,
            # Keep legacy fields for backward compat
            "aiCharacter": ai_characters_list[0] if len(ai_characters_list) > 0 else None,
            "aiCharacter2": ai_characters_list[1] if len(ai_characters_list) > 1 else None,
        }

        await self.broadcast(game_id, msg, reliable=True)

        # Release push-to-talk speaker lock on any phase transition
        from ws.message_handlers import _current_speaker
        if _current_speaker.get(game_id):
            _current_speaker[game_id] = None
            await self.broadcast(game_id, {
                "type": "speaker_changed",
                "speaker": None,
                "playerId": None,
            })

        # Send per-player candidate lists for night/vote phases.
        # Pass pre-fetched data to avoid duplicate Firestore reads (Issue 9).
        if phase in (Phase.NIGHT, Phase.DAY_VOTE):
            await self._send_candidates(game_id, phase, game=game, alive_players=alive_players)

        # Schedule narrator safety timeout for non-discussion narrator-controlled phases
        from ws.phase_timers import (
            _NARRATOR_TIMEOUT_DELAYS, _schedule_narrator_timeout,
            _schedule_timer_fallback,
        )
        if phase in _NARRATOR_TIMEOUT_DELAYS:
            _schedule_narrator_timeout(game_id, phase)

        # Schedule safety fallback — auto-start timers if narrator doesn't call
        # start_phase_timer within 15 seconds
        if phase in (Phase.NIGHT, Phase.DAY_DISCUSSION, Phase.DAY_VOTE):
            _schedule_timer_fallback(game_id)

    async def _send_candidates(self, game_id: str, phase: Phase,
                               game=None, alive_players=None) -> None:
        """Send per-player candidate lists for night actions or voting.
        Each player gets a list that excludes themselves.
        Accepts pre-fetched game/alive_players to avoid duplicate Firestore reads."""
        from services.firestore_service import get_firestore_service
        fs = get_firestore_service()
        if alive_players is None:
            alive_players = await fs.get_alive_players(game_id)
        if game is None:
            game = await fs.get_game(game_id)

        # Build full candidate pool: alive human character names + alive AI(s)
        all_names = [p.character_name for p in alive_players if p.character_name]
        if game:
            all_names.extend(_alive_ai_names(game))

        msg_type = "night_targets" if phase == Phase.NIGHT else "vote_candidates"

        for player in alive_players:
            # Exclude self from the candidate list
            candidates = [n for n in all_names if n != player.character_name]
            await self.send_to(game_id, player.id, {
                "type": msg_type,
                "candidates": candidates,
            })

        # Trigger atmospheric scene image for the new phase.
        # Skip first NIGHT (round 1) — the "game_started" image is already showing.
        _scene_map = {
            Phase.NIGHT: "night",
            Phase.DAY_DISCUSSION: "day_discussion",
            Phase.ELIMINATION: "elimination",
        }
        skip_scene = (phase == Phase.NIGHT and game and game.round <= 1)
        if phase in _scene_map and not skip_scene:
            from agents.scene_agent import trigger_scene_image
            safe_create_task(
                trigger_scene_image(game_id, _scene_map[phase]),
                name=f"scene-{_scene_map[phase]}-{game_id}",
                game_id=game_id,
            )

    async def broadcast_elimination(
        self,
        game_id: str,
        character_name: str,
        was_traitor: bool,
        role: Optional[str],
        needs_hunter_revenge: bool = False,
        tally: Optional[Dict] = None,
        individual_votes: Optional[Dict] = None,
        is_tie: bool = False,
    ) -> None:
        await self.broadcast(game_id, {
            "type": "elimination",
            "characterName": character_name,
            "wasTraitor": was_traitor,
            "role": role,
            "triggerHunterRevenge": needs_hunter_revenge,
            "tally": tally or {},
            "individualVotes": individual_votes or {},
            "isTie": is_tie,
        }, reliable=True)

    async def broadcast_game_over(
        self,
        game_id: str,
        winner: str,
        reason: str,
        character_reveals: list,
        timeline: Optional[list] = None,
    ) -> None:
        await self.broadcast(game_id, {
            "type": "game_over",
            "winner": winner,
            "reason": reason,
            "characterReveals": character_reveals,
            "timeline": timeline or [],
        }, reliable=True)

    async def broadcast_transcript(
        self,
        game_id: str,
        speaker: str,
        text: str,
        source: str = "player",
        phase: Optional[str] = None,
        round_num: Optional[int] = None,
    ) -> None:
        """Broadcast a dialogue line (player chat or narrator speech)."""
        msg: Dict[str, Any] = {
            "type": "transcript",
            "speaker": speaker,
            "text": text,
            "source": source,
        }
        if phase:
            msg["phase"] = phase
        if round_num is not None:
            msg["round"] = round_num
        await self.broadcast(game_id, msg)

    async def broadcast_audio(
        self, game_id: str, pcm_base64: str
    ) -> None:
        """Broadcast a PCM audio chunk via audio queues (drops oldest if full)."""
        msg = {"type": "audio", "data": pcm_base64, "sampleRate": 24000}
        for pid in list(self._games.get(game_id, {})):
            audio_q = self._audio_queues.get(game_id, {}).get(pid)
            if audio_q is not None:
                try:
                    audio_q.put_nowait(msg)
                except asyncio.QueueFull:
                    # Drop oldest audio chunk, add new one
                    try:
                        audio_q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        audio_q.put_nowait(msg)
                    except asyncio.QueueFull:
                        pass

    async def broadcast_scene_image(
        self, game_id: str, image_b64: str, scene_key: str
    ) -> None:
        """Broadcast a base64-encoded PNG scene illustration."""
        await self.broadcast(game_id, {
            "type": "scene_image",
            "data": image_b64,
            "sceneKey": scene_key,
        })


# Module-level singleton — imported by game_router, narrator, and traitor agent
manager = ConnectionManager()

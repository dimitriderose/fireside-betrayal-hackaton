"""
Game HTTP endpoints.

Routes:
  POST /api/games                         — Create game + register host as first player
  POST /api/games/{game_id}/join          — Player joins the lobby
  GET  /api/games/{game_id}               — Public game state (roles hidden)
  POST /api/games/{game_id}/start         — Host starts game (triggers role assignment)
  GET  /api/games/{game_id}/events        — Event log (visible only, or all post-game)
  GET  /api/games/{game_id}/result        — Post-game result (winner, reveals, timeline)
"""
import asyncio
import uuid
import logging
import re
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from models.game import (
    CreateGameRequest, CreateGameResponse,
    JoinGameRequest, JoinGameResponse,
    GameStatus,
)
from services.firestore_service import get_firestore_service
from agents.role_assigner import role_assigner
from agents.game_master import game_master
from agents.narrator_agent import narrator_manager, build_phase_prompt
from agents.traitor_agent import trigger_all_night_actions
from routers.ws_router import manager as ws_manager

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

router = APIRouter(tags=["games"])
limiter = Limiter(key_func=get_remote_address)

# Cache for pre-generated scene images: game_id -> base64 string
_scene_cache: dict[str, str] = {}


async def _pregenerate_scene(game_id: str) -> None:
    """Generate the opening scene image in the background during lobby."""
    from agents.scene_agent import generate_scene_image
    try:
        image_b64 = await generate_scene_image("game_started")
        if image_b64:
            _scene_cache[game_id] = image_b64
            logger.info("[%s] Opening scene pre-generated and cached", game_id)
    except Exception:
        logger.warning("[%s] Scene pre-generation failed", game_id, exc_info=True)

# Game code format: 8-char uppercase hex (see GameState.id default_factory)
_GAME_CODE_RE = re.compile(r"^[A-Z0-9]{8}$")


async def verify_player_access(game_id: str, player_id: Optional[str]) -> None:
    """Check that the player_id belongs to this game. Raises 403 if not.

    If player_id is not provided, access is allowed (the frontend doesn't
    always have it available, e.g. on initial page load from a share link).
    The WebSocket endpoint has its own player validation.
    """
    if not player_id:
        return  # Allow unauthenticated reads — WS endpoint enforces real auth

    fs = get_firestore_service()
    player = await fs.get_player(game_id, player_id)
    if not player:
        raise HTTPException(
            status_code=403,
            detail="You are not a participant in this game",
        )

@router.post("/games", response_model=CreateGameResponse, status_code=201)
@limiter.limit("5/minute")
async def create_game(request: Request, body: CreateGameRequest):
    """Create a new game and register the host as the first player."""
    fs = get_firestore_service()
    host_player_id = str(uuid.uuid4())
    game = await fs.create_game(
        host_player_id=host_player_id,
        difficulty=body.difficulty.value,
        random_alignment=body.random_alignment,
        narrator_preset=body.narrator_preset.value,
        in_person_mode=body.in_person_mode,
    )
    await fs.add_player(game.id, host_player_id, body.host_name)
    logger.info(f"Game {game.id} created by host {host_player_id} ({body.host_name})")

    # Pre-generate opening scene image in background while players join the lobby.
    # By the time host clicks "Start Game", the image is likely already cached.
    from utils.tasks import safe_create_task
    safe_create_task(
        _pregenerate_scene(game.id),
        name=f"scene-pregen-{game.id[:8]}",
        game_id=game.id,
    )

    return CreateGameResponse(game_id=game.id, host_player_id=host_player_id)


@router.post("/games/{game_id}/join", response_model=JoinGameResponse, status_code=200)
@limiter.limit("10/minute")
async def join_game(request: Request, game_id: str, body: JoinGameRequest):
    """Add a player to the lobby. Rejected if the game has already started."""
    # Validate game code format
    if not _GAME_CODE_RE.match(game_id):
        raise HTTPException(status_code=400, detail="Invalid game code format")
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.status != GameStatus.LOBBY:
        raise HTTPException(status_code=409, detail="Game already in progress or finished")

    existing_players = await fs.get_all_players(game_id)
    if len(existing_players) >= 8:
        raise HTTPException(status_code=409, detail="Game is full (maximum 7 players)")

    player_id = str(uuid.uuid4())
    await fs.add_player(game_id, player_id, body.player_name)
    logger.info(f"Player {player_id} ({body.player_name}) joined game {game_id}")
    return JoinGameResponse(player_id=player_id, game_id=game_id)


@router.get("/games/{game_id}")
async def get_game(
    game_id: str,
    player_id: Optional[str] = Query(None, description="Player ID for access verification"),
):
    """
    Public game state.
    Player roles are NOT included — those are delivered privately via WebSocket.
    """
    await verify_player_access(game_id, player_id)
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    players = await fs.get_all_players(game_id)
    player_count = len(players)
    return {
        "game_id": game.id,
        "status": game.status.value,
        "phase": game.phase.value,
        "round": game.round,
        "difficulty": game.difficulty.value,
        "character_cast": game.character_cast,
        "ai_character": None,  # identity delivered privately via WS connected message
        "players": [p.to_public() for p in players],
        "player_count": player_count,
        # Lobby-only: shown before game start so host can see role breakdown + duration.
        # Hidden once the game is in progress to avoid leaking structural role info.
        # n = human players + 1 AI (AI is not in the players collection).
        "lobby_summary": (
            game_master.get_lobby_summary(player_count + 1, game.difficulty.value)
            if game.status == GameStatus.LOBBY
            else None
        ),
    }


@router.post("/games/{game_id}/start", status_code=200)
@limiter.limit("3/minute")
async def start_game(
    request: Request,
    game_id: str,
    host_player_id: str = Query(..., description="Must match the game's host_player_id"),
):
    """
    Host starts the game.
    - Assigns roles and character identities to all players.
    - Sets game status to IN_PROGRESS.
    - Returns assignment data so the WebSocket hub can broadcast private role cards.
    Requires at least 2 human players to have joined.
    """
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.host_player_id != host_player_id:
        raise HTTPException(status_code=403, detail="Only the host can start the game")

    # Atomically check status==LOBBY and set IN_PROGRESS via Firestore transaction.
    # Prevents double-start race where two concurrent requests both see LOBBY.
    started = await fs.start_game_transactional(game_id)
    if not started:
        raise HTTPException(status_code=409, detail="Game is not in lobby state")

    # Retrieve pre-generated scene image from cache (generated at game creation time).
    # If not ready yet, wait up to 30s for it to finish generating.
    opening_scene_b64 = _scene_cache.pop(game_id, None)
    if opening_scene_b64:
        logger.info("[%s] Using cached opening scene image", game_id)
    else:
        logger.info("[%s] No cached scene — waiting up to 30s for generation", game_id)
        from agents.scene_agent import generate_scene_image
        try:
            opening_scene_b64 = await asyncio.wait_for(
                generate_scene_image("game_started"), timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.warning("[%s] Scene generation timed out after 30s — starting without it", game_id)
        except Exception:
            logger.warning("[%s] Scene generation failed — starting without it", game_id, exc_info=True)

    try:
        assignment = await role_assigner.assign_roles(game_id)
    except ValueError as exc:
        # Restore lobby so the host can fix the issue and try again
        await fs.set_status(game_id, GameStatus.LOBBY.value)
        raise HTTPException(status_code=400, detail=str(exc))
    # Persist phase=NIGHT / round=1 to Firestore before broadcasting
    await game_master.advance_phase(game_id)
    # Fire traitor night selection for Round 1 in the background
    from utils.tasks import safe_create_task
    safe_create_task(trigger_all_night_actions(game_id), name=f"night-actions-r1-{game_id[:8]}", game_id=game_id)

    # Broadcast phase_change → NIGHT and send private role cards via WebSocket
    await ws_manager.broadcast_game_start(game_id, assignment["assignments"], opening_scene_b64=opening_scene_b64)

    # Start narrator session and kick off Round 1 opening narration
    await narrator_manager.start_game(
        game_id,
        initial_prompt=build_phase_prompt(
            "game_started",
            {"character_cast": assignment["character_cast"]},
        ),
    )

    logger.info(
        f"Game {game_id} started with {len(assignment['assignments'])} players. "
        f"Characters in play: {assignment['character_cast']}."
    )
    return {
        "status": "started",
        "game_id": game_id,
        "character_cast": assignment["character_cast"],
        "ai_character": None,  # identity never exposed via HTTP responses
    }


@router.get("/games/{game_id}/events")
async def get_events(
    game_id: str,
    player_id: Optional[str] = Query(None, description="Player ID for access verification"),
    visible_only: bool = Query(
        True, description="True = public events only; False = full log (post-game reveal)"
    ),
):
    """
    Game event log.
    During play: only public events (eliminations, hunter revenge).
    After game ends: set visible_only=false for the full hidden-action reveal.
    """
    await verify_player_access(game_id, player_id)
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Enforce post-game-only access for hidden events — prevents mid-game
    # callers from reading night_target/kill events that reveal AI alignment.
    if not visible_only and game.status != GameStatus.FINISHED:
        raise HTTPException(
            status_code=403,
            detail="Full event log is only available after the game has ended.",
        )

    events = await fs.get_events(game_id, visible_only=visible_only)
    return {
        "game_id": game_id,
        "events": [
            {
                "id": e.id,
                "type": e.type,
                "round": e.round,
                "phase": e.phase.value,
                "actor": e.actor,
                "target": e.target,
                "data": e.data,
                "narration": e.narration,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in events
        ],
    }


@router.get("/games/{game_id}/result")
async def get_result(
    game_id: str,
    player_id: Optional[str] = Query(None, description="Player ID for access verification"),
):
    """
    Post-game result: winner, character reveals, and timeline.
    Only available after the game has finished.
    Used by GameOver page when navigating directly via URL (no WS state).
    """
    await verify_player_access(game_id, player_id)
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.status != GameStatus.FINISHED:
        raise HTTPException(status_code=403, detail="Game has not finished yet")

    all_players = await fs.get_all_players(game_id)
    reveals = [
        {
            "characterName": p.character_name,
            "playerName": p.name,
            "role": p.role.value if p.role else "villager",
            "alive": p.alive,
        }
        for p in all_players
    ]
    for ai in [game.ai_character, game.ai_character_2]:
        if ai:
            reveals.append({
                "characterName": ai.name,
                "playerName": ai.name,
                "role": "shapeshifter" if ai.is_traitor else (ai.role.value if ai.role else "villager"),
                "alive": ai.alive,
            })

    # Build timeline from all events (including hidden)
    all_events = await fs.get_events(game_id, visible_only=False)
    by_round: Dict[int, list] = {}
    for ev in all_events:
        r = ev.round or 0
        if r == 0:
            continue
        by_round.setdefault(r, []).append({
            "id": ev.id,
            "type": ev.type,
            "actor": ev.actor,
            "target": ev.target,
            "data": ev.data or {},
            "visible": ev.visible_in_game,
        })
    timeline = [{"round": r, "events": evs} for r, evs in sorted(by_round.items())]

    return {
        "winner": game.winner,
        "reveals": reveals,
        "timeline": timeline,
    }


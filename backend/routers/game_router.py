"""
Game HTTP endpoints.

Routes:
  POST /api/games                    — Create game + register host as first player
  POST /api/games/{game_id}/join     — Player joins the lobby
  GET  /api/games/{game_id}          — Public game state (roles hidden)
  POST /api/games/{game_id}/start    — Host starts game (triggers role assignment)
  GET  /api/games/{game_id}/events   — Event log (visible only, or all post-game)
"""
import asyncio
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from models.game import (
    CreateGameRequest, CreateGameResponse,
    JoinGameRequest, JoinGameResponse,
    GameStatus,
)
from services.firestore_service import get_firestore_service
from agents.role_assigner import role_assigner
from agents.game_master import game_master
from agents.narrator_agent import narrator_manager, build_phase_prompt
from agents.traitor_agent import trigger_night_selection
from routers.ws_router import manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["games"])


@router.post("/games", response_model=CreateGameResponse, status_code=201)
async def create_game(body: CreateGameRequest):
    """Create a new game and register the host as the first player."""
    fs = get_firestore_service()
    host_player_id = str(uuid.uuid4())
    game = await fs.create_game(
        host_player_id=host_player_id,
        difficulty=body.difficulty.value,
        random_alignment=body.random_alignment,
    )
    await fs.add_player(game.id, host_player_id, body.host_name)
    logger.info(f"Game {game.id} created by host {host_player_id} ({body.host_name})")
    return CreateGameResponse(game_id=game.id, host_player_id=host_player_id)


@router.post("/games/{game_id}/join", response_model=JoinGameResponse, status_code=200)
async def join_game(game_id: str, body: JoinGameRequest):
    """Add a player to the lobby. Rejected if the game has already started."""
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.status != GameStatus.LOBBY:
        raise HTTPException(status_code=409, detail="Game already in progress or finished")

    player_id = str(uuid.uuid4())
    await fs.add_player(game_id, player_id, body.player_name)
    logger.info(f"Player {player_id} ({body.player_name}) joined game {game_id}")
    return JoinGameResponse(player_id=player_id, game_id=game_id)


@router.get("/games/{game_id}")
async def get_game(game_id: str):
    """
    Public game state.
    Player roles are NOT included — those are delivered privately via WebSocket.
    """
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
        "ai_character": (
            {
                "name": game.ai_character.name,
                "alive": game.ai_character.alive,
            }
            if game.ai_character
            else None
        ),
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
async def start_game(
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
    if game.status != GameStatus.LOBBY:
        raise HTTPException(status_code=409, detail="Game is not in lobby state")

    # Lock against double-start: update status BEFORE assign_roles so a second
    # concurrent request sees IN_PROGRESS and returns 409 rather than running
    # a second role assignment that would clobber the first.
    await fs.set_status(game_id, GameStatus.IN_PROGRESS.value)

    try:
        assignment = await role_assigner.assign_roles(game_id)
    except ValueError as exc:
        # Restore lobby so the host can fix the issue and try again
        await fs.set_status(game_id, GameStatus.LOBBY.value)
        raise HTTPException(status_code=400, detail=str(exc))
    # Persist phase=NIGHT / round=1 to Firestore before broadcasting
    await game_master.advance_phase(game_id)
    # Fire traitor night selection for Round 1 in the background
    asyncio.create_task(trigger_night_selection(game_id))

    # Broadcast phase_change → NIGHT and send private role cards via WebSocket
    await ws_manager.broadcast_game_start(game_id, assignment["assignments"])

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
        "ai_character": assignment["ai_character"],
    }


@router.get("/games/{game_id}/events")
async def get_events(
    game_id: str,
    visible_only: bool = Query(
        True, description="True = public events only; False = full log (post-game reveal)"
    ),
):
    """
    Game event log.
    During play: only public events (eliminations, hunter revenge).
    After game ends: set visible_only=false for the full hidden-action reveal.
    """
    fs = get_firestore_service()
    game = await fs.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

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

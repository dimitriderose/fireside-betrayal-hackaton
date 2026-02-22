from fastapi import APIRouter

# Game HTTP endpoints — implemented in feature/websocket-hub
# POST /api/games         — create game
# GET  /api/games/{id}    — get public game state
# POST /api/games/{id}/start — host starts the game
# GET  /api/games/{id}/events — post-game event log

router = APIRouter(tags=["games"])

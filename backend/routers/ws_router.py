from fastapi import APIRouter

# WebSocket hub — implemented in feature/websocket-hub
# WS /ws/{gameId}/{playerId} — player real-time connection

router = APIRouter(tags=["websocket"])

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔥 Fireside: Betrayal backend starting up...")
    yield
    logger.info("Backend shutting down.")


app = FastAPI(
    title="Fireside: Betrayal",
    version="0.1.0",
    description="Real-time multiplayer AI social deduction game — powered by Gemini Live API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "fireside-betrayal", "version": "0.1.0"}


# Routers are registered here as each P0 feature branch is merged:
# from routers.game_router import router as game_router
# from routers.ws_router import router as ws_router
# app.include_router(game_router, prefix="/api")
# app.include_router(ws_router)


# Serve compiled frontend in production (Cloud Run)
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="static")
    logger.info(f"Serving frontend from {_frontend_dist}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

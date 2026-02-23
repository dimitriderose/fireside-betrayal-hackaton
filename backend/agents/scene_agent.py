"""
Scene Image Agent — §12.3.14

Generates atmospheric scene illustrations using Gemini image generation
(standard generate_content with response_modalities=["IMAGE"]).

Called on phase transitions: game start, night resolved, elimination, game over.
Image data is sent inline (base64) over WebSocket — no GCS needed for hackathon.
Falls through silently on any generation failure so game flow is never blocked.
"""
import asyncio
import base64
import logging
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# ── Scene description templates ───────────────────────────────────────────────

_STYLE = (
    "Dark painterly illustration, firelit, medieval fantasy. "
    "Campfire-tale aesthetic meets woodcut print. Muted earth tones with "
    "warm amber firelight accents. No text. No characters visible — atmosphere only."
)

_PHASE_SCENES = {
    "game_started": (
        "The village of Thornwood at night. Dark forest silhouettes surround a cluster of "
        "candlelit stone cottages. A crescent moon half-hidden behind storm clouds. "
        "Smoke curls from chimneys. The village square is empty and still.",
        "ominous",
    ),
    "day_discussion": (
        "The village square of Thornwood at pale dawn. Stone well at the center, "
        "torches guttering in morning mist, wet cobblestones. An empty chair overturned. "
        "Crows on the roof of the inn.",
        "tense",
    ),
    "night": (
        "Thornwood after midnight. The forest edge creeps close. A single lantern "
        "swinging in the wind outside the smithy. Shadows lengthen between the houses. "
        "Something moves in the dark between the trees.",
        "ominous",
    ),
    "elimination": (
        "A single chair at the center of Thornwood's square, empty, a melted candle "
        "beside it. The cobblestones are cold. The village holds its breath. "
        "Morning light filters through iron-grey clouds.",
        "tragic",
    ),
    "game_over_villagers": (
        "Thornwood at sunrise. Golden light breaks over the treeline. The village square "
        "is peaceful, smoke rising from hearths. A fire burns in the central pit, "
        "villagers' silhouettes gathered in relief around its warmth.",
        "hopeful",
    ),
    "game_over_shapeshifter": (
        "Thornwood in darkness. The village square empty, torches extinguished. "
        "A lone shadowed figure at the forest's edge, half-turned to look back. "
        "The moon is hidden. The fire in the square has gone cold.",
        "tragic",
    ),
    "game_over_tanner": (
        "Thornwood village square. A crowd of silhouettes faces away from a single "
        "departing figure who raises both arms in triumph. The sky is an unusual amber, "
        "neither dawn nor dusk. The village stands dumbfounded.",
        "tense",
    ),
}


async def generate_scene_image(scene_key: str) -> Optional[str]:
    """
    Generate a scene image for the given key and return base64-encoded PNG data.
    Returns None on any failure — caller should fall through silently.
    """
    if not settings.gemini_api_key:
        return None

    description, mood = _PHASE_SCENES.get(scene_key, _PHASE_SCENES["night"])

    try:
        from google import genai
        from google.genai import types as gtypes

        client = genai.Client(api_key=settings.gemini_api_key)

        prompt = (
            f"Generate an atmospheric illustration for a dark fantasy social deduction game.\n\n"
            f"Scene: {description}\n"
            f"Mood: {mood}\n"
            f"Style: {_STYLE}"
        )

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.0-flash-preview-image-generation",
                contents=prompt,
                config=gtypes.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                ),
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                image_bytes = part.inline_data.data
                # data may already be bytes or base64 string depending on SDK version
                if isinstance(image_bytes, bytes):
                    return base64.b64encode(image_bytes).decode("utf-8")
                return image_bytes  # already base64

    except Exception:
        logger.warning("Scene image generation failed for '%s'", scene_key, exc_info=True)

    return None


async def trigger_scene_image(game_id: str, scene_key: str) -> None:
    """
    Fire-and-forget: generate and broadcast a scene image for the given phase event.
    Called as asyncio.create_task() from ws_router so it never blocks the main flow.
    """
    from routers.ws_router import manager as ws_manager

    image_b64 = await generate_scene_image(scene_key)
    if image_b64:
        await ws_manager.broadcast_scene_image(game_id, image_b64, scene_key)
        logger.info("[%s] Scene image broadcast for '%s'", game_id, scene_key)

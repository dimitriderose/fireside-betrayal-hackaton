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
    "Flat vector illustration, limited color palette (5-6 colors max), "
    "medieval fantasy. Bold shapes, no gradients, no fine textures. "
    "Woodcut-inspired with solid fills and hard edges. "
    "Dark muted earth tones, single warm amber accent color. "
    "No text, no characters, no faces. Minimal composition — one focal point only. "
    "Small thumbnail style, low detail, clean silhouettes against simple backgrounds."
)

_PHASE_SCENES = {
    "game_started": (
        "Village silhouette at night. Dark tree shapes against a deep blue sky. "
        "One crescent moon. A few cottage shapes with tiny amber window squares.",
        "ominous",
    ),
    "day_discussion": (
        "Village square at dawn. A stone well silhouette in center. "
        "Pale grey-blue sky, faint orange horizon line. Empty cobblestone ground.",
        "tense",
    ),
    "night": (
        "Dark forest edge. A single lantern glow between black tree silhouettes. "
        "Deep indigo sky, no stars.",
        "ominous",
    ),
    "elimination": (
        "A single empty chair silhouette. A melted candle beside it. "
        "Cold grey background, faint dawn light at the horizon.",
        "tragic",
    ),
    "game_over_villagers": (
        "Sunrise over village rooftops. Warm golden-orange sky gradient. "
        "Simple cottage silhouettes, one campfire glow in the center.",
        "hopeful",
    ),
    "game_over_shapeshifter": (
        "Dark empty village square. All lights extinguished. "
        "A single shadow shape at the forest edge. Black and deep grey tones.",
        "tragic",
    ),
    "game_over_tanner": (
        "Village square, amber sky. A single figure silhouette with raised arms. "
        "Other silhouettes turned away. Unusual warm light.",
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

        response = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.5-flash-image",
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
                    encoded = base64.b64encode(image_bytes).decode("utf-8")
                else:
                    encoded = image_bytes  # already base64
                # Guard: drop images over 1.5 MB encoded to avoid stalling WebSocket
                if len(encoded) > 1_500_000:
                    logger.warning("Scene image too large (%d bytes), skipping", len(encoded))
                    return None
                return encoded

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

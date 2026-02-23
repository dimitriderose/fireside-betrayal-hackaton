"""
Camera Vote Agent — §12.3.16

Uses Gemini Flash vision (generate_content with inline image) to count
raised hands in a camera frame captured by the host's browser.

Called from ws_router when the host sends an `in_person_vote_frame` message:
  { characterName: str, imageData: str (base64 JPEG) }

Returns a count dict:
  { hand_count: int, confidence: "high"|"medium"|"low" }

Falls through to { hand_count: 0, confidence: "low" } on any failure —
ws_router falls back to normal phone voting in that case.
"""
import base64
import json
import logging
from typing import Dict, Any

from config import settings

logger = logging.getLogger(__name__)

_COUNT_PROMPT = """\
Look at this image of players sitting or standing together.
Count the number of raised hands. A raised hand is any hand clearly
held above shoulder level. Partial raises or hands at ear level count.

Return ONLY a JSON object with no markdown:
{"hand_count": <integer>, "confidence": "high" or "medium" or "low"}

If the image is unclear or you cannot determine hand count reliably,
return {"hand_count": 0, "confidence": "low"}
"""


async def count_raised_hands(image_b64: str) -> Dict[str, Any]:
    """
    Use Gemini Flash vision to count raised hands in a base64-encoded JPEG.
    Returns { hand_count: int, confidence: "high"|"medium"|"low" }.
    Falls through to low-confidence zero on any error.
    """
    fallback = {"hand_count": 0, "confidence": "low"}

    if not settings.gemini_api_key or not image_b64:
        return fallback

    try:
        # Validate and decode — reject obviously malformed data early
        image_bytes = base64.b64decode(image_b64, validate=True)
    except Exception:
        logger.warning("camera_vote: invalid base64 image data")
        return fallback

    try:
        from google import genai
        from google.genai import types as gtypes

        client = genai.Client(api_key=settings.gemini_api_key)

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                gtypes.Content(parts=[
                    gtypes.Part(text=_COUNT_PROMPT),
                    gtypes.Part(inline_data=gtypes.Blob(
                        mime_type="image/jpeg",
                        data=image_bytes,
                    )),
                ])
            ],
            config=gtypes.GenerateContentConfig(
                max_output_tokens=64,
                temperature=0.0,
            ),
        )

        text = (response.text or "").strip()
        # Strip any accidental markdown fences
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()

        result = json.loads(text)
        hand_count = int(result.get("hand_count", 0))
        confidence = result.get("confidence", "low")
        if confidence not in ("high", "medium", "low"):
            confidence = "low"

        logger.info("camera_vote: counted %d hands (confidence=%s)", hand_count, confidence)
        return {"hand_count": hand_count, "confidence": confidence}

    except Exception:
        logger.warning("camera_vote: Gemini vision call failed", exc_info=True)
        return fallback

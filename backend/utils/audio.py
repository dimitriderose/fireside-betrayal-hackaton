import base64
from typing import List


def pcm_to_base64(pcm_bytes: bytes) -> str:
    """Encode raw PCM bytes to base64 string for WebSocket transmission."""
    return base64.b64encode(pcm_bytes).decode("utf-8")


def base64_to_pcm(b64: str) -> bytes:
    """Decode base64 string back to raw PCM bytes."""
    return base64.b64decode(b64)


def chunk_audio(audio_bytes: bytes, chunk_size: int = 4096) -> List[bytes]:
    """Split audio bytes into fixed-size chunks for streaming."""
    return [audio_bytes[i:i + chunk_size] for i in range(0, len(audio_bytes), chunk_size)]

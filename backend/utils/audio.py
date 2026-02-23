import base64
import struct
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


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    """Wrap raw 16-bit LE mono PCM bytes in a minimal RIFF/WAV container."""
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(pcm_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, num_channels, sample_rate,
        byte_rate, block_align, bits_per_sample,
        b"data", data_size,
    )
    return header + pcm_data

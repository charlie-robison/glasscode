"""Speech-to-text via faster-whisper (runs locally, no API cost)."""

import io
import wave
from typing import Optional

from .config import config

_model = None


def get_model():
    """Lazy-load the Whisper model."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(
            config.whisper_model_size,
            device="cpu",
            compute_type="int8",
        )
    return _model


def transcribe_audio(wav_bytes: bytes) -> str:
    """Transcribe WAV audio bytes to text.

    Accepts raw WAV file bytes (16kHz, 16-bit, mono).
    Returns the transcribed text.
    """
    model = get_model()

    # Write to a temporary in-memory file for faster-whisper
    audio_file = io.BytesIO(wav_bytes)

    segments, info = model.transcribe(
        audio_file,
        language="en",
        beam_size=5,
        vad_filter=True,
    )

    text = " ".join(segment.text.strip() for segment in segments)
    return text.strip()


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Convert raw PCM bytes to WAV format."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()

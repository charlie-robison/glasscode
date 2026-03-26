"""GlassCode server configuration."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Project discovery — directories to scan for git repos
    project_scan_roots: list[str] = field(default_factory=lambda: [
        str(Path.home() / "Desktop" / "Github" / "charlie-robison"),
    ])

    # Wake words (including common Whisper mis-hearings)
    wake_words: list[str] = field(default_factory=lambda: [
        "hey claude", "claude", "hey clod", "clod",
        "hey clawed", "clawed", "hey cloud", "cloud",
        "hey clawd", "clawd", "hey klaud", "klaud",
        "hey clodd", "clodd", "hey claud", "claud",
    ])

    # STT
    whisper_model_size: str = "tiny"

    # TTS
    tts_voice: str = "Samantha"
    tts_rate: int = 200  # words per minute

    # Claude CLI
    claude_binary: str = "claude"


config = Config()

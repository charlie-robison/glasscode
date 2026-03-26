"""Text-to-speech via macOS `say` command (zero cost, no API key)."""

import asyncio
import tempfile
from pathlib import Path

from .config import config


async def synthesize_speech(text: str) -> bytes:
    """Convert text to WAV audio bytes using macOS `say`.

    Returns 16kHz 16-bit mono WAV bytes.
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out_path = f.name

    try:
        proc = await asyncio.create_subprocess_exec(
            "say",
            "-v", config.tts_voice,
            "-r", str(config.tts_rate),
            "-o", out_path,
            "--data-format=LEI16@16000",
            text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

        wav_bytes = Path(out_path).read_bytes()
        return wav_bytes
    finally:
        Path(out_path).unlink(missing_ok=True)


def summarize_for_speech(claude_output: list[dict]) -> str:
    """Extract a concise spoken summary from Claude's stream-json output."""
    text_parts = []

    for item in claude_output:
        msg_type = item.get("type")

        if msg_type == "assistant":
            # Extract text content
            message = item.get("message", {})
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block["text"])
            elif isinstance(content, str):
                text_parts.append(content)

        elif msg_type == "result":
            result_text = item.get("result", "")
            if result_text:
                text_parts.append(result_text)

    full_text = " ".join(text_parts)

    # Truncate for speech — keep it under ~200 chars for a natural spoken response
    if len(full_text) > 300:
        # Take first two sentences
        sentences = full_text.split(". ")
        summary = ". ".join(sentences[:2])
        if not summary.endswith("."):
            summary += "."
        return summary

    return full_text if full_text else "Done."

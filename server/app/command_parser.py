"""Voice command parser — wake word detection + intent extraction."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .config import config
from .project_router import fuzzy_match_project


class Intent(str, Enum):
    OPEN_PROJECT = "open_project"
    PROMPT = "prompt"
    NEW_SESSION = "new_session"
    SWITCH = "switch"
    STATUS = "status"
    STOP = "stop"
    REMOTE_CONTROL = "remote_control"
    EXIT_REMOTE = "exit_remote"


@dataclass
class Command:
    intent: Intent
    project: Optional[dict]  # Matched project info
    prompt_text: str  # The remaining text to send to Claude
    raw_text: str  # Original transcription


# Intent keywords mapped to intents
INTENT_PATTERNS = [
    (r"\b(remote\s+control|go\s+remote|remote\s+mode)\b", Intent.REMOTE_CONTROL),
    (r"\b(exit\s+remote|back\s+to\s+normal|leave\s+remote|local\s+mode)\b", Intent.EXIT_REMOTE),
    (r"\b(start\s+working\s+on|open|work\s+on)\b", Intent.OPEN_PROJECT),
    (r"\b(new\s+terminal\s+for|new\s+session\s+for|new\s+session)\b", Intent.NEW_SESSION),
    (r"\b(switch\s+to|go\s+to|change\s+to)\b", Intent.SWITCH),
    (r"\b(status|what'?s?\s+the\s+status|what\s+are\s+you\s+doing)\b", Intent.STATUS),
    (r"\b(stop|quit|cancel|kill)\b", Intent.STOP),
]


def _normalize(text: str) -> str:
    """Strip punctuation and extra whitespace for matching."""
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def strip_wake_word(text: str) -> Optional[str]:
    """Remove wake word from the beginning of text. Returns None if no wake word found."""
    normalized = _normalize(text)

    # Sort wake words by length (longest first) to match greedily
    sorted_wake_words = sorted(config.wake_words, key=len, reverse=True)

    for wake in sorted_wake_words:
        if normalized.startswith(wake):
            # Find where the wake word ends in the original text
            # Count how many real word characters we consumed
            wake_words = wake.split()
            pos = 0
            for ww in wake_words:
                # Skip to the next word in the original text
                while pos < len(text) and not text[pos].isalnum():
                    pos += 1
                # Skip past this word
                word_start = pos
                while pos < len(text) and text[pos].isalnum():
                    pos += 1
            # pos is now past the wake word in the original text
            remainder = text[pos:].strip().lstrip(".,!?:;").strip()
            return remainder

    return None


def parse_command(text: str, require_wake_word: bool = True) -> Optional[Command]:
    """Parse a transcribed voice command into a structured Command.

    Returns None if no wake word is detected (when required).
    """
    if require_wake_word:
        remainder = strip_wake_word(text)
        if remainder is None:
            return None
    else:
        remainder = text.strip()

    if not remainder:
        return Command(intent=Intent.STATUS, project=None, prompt_text="", raw_text=text)

    remainder_lower = remainder.lower()

    # Check for intents that don't need a project name
    for pattern, intent in INTENT_PATTERNS:
        if intent in (Intent.STATUS, Intent.STOP, Intent.REMOTE_CONTROL, Intent.EXIT_REMOTE):
            if re.search(pattern, remainder_lower):
                return Command(intent=intent, project=None, prompt_text=remainder, raw_text=text)

    # Check for intents that include a project name
    for pattern, intent in INTENT_PATTERNS:
        if intent in (Intent.STATUS, Intent.STOP):
            continue
        match = re.search(pattern, remainder_lower)
        if match:
            # Everything after the intent keyword is the project name + optional prompt
            after_intent = remainder[match.end():].strip()
            parts = after_intent.split(",", 1)  # Split on comma for "project, then prompt"

            project_name = parts[0].strip()
            prompt_text = parts[1].strip() if len(parts) > 1 else ""

            project = fuzzy_match_project(project_name) if project_name else None

            return Command(
                intent=intent,
                project=project,
                prompt_text=prompt_text,  # Empty if no explicit prompt after project name
                raw_text=text,
            )

    # Default: treat entire remainder as a prompt to the active session
    # Try to extract a project name from the text
    project = None

    # Check if text mentions "for <project>" or "on <project>"
    for_match = re.search(r"\b(?:for|on|in)\s+(\w[\w-]*)", remainder_lower)
    if for_match:
        candidate = for_match.group(1)
        project = fuzzy_match_project(candidate)

    return Command(
        intent=Intent.PROMPT,
        project=project,
        prompt_text=remainder,
        raw_text=text,
    )

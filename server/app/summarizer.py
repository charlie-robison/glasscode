"""Summarize Claude's remote output into TTS-friendly text."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .remote_session import RemoteSession


def summarize_remote_result(session: RemoteSession) -> str:
    """Build a concise spoken summary of what Claude did."""
    if session.is_error and session.error:
        msg = _truncate(session.error, 200)
        return f"I ran into a problem. {msg}"

    has_file_ops = session.files_created or session.files_modified

    # If result_text is short and there are no file ops, use it directly
    if session.result_text and len(session.result_text) < 200 and not has_file_ops:
        return session.result_text

    parts: list[str] = []

    # File operations summary
    created = len(session.files_created)
    modified = len(session.files_modified)
    if created or modified:
        file_parts = []
        if created:
            names = _format_file_list(session.files_created)
            file_parts.append(f"created {names}")
        if modified:
            names = _format_file_list(session.files_modified)
            file_parts.append(f"modified {names}")
        parts.append("I " + " and ".join(file_parts) + ".")

    # Commands summary
    if session.commands_run and not created and not modified:
        n = len(session.commands_run)
        parts.append(f"I ran {n} command{'s' if n > 1 else ''}.")

    # Add assistant text summary (first 1-2 sentences)
    text = session.result_text or session.assistant_text
    if text:
        summary = _truncate_to_sentences(text, 200)
        if summary and summary not in " ".join(parts):
            parts.append(summary)

    result = " ".join(parts) if parts else "Done."

    return _truncate(result, 350)


def _format_file_list(files: list[str], max_items: int = 3) -> str:
    """Format file paths for speech — basenames only."""
    names = [os.path.basename(f) for f in files]

    if len(names) <= max_items:
        if len(names) == 1:
            return names[0]
        return ", ".join(names[:-1]) + f" and {names[-1]}"

    shown = ", ".join(names[:max_items])
    remaining = len(names) - max_items
    return f"{shown}, and {remaining} other{'s' if remaining > 1 else ''}"


def _truncate_to_sentences(text: str, max_chars: int) -> str:
    """Truncate text at sentence boundaries."""
    if len(text) <= max_chars:
        return text

    sentences = text.split(". ")
    result = sentences[0]
    if not result.endswith("."):
        result += "."

    for s in sentences[1:]:
        candidate = result + " " + s
        if not candidate.endswith("."):
            candidate += "."
        if len(candidate) > max_chars:
            break
        result = candidate

    return result


def _truncate(text: str, max_chars: int) -> str:
    """Hard truncate with ellipsis."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3].rsplit(" ", 1)[0] + "..."

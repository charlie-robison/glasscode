"""Remote session manager — runs claude -p subprocess with output capture."""

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field

from .config import config

# Pattern to detect GitHub PR/push URLs in tool output
PR_URL_PATTERN = re.compile(r"https://github\.com/[^\s)\"']+/pull/\d+")
PUSH_PATTERN = re.compile(r"git push")


@dataclass
class FileDiff:
    """A single file change."""
    file_path: str
    action: str  # "created", "modified"
    old_string: str | None = None  # For edits
    new_string: str | None = None  # For edits
    content: str | None = None  # For new files (truncated)

    def to_dict(self) -> dict:
        d: dict = {"file_path": self.file_path, "action": self.action}
        if self.old_string is not None:
            d["old_string"] = self.old_string[:500]
        if self.new_string is not None:
            d["new_string"] = self.new_string[:500]
        if self.content is not None:
            d["content"] = self.content[:2000]
        return d


@dataclass
class RemoteSession:
    """Tracks state from a single remote prompt execution."""
    session_id: str  # GlassCode session ID
    claude_session_id: str | None = None  # Claude CLI session UUID for --resume
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    file_diffs: list[FileDiff] = field(default_factory=list)
    commands_run: list[str] = field(default_factory=list)
    assistant_text: str = ""
    result_text: str = ""
    error: str | None = None
    duration_ms: int | None = None
    is_error: bool = False
    pr_url: str | None = None
    git_pushed: bool = False


class RemoteSessionManager:
    def __init__(self):
        self.processes: dict[str, asyncio.subprocess.Process] = {}

    async def send_prompt(
        self,
        session_id: str,
        project_path: str,
        prompt: str,
        resume_id: str | None = None,
    ) -> RemoteSession:
        """Run a prompt through claude -p subprocess, parse stream-json output."""
        result = RemoteSession(session_id=session_id)

        cmd = [
            config.claude_binary,
            "-p",
            "--output-format", "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
        ]

        if resume_id:
            cmd.extend(["--resume", resume_id])

        cmd.append(prompt)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,  # Prevent hanging on any prompts
            cwd=project_path,
            env={**os.environ, "TERM": "dumb"},
        )
        self.processes[session_id] = proc

        print(f"[remote] Running: {' '.join(cmd)}", file=sys.stderr)
        print(f"[remote] cwd: {project_path}", file=sys.stderr)

        try:
            await asyncio.wait_for(
                self._read_stream(proc, result),
                timeout=config.remote_timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            # Grab stderr for debugging
            if proc.stderr:
                stderr = await proc.stderr.read()
                stderr_text = stderr.decode().strip()
                if stderr_text:
                    print(f"[remote] stderr on timeout: {stderr_text[:500]}", file=sys.stderr)
                    result.error = f"Timed out. stderr: {stderr_text[:200]}"
                else:
                    result.error = "Timed out"
            else:
                result.error = "Timed out"
            result.is_error = True
        finally:
            self.processes.pop(session_id, None)

        return result

    async def _read_stream(self, proc: asyncio.subprocess.Process, result: RemoteSession):
        """Read stdout line-by-line, parse stream-json events."""
        assert proc.stdout is not None

        while True:
            line = await proc.stdout.readline()
            if not line:
                break

            line_str = line.decode().strip()
            if not line_str:
                continue

            try:
                event = json.loads(line_str)
            except json.JSONDecodeError:
                continue

            self._process_event(event, result)

        await proc.wait()

        # Check for errors from stderr
        if proc.returncode and proc.returncode != 0 and proc.stderr:
            stderr = await proc.stderr.read()
            stderr_text = stderr.decode().strip()
            if stderr_text and not result.error:
                result.error = stderr_text[:500]
                result.is_error = True

    def _process_event(self, event: dict, result: RemoteSession):
        """Process a single stream-json event."""
        event_type = event.get("type")

        if event_type == "system":
            # Extract Claude CLI session ID for --resume
            sid = event.get("session_id")
            if sid:
                result.claude_session_id = sid

        elif event_type == "assistant":
            message = event.get("message", {})
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            if result.assistant_text:
                                result.assistant_text += " "
                            result.assistant_text += text
                    elif block.get("type") == "tool_use":
                        self._track_tool_use(block, result)

        elif event_type == "user":
            # Tool results — check for PR URLs in bash output
            content = event.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_result":
                        result_content = block.get("content", "")
                        if isinstance(result_content, str):
                            self._scan_for_urls(result_content, result)
                        elif isinstance(result_content, list):
                            for item in result_content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    self._scan_for_urls(item.get("text", ""), result)

        elif event_type == "result":
            result.result_text = event.get("result", "")
            result.is_error = event.get("is_error", False)
            result.duration_ms = event.get("duration_ms")
            if result.is_error and not result.error:
                result.error = result.result_text
            # Also scan result text for PR URLs
            self._scan_for_urls(result.result_text, result)

    def _track_tool_use(self, block: dict, result: RemoteSession):
        """Track file operations and commands from tool_use blocks."""
        tool_name = block.get("name", "")
        tool_input = block.get("input", {})

        if tool_name == "Write":
            path = tool_input.get("file_path", "")
            if path and path not in result.files_created:
                result.files_created.append(path)
                result.file_diffs.append(FileDiff(
                    file_path=path,
                    action="created",
                    content=tool_input.get("content", ""),
                ))
        elif tool_name == "Edit":
            path = tool_input.get("file_path", "")
            if path and path not in result.files_modified and path not in result.files_created:
                result.files_modified.append(path)
            # Always track individual edits (a file can have multiple edits)
            if path:
                result.file_diffs.append(FileDiff(
                    file_path=path,
                    action="modified",
                    old_string=tool_input.get("old_string", ""),
                    new_string=tool_input.get("new_string", ""),
                ))
        elif tool_name == "Bash":
            cmd = tool_input.get("command", "")
            if cmd:
                result.commands_run.append(cmd[:200])
                if PUSH_PATTERN.search(cmd):
                    result.git_pushed = True

    def _scan_for_urls(self, text: str, result: RemoteSession):
        """Scan text for GitHub PR URLs."""
        if not text:
            return
        match = PR_URL_PATTERN.search(text)
        if match and not result.pr_url:
            result.pr_url = match.group(0)

    async def cancel(self, session_id: str) -> bool:
        """Kill a running subprocess."""
        proc = self.processes.get(session_id)
        if proc:
            proc.kill()
            self.processes.pop(session_id, None)
            return True
        return False


# Singleton
remote_session_manager = RemoteSessionManager()

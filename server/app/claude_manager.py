"""Claude Code process manager — uses tmux for reliable terminal interaction."""

import asyncio
import shlex
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .config import config


class SessionStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class ClaudeSession:
    session_id: str
    project_path: str
    tmux_session: str  # tmux session name
    status: SessionStatus = SessionStatus.RUNNING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    remote_mode: bool = False
    claude_resume_id: str | None = None  # Claude CLI session UUID for --resume

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "project_path": self.project_path,
            "status": self.status.value,
            "created_at": self.created_at,
            "project_name": self.project_path.rstrip("/").split("/")[-1],
            "remote_mode": self.remote_mode,
        }


class ClaudeManager:
    def __init__(self):
        self.sessions: dict[str, ClaudeSession] = {}
        self.active_session_id: str | None = None

    async def _run(self, *args: str) -> tuple[str, str, int]:
        """Run a command and return (stdout, stderr, returncode)."""
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode().strip(), stderr.decode().strip(), proc.returncode

    async def open_project(self, project_path: str) -> ClaudeSession:
        """Step 1: Start Claude in a tmux session, open Terminal.app attached to it."""
        session_id = str(uuid.uuid4())[:8]
        tmux_name = f"gc_{session_id}"

        # Create a detached tmux session running interactive claude in the project dir
        await self._run(
            "tmux", "new-session",
            "-d",                    # detached
            "-s", tmux_name,         # session name
            "-c", project_path,      # working directory
            config.claude_binary,    # run claude interactively
        )

        # Open Terminal.app window attached to the tmux session
        attach_cmd = f"tmux attach -t {tmux_name}"
        as_cmd = attach_cmd.replace('"', '\\"')
        applescript = f'''
        tell application "Terminal"
            do script "{as_cmd}"
            activate
            set custom title of selected tab of front window to "GlassCode [{session_id}]"
        end tell
        '''
        await self._run("osascript", "-e", applescript)

        session = ClaudeSession(
            session_id=session_id,
            project_path=project_path,
            tmux_session=tmux_name,
        )
        self.sessions[session_id] = session
        self.active_session_id = session_id
        return session

    async def send_prompt(self, session_id: str, prompt: str) -> bool:
        """Step 2: Type a prompt into the running Claude session via tmux send-keys."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        # tmux send-keys types text into the session and Enter submits it
        _, _, rc = await self._run(
            "tmux", "send-keys",
            "-t", session.tmux_session,
            prompt,
            "Enter",
        )
        return rc == 0

    async def stop_session(self, session_id: str) -> bool:
        """Stop a running session by killing the tmux session."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        # Send Ctrl+C first to interrupt Claude, then kill the tmux session
        await self._run("tmux", "send-keys", "-t", session.tmux_session, "C-c", "")
        await asyncio.sleep(0.5)
        await self._run("tmux", "kill-session", "-t", session.tmux_session)

        session.status = SessionStatus.STOPPED
        return True

    def list_sessions(self) -> list[dict]:
        """List all tracked sessions."""
        return [s.to_dict() for s in self.sessions.values()]

    def get_active_session(self) -> ClaudeSession | None:
        """Get the currently active session."""
        if self.active_session_id:
            return self.sessions.get(self.active_session_id)
        return None

    def switch_session(self, session_id: str) -> ClaudeSession | None:
        """Switch the active session."""
        if session_id in self.sessions:
            self.active_session_id = session_id
            return self.sessions[session_id]
        return None

    def enable_remote(self, session_id: str) -> bool:
        """Enable remote control mode on a session."""
        session = self.sessions.get(session_id)
        if session:
            session.remote_mode = True
            return True
        return False

    def disable_remote(self, session_id: str) -> bool:
        """Disable remote control mode."""
        session = self.sessions.get(session_id)
        if session:
            session.remote_mode = False
            return True
        return False


# Singleton
claude_manager = ClaudeManager()

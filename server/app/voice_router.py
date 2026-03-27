"""Voice WebSocket endpoint — the main audio pipeline."""

import asyncio
import base64
import json
import traceback

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .claude_manager import claude_manager
from .command_parser import Intent, parse_command
from .remote_session import remote_session_manager
from .speech_to_text import pcm_to_wav, transcribe_audio
from .summarizer import summarize_remote_result
from .tts import synthesize_speech

router = APIRouter()


@router.websocket("/ws/voice")
async def voice_pipeline(websocket: WebSocket):
    """Main voice pipeline WebSocket.

    Protocol:
    - Client sends binary PCM chunks (16kHz, 16-bit, mono)
    - Client sends JSON {"action": "transcribe"} to trigger transcription
    - Server responds with JSON messages:
      - {"type": "transcription", "text": "..."}
      - {"type": "command", "intent": "...", "project": "...", "prompt": "..."}
      - {"type": "tts_audio", "audio": "<base64 wav>"}
      - {"type": "error", "message": "..."}
    """
    await websocket.accept()
    audio_buffer = bytearray()
    active_remote_task: asyncio.Task | None = None

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message:
                audio_buffer.extend(message["bytes"])
                continue

            if "text" in message:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                    continue

                action = data.get("action")

                if action == "transcribe":
                    await handle_transcribe(websocket, audio_buffer)
                    audio_buffer = bytearray()
                elif action == "text_command":
                    text = data.get("text", "")
                    await handle_command_text(websocket, text)
                elif action == "clear_buffer":
                    audio_buffer = bytearray()
                    await websocket.send_json({"type": "status", "message": "Buffer cleared"})
                else:
                    await websocket.send_json({"type": "error", "message": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        # Cancel any running remote subprocess
        active = claude_manager.get_active_session()
        if active and active.remote_mode:
            await remote_session_manager.cancel(active.session_id)


async def handle_transcribe(websocket: WebSocket, audio_buffer: bytearray):
    """Transcribe audio buffer and process the command."""
    if not audio_buffer:
        await websocket.send_json({"type": "error", "message": "No audio data to transcribe"})
        return

    try:
        raw = bytes(audio_buffer)
        # Phone sends WAV files, glass_client sends raw PCM — handle both
        if raw[:4] == b"RIFF":
            wav_bytes = raw
        else:
            wav_bytes = pcm_to_wav(raw)
        text = transcribe_audio(wav_bytes)
        await websocket.send_json({"type": "transcription", "text": text})
        if text:
            await handle_command_text(websocket, text)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Transcription failed: {str(e)}"})
        traceback.print_exc()


async def handle_command_text(websocket: WebSocket, text: str):
    """Parse and execute a text command."""
    command = parse_command(text)

    if command is None:
        await websocket.send_json({
            "type": "info",
            "message": "No wake word detected",
        })
        return

    await websocket.send_json({
        "type": "command",
        "intent": command.intent.value,
        "project": command.project.get("name") if command.project else None,
        "prompt": command.prompt_text,
    })

    try:
        if command.intent == Intent.OPEN_PROJECT:
            await handle_open_project(websocket, command)
        elif command.intent == Intent.PROMPT:
            await handle_prompt(websocket, command)
        elif command.intent == Intent.NEW_SESSION:
            await handle_new_session(websocket, command)
        elif command.intent == Intent.SWITCH:
            await handle_switch(websocket, command)
        elif command.intent == Intent.STATUS:
            await handle_status(websocket)
        elif command.intent == Intent.STOP:
            await handle_stop(websocket)
        elif command.intent == Intent.REMOTE_CONTROL:
            await handle_remote_control(websocket)
        elif command.intent == Intent.EXIT_REMOTE:
            await handle_exit_remote(websocket)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        traceback.print_exc()


async def send_tts(websocket: WebSocket, text: str):
    """Synthesize and send TTS audio."""
    tts_audio = await synthesize_speech(text)
    await websocket.send_json({"type": "tts_audio", "audio": base64.b64encode(tts_audio).decode()})


async def handle_open_project(websocket: WebSocket, command):
    """Open a project session with remote mode auto-enabled."""
    if not command.project:
        msg = "I couldn't find that project. Try again?"
        await websocket.send_json({"type": "error", "message": msg})
        await send_tts(websocket, msg)
        return

    # Open interactive claude in the project directory
    session = await claude_manager.open_project(command.project["path"])

    # Auto-enable remote mode — voice users always want output capture
    claude_manager.enable_remote(session.session_id)

    msg = f"Opened Claude in {command.project['name']}. Remote control is on."
    await websocket.send_json({
        "type": "session_created",
        "session_id": session.session_id,
        "project": command.project["name"],
    })
    await send_tts(websocket, msg)

    # If there was an explicit prompt, run it through remote subprocess
    if command.prompt_text:
        await handle_remote_prompt(websocket, session, command)


async def handle_prompt(websocket: WebSocket, command):
    """Send a prompt — via remote subprocess if remote mode, otherwise tmux."""
    active = claude_manager.get_active_session()

    if not active:
        if command.project:
            # No session yet — open one first, then send the prompt via remote
            session = await claude_manager.open_project(command.project["path"])
            claude_manager.enable_remote(session.session_id)

            await websocket.send_json({
                "type": "session_created",
                "session_id": session.session_id,
                "project": command.project["name"],
            })

            await handle_remote_prompt(websocket, session, command)
            return
        else:
            msg = "No active session. Say 'Hey Claude, start working on' followed by a project name."
            await websocket.send_json({"type": "error", "message": msg})
            await send_tts(websocket, msg)
            return
    elif active.remote_mode:
        # Remote control mode — run via subprocess with output capture
        await handle_remote_prompt(websocket, active, command)
        return
    else:
        # Type the prompt into the existing terminal
        project_name = active.project_path.rstrip("/").split("/")[-1]
        sent = await claude_manager.send_prompt(active.session_id, command.prompt_text)
        if not sent:
            msg = f"Couldn't find the terminal for {project_name}. It may have been closed."
            await websocket.send_json({"type": "error", "message": msg})
            await send_tts(websocket, msg)
            return

    msg = "Sent to Claude."
    await websocket.send_json({"type": "prompt_sent", "prompt": command.prompt_text})
    await send_tts(websocket, msg)


async def handle_new_session(websocket: WebSocket, command):
    """Open a parallel interactive Claude session for a project."""
    if not command.project:
        msg = "Which project should I start a new session for?"
        await websocket.send_json({"type": "error", "message": msg})
        await send_tts(websocket, msg)
        return

    session = await claude_manager.open_project(command.project["path"])

    msg = f"Opened a new terminal for {command.project['name']}."
    await websocket.send_json({
        "type": "session_created",
        "session_id": session.session_id,
        "project": command.project["name"],
    })
    await send_tts(websocket, msg)

    if command.prompt_text:
        await asyncio.sleep(3)
        await claude_manager.send_prompt(session.session_id, command.prompt_text)
        await websocket.send_json({"type": "prompt_sent", "prompt": command.prompt_text})


async def handle_switch(websocket: WebSocket, command):
    """Switch the active session to a different project."""
    if not command.project:
        msg = "Which project should I switch to?"
        await websocket.send_json({"type": "error", "message": msg})
        return

    for sid, session in claude_manager.sessions.items():
        if command.project["path"] == session.project_path:
            claude_manager.switch_session(sid)
            msg = f"Switched to {command.project['name']}."
            await websocket.send_json({"type": "switched", "session_id": sid, "project": command.project["name"]})
            await send_tts(websocket, msg)
            return

    msg = f"No active session for {command.project['name']}. Want me to start one?"
    await websocket.send_json({"type": "error", "message": msg})
    await send_tts(websocket, msg)


async def handle_status(websocket: WebSocket):
    """Report back session status."""
    sessions = claude_manager.list_sessions()
    active_id = claude_manager.active_session_id

    if not sessions:
        msg = "No active sessions."
    else:
        parts = [f"{len(sessions)} session{'s' if len(sessions) > 1 else ''}. "]
        for s in sessions:
            marker = " (active)" if s["session_id"] == active_id else ""
            remote = " remote" if s.get("remote_mode") else ""
            parts.append(f"{s['project_name']}: {s['status']}{remote}{marker}. ")
        msg = "".join(parts)

    await websocket.send_json({"type": "status", "sessions": sessions, "active_session_id": active_id})
    await send_tts(websocket, msg)


async def handle_stop(websocket: WebSocket):
    """Stop the active session."""
    active = claude_manager.get_active_session()
    if not active:
        msg = "No active session to stop."
        await websocket.send_json({"type": "error", "message": msg})
        return

    # Cancel any running remote subprocess too
    if active.remote_mode:
        await remote_session_manager.cancel(active.session_id)

    project_name = active.project_path.rstrip("/").split("/")[-1]
    await claude_manager.stop_session(active.session_id)
    msg = f"Stopped session for {project_name}."
    await websocket.send_json({"type": "stopped", "session_id": active.session_id})
    await send_tts(websocket, msg)


# ── Remote control handlers ──────────────────────────────────────────────


async def handle_remote_control(websocket: WebSocket):
    """Activate remote control mode on the active session."""
    active = claude_manager.get_active_session()
    if not active:
        msg = "No active session. Open a project first, then say remote control."
        await websocket.send_json({"type": "error", "message": msg})
        await send_tts(websocket, msg)
        return

    claude_manager.enable_remote(active.session_id)
    project_name = active.project_path.rstrip("/").split("/")[-1]
    msg = f"Remote control activated for {project_name}. I'll tell you what Claude does."

    await websocket.send_json({
        "type": "remote_enabled",
        "session_id": active.session_id,
        "project": project_name,
    })
    await send_tts(websocket, msg)


async def handle_exit_remote(websocket: WebSocket):
    """Deactivate remote control mode."""
    active = claude_manager.get_active_session()
    if not active or not active.remote_mode:
        msg = "Remote control is not active."
        await websocket.send_json({"type": "error", "message": msg})
        await send_tts(websocket, msg)
        return

    claude_manager.disable_remote(active.session_id)
    project_name = active.project_path.rstrip("/").split("/")[-1]
    msg = f"Back to normal mode for {project_name}."

    await websocket.send_json({
        "type": "remote_disabled",
        "session_id": active.session_id,
    })
    await send_tts(websocket, msg)


async def handle_remote_prompt(websocket: WebSocket, session, command):
    """Run a prompt via subprocess, capture output, summarize, and speak back."""
    project_name = session.project_path.rstrip("/").split("/")[-1]

    # Acknowledge
    await websocket.send_json({
        "type": "remote_working",
        "session_id": session.session_id,
        "prompt": command.prompt_text,
    })
    await send_tts(websocket, "Working on it.")

    # Periodic progress updates for long operations
    progress_task = asyncio.create_task(_send_progress_updates(websocket, session.session_id))

    try:
        remote = await remote_session_manager.send_prompt(
            session_id=session.session_id,
            project_path=session.project_path,
            prompt=command.prompt_text,
            resume_id=session.claude_resume_id,
        )

        # Store Claude session ID for --resume continuity
        if remote.claude_session_id:
            session.claude_resume_id = remote.claude_session_id

        # Summarize and speak
        summary = summarize_remote_result(remote)

        await websocket.send_json({
            "type": "remote_result",
            "session_id": session.session_id,
            "summary": summary,
            "files_created": remote.files_created,
            "files_modified": remote.files_modified,
            "file_diffs": [d.to_dict() for d in remote.file_diffs],
            "commands_run": remote.commands_run,
            "duration_ms": remote.duration_ms,
            "error": remote.error,
            "pr_url": remote.pr_url,
            "git_pushed": remote.git_pushed,
        })
        await send_tts(websocket, summary)

    except Exception as e:
        msg = f"Something went wrong: {str(e)}"
        await websocket.send_json({"type": "error", "message": msg})
        await send_tts(websocket, msg)
    finally:
        progress_task.cancel()


async def _send_progress_updates(websocket: WebSocket, session_id: str):
    """Send periodic 'still working' TTS updates for long operations."""
    try:
        await asyncio.sleep(15)
        await websocket.send_json({"type": "remote_progress", "session_id": session_id})
        await send_tts(websocket, "Still working on it...")

        await asyncio.sleep(30)
        await websocket.send_json({"type": "remote_progress", "session_id": session_id})
        await send_tts(websocket, "Still going. This is a big one.")

        # After that, update every 60 seconds
        while True:
            await asyncio.sleep(60)
            await websocket.send_json({"type": "remote_progress", "session_id": session_id})
            await send_tts(websocket, "Still working...")
    except asyncio.CancelledError:
        pass

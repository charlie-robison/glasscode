"""Voice WebSocket endpoint — the main audio pipeline."""

import base64
import json
import traceback

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .claude_manager import claude_manager
from .command_parser import Intent, parse_command
from .speech_to_text import pcm_to_wav, transcribe_audio
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
        pass


async def handle_transcribe(websocket: WebSocket, audio_buffer: bytearray):
    """Transcribe audio buffer and process the command."""
    if not audio_buffer:
        await websocket.send_json({"type": "error", "message": "No audio data to transcribe"})
        return

    try:
        wav_bytes = pcm_to_wav(bytes(audio_buffer))
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
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        traceback.print_exc()


async def send_tts(websocket: WebSocket, text: str):
    """Synthesize and send TTS audio."""
    tts_audio = await synthesize_speech(text)
    await websocket.send_json({"type": "tts_audio", "audio": base64.b64encode(tts_audio).decode()})


async def handle_open_project(websocket: WebSocket, command):
    """Step 1: Open an interactive Claude session in a Terminal.app window."""
    if not command.project:
        msg = "I couldn't find that project. Try again?"
        await websocket.send_json({"type": "error", "message": msg})
        await send_tts(websocket, msg)
        return

    # Open interactive claude (no -p) in the project directory
    session = await claude_manager.open_project(command.project["path"])

    msg = f"Opened Claude in {command.project['name']}."
    await websocket.send_json({
        "type": "session_created",
        "session_id": session.session_id,
        "project": command.project["name"],
    })
    await send_tts(websocket, msg)

    # If there was an explicit prompt after the project name, send it as step 2
    if command.prompt_text:
        # Small delay to let Claude finish loading in the terminal
        import asyncio
        await asyncio.sleep(3)
        sent = await claude_manager.send_prompt(session.session_id, command.prompt_text)
        if sent:
            await websocket.send_json({"type": "prompt_sent", "prompt": command.prompt_text})


async def handle_prompt(websocket: WebSocket, command):
    """Step 2: Type a prompt into the active Claude terminal."""
    active = claude_manager.get_active_session()

    if not active:
        if command.project:
            # No session yet — open one first, then send the prompt
            session = await claude_manager.open_project(command.project["path"])
            project_name = command.project["name"]

            await websocket.send_json({
                "type": "session_created",
                "session_id": session.session_id,
                "project": project_name,
            })

            import asyncio
            await asyncio.sleep(3)
            await claude_manager.send_prompt(session.session_id, command.prompt_text)
        else:
            msg = "No active session. Say 'Hey Claude, start working on' followed by a project name."
            await websocket.send_json({"type": "error", "message": msg})
            await send_tts(websocket, msg)
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

    msg = f"Sent to Claude."
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
        import asyncio
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
            parts.append(f"{s['project_name']}: {s['status']}{marker}. ")
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

    project_name = active.project_path.rstrip("/").split("/")[-1]
    await claude_manager.stop_session(active.session_id)
    msg = f"Stopped session for {project_name}."
    await websocket.send_json({"type": "stopped", "session_id": active.session_id})
    await send_tts(websocket, msg)

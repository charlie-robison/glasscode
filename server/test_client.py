#!/usr/bin/env python3
"""GlassCode test client — test the voice pipeline from the command line.

Usage:
    python test_client.py                    # Interactive text mode
    python test_client.py --wav hello.wav    # Send a WAV file for transcription
"""

import argparse
import asyncio
import base64
import json
import sys
import tempfile
from pathlib import Path

try:
    import websockets
except ImportError:
    print("Install websockets: pip install websockets")
    sys.exit(1)


async def send_wav(ws, wav_path: str):
    """Send a WAV file for transcription."""
    wav_bytes = Path(wav_path).read_bytes()

    # Send raw audio bytes
    await ws.send(wav_bytes)

    # Trigger transcription
    await ws.send(json.dumps({"action": "transcribe"}))

    # Read responses until we get TTS or error
    await read_responses(ws)


async def send_text_command(ws, text: str):
    """Send a text command directly (bypasses STT)."""
    await ws.send(json.dumps({"action": "text_command", "text": text}))
    await read_responses(ws)


async def read_responses(ws, timeout: float = 60.0):
    """Read and display server responses."""
    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except asyncio.TimeoutError:
                print("[timeout]")
                break

            data = json.loads(msg)
            msg_type = data.get("type")

            if msg_type == "transcription":
                print(f"\n🎤 Transcription: {data['text']}")

            elif msg_type == "command":
                print(f"🎯 Intent: {data['intent']}", end="")
                if data.get("project"):
                    print(f" | Project: {data['project']}", end="")
                if data.get("prompt"):
                    print(f" | Prompt: {data['prompt']}", end="")
                print()

            elif msg_type == "session_created":
                print(f"\n✅ Session {data['session_id']} — Terminal opened for {data.get('project', '?')}")

            elif msg_type == "tts_audio":
                audio_b64 = data.get("audio", "")
                if audio_b64:
                    audio_bytes = base64.b64decode(audio_b64)
                    # Save and play TTS audio
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        f.write(audio_bytes)
                        tmp_path = f.name
                    print(f"\n🔊 TTS audio saved: {tmp_path}")
                    # Play via macOS afplay
                    proc = await asyncio.create_subprocess_exec("afplay", tmp_path)
                    await proc.wait()
                    Path(tmp_path).unlink(missing_ok=True)
                break  # TTS is the last message in the pipeline

            elif msg_type == "error":
                print(f"\n❌ Error: {data['message']}")
                break

            elif msg_type == "status":
                sessions = data.get("sessions", [])
                if not sessions:
                    print("\n📊 No active sessions")
                else:
                    print(f"\n📊 {len(sessions)} session(s):")
                    for s in sessions:
                        name = s.get("project_name", s["project_path"].split("/")[-1])
                        active = " (active)" if s["session_id"] == data.get("active_session_id") else ""
                        print(f"   - {s['session_id'][:8]} {name}: {s['status']}{active}")
                break

            elif msg_type in ("switched", "stopped"):
                break

            elif msg_type == "info":
                print(f"ℹ️  {data.get('message', '')}")
                break

    except Exception as e:
        print(f"\nConnection error: {e}")


async def interactive_mode(server_url: str):
    """Interactive text command mode."""
    print("GlassCode Test Client")
    print(f"Connecting to {server_url}...")

    async with websockets.connect(server_url) as ws:
        print("Connected! Type commands (prefix with 'Hey Claude' or just type prompts).")
        print("Examples:")
        print('  Hey Claude, start working on swivel')
        print('  Hey Claude, add a login page')
        print('  Hey Claude, status')
        print('  Hey Claude, stop')
        print('  quit')
        print()

        while True:
            try:
                text = input("You > ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not text:
                continue
            if text.lower() in ("quit", "exit", "q"):
                break

            await send_text_command(ws, text)
            print()  # blank line after response


async def main():
    parser = argparse.ArgumentParser(description="GlassCode test client")
    parser.add_argument("--server", default="ws://localhost:8000/ws/voice", help="WebSocket server URL")
    parser.add_argument("--wav", help="Send a WAV file for transcription")
    args = parser.parse_args()

    if args.wav:
        async with websockets.connect(args.server) as ws:
            await send_wav(ws, args.wav)
    else:
        await interactive_mode(args.server)


if __name__ == "__main__":
    asyncio.run(main())

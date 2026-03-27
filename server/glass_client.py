#!/usr/bin/env python3
"""GlassCode direct client — connect Meta glasses to Mac via Bluetooth.

Skip the phone entirely. Pair glasses to your Mac, then:
  System Settings > Sound > Input:  Ray-Ban | Meta
  System Settings > Sound > Output: Ray-Ban | Meta

Usage:
    python glass_client.py                    # Voice-activated (default, hands-free)
    python glass_client.py --list-devices     # Show available audio devices
    python glass_client.py --device 3         # Use a specific audio device index
    python glass_client.py --threshold 0.02   # Adjust mic sensitivity
"""

import argparse
import asyncio
import base64
import io
import json
import sys
import tempfile
import wave
from pathlib import Path

try:
    import numpy as np
    import sounddevice as sd
except ImportError:
    print("Install dependencies: pip install sounddevice numpy")
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("Install websockets: pip install websockets")
    sys.exit(1)

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"

# Status symbols
SYM_IDLE = "\033[90m○\033[0m"       # grey circle
SYM_LISTEN = "\033[92m●\033[0m"     # green circle
SYM_PROCESS = "\033[93m◉\033[0m"    # yellow circle
SYM_PLAY = "\033[96m♪\033[0m"       # cyan note


def clear_line():
    """Clear the current terminal line."""
    print("\r\033[K", end="", flush=True)


def status(sym: str, text: str, newline: bool = False):
    """Print a status line, overwriting the current line."""
    clear_line()
    end = "\n" if newline else ""
    print(f"\r  {sym}  {text}", end=end, flush=True)


def list_devices():
    """Print available audio devices."""
    print("\nAudio Devices:")
    print("-" * 60)
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        direction = ""
        if d["max_input_channels"] > 0:
            direction += " [INPUT]"
        if d["max_output_channels"] > 0:
            direction += " [OUTPUT]"
        marker = ""
        defaults = sd.default.device
        if i == defaults[0]:
            marker += " << DEFAULT INPUT"
        if i == defaults[1]:
            marker += " << DEFAULT OUTPUT"
        print(f"  {i}: {d['name']}{direction}{marker}")
    print()


def play_wav_bytes(wav_bytes: bytes, device=None):
    """Play WAV audio bytes through the output device."""
    try:
        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            channels = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())

        audio = np.frombuffer(frames, dtype=np.int16)
        if channels > 1:
            audio = audio.reshape(-1, channels)

        sd.play(audio, samplerate=rate, device=device)
        sd.wait()
    except Exception:
        # Fallback to afplay
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp = f.name
        import subprocess
        subprocess.run(["afplay", tmp], check=False)
        Path(tmp).unlink(missing_ok=True)


async def run(server_url: str, device=None, threshold: float = 0.01, silence_ms: int = 1500):
    """Always-listening voice client with automatic speech detection."""
    print()
    print("  \033[1mGlassCode\033[0m")
    print(f"  Connecting to {server_url}...")

    async with websockets.connect(server_url) as ws:
        print("  Connected!")
        print()
        print(f"  Threshold: {threshold}  |  Silence timeout: {silence_ms}ms")
        print(f"  Ctrl+C to exit")
        print()

        loop = asyncio.get_event_loop()
        audio_queue: asyncio.Queue = asyncio.Queue()

        # Mutable state shared with audio callback thread
        state = {
            "speaking": False,
            "silence_counter": 0,
            "frames": [],
            "paused": False,  # Pause listening while processing/playing
        }
        silence_blocks = max(1, int((silence_ms / 1000) * (SAMPLE_RATE / 1024)))

        def audio_callback(indata, frame_count, time_info, sd_status):
            if state["paused"]:
                return

            energy = np.sqrt(np.mean(indata.astype(np.float32) ** 2)) / 32768.0

            if energy > threshold:
                if not state["speaking"]:
                    state["speaking"] = True
                state["silence_counter"] = 0
                state["frames"].append(indata.copy())
            elif state["speaking"]:
                state["frames"].append(indata.copy())
                state["silence_counter"] += 1
                if state["silence_counter"] >= silence_blocks:
                    # Speech ended — send audio for processing
                    state["speaking"] = False
                    state["silence_counter"] = 0
                    captured = list(state["frames"])
                    state["frames"].clear()
                    loop.call_soon_threadsafe(audio_queue.put_nowait, captured)

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            device=device,
            callback=audio_callback,
            blocksize=1024,
        )

        stream.start()
        status(SYM_IDLE, "Listening...")

        try:
            while True:
                captured_frames = await audio_queue.get()
                if not captured_frames:
                    continue

                # Pause mic while processing so TTS playback doesn't re-trigger
                state["paused"] = True

                # Convert to WAV
                audio = np.concatenate(captured_frames)
                duration = len(audio) / SAMPLE_RATE

                # Skip very short blips (< 0.3s)
                if duration < 0.3:
                    state["paused"] = False
                    status(SYM_IDLE, "Listening...")
                    continue

                status(SYM_PROCESS, f"Processing ({duration:.1f}s of audio)...")

                buf = io.BytesIO()
                with wave.open(buf, "wb") as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(2)
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(audio.tobytes())
                wav_bytes = buf.getvalue()

                await ws.send(wav_bytes)
                await ws.send(json.dumps({"action": "transcribe"}))

                await read_responses(ws, device)

                # Resume listening
                state["paused"] = False
                status(SYM_IDLE, "Listening...")

        except KeyboardInterrupt:
            clear_line()
            print("\r  Bye!")
        finally:
            stream.stop()
            stream.close()


async def read_responses(ws, device=None, timeout: float = 60.0):
    """Read and display server responses, play TTS audio."""
    got_result = False  # Track whether we've received a terminal event

    try:
        while True:
            try:
                # Use longer timeout when waiting for remote results
                wait_timeout = 300.0 if not got_result else timeout
                msg = await asyncio.wait_for(ws.recv(), timeout=wait_timeout)
            except asyncio.TimeoutError:
                break

            data = json.loads(msg)
            msg_type = data.get("type")

            if msg_type == "transcription":
                status(SYM_LISTEN, f'"{data["text"]}"', newline=True)

            elif msg_type == "command":
                parts = [data["intent"]]
                if data.get("project"):
                    parts.append(data["project"])
                status(SYM_PROCESS, " > ".join(parts), newline=True)

            elif msg_type == "session_created":
                status(SYM_PROCESS, f"Terminal opened for {data.get('project', '?')}", newline=True)

            elif msg_type == "prompt_sent":
                status(SYM_PROCESS, "Sent to Claude", newline=True)

            # ── Remote control messages ──

            elif msg_type == "remote_enabled":
                status(SYM_PROCESS, f"Remote control ON for {data.get('project', '?')}", newline=True)

            elif msg_type == "remote_disabled":
                status(SYM_IDLE, "Back to normal mode", newline=True)

            elif msg_type == "remote_working":
                prompt = data.get("prompt", "?")
                status(SYM_PROCESS, f"Claude is working: {prompt[:60]}...", newline=True)

            elif msg_type == "remote_progress":
                pass  # TTS audio follows automatically

            elif msg_type == "remote_result":
                summary = data.get("summary", "Done.")
                files = data.get("files_created", []) + data.get("files_modified", [])
                if files:
                    names = ", ".join(f.split("/")[-1] for f in files[:4])
                    status(SYM_PROCESS, f"Changed: {names}", newline=True)
                duration = data.get("duration_ms")
                if duration:
                    status(SYM_PROCESS, f"Done in {duration / 1000:.1f}s", newline=True)
                got_result = True  # Next TTS is the final one

            # ── TTS audio ──

            elif msg_type == "tts_audio":
                audio_b64 = data.get("audio", "")
                if audio_b64:
                    wav_bytes = base64.b64decode(audio_b64)
                    status(SYM_PLAY, "Speaking...")
                    await asyncio.get_event_loop().run_in_executor(
                        None, lambda: play_wav_bytes(wav_bytes, device)
                    )
                # Only break on TTS after receiving a terminal event (result/error)
                # or for non-remote flows (which don't set remote_working)
                if got_result:
                    break

            elif msg_type == "error":
                status(SYM_PROCESS, f"Error: {data['message']}", newline=True)
                got_result = True  # Break after next TTS, or now if no TTS follows

            elif msg_type == "status":
                sessions = data.get("sessions", [])
                if not sessions:
                    status(SYM_IDLE, "No active sessions", newline=True)
                else:
                    status(SYM_IDLE, f"{len(sessions)} session(s):", newline=True)
                    for s in sessions:
                        name = s.get("project_name", "?")
                        remote = " [remote]" if s.get("remote_mode") else ""
                        active = " *" if s["session_id"] == data.get("active_session_id") else ""
                        print(f"       {s['session_id'][:8]} {name}: {s['status']}{remote}{active}")
                break

            elif msg_type in ("switched", "stopped", "info"):
                if "message" in data:
                    status(SYM_IDLE, data["message"], newline=True)
                break

    except Exception as e:
        status(SYM_PROCESS, f"Connection error: {e}", newline=True)


async def main():
    parser = argparse.ArgumentParser(description="GlassCode — voice-controlled Claude Code")
    parser.add_argument("--server", default="ws://localhost:8000/ws/voice", help="Server WebSocket URL")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    parser.add_argument("--device", type=int, default=None, help="Audio device index (input & output)")
    parser.add_argument("--threshold", type=float, default=0.01, help="VAD energy threshold (0-1)")
    parser.add_argument("--silence-ms", type=int, default=1500, help="Silence duration before sending (ms)")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return

    await run(args.server, device=args.device, threshold=args.threshold, silence_ms=args.silence_ms)


if __name__ == "__main__":
    asyncio.run(main())

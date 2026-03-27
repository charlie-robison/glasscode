# GlassCode

Voice-control Claude Code from your Meta Ray-Ban glasses. Talk to your glasses, and Claude writes your code.

## How It Works

```
Meta Ray-Ban Glasses  -->  iPhone (pocket relay)  -->  Mac (FastAPI server)  -->  Claude Code CLI
         mic/speaker          BT audio + WebSocket         STT / TTS / tmux          coding agent
```

You wear your glasses, say "Hey Claude, start working on my-project," and a Claude Code terminal opens on your Mac. From there you can dictate prompts, switch projects, check status, or flip into **remote control mode** where Claude works autonomously and speaks a summary of what it did back through your glasses.

The phone is a dumb pipe — it captures mic audio, forwards it over WebSocket, and plays back TTS. All the intelligence lives on the Mac.

## Two Modes

### Normal Mode (Interactive Terminal)
Claude runs in a visible Terminal window via tmux. You dictate prompts; they get typed in. You can glance at your screen to see Claude's full output.

### Remote Control Mode
Claude runs as a headless subprocess. The server captures structured JSON output, tracks file operations and commands, summarizes the result into a short sentence, and speaks it back through your glasses. You never need to look at a screen.

## Voice Commands

| Say this | What happens |
|---|---|
| "Hey Claude, start working on [project]" | Opens a Claude terminal for that project |
| "Hey Claude, [any prompt]" | Sends the prompt to the active session |
| "Hey Claude, new session for [project]" | Opens a parallel session for a different project |
| "Hey Claude, switch to [project]" | Changes the active session |
| "Hey Claude, status" | Reads back what Claude is doing |
| "Hey Claude, stop" | Kills the active session |
| "Hey Claude, remote control" | Enters remote mode (headless + TTS summaries) |
| "Hey Claude, back to normal" | Exits remote mode |

The wake word is forgiving — Whisper often hears "Hey Clod" or "Hey Cloud" and those work too.

## Features

- **Hands-free coding** — Dictate prompts and manage sessions entirely by voice through your glasses
- **Two operating modes** — Interactive terminal for when you're at your desk, remote control for when you're away from the screen
- **Multi-session support** — Run parallel Claude sessions across different projects and switch between them by voice
- **Fully local speech pipeline** — STT via faster-whisper and TTS via macOS `say`. No cloud APIs, no cost, no latency
- **Fuzzy project matching** — Say a project name roughly and Levenshtein distance matching finds the right one
- **Session continuity** — Remote mode preserves Claude's conversation context across prompts via `--resume`
- **Spoken result summaries** — In remote mode, Claude's output is parsed (files created/modified, commands run) and condensed into a natural spoken summary
- **Background operation** — Phone app stays active when pocketed via background audio mode

## Tech Stack

### Server (Python / FastAPI)

Located in `server/app/`. Handles the full pipeline on the Mac side:

- **FastAPI + WebSockets** — Audio pipeline via `/ws/voice` endpoint
- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — Local speech-to-text (tiny model, CPU-only, ~40MB, no API key)
- **macOS `say` command** — Text-to-speech (Samantha voice, 200 wpm, zero cost)
- **tmux** — Manages interactive Claude sessions. Opens Terminal.app windows via AppleScript, sends prompts via `tmux send-keys`
- **Subprocess management** — Remote mode runs `claude -p --output-format stream-json`, parses streaming JSON events to track file operations, commands, and assistant text
- **Command parser** — Wake word detection + regex-based intent extraction
- **Project discovery** — Scans configured directories for `.git` or `CLAUDE.md` markers, caches results, fuzzy-matches project names via Levenshtein distance
- **Output summarizer** — Condenses Claude's structured output into spoken summaries (max ~350 chars)

### Mobile App (React Native / Expo)

Located in `app/`. A minimal pocket relay with no business logic:

- **TypeScript, zero Swift code**
- **VAD-based recording** — Continuously monitors mic via expo-av metering, auto-records when speech is detected, sends on silence
- **WebSocket relay** — Streams 16kHz 16-bit mono PCM to the server
- **TTS playback queue** — Plays spoken summaries sequentially through glasses speakers
- **Background audio mode** — Stays active when the phone is pocketed
- **Minimal UI** — Color-coded status dot, relay state text, last event display, editable server URL

### Direct Bluetooth Client (Optional)

`server/glass_client.py` connects glasses directly to the Mac via Bluetooth, bypassing the phone entirely. Uses sounddevice + numpy for audio I/O with energy-based VAD. Useful for desk setups.

**No cloud dependencies for STT or TTS.** Everything runs locally on your Mac.

## Setup

### Prerequisites
- macOS (uses `say`, Terminal.app, tmux, AppleScript)
- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- Node.js (for the Expo app)
- Meta Ray-Ban glasses paired to your iPhone

### Server
```bash
cd server
./run.sh
```
This creates a virtual environment, installs dependencies, and starts the server on `0.0.0.0:8000`.

### Mobile App
```bash
cd app
npm install
npx expo start
```
Open in Expo Go on your iPhone. Tap the server URL field to point it at your Mac's IP.

### Direct Bluetooth (Optional)
If you'd rather skip the phone entirely, pair your glasses directly to your Mac via Bluetooth, set them as the audio input/output in System Settings, and run:
```bash
python server/glass_client.py --list-devices
python server/glass_client.py --device <id>
```

## Project Discovery

The server scans configurable root directories (default: `~/Desktop/Github/charlie-robison`) for directories containing `.git` or `CLAUDE.md`. When you say a project name, it fuzzy-matches against discovered projects using a three-stage strategy:

1. **Exact match** (case-insensitive)
2. **Substring match** (both directions)
3. **Levenshtein distance** (score >= 0.5)

So "glass code" matches `glasscode`, "swivel" matches `swivel`, etc.

## How Remote Mode Works

1. You say "Hey Claude, remote control" to enable it
2. You dictate a prompt
3. The server runs `claude -p --output-format stream-json` as a subprocess
4. It parses the streaming JSON to track files created/modified, commands run, and assistant text
5. It captures Claude's session ID from the stream for `--resume` continuity on the next prompt
6. It summarizes the result into a short spoken sentence (max ~350 chars)
7. TTS audio is sent to your phone and played through your glasses speakers
8. You hear something like: *"Done. I created index.html and modified three files. Two commands ran successfully."*

## Data Flow

```
Glasses Mic
    ↓ Bluetooth
iPhone App (useRelay hook)
    ├─ VAD detects speech → records 16kHz PCM
    └─ Sends audio via WebSocket binary + "transcribe" JSON
        ↓
Mac FastAPI Server
    ├─ faster-whisper transcribes audio → text
    ├─ Command parser extracts intent + project name
    └─ Dispatches to handler:
        │
        ├─ Interactive Mode:
        │   └─ tmux send-keys → prompt typed into terminal
        │
        └─ Remote Mode:
            └─ claude -p --output-format stream-json
            └─ Parse events → file ops, commands, text
            └─ Summarize → TTS via macOS say
            └─ Base64 WAV sent over WebSocket
                ↓
iPhone receives TTS audio
    └─ Queued playback → glasses speakers
```

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
| "Hey Claude, switch to [project]" | Changes the active session |
| "Hey Claude, status" | Reads back what Claude is doing |
| "Hey Claude, stop" | Kills the active session |
| "Hey Claude, remote control" | Enters remote mode (headless + TTS summaries) |
| "Hey Claude, back to normal" | Exits remote mode |

The wake word is forgiving — Whisper often hears "Hey Clod" or "Hey Cloud" and those work too.

## Tech Stack

**Server (Python)**
- FastAPI + WebSockets for the audio pipeline
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for local speech-to-text (no API key)
- macOS `say` command for text-to-speech (zero cost)
- tmux for managing interactive Claude sessions
- Fuzzy project name matching via Levenshtein distance

**Mobile App (React Native / Expo)**
- TypeScript, zero Swift code
- expo-av for mic capture with metering-based VAD
- Background audio mode so it works while pocketed
- TTS playback queue for multi-message remote responses

**No cloud dependencies for STT or TTS.** Everything runs locally on your Mac.

## Setup

### Prerequisites
- macOS (uses `say`, Terminal.app, tmux, AppleScript)
- Python 3.8+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- Node.js (for the Expo app)
- Meta Ray-Ban glasses paired to your iPhone

### Server
```bash
cd server
pip install -r requirements.txt
./run.sh
```
The server starts on `0.0.0.0:8000`.

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
python server/glass_client.py
```

## Project Discovery

The server scans `~/Desktop/Github/charlie-robison` for directories containing `.git` or `CLAUDE.md`. When you say a project name, it fuzzy-matches against discovered projects — so "glass code" matches `glasscode`, "swivel" matches `swivel`, etc.

## How Remote Mode Works

1. You say "Hey Claude, remote control" to enable it
2. You dictate a prompt
3. The server runs `claude -p --output-format stream-json` as a subprocess
4. It parses the streaming JSON to track files created/modified, commands run, and assistant text
5. It summarizes the result into a short spoken sentence (max ~350 chars)
6. TTS audio is sent to your phone and played through your glasses speakers
7. You hear something like: *"Done. I created index.html and modified three files. Two commands ran successfully."*

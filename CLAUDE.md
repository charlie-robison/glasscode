# GlassCode

Voice-control Claude Code from Meta Ray-Ban glasses.

## Architecture

```
Meta Glasses → iPhone (thin BT relay) → Mac (FastAPI server) → Claude Code CLI subprocesses
```

## Server (Python)

- FastAPI server in `server/app/`
- Run: `cd server && ./run.sh`
- Uses `claude -p --output-format stream-json --bare` for CLI interaction
- STT via faster-whisper (local, no API key)
- TTS via macOS `say` command (zero cost)
- WebSocket `/ws/voice` for audio relay from phone
- WebSocket `/ws/session/{id}` for streaming Claude output

## App (React Native Expo)

- Expo app in `app/`
- TypeScript, zero Swift code
- Thin relay: captures glasses mic audio via expo-av, sends to server over WebSocket
- Plays TTS audio back through glasses speakers
- Background audio mode keeps relay active when phone is pocketed

## Commands

| Voice | Action |
|---|---|
| "Hey Claude, start working on [project]" | Open project session |
| "Hey Claude, [any prompt]" | Send to active session |
| "Hey Claude, switch to [project]" | Change active session |
| "Hey Claude, status" | Read back session status |
| "Hey Claude, stop" | Stop active session |

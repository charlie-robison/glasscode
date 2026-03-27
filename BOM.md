# GlassCode — Bill of Materials

Complete list of hardware, software, and dependencies required to build and run GlassCode.

## Hardware

| Component | Purpose | Required |
|---|---|---|
| Meta Ray-Ban Smart Glasses | Mic input / speaker output | Yes (or any BT audio device) |
| iPhone | Bluetooth relay between glasses and Mac | Yes (or pair glasses directly to Mac) |
| Mac (Apple Silicon or Intel) | Runs FastAPI server, Claude Code CLI, STT, TTS | Yes |

## System Prerequisites (macOS)

| Tool | Version | Purpose | Install |
|---|---|---|---|
| macOS | 12+ | Host OS (uses `say`, Terminal.app, AppleScript) | — |
| Python | 3.8+ | Server runtime | `brew install python` |
| Node.js | 18+ | Expo / React Native tooling | `brew install node` |
| tmux | any | Manages interactive Claude terminal sessions | `brew install tmux` |
| Claude Code CLI | latest | AI coding agent | `npm install -g @anthropic-ai/claude-code` |
| Expo CLI | latest | React Native dev server | `npx expo` (comes with Expo SDK) |

## Server Dependencies (Python)

| Package | Version | Purpose | License |
|---|---|---|---|
| fastapi | >=0.110.0 | Async web framework, REST + WebSocket | MIT |
| uvicorn[standard] | >=0.29.0 | ASGI server | BSD-3 |
| websockets | >=12.0 | WebSocket protocol support | BSD-3 |
| faster-whisper | >=1.0.0 | Local speech-to-text (CTranslate2 backend) | MIT |
| python-Levenshtein | >=0.25.0 | Fuzzy project name matching | GPL-2.0 |
| python-multipart | >=0.0.9 | Multipart form data parsing | Apache-2.0 |
| sounddevice | >=0.5.0 | Direct audio I/O (optional, for glass_client.py) | MIT |
| numpy | >=1.26.0 | Numerical operations for Whisper | BSD-3 |

## Mobile App Dependencies (React Native / TypeScript)

### Production

| Package | Version | Purpose | License |
|---|---|---|---|
| expo | ~54.0.0 | React Native framework | MIT |
| expo-av | ~15.0.0 | Audio recording & playback with metering | MIT |
| expo-file-system | ~18.0.0 | File I/O for audio caching | MIT |
| expo-keep-awake | ~14.0.0 | Prevents screen sleep while relaying | MIT |
| react | 18.3.1 | UI library | MIT |
| react-native | 0.77.0 | Mobile UI framework | MIT |
| @react-native-async-storage/async-storage | 2.1.0 | Persistent key-value storage (server URL) | MIT |

### Development

| Package | Version | Purpose | License |
|---|---|---|---|
| @types/react | ~18.3.0 | TypeScript type definitions | MIT |
| typescript | ~5.3.0 | Type-safe JavaScript | Apache-2.0 |

## macOS System Utilities (No Install Needed)

| Utility | Purpose |
|---|---|
| `say` | Text-to-speech (Samantha voice, 200 WPM) |
| Terminal.app | Hosts Claude Code interactive sessions |
| AppleScript (`osascript`) | Opens/focuses Terminal windows |

## AI Models

| Model | Runs On | Purpose |
|---|---|---|
| Whisper "tiny" | Local CPU (via faster-whisper / CTranslate2) | Speech-to-text |
| Claude (via Claude Code CLI) | Anthropic API | Code generation agent |

## Network / Ports

| Port | Protocol | Purpose |
|---|---|---|
| 8000 | HTTP + WebSocket | FastAPI server (phone connects here) |

## iOS App Entitlements

| Entitlement | Purpose |
|---|---|
| `UIBackgroundModes: audio` | Keeps relay active when phone is pocketed |
| Microphone permission | Captures glasses mic audio via expo-av |

## Cost

| Component | Cost |
|---|---|
| Speech-to-text | Free (local Whisper) |
| Text-to-speech | Free (macOS `say`) |
| Claude Code | Anthropic API usage (requires active plan) |
| Meta Ray-Ban Glasses | ~$299 retail |

/**
 * useRelay — unified hook for the GlassCode pocket relay.
 *
 * Combines WebSocket, VAD recording, and TTS playback into one hook.
 * Designed for hands-free, phone-in-pocket operation with Meta glasses.
 *
 * Flow: always recording with metering → VAD detects speech end →
 * stop recording, send audio → start new recording → repeat.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { Audio, InterruptionModeIOS } from "expo-av";
import * as FileSystem from "expo-file-system";

// ── Types ──

export type ConnectionStatus = "disconnected" | "connecting" | "connected";
export type RelayStatus =
  | "listening"
  | "recording"
  | "processing"
  | "working"
  | "playing";

export interface FileDiff {
  file_path: string;
  action: "created" | "modified";
  old_string?: string;
  new_string?: string;
  content?: string;
}

export interface RemoteResult {
  summary: string;
  files_created: string[];
  files_modified: string[];
  file_diffs: FileDiff[];
  commands_run: string[];
  duration_ms: number | null;
  error: string | null;
  pr_url: string | null;
  git_pushed: boolean;
}

interface RelayState {
  connectionStatus: ConnectionStatus;
  relayStatus: RelayStatus;
  lastEvent: string;
  lastResult: RemoteResult | null;
  clearResult: () => void;
}

// ── Constants ──

const RECONNECT_MS = 3000;
const VAD_POLL_MS = 100;
const VAD_THRESHOLD = 0.02;
const SILENCE_TIMEOUT_MS = 1500;
const MIN_SPEECH_DURATION_MS = 400;

const RECORDING_OPTIONS: Audio.RecordingOptions = {
  isMeteringEnabled: true,
  android: {
    extension: ".wav",
    outputFormat: 0,
    audioEncoder: 0,
    sampleRate: 16000,
    numberOfChannels: 1,
    bitRate: 256000,
  },
  ios: {
    extension: ".wav",
    outputFormat: Audio.IOSOutputFormat.LINEARPCM,
    audioQuality: Audio.IOSAudioQuality.MAX,
    sampleRate: 16000,
    numberOfChannels: 1,
    bitRate: 256000,
    linearPCMBitDepth: 16,
    linearPCMIsBigEndian: false,
    linearPCMIsFloat: false,
  },
  web: { mimeType: "audio/wav", bitsPerSecond: 256000 },
};

// ── Hook ──

export function useRelay(serverUrl: string): RelayState {
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("disconnected");
  const [relayStatus, setRelayStatus] = useState<RelayStatus>("listening");
  const [lastEvent, setLastEvent] = useState("Waiting for connection...");
  const [lastResult, setLastResult] = useState<RemoteResult | null>(null);

  const clearResult = useCallback(() => setLastResult(null), []);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const activeRecording = useRef<Audio.Recording | null>(null);
  const vadTimer = useRef<ReturnType<typeof setInterval>>();
  const silenceTimer = useRef<ReturnType<typeof setTimeout>>();
  const speechStartTime = useRef<number>(0);
  const isSpeaking = useRef(false);
  const isPaused = useRef(false); // Pause VAD during processing/playback
  const ttsQueue = useRef<string[]>([]);
  const isPlayingTTS = useRef(false);

  // ── Audio mode helpers ──

  const setRecordingMode = useCallback(async () => {
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: true,
      playsInSilentModeIOS: true,
      interruptionModeIOS: InterruptionModeIOS.DoNotMix,
    });
  }, []);

  const setPlaybackMode = useCallback(async () => {
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: false,
      playsInSilentModeIOS: true,
      interruptionModeIOS: InterruptionModeIOS.DoNotMix,
    });
  }, []);

  // ── WebSocket ──

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    setConnectionStatus("connecting");

    const ws = new WebSocket(serverUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnectionStatus("connected");
      setLastEvent("Connected. Listening...");
      startListening();
    };

    ws.onmessage = (event: WebSocketMessageEvent) => {
      if (typeof event.data !== "string") return;
      try {
        const data = JSON.parse(event.data);
        handleMessage(data);
      } catch {
        // ignore non-JSON
      }
    };

    ws.onclose = () => {
      setConnectionStatus("disconnected");
      setLastEvent("Disconnected. Reconnecting...");
      wsRef.current = null;
      stopListening();
      reconnectTimer.current = setTimeout(connect, RECONNECT_MS);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [serverUrl]);

  // ── Server message handling ──

  const handleMessage = useCallback((data: Record<string, unknown>) => {
    const type = data.type as string;

    switch (type) {
      case "transcription":
        setLastEvent(`"${data.text}"`);
        break;
      case "command":
        setLastEvent(
          `${data.intent}${data.project ? ` > ${data.project}` : ""}`
        );
        break;
      case "session_created":
        setLastEvent(`Session: ${data.project}`);
        break;
      case "prompt_sent":
        setLastEvent("Sent to Claude");
        break;
      case "remote_enabled":
        setLastEvent(`Remote ON: ${data.project}`);
        break;
      case "remote_disabled":
        setLastEvent("Back to normal");
        break;
      case "remote_working":
        setRelayStatus("working");
        setLastEvent("Claude is working...");
        break;
      case "remote_progress":
        break; // TTS follows
      case "remote_result": {
        const summary = (data.summary as string) || "Done.";
        setLastEvent(summary.slice(0, 100));
        setLastResult({
          summary,
          files_created: (data.files_created as string[]) || [],
          files_modified: (data.files_modified as string[]) || [],
          file_diffs: (data.file_diffs as FileDiff[]) || [],
          commands_run: (data.commands_run as string[]) || [],
          duration_ms: (data.duration_ms as number) ?? null,
          error: (data.error as string) ?? null,
          pr_url: (data.pr_url as string) ?? null,
          git_pushed: (data.git_pushed as boolean) || false,
        });
        break;
      }
      case "tts_audio": {
        const audio = data.audio as string;
        if (audio) {
          ttsQueue.current.push(audio);
          playNextTTS();
        }
        break;
      }
      case "error":
        setLastEvent(`Error: ${data.message}`);
        break;
      case "status": {
        const sessions = data.sessions as Array<Record<string, unknown>>;
        setLastEvent(
          sessions?.length
            ? `${sessions.length} session(s) active`
            : "No sessions"
        );
        break;
      }
      default:
        if (data.message) setLastEvent(data.message as string);
        break;
    }
  }, []);

  // ── TTS playback (sequential queue) ──

  const playNextTTS = useCallback(async () => {
    if (isPlayingTTS.current) return;
    const b64 = ttsQueue.current.shift();
    if (!b64) {
      // Queue empty — resume listening
      isPlayingTTS.current = false;
      resumeListening();
      return;
    }

    isPlayingTTS.current = true;
    setRelayStatus("playing");
    isPaused.current = true;

    // Stop any active recording before switching to playback mode
    await stopRecording(false);

    try {
      await setPlaybackMode();

      const uri = FileSystem.cacheDirectory + `tts_${Date.now()}.wav`;
      await FileSystem.writeAsStringAsync(uri, b64, {
        encoding: FileSystem.EncodingType.Base64,
      });

      const { sound } = await Audio.Sound.createAsync({ uri });
      sound.setOnPlaybackStatusUpdate((status) => {
        if ("didJustFinish" in status && status.didJustFinish) {
          sound.unloadAsync();
          FileSystem.deleteAsync(uri, { idempotent: true });
          isPlayingTTS.current = false;

          if (ttsQueue.current.length > 0) {
            playNextTTS();
          } else {
            resumeListening();
          }
        }
      });
      await sound.playAsync();
    } catch (e) {
      console.error("TTS playback error:", e);
      isPlayingTTS.current = false;
      resumeListening();
    }
  }, []);

  // ── Recording + VAD ──

  const startListening = useCallback(async () => {
    isPaused.current = false;
    setRelayStatus("listening");

    try {
      await setRecordingMode();
      await startNewRecording();
      startVADPolling();
    } catch (e) {
      console.error("Start listening error:", e);
    }
  }, []);

  const resumeListening = useCallback(async () => {
    isPaused.current = false;
    setRelayStatus("listening");

    try {
      await setRecordingMode();
      await startNewRecording();
      startVADPolling();
    } catch (e) {
      console.error("Resume listening error:", e);
    }
  }, []);

  const stopListening = useCallback(() => {
    isPaused.current = true;
    stopVADPolling();
    stopRecording(false);
  }, []);

  const startNewRecording = useCallback(async () => {
    if (activeRecording.current) {
      await activeRecording.current.stopAndUnloadAsync().catch(() => {});
      activeRecording.current = null;
    }

    const recording = new Audio.Recording();
    await recording.prepareToRecordAsync(RECORDING_OPTIONS);
    await recording.startAsync();
    activeRecording.current = recording;
  }, []);

  const stopRecording = useCallback(
    async (sendAudio: boolean) => {
      const recording = activeRecording.current;
      if (!recording) return;
      activeRecording.current = null;

      try {
        const status = await recording.getStatusAsync();
        if (!status.isRecording) return;

        await recording.stopAndUnloadAsync();

        if (sendAudio) {
          const uri = recording.getURI();
          if (uri) {
            await sendAudioToServer(uri);
            await FileSystem.deleteAsync(uri, { idempotent: true });
          }
        }
      } catch (e) {
        console.error("Stop recording error:", e);
      }
    },
    []
  );

  const startVADPolling = useCallback(() => {
    stopVADPolling();
    vadTimer.current = setInterval(async () => {
      if (isPaused.current || !activeRecording.current) return;

      try {
        const status = await activeRecording.current.getStatusAsync();
        if (!status.isRecording) return;

        const metering = status.metering ?? -160;
        const energy = Math.pow(10, metering / 20);

        if (energy > VAD_THRESHOLD) {
          if (!isSpeaking.current) {
            isSpeaking.current = true;
            speechStartTime.current = Date.now();
            setRelayStatus("recording");
          }
          // Clear silence timer — still speaking
          if (silenceTimer.current) {
            clearTimeout(silenceTimer.current);
            silenceTimer.current = undefined;
          }
        } else if (isSpeaking.current && !silenceTimer.current) {
          // Start silence countdown
          silenceTimer.current = setTimeout(async () => {
            silenceTimer.current = undefined;
            isSpeaking.current = false;

            const speechDuration = Date.now() - speechStartTime.current;
            if (speechDuration < MIN_SPEECH_DURATION_MS) {
              // Too short — ignore and keep listening
              setRelayStatus("listening");
              return;
            }

            // Speech ended — stop recording, send audio, start new recording
            isPaused.current = true;
            stopVADPolling();
            setRelayStatus("processing");
            await stopRecording(true);

            // If no TTS is expected to resume us, restart listening
            // (The server will send TTS which triggers resumeListening)
            // Give it a moment to see if TTS comes back
            setTimeout(() => {
              if (!isPlayingTTS.current && isPaused.current) {
                resumeListening();
              }
            }, 5000);
          }, SILENCE_TIMEOUT_MS);
        }
      } catch {
        // Recording may have been stopped
      }
    }, VAD_POLL_MS);
  }, []);

  const stopVADPolling = useCallback(() => {
    if (vadTimer.current) {
      clearInterval(vadTimer.current);
      vadTimer.current = undefined;
    }
    if (silenceTimer.current) {
      clearTimeout(silenceTimer.current);
      silenceTimer.current = undefined;
    }
    isSpeaking.current = false;
  }, []);

  // ── Send audio to server ──

  const sendAudioToServer = useCallback(async (uri: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    try {
      const b64 = await FileSystem.readAsStringAsync(uri, {
        encoding: FileSystem.EncodingType.Base64,
      });

      // Convert base64 to binary ArrayBuffer
      const binaryString = atob(b64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      ws.send(bytes.buffer);
      ws.send(JSON.stringify({ action: "transcribe" }));
    } catch (e) {
      console.error("Send audio error:", e);
    }
  }, []);

  // ── Lifecycle ──

  useEffect(() => {
    Audio.requestPermissionsAsync();
    connect();

    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      stopListening();
      wsRef.current?.close();
    };
  }, [serverUrl]);

  return { connectionStatus, relayStatus, lastEvent, lastResult, clearResult };
}

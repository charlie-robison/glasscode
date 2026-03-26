import React, { useCallback, useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useWebSocket, ServerMessage } from "../hooks/useWebSocket";
import { useAudioRelay } from "../hooks/useAudioRelay";
import { useVoiceActivation } from "../hooks/useVoiceActivation";

const DEFAULT_SERVER = "ws://192.168.1.100:8000/ws/voice";

export default function HomeScreen() {
  const [serverUrl, setServerUrl] = useState(DEFAULT_SERVER);
  const [logs, setLogs] = useState<string[]>([]);
  const [vadEnabled, setVadEnabled] = useState(false);

  // Load saved server URL
  React.useEffect(() => {
    AsyncStorage.getItem("serverUrl").then((url) => {
      if (url) setServerUrl(url);
    });
  }, []);

  const addLog = useCallback((msg: string) => {
    setLogs((prev) => [...prev.slice(-50), msg]); // Keep last 50 logs
  }, []);

  const handleMessage = useCallback(
    (msg: ServerMessage) => {
      switch (msg.type) {
        case "transcription":
          addLog(`[STT] ${msg.text}`);
          break;
        case "command":
          addLog(`[CMD] ${msg.intent}${msg.project ? ` → ${msg.project}` : ""}`);
          break;
        case "claude_output":
          const chunk = msg.data;
          if (chunk?.type === "assistant") {
            const content = chunk.message?.content;
            if (Array.isArray(content)) {
              for (const block of content) {
                if (block?.type === "text") {
                  addLog(`[Claude] ${block.text.slice(0, 100)}`);
                }
              }
            }
          }
          break;
        case "tts_audio":
          addLog("[TTS] Playing response...");
          playTTSAudio(msg.audio);
          break;
        case "error":
          addLog(`[ERR] ${msg.message}`);
          break;
        case "session_created":
          addLog(`[Session] Created: ${msg.project}`);
          break;
        default:
          addLog(`[${msg.type}] ${JSON.stringify(msg).slice(0, 80)}`);
      }
    },
    [addLog]
  );

  const { status, sendBinary, sendJSON } = useWebSocket({
    serverUrl,
    onMessage: handleMessage,
  });

  const { isRecording, startRecording, stopRecording, playTTSAudio } =
    useAudioRelay({ sendBinary, sendJSON });

  // Voice activation (hands-free mode)
  const { isSpeaking } = useVoiceActivation({
    enabled: vadEnabled && !isRecording,
    onSpeechStart: () => {
      addLog("[VAD] Speech detected — recording...");
      startRecording();
    },
    onSpeechEnd: () => {
      addLog("[VAD] Silence — sending for transcription...");
      stopRecording();
    },
  });

  const statusColor =
    status === "connected" ? "#00ff88" : status === "connecting" ? "#ffaa00" : "#ff4444";

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>GlassCode</Text>
        <View style={styles.statusRow}>
          <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
          <Text style={styles.statusText}>{status}</Text>
        </View>
      </View>

      {/* Big tap-to-talk button */}
      <Pressable
        onPressIn={startRecording}
        onPressOut={stopRecording}
        style={({ pressed }) => [
          styles.talkButton,
          isRecording && styles.talkButtonActive,
          pressed && styles.talkButtonPressed,
        ]}
      >
        <Text style={styles.talkButtonText}>
          {isRecording ? "Listening..." : "Hold to Talk"}
        </Text>
        <Text style={styles.talkButtonSub}>
          {vadEnabled ? "VAD: ON (hands-free)" : "or enable hands-free below"}
        </Text>
      </Pressable>

      {/* VAD toggle */}
      <Pressable
        onPress={() => setVadEnabled((v) => !v)}
        style={[styles.vadToggle, vadEnabled && styles.vadToggleActive]}
      >
        <Text style={styles.vadToggleText}>
          {vadEnabled ? "Hands-Free: ON" : "Hands-Free: OFF"}
        </Text>
      </Pressable>

      {/* Log output */}
      <ScrollView style={styles.logScroll} ref={(ref) => ref?.scrollToEnd()}>
        {logs.map((log, i) => (
          <Text key={i} style={styles.logLine}>
            {log}
          </Text>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    backgroundColor: "#0a0a0a",
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 20,
    marginTop: 10,
  },
  title: {
    fontSize: 24,
    fontWeight: "bold",
    color: "#ffffff",
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  statusDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  statusText: {
    color: "#888",
    fontSize: 14,
  },
  talkButton: {
    backgroundColor: "#1a1a2e",
    borderRadius: 20,
    paddingVertical: 60,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
    borderWidth: 2,
    borderColor: "#333",
  },
  talkButtonActive: {
    backgroundColor: "#0f3d0f",
    borderColor: "#00ff88",
  },
  talkButtonPressed: {
    opacity: 0.8,
  },
  talkButtonText: {
    color: "#ffffff",
    fontSize: 22,
    fontWeight: "600",
  },
  talkButtonSub: {
    color: "#666",
    fontSize: 13,
    marginTop: 8,
  },
  vadToggle: {
    backgroundColor: "#1a1a2e",
    borderRadius: 12,
    padding: 14,
    alignItems: "center",
    marginBottom: 16,
    borderWidth: 1,
    borderColor: "#333",
  },
  vadToggleActive: {
    backgroundColor: "#1a2e1a",
    borderColor: "#00ff88",
  },
  vadToggleText: {
    color: "#ccc",
    fontSize: 15,
    fontWeight: "500",
  },
  logScroll: {
    flex: 1,
    backgroundColor: "#111",
    borderRadius: 12,
    padding: 12,
  },
  logLine: {
    color: "#8f8",
    fontSize: 12,
    fontFamily: "Courier",
    marginBottom: 4,
  },
});

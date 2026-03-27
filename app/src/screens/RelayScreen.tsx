/**
 * RelayScreen — minimal pocket-friendly UI.
 *
 * Designed to be glanced at once (confirm connection), then pocketed.
 * Shows: connection status, relay state, last event, editable server URL.
 */

import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  SafeAreaView,
  TouchableOpacity,
  Keyboard,
  KeyboardAvoidingView,
  ScrollView,
  Platform,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useRelay, ConnectionStatus, RelayStatus } from "../hooks/useRelay";

const DEFAULT_SERVER = "ws://192.168.1.100:8000/ws/voice";
const STORAGE_KEY = "glasscode_server_url";

const STATUS_COLORS: Record<ConnectionStatus, string> = {
  connected: "#00ff88",
  connecting: "#ffaa00",
  disconnected: "#ff4444",
};

const RELAY_LABELS: Record<RelayStatus, string> = {
  listening: "Listening...",
  recording: "Hearing you...",
  processing: "Processing...",
  working: "Claude is working...",
  playing: "Speaking...",
};

export default function RelayScreen() {
  const [serverUrl, setServerUrl] = useState(DEFAULT_SERVER);
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState("");
  const [loaded, setLoaded] = useState(false);

  // Load saved server URL
  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY).then((saved) => {
      if (saved) setServerUrl(saved);
      setLoaded(true);
    });
  }, []);

  const { connectionStatus, relayStatus, lastEvent } = useRelay(
    loaded ? serverUrl : ""
  );

  const saveUrl = () => {
    const url = editValue.trim();
    if (url) {
      setServerUrl(url);
      AsyncStorage.setItem(STORAGE_KEY, url);
    }
    setEditing(false);
    Keyboard.dismiss();
  };

  const dotColor = STATUS_COLORS[connectionStatus];

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
        >
          {/* Title */}
          <Text style={styles.title}>GlassCode</Text>
          <Text style={styles.subtitle}>Pocket Relay</Text>

          {/* Big status indicator */}
          <View style={styles.statusCircle}>
            <View
              style={[
                styles.dot,
                {
                  backgroundColor: dotColor,
                  shadowColor: dotColor,
                },
              ]}
            />
          </View>

          {/* Relay status */}
          <Text style={[styles.relayStatus, { color: dotColor }]}>
            {connectionStatus === "connected"
              ? RELAY_LABELS[relayStatus]
              : connectionStatus === "connecting"
              ? "Connecting..."
              : "Disconnected"}
          </Text>

          {/* Last event */}
          <Text style={styles.lastEvent} numberOfLines={3}>
            {lastEvent}
          </Text>

          {/* Server URL — tap to edit */}
          {editing ? (
            <View style={styles.editRow}>
              <TextInput
                style={styles.input}
                value={editValue}
                onChangeText={setEditValue}
                autoFocus
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
                returnKeyType="done"
                onSubmitEditing={saveUrl}
                placeholderTextColor="#555"
                placeholder="ws://ip:port/ws/voice"
              />
              <TouchableOpacity onPress={saveUrl} style={styles.saveBtn}>
                <Text style={styles.saveBtnText}>Save</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity
              onPress={() => {
                setEditValue(serverUrl);
                setEditing(true);
              }}
            >
              <Text style={styles.serverUrl}>{serverUrl}</Text>
            </TouchableOpacity>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0a0a0a",
  },
  flex: {
    flex: 1,
  },
  content: {
    flexGrow: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
    paddingVertical: 48,
  },
  title: {
    fontSize: 28,
    fontWeight: "700",
    color: "#fff",
    letterSpacing: 1,
  },
  subtitle: {
    fontSize: 14,
    color: "#666",
    marginBottom: 48,
  },
  statusCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: "#1a1a1a",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 24,
  },
  dot: {
    width: 32,
    height: 32,
    borderRadius: 16,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 12,
  },
  relayStatus: {
    fontSize: 18,
    fontWeight: "600",
    marginBottom: 12,
  },
  lastEvent: {
    fontSize: 14,
    color: "#888",
    textAlign: "center",
    marginBottom: 48,
    lineHeight: 20,
    minHeight: 60,
  },
  serverUrl: {
    fontSize: 12,
    color: "#444",
    textDecorationLine: "underline",
  },
  editRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  input: {
    flex: 1,
    fontSize: 13,
    color: "#fff",
    borderWidth: 1,
    borderColor: "#333",
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: "#111",
  },
  saveBtn: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: "#00ff88",
    borderRadius: 8,
  },
  saveBtnText: {
    color: "#000",
    fontWeight: "600",
    fontSize: 13,
  },
});

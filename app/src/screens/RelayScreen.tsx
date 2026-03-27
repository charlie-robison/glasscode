/**
 * RelayScreen — minimal pocket-friendly UI with results panel.
 *
 * Shows: connection status, relay state, last event, editable server URL.
 * After a remote result: shows file changes (tappable for diffs) and PR links.
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
  Linking,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  useRelay,
  ConnectionStatus,
  RelayStatus,
  FileDiff,
} from "../hooks/useRelay";

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
  const [expandedFile, setExpandedFile] = useState<string | null>(null);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY).then((saved) => {
      if (saved) setServerUrl(saved);
      setLoaded(true);
    });
  }, []);

  const { connectionStatus, relayStatus, lastEvent, lastResult, clearResult } =
    useRelay(loaded ? serverUrl : "");

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
  const basename = (p: string) => p.split("/").pop() || p;

  // Group diffs by file
  const diffsByFile: Record<string, FileDiff[]> = {};
  if (lastResult) {
    for (const d of lastResult.file_diffs) {
      const key = d.file_path;
      if (!diffsByFile[key]) diffsByFile[key] = [];
      diffsByFile[key].push(d);
    }
  }

  const allFiles = lastResult
    ? [
        ...lastResult.files_created.map((f) => ({ path: f, action: "created" as const })),
        ...lastResult.files_modified.map((f) => ({ path: f, action: "modified" as const })),
      ]
    : [];

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          {/* Header */}
          <View style={styles.header}>
            <Text style={styles.title}>GlassCode</Text>
            <Text style={styles.subtitle}>Pocket Relay</Text>
          </View>

          {/* Status dot */}
          <View style={styles.statusCircle}>
            <View
              style={[
                styles.dot,
                { backgroundColor: dotColor, shadowColor: dotColor },
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

          {/* ── Results panel ── */}
          {lastResult && (
            <View style={styles.resultPanel}>
              {/* Dismiss */}
              <TouchableOpacity
                style={styles.dismissBtn}
                onPress={() => {
                  clearResult();
                  setExpandedFile(null);
                }}
              >
                <Text style={styles.dismissText}>Clear</Text>
              </TouchableOpacity>

              {/* Summary */}
              <Text style={styles.resultSummary}>{lastResult.summary}</Text>

              {/* Duration */}
              {lastResult.duration_ms && (
                <Text style={styles.resultMeta}>
                  {(lastResult.duration_ms / 1000).toFixed(1)}s
                </Text>
              )}

              {/* PR link */}
              {lastResult.pr_url && (
                <TouchableOpacity
                  style={styles.prLink}
                  onPress={() => Linking.openURL(lastResult.pr_url!)}
                >
                  <Text style={styles.prLinkText}>
                    View Pull Request
                  </Text>
                </TouchableOpacity>
              )}

              {/* File list */}
              {allFiles.length > 0 && (
                <View style={styles.fileList}>
                  <Text style={styles.fileListTitle}>Files Changed</Text>
                  {allFiles.map(({ path, action }) => (
                    <View key={path}>
                      <TouchableOpacity
                        style={styles.fileRow}
                        onPress={() =>
                          setExpandedFile(
                            expandedFile === path ? null : path
                          )
                        }
                      >
                        <Text
                          style={[
                            styles.fileAction,
                            {
                              color:
                                action === "created" ? "#00ff88" : "#ffaa00",
                            },
                          ]}
                        >
                          {action === "created" ? "+" : "~"}
                        </Text>
                        <Text style={styles.fileName} numberOfLines={1}>
                          {basename(path)}
                        </Text>
                        <Text style={styles.fileChevron}>
                          {expandedFile === path ? "v" : ">"}
                        </Text>
                      </TouchableOpacity>

                      {/* Expanded diff */}
                      {expandedFile === path && diffsByFile[path] && (
                        <View style={styles.diffBox}>
                          {diffsByFile[path].map((diff, i) =>
                            diff.action === "created" ? (
                              <View key={i}>
                                <Text style={styles.diffLabel}>
                                  New file
                                </Text>
                                <Text style={styles.diffAdded}>
                                  {(diff.content || "").slice(0, 1000)}
                                </Text>
                              </View>
                            ) : (
                              <View key={i}>
                                {diff.old_string && (
                                  <>
                                    <Text style={styles.diffLabel}>
                                      Removed
                                    </Text>
                                    <Text style={styles.diffRemoved}>
                                      {diff.old_string.slice(0, 500)}
                                    </Text>
                                  </>
                                )}
                                {diff.new_string && (
                                  <>
                                    <Text style={styles.diffLabel}>
                                      Added
                                    </Text>
                                    <Text style={styles.diffAdded}>
                                      {diff.new_string.slice(0, 500)}
                                    </Text>
                                  </>
                                )}
                              </View>
                            )
                          )}
                        </View>
                      )}
                    </View>
                  ))}
                </View>
              )}
            </View>
          )}

          {/* Server URL */}
          <View style={styles.urlSection}>
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
          </View>
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
  scrollContent: {
    flexGrow: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 24,
    paddingVertical: 48,
  },
  header: {
    alignItems: "center",
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
    marginBottom: 36,
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
    marginBottom: 8,
  },
  lastEvent: {
    fontSize: 14,
    color: "#888",
    textAlign: "center",
    marginBottom: 24,
    lineHeight: 20,
    minHeight: 40,
  },

  // ── Results panel ──
  resultPanel: {
    width: "100%",
    backgroundColor: "#111",
    borderRadius: 12,
    padding: 16,
    marginBottom: 24,
    borderWidth: 1,
    borderColor: "#222",
  },
  dismissBtn: {
    position: "absolute",
    top: 8,
    right: 12,
    zIndex: 1,
  },
  dismissText: {
    color: "#555",
    fontSize: 12,
  },
  resultSummary: {
    color: "#ccc",
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 8,
    paddingRight: 40,
  },
  resultMeta: {
    color: "#555",
    fontSize: 12,
    marginBottom: 12,
  },

  // PR link
  prLink: {
    backgroundColor: "#1a3a2a",
    borderRadius: 8,
    paddingVertical: 10,
    paddingHorizontal: 16,
    marginBottom: 12,
    alignItems: "center",
  },
  prLinkText: {
    color: "#00ff88",
    fontWeight: "600",
    fontSize: 14,
  },

  // File list
  fileList: {
    marginTop: 4,
  },
  fileListTitle: {
    color: "#666",
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 1,
    marginBottom: 8,
  },
  fileRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "#1a1a1a",
  },
  fileAction: {
    fontSize: 16,
    fontWeight: "700",
    width: 20,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
  fileName: {
    flex: 1,
    color: "#aaa",
    fontSize: 13,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
  fileChevron: {
    color: "#555",
    fontSize: 12,
    marginLeft: 8,
  },

  // Diff view
  diffBox: {
    backgroundColor: "#0d0d0d",
    borderRadius: 8,
    padding: 12,
    marginTop: 4,
    marginBottom: 8,
  },
  diffLabel: {
    color: "#666",
    fontSize: 10,
    textTransform: "uppercase",
    letterSpacing: 1,
    marginBottom: 4,
    marginTop: 8,
  },
  diffRemoved: {
    color: "#ff6b6b",
    fontSize: 11,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    lineHeight: 16,
  },
  diffAdded: {
    color: "#00ff88",
    fontSize: 11,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    lineHeight: 16,
  },

  // Server URL
  urlSection: {
    width: "100%",
    alignItems: "center",
    marginTop: 8,
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
    width: "100%",
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

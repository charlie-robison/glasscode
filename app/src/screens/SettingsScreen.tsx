import React, { useEffect, useState } from "react";
import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

interface SettingsScreenProps {
  onSave?: (serverUrl: string) => void;
}

export default function SettingsScreen({ onSave }: SettingsScreenProps) {
  const [serverIp, setServerIp] = useState("192.168.1.100");
  const [serverPort, setServerPort] = useState("8000");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem("serverUrl").then((url) => {
      if (url) {
        const match = url.match(/ws:\/\/([\d.]+):(\d+)/);
        if (match) {
          setServerIp(match[1]);
          setServerPort(match[2]);
        }
      }
    });
  }, []);

  const handleSave = async () => {
    const url = `ws://${serverIp}:${serverPort}/ws/voice`;
    await AsyncStorage.setItem("serverUrl", url);
    setSaved(true);
    onSave?.(url);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Server Settings</Text>

      <Text style={styles.label}>Server IP</Text>
      <TextInput
        style={styles.input}
        value={serverIp}
        onChangeText={setServerIp}
        placeholder="192.168.1.100"
        placeholderTextColor="#555"
        keyboardType="numbers-and-punctuation"
        autoCapitalize="none"
        autoCorrect={false}
      />

      <Text style={styles.label}>Port</Text>
      <TextInput
        style={styles.input}
        value={serverPort}
        onChangeText={setServerPort}
        placeholder="8000"
        placeholderTextColor="#555"
        keyboardType="number-pad"
      />

      <Text style={styles.urlPreview}>
        ws://{serverIp}:{serverPort}/ws/voice
      </Text>

      <Pressable onPress={handleSave} style={styles.saveButton}>
        <Text style={styles.saveButtonText}>
          {saved ? "Saved!" : "Save"}
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    backgroundColor: "#0a0a0a",
  },
  title: {
    fontSize: 22,
    fontWeight: "bold",
    color: "#ffffff",
    marginBottom: 30,
    marginTop: 10,
  },
  label: {
    color: "#888",
    fontSize: 14,
    marginBottom: 6,
    marginTop: 16,
  },
  input: {
    backgroundColor: "#1a1a2e",
    borderRadius: 10,
    padding: 14,
    color: "#fff",
    fontSize: 16,
    borderWidth: 1,
    borderColor: "#333",
  },
  urlPreview: {
    color: "#555",
    fontSize: 12,
    marginTop: 16,
    fontFamily: "Courier",
  },
  saveButton: {
    backgroundColor: "#00ff88",
    borderRadius: 12,
    padding: 16,
    alignItems: "center",
    marginTop: 30,
  },
  saveButtonText: {
    color: "#000",
    fontSize: 16,
    fontWeight: "600",
  },
});

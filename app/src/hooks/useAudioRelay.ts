import { useCallback, useRef, useState } from "react";
import { Audio } from "expo-av";
import * as FileSystem from "expo-file-system";

interface UseAudioRelayOptions {
  sendBinary: (data: ArrayBuffer) => void;
  sendJSON: (data: Record<string, any>) => void;
}

export function useAudioRelay({ sendBinary, sendJSON }: UseAudioRelayOptions) {
  const [isRecording, setIsRecording] = useState(false);
  const recordingRef = useRef<Audio.Recording | null>(null);

  const startRecording = useCallback(async () => {
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) return;

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
        // iOS routes audio through connected Bluetooth device (Meta glasses)
        interruptionModeIOS: 1, // DoNotMix
      });

      const { recording } = await Audio.Recording.createAsync({
        isMeteringEnabled: false,
        android: {
          extension: ".wav",
          outputFormat: 2, // THREE_GPP — overridden below
          audioEncoder: 1, // AMR_NB — overridden below
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 256000,
        },
        ios: {
          extension: ".wav",
          outputFormat: "linearPCM",
          audioQuality: 127, // max
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 256000,
          linearPCMBitDepth: 16,
          linearPCMIsBigEndian: false,
          linearPCMIsFloat: false,
        },
        web: {
          mimeType: "audio/wav",
          bitsPerSecond: 256000,
        },
      });

      recordingRef.current = recording;
      setIsRecording(true);
    } catch (err) {
      console.error("Failed to start recording:", err);
    }
  }, []);

  const stopRecording = useCallback(async () => {
    const recording = recordingRef.current;
    if (!recording) return;

    try {
      setIsRecording(false);
      await recording.stopAndUnloadAsync();

      const uri = recording.getURI();
      if (uri) {
        // Read the WAV file as base64 and convert to binary
        const base64 = await FileSystem.readAsStringAsync(uri, {
          encoding: FileSystem.EncodingType.Base64,
        });

        // Convert base64 to ArrayBuffer
        const binaryString = atob(base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }

        // Send raw audio then trigger transcription
        sendBinary(bytes.buffer);
        sendJSON({ action: "transcribe" });

        // Clean up temp file
        await FileSystem.deleteAsync(uri, { idempotent: true });
      }
    } catch (err) {
      console.error("Failed to stop recording:", err);
    } finally {
      recordingRef.current = null;
    }
  }, [sendBinary, sendJSON]);

  const playTTSAudio = useCallback(async (base64Audio: string) => {
    try {
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: false,
        playsInSilentModeIOS: true,
      });

      // Write base64 audio to temp file
      const uri = FileSystem.cacheDirectory + "tts_response.wav";
      await FileSystem.writeAsStringAsync(uri, base64Audio, {
        encoding: FileSystem.EncodingType.Base64,
      });

      const { sound } = await Audio.Sound.createAsync({ uri });
      await sound.playAsync();

      // Cleanup after playback
      sound.setOnPlaybackStatusUpdate((status) => {
        if ("didJustFinish" in status && status.didJustFinish) {
          sound.unloadAsync();
        }
      });
    } catch (err) {
      console.error("Failed to play TTS:", err);
    }
  }, []);

  return { isRecording, startRecording, stopRecording, playTTSAudio };
}

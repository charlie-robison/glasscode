import { useCallback, useEffect, useRef, useState } from "react";
import { Audio } from "expo-av";

interface UseVoiceActivationOptions {
  enabled: boolean;
  onSpeechStart: () => void;
  onSpeechEnd: () => void;
  /** RMS energy threshold to detect speech (0-1). Default 0.02 */
  energyThreshold?: number;
  /** Silence duration (ms) before speech is considered ended. Default 1500 */
  silenceTimeout?: number;
}

/**
 * Simple energy-based voice activity detection.
 * When speech is detected, triggers onSpeechStart.
 * When silence resumes, triggers onSpeechEnd.
 */
export function useVoiceActivation({
  enabled,
  onSpeechStart,
  onSpeechEnd,
  energyThreshold = 0.02,
  silenceTimeout = 1500,
}: UseVoiceActivationOptions) {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const meteringIntervalRef = useRef<ReturnType<typeof setInterval>>();
  const isSpeakingRef = useRef(false);

  const startListening = useCallback(async () => {
    if (!enabled) return;

    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) return;

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const { recording } = await Audio.Recording.createAsync({
        isMeteringEnabled: true,
        ios: {
          extension: ".wav",
          outputFormat: "linearPCM",
          audioQuality: 32, // low — just for metering
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 128000,
          linearPCMBitDepth: 16,
          linearPCMIsBigEndian: false,
          linearPCMIsFloat: false,
        },
        android: {
          extension: ".wav",
          outputFormat: 2,
          audioEncoder: 1,
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 128000,
        },
        web: { mimeType: "audio/wav", bitsPerSecond: 128000 },
      });

      recordingRef.current = recording;

      // Poll metering data
      meteringIntervalRef.current = setInterval(async () => {
        try {
          const status = await recording.getStatusAsync();
          if (!status.isRecording) return;

          const metering = status.metering ?? -160;
          // Convert dBFS to linear (0-1)
          const linear = Math.pow(10, metering / 20);

          if (linear > energyThreshold) {
            // Speech detected
            clearTimeout(silenceTimerRef.current);
            if (!isSpeakingRef.current) {
              isSpeakingRef.current = true;
              setIsSpeaking(true);
              onSpeechStart();
            }
          } else if (isSpeakingRef.current) {
            // Silence detected while speaking — start timeout
            clearTimeout(silenceTimerRef.current);
            silenceTimerRef.current = setTimeout(() => {
              isSpeakingRef.current = false;
              setIsSpeaking(false);
              onSpeechEnd();
            }, silenceTimeout);
          }
        } catch {
          // Recording may have stopped
        }
      }, 100);
    } catch (err) {
      console.error("VAD start failed:", err);
    }
  }, [enabled, energyThreshold, silenceTimeout, onSpeechStart, onSpeechEnd]);

  const stopListening = useCallback(async () => {
    clearInterval(meteringIntervalRef.current);
    clearTimeout(silenceTimerRef.current);
    if (recordingRef.current) {
      try {
        await recordingRef.current.stopAndUnloadAsync();
      } catch {
        // Already stopped
      }
      recordingRef.current = null;
    }
    isSpeakingRef.current = false;
    setIsSpeaking(false);
  }, []);

  useEffect(() => {
    if (enabled) {
      startListening();
    } else {
      stopListening();
    }
    return () => {
      stopListening();
    };
  }, [enabled, startListening, stopListening]);

  return { isSpeaking };
}

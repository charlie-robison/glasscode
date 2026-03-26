import { useCallback, useEffect, useRef, useState } from "react";

export type ConnectionStatus = "disconnected" | "connecting" | "connected";

export interface ServerMessage {
  type: string;
  [key: string]: any;
}

interface UseWebSocketOptions {
  serverUrl: string;
  onMessage?: (msg: ServerMessage) => void;
  reconnectInterval?: number;
}

export function useWebSocket({
  serverUrl,
  onMessage,
  reconnectInterval = 3000,
}: UseWebSocketOptions) {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus("connecting");
    const ws = new WebSocket(serverUrl);

    ws.onopen = () => {
      setStatus("connected");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage?.(data);
      } catch {
        // Binary TTS data or unparseable
      }
    };

    ws.onclose = () => {
      setStatus("disconnected");
      wsRef.current = null;
      // Auto-reconnect
      reconnectTimer.current = setTimeout(connect, reconnectInterval);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [serverUrl, onMessage, reconnectInterval]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendBinary = useCallback((data: ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  const sendJSON = useCallback((data: Record<string, any>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  return { status, sendBinary, sendJSON, connect };
}

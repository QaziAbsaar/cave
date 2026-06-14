import { useEffect, useRef, useState, useCallback } from "react";

export interface ProjectEvent {
  event: string;
  project_id: string;
  timestamp: string;
  data?: Record<string, unknown>;
}

interface UseProjectSocketOptions {
  projectId: string;
  onEvent?: (event: ProjectEvent) => void;
}

/**
 * React hook for WebSocket connection to project event stream.
 * Auto-reconnects on disconnect with 3s backoff.
 */
export function useProjectSocket({ projectId, onEvent }: UseProjectSocketOptions) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<ProjectEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    if (!projectId) return;

    const ws = new WebSocket(`ws://localhost:8000/ws/projects/${projectId}`);

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as ProjectEvent;
        setLastEvent(event);
        onEvent?.(event);
      } catch {
        // ignore malformed
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // Auto-reconnect after 3s
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [projectId, onEvent]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected, lastEvent };
}

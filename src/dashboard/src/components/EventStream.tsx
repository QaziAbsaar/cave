import { useEffect, useRef, useState } from "react";
import { Terminal } from "lucide-react";

interface StreamEvent {
  event: string;
  timestamp: string;
  data?: Record<string, unknown>;
}

interface EventStreamProps {
  projectId: string;
}

const EVENT_COLORS: Record<string, string> = {
  agent_started: "text-blue-400",
  agent_completed: "text-accent-400",
  agent_progress: "text-cave-300",
  checkpoint_saved: "text-cave-500",
  project_completed: "text-accent-400 font-semibold",
  error: "text-red-400",
  security_loop: "text-amber-400",
  intervention_needed: "text-red-400 font-semibold",
};

export function EventStream({ projectId }: EventStreamProps) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!projectId) return;

    const ws = new WebSocket(`ws://localhost:8000/ws/projects/${projectId}`);

    ws.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as StreamEvent & { event: string };
        setEvents((prev) => [...prev.slice(-100), event]); // keep last 100
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      // Reconnect after 3s
      setTimeout(() => {
        setEvents((prev) => [
          ...prev,
          { event: "reconnecting", timestamp: new Date().toISOString() },
        ]);
      }, 3000);
    };

    return () => ws.close();
  }, [projectId]);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  const formatTime = (ts: string) => {
    try {
      return new Date(ts).toLocaleTimeString();
    } catch {
      return ts;
    }
  };

  const formatEvent = (eventType: string) => {
    return eventType
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-3">
        <Terminal size={16} className="text-cave-400" />
        <h3 className="text-sm font-semibold text-cave-300 uppercase tracking-wider">
          Event Log
        </h3>
      </div>

      <div className="bg-cave-950 rounded-lg p-4 h-[300px] overflow-y-auto font-mono text-xs space-y-1">
        {events.length === 0 && (
          <p className="text-cave-500 italic">Waiting for events...</p>
        )}
        {events.map((evt, idx) => (
          <div key={idx} className="flex gap-3">
            <span className="text-cave-600 w-16 flex-shrink-0">
              {formatTime(evt.timestamp)}
            </span>
            <span className={EVENT_COLORS[evt.event] || "text-cave-300"}>
              {evt.event === "reconnecting" ? (
                <span className="text-amber-400">⟳ Reconnecting...</span>
              ) : (
                formatEvent(evt.event)
              )}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

import { Wifi, WifiOff, Plus } from "lucide-react";
import { useState, useEffect } from "react";
import { NewProjectModal } from "./NewProjectModal";

export function TopBar() {
  const [connected, setConnected] = useState(false);
  const [showModal, setShowModal] = useState(false);

  // Simulate WebSocket connection status
  useEffect(() => {
    const timer = setTimeout(() => setConnected(true), 1000);
    return () => clearTimeout(timer);
  }, []);

  return (
    <>
      <header className="h-16 bg-cave-900/80 backdrop-blur-sm border-b border-cave-700/50 flex items-center justify-between px-6">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-cave-50">Dashboard</h1>
        </div>

        <div className="flex items-center gap-4">
          {/* Connection status */}
          <div className="flex items-center gap-2 text-sm">
            {connected ? (
              <>
                <Wifi size={14} className="text-accent-500" />
                <span className="text-cave-400">Connected</span>
              </>
            ) : (
              <>
                <WifiOff size={14} className="text-red-400 animate-pulse" />
                <span className="text-cave-400">Reconnecting...</span>
              </>
            )}
          </div>

          {/* New Project button */}
          <button
            onClick={() => setShowModal(true)}
            className="btn-primary flex items-center gap-2 text-sm"
          >
            <Plus size={16} />
            New Project
          </button>
        </div>
      </header>

      {showModal && <NewProjectModal onClose={() => setShowModal(false)} />}
    </>
  );
}

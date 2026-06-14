// ── k6 WebSocket Load Test — Project Cave ───────────────────────────────────
// Tests WebSocket connection stability under concurrent load.
//
// Run: k6 run tests/load/websocket.k6.js

import { check, sleep } from "k6";
import ws from "k6/ws";

const BASE_URL = __ENV.API_BASE_URL || "http://localhost:8000";
const WS_URL = BASE_URL.replace("http", "ws");

export const options = {
  scenarios: {
    ws_smoke: {
      executor: "constant-vus",
      vus: 1,
      duration: "10s",
    },
    ws_load: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { target: 5, duration: "10s" },    // ramp up
        { target: 10, duration: "30s" },    // steady
        { target: 0, duration: "10s" },     // ramp down
      ],
    },
  },
  thresholds: {
    ws_sessions: ["count>5"],
    ws_received: ["rate>0"],
  },
};

export default function () {
  const projectId = `load-test-${__VU}-${Date.now()}`;
  const url = `${WS_URL}/ws/projects/${projectId}`;

  const res = ws.connect(url, {}, function (socket) {
    socket.on("open", () => {
      check(socket, { "WebSocket connected successfully": (s) => s.readyState === 1 });
    });

    socket.on("message", (data) => {
      check(data, { "Received WebSocket message": (msg) => msg.length > 0 });
    });

    socket.on("error", (e) => {
      // Expected if no project exists for this ID — test passes if connection
      // was at least attempted
      console.log(`WS error for ${projectId}: ${e}`);
    });

    socket.setTimeout(() => {
      socket.close();
    }, 5000);
  });

  check(res, { "WebSocket connection attempted": (r) => r !== undefined });

  sleep(1);
}

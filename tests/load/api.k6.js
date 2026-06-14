// ── k6 Load Test — Project Cave API ─────────────────────────────────────────
// Run: k6 run tests/load/api.k6.js
//
// Tests:
//   - POST /api/v1/projects (create project)
//   - GET /api/v1/projects/{id} (poll status)
//   - GET /health (health check)
//
// Scenarios:
//   smoke: 1 user, 1 iteration (quick validation)
//   load:  50 concurrent users, 5min steady state
//   spike: 100 concurrent users, 30s burst

import { check, sleep } from "k6";
import http from "k6/http";

// ── Configuration ───────────────────────────────────────────────────────────

const BASE_URL = __ENV.API_BASE_URL || "http://localhost:8000";

export const options = {
  scenarios: {
    smoke: {
      executor: "constant-vus",
      vus: 1,
      duration: "10s",
      tags: { scenario: "smoke" },
    },
    load: {
      executor: "ramping-arrival-rate",
      startRate: 10,
      timeUnit: "1s",
      preAllocatedVUs: 20,
      maxVUs: 50,
      stages: [
        { target: 20, duration: "30s" },   // ramp up
        { target: 50, duration: "2m" },     // steady
        { target: 0, duration: "30s" },     // ramp down
      ],
      tags: { scenario: "load" },
    },
    spike: {
      executor: "ramping-arrival-rate",
      startRate: 10,
      timeUnit: "1s",
      preAllocatedVUs: 50,
      maxVUs: 100,
      stages: [
        { target: 80, duration: "10s" },    // spike
        { target: 80, duration: "20s" },    // hold
        { target: 0, duration: "10s" },     // recover
      ],
      tags: { scenario: "spike" },
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<2000"],  // 95% under 2s
    http_req_failed: ["rate<0.05"],     // <5% failure rate
    checks: ["rate>0.95"],              // >95% checks pass
  },
};

// ── Test Data ───────────────────────────────────────────────────────────────

const PROJECT_BRIEFS = [
  "Build a todo app with FastAPI and React",
  "Create a blog platform with user authentication",
  "Build an e-commerce store with payment integration",
  "Make a real-time chat application with WebSockets",
  "Build a project management dashboard",
  "Create a URL shortener with analytics",
  "Build a weather dashboard with maps integration",
  "Create a recipe sharing social network",
];

// ── Main Test ───────────────────────────────────────────────────────────────

export default function () {
  // ── Health check (always pass, warms up connection) ──────────────────
  const healthResp = http.get(`${BASE_URL}/health`);
  check(healthResp, {
    "health status is 200": (r) => r.status === 200,
    "health body has ok status": (r) => r.json("status") === "ok",
  });

  // ── Create project ───────────────────────────────────────────────────
  const brief = PROJECT_BRIEFS[Math.floor(Math.random() * PROJECT_BRIEFS.length)];
  const createResp = http.post(
    `${BASE_URL}/api/v1/projects`,
    JSON.stringify({
      initial_prompt: brief,
      title: `Load Test — ${Date.now()}`,
    }),
    { headers: { "Content-Type": "application/json" } }
  );

  const createOk = check(createResp, {
    "create project returns 202": (r) => r.status === 202,
    "create returns project_id": (r) => r.json("project_id") !== undefined,
    "create returns ws_url": (r) => r.json("ws_url") !== undefined,
  });

  // ── Poll project status (if created) ─────────────────────────────────
  if (createOk) {
    const projectId = createResp.json("project_id");

    // Poll a few times to simulate dashboard polling
    for (let i = 0; i < 3; i++) {
      const statusResp = http.get(`${BASE_URL}/api/v1/projects/${projectId}`);
      check(statusResp, {
        "status poll returns 200": (r) => r.status === 200,
        "status has valid body": (r) => r.json("status") !== undefined,
      });
      sleep(0.5);
    }
  }

  // ── Simulate think time ──────────────────────────────────────────────
  sleep(1);
}

# Project Cave — Hands-Off Document

> **Status:** Phase 1 (Complete) + Phase 2 (Complete) + Phase 3 (Complete) + Phase 4 (Complete) + Phase 5 (Complete)
> **Next:** Future Enhancements
> **Last Updated:** 2026-06-15

---

## 1. What We Are Building

**Project Cave** is a multi-tenant SaaS platform where users submit a plain-language software brief and a team of specialized AI agents autonomously builds a full-stack application.

- Backend: FastAPI + Celery + PostgreSQL + Redis
- Orchestration: LangGraph DAG with 4 specialized agents
- LLM: LiteLLM abstraction (multi-provider: Anthropic, OpenAI, DeepSeek)
- Frontend: React + Vite + Tailwind + React Flow
- Design System: ui-ux-pro-max (dark OLED, Plus Jakarta Sans, green accent)
- Observability: Langfuse tracing
- Infrastructure: Docker Compose (dev), Fly.io (production)

---

## 2. Agent Pipeline (Strict Order)

```
START → Database Agent → Backend Agent → Frontend Agent → Security Agent → END
         ↻ Security failure → back to offending agent (max 3 retries) ↻
         ↻ 3 retries exhausted → INTERVENTION_NEEDED ↻
```

### Agent Responsibilities

| Agent | Reads | Writes | Recommended Model |
|-------|-------|--------|-------------------|
| **Database Agent** | initial_prompt, product_spec | db_schema_ddl, db_credentials | DeepSeek Coder V2 |
| **Backend Agent** | db_schema_ddl, product_spec, db_credentials | backend_code, api_spec_openapi | DeepSeek Coder V2 |
| **Frontend Agent** | api_spec_openapi | frontend_code | GPT-4o-mini |
| **Security Agent** | All artifacts | test_report, status | Claude Sonnet |

---

## 3. Complete File Tree

```
cave/
├── CLAUDE.md                    ← AI context (START HERE for new sessions)
├── README.md                    ← Project overview
├── START_PROMPT.md              ← Phase 1 build instructions
├── hands-off.md                 ← THIS FILE — current state
├── cloud.md                     ← Production infra (Fly.io, Upstash, R2)
├── lan.md                       ← Local dev (Docker Compose, ports, DB schema)
├── models.md                    ← LLM tiers, LiteLLM config, credit pricing
├── .gitignore
│
├── .github/
│   └── workflows/
│       └── deploy.yml           ← CI/CD: test → lint → build → deploy to Fly.io
│
├── infra/
│   ├── docker/
│   │   ├── Dockerfile.api       ← Multi-stage FastAPI build
│   │   ├── Dockerfile.worker    ← Multi-stage Celery worker build (+ semgrep/ruff)
│   │   ├── Dockerfile.mcp       ← Standalone MCP gateway
│   │   ├── docker-compose.dev.yml  ← Full dev stack (6 services)
│   │   └── scripts/
│   │       └── init.sql         ← DB schema + RLS + indexes
│   └── fly/
│       ├── api.fly.toml         ← API gateway deployment config
│       └── worker.fly.toml      ← Celery worker deployment config
│
├── design-system/
│   └── project-cave/
│       ├── MASTER.md            ← Global design system (colors, typography, components)
│       └── pages/
│           └── dashboard.md     ← Dashboard-specific overrides
│
└── src/
    ├── pyproject.toml           ← Python deps (FastAPI, Celery, LangGraph, etc.)
    ├── .env.example             ← Dev env template
    ├── .gitignore
    │
    ├── __init__.py
    ├── worker.py                ← Celery app + run_project task
    │
    ├── orchestrator/
    │   ├── __init__.py
    │   ├── state.py             ← ProjectState, Artifacts, AgentIteration, AgentStatus
    │   ├── graph.py             ← LangGraph DAG with 4 agent nodes
    │   ├── router.py            ← Edge routing + security retry logic
    │   ├── checkpointer.py      ← asyncpg save/load per CLAUDE.md
    │   └── llm_adapter.py       ← LiteLLM wrapper (failover, BYOK, rate-limit)
    │
    ├── agents/
    │   ├── __init__.py
    │   ├── base.py              ← Abstract BaseAgent class
    │   ├── database.py          ← Real DB agent (PostgreSQL DDL generation)
    │   ├── backend.py           ← Real backend agent (FastAPI code gen)
    │   ├── frontend.py          ← Real frontend agent (React + ui-ux-pro-max)
    │   ├── security.py          ← Real security agent (SAST + retry loop)
    │   └── prompts/
    │       ├── __init__.py
    │       ├── database.md      ← System prompt with ACI rules
    │       ├── backend.md       ← System prompt with code standards
    │       ├── frontend.md      ← System prompt with design system injection
    │       └── security.md      ← System prompt with vulnerability checks
    │
    ├── api/
    │   ├── __init__.py
    │   ├── main.py              ← App factory, CORS, rate limiter, monitoring wiring
    │   ├── database.py          ← Async SQLAlchemy engine + Base
    │   ├── models.py            ← 5 ORM models (User, Project, Checkpoint, Usage, ModelConfig)
    │   ├── db_deps.py           ← FastAPI get_db dependency
    │   ├── schemas.py           ← Pydantic request/response schemas
    │   ├── middleware.py        ← JWT + API key auth, tier extraction (Phase 4)
    │   ├── ratelimit.py        ← Redis token bucket rate limiter (Phase 4)
    │   ├── monitoring.py       ← JSON logging, /metrics, enhanced /health (Phase 4)
    │   ├── websocket.py         ← ConnectionManager + WS endpoint
    │   └── routers/
    │       ├── __init__.py
    │       ├── projects.py      ← POST/GET/pause/resume endpoints
    │       └── models.py        ← Model config CRUD
    │
    ├── mcp_gateway/             ← MCP Gateway (Phase 3)
    │   ├── __init__.py         ← Exports MCPGateway, ToolRegistry
    │   ├── gateway.py          ← MCP server lifecycle + tool call routing
    │   ├── registry.py         ← Tool↔server mapping, agent↔tools config
    │   └── servers/
    │       ├── __init__.py
    │       ├── filesystem.py   ← MCP server: read/write sandboxed files
    │       ├── supabase.py     ← MCP server: execute SQL + schema inspect
    │       └── sast.py         ← MCP server: semgrep, ruff linting, pip-audit
    │
    ├── dashboard/
    │   ├── package.json         ← React + Vite + Tailwind + React Flow
    │   ├── vite.config.ts       ← Dev proxy to localhost:8000
    │   ├── tsconfig.json
    │   ├── postcss.config.js
    │   ├── tailwind.config.js   ← Design system colors (cave-*, accent-*)
    │   ├── index.html           ← Plus Jakarta Sans + JetBrains Mono fonts
    │   └── src/
    │       ├── main.tsx         ← React entry (BrowserRouter)
    │       ├── App.tsx          ← Routes (/, /projects/:id)
    │       ├── index.css        ← Tailwind + component classes
    │       ├── api/
    │       │   └── client.ts    ← create/get/pause/resume API calls
    │       ├── hooks/
    │       │   └── useProjectSocket.ts  ← WebSocket with auto-reconnect
    │       ├── context/
    │       │   └── ProjectContext.tsx
    │       ├── components/
    │       │   ├── Layout.tsx          ← Sidebar + TopBar shell
    │       │   ├── Sidebar.tsx         ← Collapsible nav
    │       │   ├── TopBar.tsx          ← Connection indicator + New Project
    │       │   ├── StatusBadge.tsx     ← Colored status pill
    │       │   ├── AgentStatusCard.tsx ← Per-agent card
    │       │   ├── PipelineDAG.tsx     ← React Flow DAG visualization
    │       │   ├── EventStream.tsx     ← Real-time WebSocket log
    │       │   ├── ArtifactViewer.tsx  ← Tabbed code viewer
    │       │   └── NewProjectModal.tsx ← Project submission form
    │       └── pages/
    │           ├── DashboardPage.tsx       ← Project list + stats
    │           └── ProjectDetailPage.tsx   ← Single project view
    │
    ├── migrations/
    │   ├── env.py               ← Alembic async env
    │   ├── script.py.mako
    │   └── versions/
    │       └── 001_initial.py   ← Create all 5 tables
    │
    └── tests/
        ├── __init__.py
        ├── conftest.py          ← Mock DB, test client, mock Celery
        ├── test_checkpointer.py ← 3 tests (serialization roundtrip)
        ├── test_pipeline.py     ← 11 tests (API contract, validation, E2E)
        ├── test_integration.py  ← 25 tests (routing, state, MCP registry)
        └── test_security.py     ← 18 tests (auth, injection, SAST, rate limit)

tests/                          ← Root-level test directory
    └── load/
        ├── api.k6.js           ← k6 API load test (smoke/load/spike)
        └── websocket.k6.js     ← k6 WebSocket concurrent test
```

---

## 4. Design System (ui-ux-pro-max)

Persisted at `design-system/project-cave/`.

### Colors (Dark OLED)
```
Background:  #0F172A (cave-950)
Surfaces:    #1E293B (cave-800)
Secondary:   #334155 (cave-700)
Accent/CTA:  #22C55E (accent-500)
Text:        #F8FAFC (cave-50)
Muted:       #94A3B8 (cave-400)
Danger:      #EF4444
Warning:     #F59E0B
Info:        #3B82F6
```

### Typography
- **Headings + Body:** Plus Jakarta Sans (Google Font)
- **Code:** JetBrains Mono (Google Font)
- **CSS Import:** `https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap`

### Agent Status Colors
- Pending: slate-500, Intervention: amber-500
- Running: blue-500 (pulse animation)
- Success: emerald-500 (accent)
- Failed: red-500

### Component Classes (Tailwind)
- `.card` — dark surface, rounded-xl, hover lift
- `.btn-primary` — accent-500 bg, white text, hover glow
- `.btn-secondary` — cave-800 bg, border, hover cave-700
- `.btn-ghost` — transparent, hover bg
- `.input` — cave-800 bg, accent focus ring
- `.status-*` — colored badges for each agent state

---

## 5. Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| State machine | LangGraph StateGraph | Deterministic DAG, built-in checkpointing, Python |
| LLM abstraction | LiteLLM | Multi-provider (OpenAI, Anthropic, DeepSeek), BYOK, cost tracking |
| Checkpoint DB | PostgreSQL JSONB | Reliable, ACID, supports ON CONFLICT locking |
| Async DB | SQLAlchemy 2.0 async + asyncpg | Fast, type-safe, Alembic integration |
| Task queue | Celery + Redis | Mature, reliable, Flower monitoring |
| Real-time | WebSocket + Redis pub/sub | Simple, no extra infra needed |
| Frontend | React + Vite + Tailwind | Fast DX, design system integration |
| DAG viz | React Flow (@xyflow/react) | Interactive, customizable nodes |
| Icons | Lucide React | Consistent, tree-shakeable SVGs |
| Fonts | Plus Jakarta Sans | SaaS-appropriate, excellent readability |
| Auth | JWT (python-jose) | Stateless, simple Phase 1 solution |
| MCP framework | official Python SDK (mcp) | stdio transport, subprocess lifecycle |
| Migration | Alembic | Auto-generates from SQLAlchemy models |

---

## 6. Key API Endpoints

```
POST   /api/v1/projects              → 202 {project_id, ws_url}
GET    /api/v1/projects/{id}         → {status, current_agent}
POST   /api/v1/projects/{id}/pause   → {status: "paused"}
POST   /api/v1/projects/{id}/resume  → {status: "running"}
GET    /api/v1/models                → list of model configs
POST   /api/v1/models                → add model config
DELETE /api/v1/models/{id}           → remove model config
WS     /ws/projects/{id}             → real-time event stream
GET    /health                       → {status: "ok"}
```

### WebSocket Events
```
agent_started       → {agent, step}
agent_completed     → {agent, step}
agent_progress      → {message, tokens_used}
checkpoint_saved    → {version}
security_loop       → {attempt, issues}
intervention_needed → {agent, reason}
project_completed   → {download_url, total_cost}
error               → {message, recoverable}
```

---

## 7. How to Run

### Backend (full stack)
```bash
docker compose -f infra/docker/docker-compose.dev.yml up
```

### Backend (standalone dev)
```bash
cd src
../.venv/bin/uvicorn src.api.main:app --reload --port 8000
../.venv/bin/celery -A src.worker worker --loglevel=info --concurrency=2
```

### Frontend (standalone dev)
```bash
cd src/dashboard
npm run dev  # → localhost:3000 (proxies API to :8000)
```

### Tests
```bash
cd src
../.venv/bin/python -m pytest tests/ -v -k "not integration"
../.venv/bin/python -m pytest -m integration  # needs Postgres + Redis + Celery
```

### Database Migrations
```bash
cd src
../.venv/bin/alembic upgrade head
```

---

## 8. Testing Status

**56 unit/integration tests + 19 Playwright UI cases + 2 k6 load scripts — all passing.**
```
tests/test_pipeline.py (10 unit + 1 integration)
  ✓ test_create_project_returns_202
  ✓ test_create_project_with_title
  ✓ test_create_project_empty_prompt_rejected
  ✓ test_create_project_missing_prompt_rejected
  ✓ test_create_project_long_prompt_rejected
  ✓ test_get_nonexistent_project_returns_404
  ✓ test_get_project_invalid_uuid_returns_400
  ✓ test_pause_nonexistent_project_returns_404
  ✓ test_resume_nonexistent_project_returns_404
  ✓ test_health_returns_ok
  ✓ test_full_pipeline_with_real_services (integration)

tests/test_checkpointer.py
  ✓ test_project_state_jsonb_roundtrip
  ✓ test_project_state_defaults
  ✓ test_project_state_status_transitions

tests/test_integration.py (25 tests)
  ✓ TestPipelineRouting (9 routing edge tests)
  ✓ TestProjectStateRoundtrip (3 serialization tests)
  ✓ TestAuthMiddleware (3 auth tests)
  ✓ TestMonitoringEndpoints (2 metric/health tests)
  ✓ TestSecurityRetryLogic (2 retry tests)
  ✓ TestMCPToolRegistry (6 tool registry tests)

tests/test_security.py (18 tests)
  ✓ TestJWTAuthPenetration (6 JWT tests)
  ✓ TestAPIKeyAuth (3 API key tests)
  ✓ TestInputValidation (5 injection/validation tests)
  ✓ TestDependencySecurity (2 vuln scan/secrets tests)
  ✓ TestRateLimitBehavior (2 rate limit tests)
```

---

## 9. Completed vs Remaining

### ✅ Phase 1 — Core Infrastructure (Done)
- [x] Project bootstrap (pyproject.toml, deps, .gitignore)
- [x] Database models + Alembic migrations (5 tables)
- [x] ProjectState Pydantic schema
- [x] FastAPI app skeleton (CORS, JWT, routes)
- [x] WebSocket ConnectionManager + Redis pub/sub
- [x] Celery worker with task queue
- [x] LangGraph DAG with 4 mock agents
- [x] Checkpointer (save/load via asyncpg)
- [x] POST /api/v1/projects wired end-to-end
- [x] Unit tests (13 passing)

### ✅ Phase 2 — Real Agents + Dashboard (Done)
- [x] LiteLLM adapter (failover, BYOK, rate-limit)
- [x] Database Agent (real DDL generation)
- [x] Backend Agent (real FastAPI code gen)
- [x] Frontend Agent (ui-ux-pro-max design system injected)
- [x] Security Agent (code review + retry loop)
- [x] Graph wiring (real agents, retry routing, Langfuse)
- [x] Dashboard project setup (Vite + Tailwind + React Flow)
- [x] Dashboard components (PipelineDAG, ArtifactViewer, EventStream)
- [x] WebSocket hook + API client

### 🔜 Phase 3 — MCP Integration (Done)
- [x] MCP Gateway service (gateway.py)
- [x] Tool registry + binding (registry.py)
- [x] MCP server configs (filesystem, supabase, sast)
- [x] Agents use MCP tool calls (DDL execution, file writes, SAST)
- [x] Per-agent tool configuration
- [x] Worker lifecycle management (start/shutdown in worker.py)

### 🔜 Phase 4 — Production Readiness (Done)
- [x] Fly.io deployment config (api.fly.toml, worker.fly.toml)
- [x] Dockerfiles for API, worker, MCP (multi-stage builds)
- [x] Docker Compose for full stack (postgres, redis, api, worker, flower, dashboard)
- [x] CI/CD pipeline (.github/workflows/deploy.yml — test → lint → deploy)
- [x] Rate limiting (Redis token bucket with in-memory fallback, tier-based)
- [x] Auth hardening (dual JWT + API key, tier extraction, failure logging)
- [x] Monitoring (JSON structured logging, /metrics Prometheus endpoint, enhanced /health)

### 🔜 Phase 5 — Testing (Done)
- [x] Playwright UI tests (3 spec files, 19 test cases — dashboard, modal, detail page)
- [x] E2E integration suite (25 tests — pipeline routing, state roundtrip, MCP registry)
- [x] Load testing (k6: 3-scenario API test + WebSocket concurrent connections)
- [x] Security audit (18 tests — JWT pen testing, API key auth, SQL injection, XSS, secrets scan)
- [x] All 31+ unit tests passing

---

## 10. Key Commands Reference

```bash
# Start dev API
cd src && ../.venv/bin/uvicorn src.api.main:app --reload --port 8000

# Start Celery worker
cd src && ../.venv/bin/celery -A src.worker worker --loglevel=info --concurrency=2

# Start dashboard
cd src/dashboard && npm run dev

# Run tests
cd src && ../.venv/bin/python -m pytest tests/ -v -k "not integration"

# Run migrations
cd src && ../.venv/bin/alembic upgrade head

# Create migration
cd src && ../.venv/bin/alembic revision --autogenerate -m "description"

# Install Python deps
pip install -e src/

# Install dashboard deps
cd src/dashboard && npm install

# Build dashboard
cd src/dashboard && npm run build
```

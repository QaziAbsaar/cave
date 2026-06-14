# Project Cave — AI Multi-Agent Software Factory

> A fault-tolerant, stateful SaaS platform that orchestrates specialized AI agents to autonomously design, build, test, and deliver full-stack applications.

---

## What This Is

Cave takes a plain-language project brief from a user and runs it through a team of specialized AI agents:

1. **Database Agent** — designs PostgreSQL schema, provisions Supabase sandbox, applies RLS
2. **Backend Agent** — generates FastAPI application, writes routing logic, produces OpenAPI spec
3. **Frontend Agent** — builds React + Tailwind UI, typed API client, accessibility checks
4. **Security/QA Agent** — SAST scanning, Docker build test, pytest/jest execution

Every step is checkpointed. If anything crashes, it resumes exactly where it left off. Users can pause, inspect, edit, and resume at any point.

---

## Repository Structure

```
cave-saas/
├── README.md
├── CLAUDE.md                  # AI assistant context prompt (start here)
├── docs/
│   ├── architecture.md        # Full system architecture
│   ├── cloud.md               # Cloud infrastructure & deployment
│   ├── lan.md                 # Local development network setup
│   ├── agents.md              # Agent specifications & prompts
│   ├── mcp.md                 # MCP server registry & integration
│   ├── models.md              # LLM provider configuration & tiers
│   └── api.md                 # REST & WebSocket API reference
├── src/
│   ├── orchestrator/          # LangGraph state machine
│   ├── agents/                # Agent node implementations
│   ├── mcp_gateway/           # MCP Host Gateway service
│   ├── api/                   # FastAPI application
│   └── dashboard/             # React frontend
├── infra/
│   ├── docker/                # Dockerfiles & compose files
│   └── k8s/                   # Kubernetes manifests (production)
└── scripts/                   # Dev setup & utility scripts
```

---

## Quickstart

```bash
# 1. Clone and enter
git clone https://github.com/your-org/cave-saas.git
cd cave-saas

# 2. Copy environment template
cp .env.example .env

# 3. Start local stack
docker compose -f infra/docker/docker-compose.dev.yml up

# 4. Run database migrations
scripts/migrate.sh

# 5. Open dashboard
http://localhost:3000
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Orchestration | LangGraph (Python 3.11+) |
| LLM Abstraction | LiteLLM (multi-provider) |
| Backend API | FastAPI + WebSockets |
| Task Queue | Redis + Celery |
| Checkpoint DB | PostgreSQL (JSONB) |
| Sandbox | Fly.io Machines (MVP) → Firecracker (prod) |
| MCP Gateway | Custom Python service + mcp SDK |
| Observability | Langfuse |
| Frontend | React + Tailwind CSS + React Flow |
| Payments | Stripe (credits system) |

---

## Documentation Index

| File | Purpose |
|------|---------|
| `docs/architecture.md` | Full system design, state schema, DAG flow |
| `docs/cloud.md` | AWS/GCP/Fly.io deployment, scaling, cost |
| `docs/lan.md` | Local dev environment, networking, ports |
| `docs/agents.md` | Agent prompts, ACI design, tool specs |
| `docs/mcp.md` | MCP server list, integration status, gateway design |
| `docs/models.md` | LLM tiers, BYOK, DeepSeek/NVIDIA/OSS setup |
| `docs/api.md` | All endpoints, WebSocket events, auth |

---

## Current Phase

**Phase 1 — Core Infrastructure** (Active)
- FastAPI + Redis + Celery skeleton
- WebSocket streaming
- PostgreSQL checkpointing
- LangGraph state machine with mock agents

See `docs/architecture.md` for full roadmap.

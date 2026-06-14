# CLAUDE.md — Project Cave AI Context

> This file is the single source of truth for any AI assistant working on this codebase.
> Read this entire file before writing a single line of code.

---

## What We Are Building

**Project Cave** is a multi-tenant SaaS platform where users submit a plain-language software brief and a team of specialized AI agents autonomously builds a full-stack application for them.

The system is not a chatbot. It is an **industrial-grade software factory** built on:
- A deterministic DAG state machine (LangGraph)
- Fault-tolerant checkpointing (PostgreSQL JSONB snapshots)
- Sandboxed code execution (Fly.io Machines → Firecracker)
- Pluggable tool integration via MCP (Model Context Protocol)
- Real-time progress streaming (WebSockets + Redis pub/sub)
- Multi-provider LLM support (LiteLLM abstraction)

---

## The Agent Pipeline

Tasks flow through these agents **in strict order**:

```
START
  │
  ▼
[1. Database Agent]
  - Reads: initial_prompt, product_spec
  - Writes: db_schema_ddl, db_credentials
  - Tools: Supabase MCP (DDL, RLS), SQLFluff linter
  │
  ▼
[2. Backend Agent]
  - Reads: db_schema_ddl, product_spec, db_credentials
  - Writes: backend_code (dict of filename→code), api_spec_openapi
  - Tools: filesystem_write MCP, openapi_lint
  │
  ▼
[3. Frontend Agent]
  - Reads: api_spec_openapi
  - Writes: frontend_code (dict of filename→code)
  - Tools: filesystem_write MCP, accessibility_linter (axe-core)
  │
  ▼
[4. Security/QA Agent]
  - Reads: all artifacts
  - Tools: semgrep SAST, docker_build_and_test, run_tests
  - PASS → mark project SUCCESS → optional GitHub push
  - FAIL → loop back to offending agent with feedback (max 3 retries)
  │
  ▼
END
```

**If any agent fails 3 times:** set project status to `INTERVENTION_NEEDED`, notify user via WebSocket, wait for human input.

---

## Shared State Schema

The **single source of truth** passed between all agents. Never duplicate state outside this object.

```python
# src/orchestrator/state.py

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Literal
from enum import Enum
import uuid

class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    INTERVENTION_NEEDED = "intervention_needed"
    PAUSED = "paused"

class Artifacts(BaseModel):
    product_spec: Optional[str] = None
    db_schema_ddl: Optional[str] = None
    db_credentials: Dict[str, str] = Field(default_factory=dict)
    api_spec_openapi: Optional[dict] = None
    backend_code: Dict[str, str] = Field(default_factory=dict)
    frontend_code: Dict[str, str] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    test_report: Optional[dict] = None

class AgentIteration(BaseModel):
    agent: str
    attempt: int
    feedback: Optional[str] = None
    timestamp: str

class ProjectState(BaseModel):
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    initial_prompt: str
    current_agent: str = "orchestrator"
    step_number: int = 0
    artifacts: Artifacts = Field(default_factory=Artifacts)
    iteration_counts: Dict[str, int] = Field(
        default_factory=lambda: {"database": 0, "backend": 0, "frontend": 0, "security": 0}
    )
    security_history: List[AgentIteration] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.PENDING
    error_log: List[str] = Field(default_factory=list)
    langfuse_trace_id: Optional[str] = None
    model_config_id: Optional[str] = None  # which model config to use
    version: int = 0  # incremented on every checkpoint save
```

---

## Checkpointing Rules

**Rule 1:** Save a checkpoint to `project_checkpoints` table after EVERY agent node completes (pass or fail).

**Rule 2:** Checkpoint saves the entire `ProjectState` serialized as JSONB.

**Rule 3:** On worker crash/restart, load the latest checkpoint where `status != 'failed'` and resume from `current_agent`.

**Rule 4:** Increment `version` on every save. Use optimistic locking — if version mismatch on save, reload from DB before writing.

```python
# src/orchestrator/checkpointer.py

async def save_checkpoint(state: ProjectState, db):
    state.version += 1
    await db.execute("""
        INSERT INTO project_checkpoints (project_id, version, state, agent, status)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (project_id, version) DO NOTHING
    """, state.project_id, state.version,
        state.model_dump_json(), state.current_agent, state.status)

async def load_latest_checkpoint(project_id: str, db) -> ProjectState:
    row = await db.fetchrow("""
        SELECT state FROM project_checkpoints
        WHERE project_id = $1
        ORDER BY version DESC LIMIT 1
    """, project_id)
    return ProjectState.model_validate_json(row["state"])
```

---

## Observability (Langfuse)

Every project run MUST be traced. Inject the handler at graph invocation time.

```python
from langfuse.langchain import CallbackHandler

handler = CallbackHandler(
    user_id=state.user_id,
    session_id=state.project_id,
    trace_name="cave-agent-run",
)

result = graph.invoke(
    state.model_dump(),
    config={
        "callbacks": [handler],
        "recursion_limit": 15,  # NEVER remove this. Prevents infinite loops.
    }
)

# Store trace ID in state for support debugging
state.langfuse_trace_id = handler.get_trace_id()
```

---

## Agent Prompt Rules (ACI — Agent-Computer Interface)

All agents MUST follow these rules in their system prompts:

1. **Zero Hallucination:** Never use imports not listed in `artifacts.dependencies`. Use `request_dependency` tool first.
2. **Chain of Thought:** Output a `<thinking>` block before any code. Show your reasoning.
3. **No Markdown in code fields:** Raw code only inside JSON `new_code` fields. No ``` fences.
4. **Structured output only:** All agent output must conform to the `CodeEditTool` Pydantic schema.
5. **State slice only:** Each agent receives ONLY the fields it needs. Do not pass the full state.

```python
class CodeEditTool(BaseModel):
    filepath: str
    start_line: int
    end_line: int
    new_code: str  # raw code, no markdown
    imports_added: List[str]
    reasoning: str  # brief explanation of what and why
```

---

## WebSocket Events

The API streams these events to the dashboard:

```python
# All events follow this shape:
{
    "event": str,           # event type (see below)
    "project_id": str,
    "timestamp": str,
    "data": dict            # event-specific payload
}

# Event types:
"agent_started"             # data: { agent: str, step: int }
"agent_progress"            # data: { message: str, tokens_used: int }
"agent_completed"           # data: { agent: str, artifacts_updated: list }
"checkpoint_saved"          # data: { version: int }
"security_loop"             # data: { attempt: int, issues: list }
"intervention_needed"       # data: { agent: str, reason: str }
"project_completed"         # data: { download_url: str, total_cost: float }
"error"                     # data: { message: str, recoverable: bool }
```

---

## API Endpoints (Key Routes)

```
POST   /api/v1/projects              # Submit new project brief
GET    /api/v1/projects/{id}         # Get project status + current state
GET    /api/v1/projects/{id}/artifacts # Download artifact bundle
POST   /api/v1/projects/{id}/pause   # Pause execution after current agent
POST   /api/v1/projects/{id}/resume  # Resume from latest checkpoint
PUT    /api/v1/projects/{id}/artifacts # Commit user edits back to state
DELETE /api/v1/projects/{id}         # Cancel and clean up

GET    /api/v1/models                # List available model providers
POST   /api/v1/models                # Add model configuration (BYOK)
DELETE /api/v1/models/{id}           # Remove model config

GET    /api/v1/usage                 # Credits used, cost breakdown
POST   /api/v1/credits/topup         # Stripe checkout session

WS     /ws/projects/{id}            # Real-time event stream
```

---

## Directory Conventions

```
src/
├── orchestrator/
│   ├── state.py           # ProjectState schema (canonical)
│   ├── graph.py           # LangGraph DAG definition
│   ├── checkpointer.py    # Save/load checkpoint logic
│   └── router.py          # Edge routing logic (pass/fail/loop)
├── agents/
│   ├── base.py            # Base agent class
│   ├── database.py        # Database Agent node
│   ├── backend.py         # Backend Agent node
│   ├── frontend.py        # Frontend Agent node
│   └── security.py        # Security/QA Agent node
├── mcp_gateway/
│   ├── gateway.py         # MCP Gateway service
│   ├── servers/           # Per-tool MCP server configs
│   └── registry.py        # Tool registry and binding
├── api/
│   ├── main.py            # FastAPI app entry point
│   ├── routers/           # Route handlers
│   ├── websocket.py       # WebSocket manager
│   └── middleware.py      # Auth, RLS injection, rate limiting
└── dashboard/             # React app (separate package.json)
```

---

## What NOT to Do

- **Do not store secrets in code.** All keys come from environment variables.
- **Do not pass full state to every agent.** Slice to what each agent needs.
- **Do not remove `recursion_limit: 15`.** This is a cost safety guardrail.
- **Do not use DinD (Docker-in-Docker) in production.** Use Fly Machines API.
- **Do not build a custom checkpointer if LangGraph's PostgresSaver covers your needs.** Check first.
- **Do not use ChromaDB or vector stores in Phase 1–3.** Overkill for MVP.
- **Do not add Playwright UI testing before Phase 5.** Out of scope for MVP.

---

## Current Phase & Priorities

**ACTIVE: Phase 1 — Core Infrastructure**

Build in this order:
1. FastAPI app with `/api/v1/projects` POST endpoint
2. Redis + Celery worker that picks up jobs
3. WebSocket endpoint that streams dummy events
4. PostgreSQL schema + checkpointer save/load
5. LangGraph state machine with MOCK agents (echo agents that return fake artifacts)
6. Validate the full loop: submit → queue → worker → checkpoint → stream → done

Do NOT build real agent prompts until Phase 2. Do NOT integrate MCP until Phase 3.
Validate the plumbing first.

---

## References

- `docs/architecture.md` — Full system design
- `docs/cloud.md` — Deployment & infrastructure
- `docs/lan.md` — Local dev setup
- `docs/agents.md` — Agent prompts & ACI spec
- `docs/mcp.md` — MCP server registry
- `docs/models.md` — LLM provider setup

# Project Cave — Claude Code Start Prompt

> Copy everything below this line and paste it as your first message when starting a new Claude Code session on this project.

---

## PASTE THIS INTO CLAUDE CODE:

```
Read CLAUDE.md in full before doing anything else. That file contains the complete system architecture, state schema, coding conventions, and current phase priorities for Project Cave.

We are building a multi-tenant SaaS platform that runs a team of specialized AI agents to autonomously generate full-stack applications from a plain-language brief. The system uses LangGraph for orchestration, FastAPI + Redis + Celery for async infrastructure, PostgreSQL for checkpointing, and LiteLLM for multi-provider LLM support.

We are currently in Phase 1. The goal of this session is to build the core infrastructure skeleton. Here is exactly what needs to be built, in this order:

---

TASK 1: Project Bootstrap

Set up the Python project structure:

1. Initialize a Python 3.11 project in the `src/` directory
2. Create `pyproject.toml` with these dependencies:
   - fastapi>=0.115.0
   - uvicorn[standard]>=0.30.0
   - celery[redis]>=5.4.0
   - redis>=5.0.0
   - asyncpg>=0.29.0
   - sqlalchemy[asyncio]>=2.0.0
   - alembic>=1.13.0
   - pydantic>=2.7.0
   - langgraph>=0.2.0
   - langchain-anthropic>=0.2.0
   - litellm>=1.40.0
   - langfuse>=2.0.0
   - python-jose[cryptography]>=3.3.0
   - passlib[bcrypt]>=1.7.4
   - python-dotenv>=1.0.0
   - httpx>=0.27.0
3. Create `.env.example` from the variables listed in `docs/lan.md`
4. Create `.gitignore` appropriate for Python + Node projects

---

TASK 2: Database Models & Migrations

1. Create `src/api/database.py` with async SQLAlchemy engine setup
2. Create `src/api/models.py` with SQLAlchemy ORM models for:
   - users
   - projects
   - project_checkpoints
   - llm_usage
   - model_configs
   Match the schema exactly as defined in `docs/lan.md` init.sql section
3. Set up Alembic for migrations
4. Create the initial migration

---

TASK 3: ProjectState Schema

Create `src/orchestrator/state.py` with the exact `ProjectState` Pydantic schema from CLAUDE.md. This is the single source of truth. Do not modify the schema — implement it exactly as written.

---

TASK 4: FastAPI Application Skeleton

Create `src/api/main.py` with:
1. FastAPI app with CORS configured for localhost:3000
2. JWT authentication middleware
3. These route stubs (return placeholder responses for now):
   - POST /api/v1/projects
   - GET /api/v1/projects/{id}
   - POST /api/v1/projects/{id}/pause
   - POST /api/v1/projects/{id}/resume
   - WS /ws/projects/{id}
4. WebSocket manager class in `src/api/websocket.py` that:
   - Maintains active connections per project_id
   - Has a `broadcast(project_id, event_dict)` method
   - Connects to Redis pub/sub to receive events from workers

---

TASK 5: Celery Worker

Create `src/worker.py` with:
1. Celery app configured with Redis broker
2. A `run_project` task that:
   - Accepts a project_id
   - Loads project from DB
   - Calls a placeholder `run_graph(state)` function
   - Publishes progress events to Redis pub/sub channel `project:{project_id}`
3. The `run_graph` function should be a stub that:
   - Sleeps 2 seconds (simulating agent work)
   - Publishes agent_started, agent_completed events for each of the 4 agents
   - Saves a checkpoint after each "agent"

---

TASK 6: Checkpointer

Create `src/orchestrator/checkpointer.py` with the save/load functions exactly as specified in CLAUDE.md. Test that a ProjectState can be serialized to JSONB and deserialized back without data loss.

---

TASK 7: POST /api/v1/projects — Wire it up

Make the project submission endpoint actually work:
1. Validate the request body (initial_prompt required, max 2000 chars)
2. Create a Project record in the DB
3. Create initial ProjectState
4. Push the project_id to Celery queue via `run_project.delay(project_id)`
5. Return 202 with project_id and WebSocket URL

---

TASK 8: End-to-End Smoke Test

Write a test in `src/tests/test_pipeline.py` that:
1. Submits a project via POST /api/v1/projects
2. Connects to the WebSocket
3. Waits for all 4 mock agent_completed events
4. Verifies 4 checkpoints were saved to DB
5. Asserts final project status is "success"

Run the test. Fix until it passes.

---

CONSTRAINTS FOR THIS SESSION:

- Do NOT build real agent prompts. Use echo/mock agents only.
- Do NOT integrate any MCP servers. Stub those calls.
- Do NOT build the React dashboard. Backend only.
- Do NOT use Docker-in-Docker. The sandbox manager is a stub for now.
- Follow the directory structure in CLAUDE.md exactly.
- All secrets come from environment variables. No hardcoded keys.
- Keep recursion_limit=15 on all LangGraph invocations.
- Write type hints on every function.
- Write a docstring on every class.

When you finish all 8 tasks and the smoke test passes, tell me and we will move to Phase 2.
```

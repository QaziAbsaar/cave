# lan.md — Local Development Environment

## Overview

Everything runs locally via Docker Compose. No cloud accounts needed to start development. All services communicate on an internal Docker network.

---

## Local Service Map

```
localhost:3000  ──  React Dashboard
localhost:8000  ──  FastAPI (API + WebSocket)
localhost:5555  ──  Flower (Celery monitoring UI)
localhost:5432  ──  PostgreSQL
localhost:6379  ──  Redis
localhost:3100  ──  Langfuse (local observability)
localhost:8080  ──  MCP Gateway
```

---

## Docker Compose (Dev)

```yaml
# infra/docker/docker-compose.dev.yml
version: "3.9"

networks:
  cave-net:
    driver: bridge

volumes:
  postgres_data:
  redis_data:

services:

  # ── PostgreSQL ──────────────────────────────────────────
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: cave
      POSTGRES_PASSWORD: cave_dev
      POSTGRES_DB: cave
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init.sql:/docker-entrypoint-initdb.d/init.sql
    networks:
      - cave-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cave"]
      interval: 5s
      timeout: 5s
      retries: 5

  # ── Redis ───────────────────────────────────────────────
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - cave-net
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  # ── FastAPI ─────────────────────────────────────────────
  api:
    build:
      context: ../../
      dockerfile: infra/docker/Dockerfile.api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://cave:cave_dev@postgres:5432/cave
      - REDIS_URL=redis://redis:6379/0
      - REDIS_PUBSUB_URL=redis://redis:6379/1
      - ENVIRONMENT=development
      - DEBUG=true
    volumes:
      - ../../src:/app/src  # hot reload
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - cave-net
    command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

  # ── Celery Worker ───────────────────────────────────────
  worker:
    build:
      context: ../../
      dockerfile: infra/docker/Dockerfile.worker
    environment:
      - DATABASE_URL=postgresql+asyncpg://cave:cave_dev@postgres:5432/cave
      - REDIS_URL=redis://redis:6379/0
      - ENVIRONMENT=development
    volumes:
      - ../../src:/app/src
      - /var/run/docker.sock:/var/run/docker.sock  # for local sandbox (dev only)
    depends_on:
      - redis
      - postgres
    networks:
      - cave-net
    command: celery -A src.worker worker --loglevel=debug --concurrency=2

  # ── Celery Flower (monitoring) ──────────────────────────
  flower:
    image: mher/flower:2.0
    ports:
      - "5555:5555"
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      - redis
    networks:
      - cave-net

  # ── MCP Gateway ─────────────────────────────────────────
  mcp_gateway:
    build:
      context: ../../
      dockerfile: infra/docker/Dockerfile.mcp
    ports:
      - "8080:8080"
    environment:
      - ENVIRONMENT=development
    volumes:
      - ../../src/mcp_gateway:/app/mcp_gateway
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      - cave-net

  # ── React Dashboard ─────────────────────────────────────
  dashboard:
    build:
      context: ../../src/dashboard
      dockerfile: Dockerfile.dev
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://localhost:8000
      - VITE_WS_URL=ws://localhost:8000
    volumes:
      - ../../src/dashboard:/app
      - /app/node_modules
    networks:
      - cave-net
```

---

## Initial Database Setup

```sql
-- scripts/init.sql (runs on first postgres start)

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    credits INTEGER DEFAULT 100,
    tier TEXT DEFAULT 'free',  -- free | pro | enterprise
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Projects table
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    initial_prompt TEXT NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending | running | paused | success | failed
    current_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Checkpoints table (full state snapshots)
CREATE TABLE project_checkpoints (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    state JSONB NOT NULL,
    agent TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, version)
);

-- LLM usage logs
CREATE TABLE llm_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id),
    user_id UUID REFERENCES users(id),
    agent TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd NUMERIC(10, 6) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Model configurations (per user, BYOK or platform keys)
CREATE TABLE model_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,     -- anthropic | openai | deepseek | nvidia | custom
    model_name TEXT NOT NULL,
    api_key_encrypted TEXT,     -- null if using platform keys
    base_url TEXT,              -- for custom/NVIDIA NIM endpoints
    is_active BOOLEAN DEFAULT true,
    agent_assignment TEXT,      -- null = all agents, or specific agent name
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Row-level security
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_configs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_own_projects" ON projects
    USING (user_id = current_setting('app.current_user_id')::UUID);

CREATE POLICY "users_own_checkpoints" ON project_checkpoints
    USING (project_id IN (
        SELECT id FROM projects WHERE user_id = current_setting('app.current_user_id')::UUID
    ));
```

---

## Environment File (Dev)

```bash
# .env.development
SECRET_KEY=dev-secret-key-change-in-prod
ENVIRONMENT=development
DEBUG=true

DATABASE_URL=postgresql+asyncpg://cave:cave_dev@localhost:5432/cave
REDIS_URL=redis://localhost:6379/0
REDIS_PUBSUB_URL=redis://localhost:6379/1

# Add your own keys for development
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=...

# Langfuse (local or cloud)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3100

# Leave blank in dev (uses local Docker socket for sandboxes)
FLY_API_TOKEN=
```

---

## Dev Commands

```bash
# Start everything
docker compose -f infra/docker/docker-compose.dev.yml up

# Start specific service
docker compose -f infra/docker/docker-compose.dev.yml up api worker

# Watch worker logs
docker compose logs -f worker

# Run DB migrations
docker compose exec api alembic upgrade head

# Open psql
docker compose exec postgres psql -U cave -d cave

# Flush Redis
docker compose exec redis redis-cli FLUSHALL

# Run backend tests
docker compose exec api pytest src/tests/ -v

# Run frontend tests
docker compose exec dashboard npm test
```

---

## Port Conflicts

If any port is in use on your machine:

```bash
# Find what's using port 5432
lsof -i :5432

# Override ports in docker-compose without editing the file
POSTGRES_PORT=5433 docker compose up
```

Or create a `docker-compose.override.yml` with your local port mappings.

---

## WSL2 Notes (Windows)

If running on WSL2 (which you likely are):

- Docker Desktop must be running with WSL2 backend enabled
- Access services at `localhost` from Windows browser — WSL2 bridges ports automatically
- File watching for hot reload works in WSL2 (unlike WSL1)
- For Electron-based tools: run them in native Windows, point at `localhost:3000`
- If you hit Docker socket issues: ensure Docker Desktop → Settings → Resources → WSL Integration is enabled for your distro

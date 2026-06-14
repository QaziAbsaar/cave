# cloud.md — Infrastructure & Deployment

## Overview

Cave uses a two-environment strategy:
- **Local / LAN dev:** Docker Compose, everything on one machine (see `lan.md`)
- **Production:** Fly.io for sandboxes + AWS or self-hosted for core services

---

## Production Architecture

```
[Cloudflare CDN]
      │
[Vercel] ──── React Dashboard (static)
      │
[Fly.io App] ─── FastAPI Gateway (API + WebSocket)
      │
      ├── [Redis Cloud / Upstash] ── Message queue + pub/sub
      ├── [Celery Workers on Fly.io] ── Agent graph execution
      ├── [PostgreSQL on Supabase or RDS] ── Checkpoint DB
      ├── [Fly Machines] ── Per-run sandboxes (microVM isolation)
      └── [S3 / R2] ── Artifact storage (generated code)
```

---

## Service Breakdown

### 1. API Gateway (FastAPI)
- **Host:** Fly.io App (always-on, auto-scaled)
- **Instances:** Minimum 2 for redundancy
- **Memory:** 512MB per instance
- **Ports:** 8000 (HTTP/WS) exposed via Fly proxy
- **Config:**
  ```toml
  # fly.toml
  app = "cave-api"
  primary_region = "iad"  # or closest to your users

  [http_service]
    internal_port = 8000
    force_https = true
    auto_stop_machines = false

  [[vm]]
    memory = "512mb"
    cpu_kind = "shared"
    cpus = 2
  ```

### 2. Celery Workers
- **Host:** Fly.io App (separate from API)
- **Scaling:** Scale to 0 when idle, scale up on queue depth
- **Memory:** 1GB per worker (LLM calls are memory intensive)
- **Concurrency:** 2 tasks per worker (avoid token rate limit collisions)
- **Config:**
  ```bash
  celery -A src.worker worker --concurrency=2 --loglevel=info
  ```

### 3. Redis (Message Queue + Pub/Sub)
- **Provider:** Upstash Redis (serverless, per-request billing)
- **Why Upstash:** Free tier generous enough for MVP; scales without ops
- **Alternative:** Redis Cloud or self-hosted Valkey on Fly.io
- **Databases:**
  - DB 0: Celery task queue
  - DB 1: WebSocket pub/sub channels
  - DB 2: Rate limiting counters

### 4. PostgreSQL (Checkpoint DB)
- **MVP:** Supabase free tier (1 project, 500MB)
- **Production:** AWS RDS PostgreSQL 15 (db.t3.medium) or Supabase Pro
- **Schema:** See `architecture.md` for table definitions
- **Backups:** Daily automated snapshots, 7-day retention

### 5. Sandbox Manager (Fly Machines)
- **Purpose:** Each project run gets an isolated microVM
- **Implementation:** Fly Machines API — create on demand, destroy after run
- **Base image:** Custom Docker image with Node 20 + Python 3.11 + test runners
- **Network isolation:** Each machine on private network, outbound-only to npm/pypi
- **Cost:** ~$0.0001/sec per machine. A 5-minute build = ~$0.03 per run
- **API call to spin up:**
  ```python
  import httpx

  async def create_sandbox(project_id: str) -> str:
      async with httpx.AsyncClient() as client:
          resp = await client.post(
              f"https://api.machines.dev/v1/apps/cave-sandbox/machines",
              headers={"Authorization": f"Bearer {FLY_API_TOKEN}"},
              json={
                  "name": f"sandbox-{project_id}",
                  "config": {
                      "image": "registry.fly.io/cave-sandbox-base:latest",
                      "auto_destroy": True,
                      "restart": {"policy": "no"},
                      "guest": {"cpu_kind": "shared", "cpus": 2, "memory_mb": 1024}
                  }
              }
          )
          return resp.json()["id"]
  ```

### 6. Artifact Storage
- **Provider:** Cloudflare R2 (S3-compatible, zero egress fees)
- **Structure:** `/{tenant_id}/{project_id}/v{version}/{filename}`
- **Access:** Presigned URLs (15-minute expiry) for dashboard downloads
- **Retention:** 30 days for free tier, 1 year for paid

---

## Environment Variables

```bash
# .env.production

# Core
SECRET_KEY=your-secret-key-here
ENVIRONMENT=production
DEBUG=false

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/cave
CHECKPOINT_DB_URL=postgresql://user:pass@host:5432/cave_checkpoints

# Redis
REDIS_URL=redis://default:pass@upstash-host:6379/0
REDIS_PUBSUB_URL=redis://default:pass@upstash-host:6379/1

# LLM Providers (platform keys for managed tier)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=...
NVIDIA_NIM_API_KEY=...

# Sandbox
FLY_API_TOKEN=fo1_...
FLY_SANDBOX_APP=cave-sandbox

# Storage
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=cave-artifacts

# Observability
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# Payments
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Supabase (for DB Agent sandbox provisioning)
SUPABASE_SERVICE_KEY=...
SUPABASE_ORG_ID=...
```

---

## Deployment Pipeline

```
GitHub Push → GitHub Actions
    │
    ├── Run tests (pytest + jest)
    ├── Build Docker images
    ├── Push to Fly.io Registry
    └── Deploy:
        ├── fly deploy --app cave-api
        └── fly deploy --app cave-worker
```

### GitHub Actions Workflow (minimal)
```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --app cave-api --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

---

## Cost Estimates (MVP Scale, ~100 runs/day)

| Service | Monthly Cost |
|---------|-------------|
| Fly.io API (2 instances) | ~$20 |
| Fly.io Workers (2 workers) | ~$30 |
| Fly Machines (sandboxes) | ~$15 |
| Upstash Redis | ~$10 |
| Supabase Pro (DB) | $25 |
| Cloudflare R2 | ~$5 |
| Vercel (dashboard) | Free |
| **Total infrastructure** | **~$105/mo** |

LLM costs are variable and passed through to users via the credits system.

---

## Scaling Playbook

**When worker queue depth > 50 jobs:** Scale Celery workers horizontally on Fly.io.

**When DB reads are slow:** Add a read replica. Checkpoint writes go to primary, state reads go to replica.

**When sandbox cold starts hurt:** Pre-warm a pool of 5 idle Fly Machines that get claimed on job start.

**When moving off Fly.io Machines:** Migrate to self-hosted Firecracker via `firecracker-containerd` on a dedicated bare-metal host. See `docs/architecture.md` for Firecracker setup.

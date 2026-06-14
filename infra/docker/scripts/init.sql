-- Initial database setup — runs on first PostgreSQL container start.
-- See lan.md for schema documentation.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Users ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    credits INTEGER DEFAULT 100,
    tier TEXT DEFAULT 'free',  -- free | pro | enterprise
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Projects ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    initial_prompt TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    current_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Checkpoints ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS project_checkpoints (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    state JSONB NOT NULL,
    agent TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, version)
);

-- ── LLM usage logs ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS llm_usage (
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

-- ── Model configurations ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS model_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    api_key_encrypted TEXT,
    base_url TEXT,
    is_active BOOLEAN DEFAULT true,
    agent_assignment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Row-Level Security ────────────────────────────────────────────────────

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_configs ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE polname = 'users_own_projects') THEN
        CREATE POLICY users_own_projects ON projects
            USING (user_id = current_setting('app.current_user_id')::UUID);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE polname = 'users_own_checkpoints') THEN
        CREATE POLICY users_own_checkpoints ON project_checkpoints
            USING (project_id IN (
                SELECT id FROM projects
                WHERE user_id = current_setting('app.current_user_id')::UUID
            ));
    END IF;
END
$$;

-- ── Indexes ────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_checkpoints_project_version ON project_checkpoints(project_id, version);
CREATE INDEX IF NOT EXISTS idx_llm_usage_project ON llm_usage(project_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_user ON llm_usage(user_id);
CREATE INDEX IF NOT EXISTS idx_model_configs_user ON model_configs(user_id);

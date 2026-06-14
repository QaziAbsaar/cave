"""Database Agent — generates PostgreSQL DDL from a product brief using LLM.

Phase 3: after LLM generates DDL, optionally executes it against a Supabase
project via the MCP supabase server.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from src.agents.base import BaseAgent
from src.orchestrator.llm_adapter import call_llm
from src.orchestrator.state import ProjectState

if TYPE_CHECKING:
    from src.mcp_gateway.gateway import MCPGateway

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "database.md"


def _load_system_prompt() -> str:
    """Load the Database Agent system prompt from file."""
    return _PROMPT_PATH.read_text()


class DatabaseAgent(BaseAgent):
    """Generates PostgreSQL schema DDL from a plain-language project brief.

    Reads: initial_prompt, product_spec from state slice.
    Writes: db_schema_ddl, db_credentials into state.artifacts.
    Phase 3: optionally executes DDL against Supabase via MCP.
    """

    def __init__(self) -> None:
        super().__init__("database_agent")
        self.system_prompt = _load_system_prompt()

    async def run(
        self,
        state: ProjectState,
        gateway: Optional[MCPGateway] = None,
    ) -> ProjectState:
        """Run the Database Agent: call LLM, optionally execute DDL via MCP."""
        logger.info("Database Agent: generating schema for project %s", state.project_id)

        # Build LLM messages
        user_content = f"## Project Brief\n\n{state.initial_prompt}\n"
        if state.artifacts.product_spec:
            user_content += f"\n## Product Spec\n\n{state.artifacts.product_spec}\n"

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]

        stub_config = type(
            "ModelConfigStub",
            (),
            {
                "litellm_model_string": "deepseek/deepseek-chat",
                "api_key_encrypted": None,
                "base_url": None,
                "model_name": "deepseek-chat",
            },
        )()

        try:
            response = await call_llm(messages, stub_config, max_tokens=4096)
            content = response["choices"][0]["message"]["content"]

            # Parse DDL from LLM response
            ddl = self._extract_ddl(content)

            # ── Phase 3: Execute DDL via Supabase MCP tool ──────────────
            if gateway is not None and ddl:
                try:
                    statements = self._split_statements(ddl)
                    executed = 0
                    for stmt in statements:
                        if not stmt.strip():
                            continue
                        result = await gateway.call_tool_text(
                            "execute_sql",
                            {"sql": stmt.strip()},
                        )
                        logger.info(
                            "DDL execution result: %s (project %s)",
                            result[:100],
                            state.project_id,
                        )
                        executed += 1

                    logger.info(
                        "Database Agent: executed %d/%d DDL statements via MCP",
                        executed,
                        len(statements),
                    )
                except Exception as mcp_err:
                    logger.warning(
                        "MCP DDL execution failed (continuing): %s", mcp_err
                    )
                    state.error_log.append(f"MCP DDL execution warning: {mcp_err}")
            # ─────────────────────────────────────────────────────────────

            # Update state
            state.artifacts.db_schema_ddl = ddl
            state.artifacts.db_credentials = {
                "db_name": "app",
                "schema_name": "public",
            }

            logger.info(
                "Database Agent: schema generated (%d chars) for project %s",
                len(ddl),
                state.project_id,
            )

        except Exception as exc:
            logger.exception("Database Agent failed: %s", exc)
            state.error_log.append(f"Database Agent error: {exc}")
            raise

        return state

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_ddl(content: str) -> str:
        """Extract SQL DDL from LLM response, handling markdown fences."""
        pattern = r"```(?:sql)?\s*\n?(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        if matches:
            return matches[0].strip()
        return content.strip()

    @staticmethod
    def _split_statements(ddl: str) -> list[str]:
        """Split a DDL script into individual SQL statements.

        Handles semicolons inside functions/triggers by doing a basic split.
        For production use a proper SQL parser (sqlparse).
        """
        # Basic split — works for CREATE TABLE, INDEX, etc.
        statements = []
        current = []
        for line in ddl.split("\n"):
            current.append(line)
            if line.strip().rstrip(";").strip() and line.strip().endswith(";"):
                stmt = "\n".join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
        # Catch any trailing statement without semicolon
        remaining = "\n".join(current).strip()
        if remaining:
            statements.append(remaining)
        return statements

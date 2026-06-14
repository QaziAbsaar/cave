"""Backend Agent — generates FastAPI application code from DB schema using LLM.

Phase 3: after LLM generates code, writes files to disk via the filesystem MCP server.
"""

from __future__ import annotations

import json
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

_PROMPT_PATH = Path(__file__).parent / "prompts" / "backend.md"


def _load_system_prompt() -> str:
    """Load the Backend Agent system prompt from file."""
    return _PROMPT_PATH.read_text()


class BackendAgent(BaseAgent):
    """Generates FastAPI backend code from PostgreSQL schema and product brief.

    Reads: db_schema_ddl, product_spec, db_credentials from state.
    Writes: backend_code, api_spec_openapi into artifacts.
    Phase 3: writes generated files to sandbox via MCP filesystem server.
    """

    def __init__(self) -> None:
        super().__init__("backend_agent")
        self.system_prompt = _load_system_prompt()

    async def run(
        self,
        state: ProjectState,
        gateway: Optional[MCPGateway] = None,
    ) -> ProjectState:
        """Run the Backend Agent: call LLM, optionally write files via MCP."""
        logger.info("Backend Agent: generating backend for project %s", state.project_id)

        user_content = f"## Database Schema\n\n{state.artifacts.db_schema_ddl or '(pending)'}\n"
        if state.artifacts.product_spec:
            user_content += f"\n## Product Spec\n\n{state.artifacts.product_spec}\n"
        user_content += f"\n## DB Credentials\n\n{json.dumps(state.artifacts.db_credentials, indent=2)}\n"

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
            response = await call_llm(messages, stub_config, max_tokens=8192)
            content = response["choices"][0]["message"]["content"]

            # Parse file blocks from response
            files = self._extract_files(content)
            openapi_spec = self._extract_openapi(content)

            state.artifacts.backend_code = files if files else {"app/main.py": content}
            if openapi_spec:
                state.artifacts.api_spec_openapi = openapi_spec

            # ── Phase 3: Write files to sandbox via MCP ─────────────────
            if gateway is not None and files:
                project_dir = f"projects/{state.project_id}/backend"
                written = 0
                for filepath, code in files.items():
                    try:
                        sandbox_path = f"{project_dir}/{filepath}"
                        await gateway.call_tool_text(
                            "write_file",
                            {"path": sandbox_path, "content": code},
                        )
                        written += 1
                    except Exception as write_err:
                        logger.warning(
                            "Failed to write %s via MCP (continuing): %s",
                            filepath,
                            write_err,
                        )

                logger.info(
                    "Backend Agent: wrote %d/%d files via MCP to %s",
                    written,
                    len(files),
                    project_dir,
                )
            # ────────────────────────────────────────────────────────────

            logger.info(
                "Backend Agent: generated %d files for project %s",
                len(state.artifacts.backend_code),
                state.project_id,
            )

        except Exception as exc:
            logger.exception("Backend Agent failed: %s", exc)
            state.error_log.append(f"Backend Agent error: {exc}")
            raise

        return state

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_files(content: str) -> dict[str, str]:
        """Extract filename→code dict from LLM response.

        Parses blocks formatted as:
        ```filepath=app/main.py
        code here
        ```
        """
        files: dict[str, str] = {}
        pattern = r"```(?:filepath=)?([^\s]+)\s*\n?(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        for filepath, code in matches:
            files[filepath.strip()] = code.strip()
        return files

    @staticmethod
    def _extract_openapi(content: str) -> Optional[dict]:
        """Try to extract an OpenAPI spec dict from the LLM response."""
        pattern = r"```(?:json|yaml)?\s*\n?(\{[\s\S]*?\"openapi\"[\s\S]*?\})```"
        matches = re.findall(pattern, content, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[0])
            except (json.JSONDecodeError, KeyError):
                pass
        return None

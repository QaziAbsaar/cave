"""Frontend Agent — generates React + Tailwind frontend from OpenAPI spec using LLM.

Injects the ui-ux-pro-max design system into the LLM prompt to ensure
all generated components follow the Project Cave brand guidelines.

Phase 3: writes generated files to sandbox via MCP filesystem server.
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

_PROMPT_PATH = Path(__file__).parent / "prompts" / "frontend.md"


def _load_system_prompt() -> str:
    """Load the Frontend Agent system prompt from file."""
    return _PROMPT_PATH.read_text()


class FrontendAgent(BaseAgent):
    """Generates React + Tailwind frontend code from an OpenAPI spec.

    Design system rules from ui-ux-pro-max are embedded in the system prompt
    to enforce brand consistency (dark OLED theme, Plus Jakarta Sans, etc.).

    Reads: api_spec_openapi from state.
    Writes: frontend_code into artifacts.
    Phase 3: writes generated files to sandbox via MCP filesystem server.
    """

    def __init__(self) -> None:
        super().__init__("frontend_agent")
        self.system_prompt = _load_system_prompt()

    async def run(
        self,
        state: ProjectState,
        gateway: Optional[MCPGateway] = None,
    ) -> ProjectState:
        """Run the Frontend Agent: call LLM, optionally write files via MCP."""
        logger.info("Frontend Agent: generating frontend for project %s", state.project_id)

        api_spec = state.artifacts.api_spec_openapi or {}
        user_content = f"## OpenAPI Spec\n\n{json.dumps(api_spec, indent=2)}\n"
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
                "litellm_model_string": "gpt-4o-mini",
                "api_key_encrypted": None,
                "base_url": None,
                "model_name": "gpt-4o-mini",
            },
        )()

        try:
            response = await call_llm(messages, stub_config, max_tokens=8192)
            content = response["choices"][0]["message"]["content"]

            files = self._extract_files(content)
            state.artifacts.frontend_code = files if files else {"src/App.tsx": content}

            # ── Phase 3: Write files to sandbox via MCP ─────────────────
            if gateway is not None and files:
                project_dir = f"projects/{state.project_id}/frontend"
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
                    "Frontend Agent: wrote %d/%d files via MCP to %s",
                    written,
                    len(files),
                    project_dir,
                )
            # ────────────────────────────────────────────────────────────

            logger.info(
                "Frontend Agent: generated %d files for project %s",
                len(state.artifacts.frontend_code),
                state.project_id,
            )

        except Exception as exc:
            logger.exception("Frontend Agent failed: %s", exc)
            state.error_log.append(f"Frontend Agent error: {exc}")
            raise

        return state

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_files(content: str) -> dict[str, str]:
        """Extract filename→code dict from LLM response.

        Parses blocks formatted as:
        ```filepath=src/components/Table.tsx
        code here
        ```
        """
        files: dict[str, str] = {}
        pattern = r"```(?:filepath=)?([^\s]+)\s*\n?(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        for filepath, code in matches:
            files[filepath.strip()] = code.strip()
        return files

"""Frontend Agent — generates React + Tailwind frontend from OpenAPI spec using LLM.

Injects the ui-ux-pro-max design system into the LLM prompt to ensure
all generated components follow the Project Cave brand guidelines.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from src.agents.base import BaseAgent
from src.orchestrator.llm_adapter import call_llm
from src.orchestrator.state import ProjectState

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
    Writes: frontend_code (dict of filename→code) into artifacts.
    """

    def __init__(self) -> None:
        super().__init__("frontend_agent")
        self.system_prompt = _load_system_prompt()

    async def run(
        self,
        state: ProjectState,
        model_config: Optional[Any] = None,
    ) -> ProjectState:
        """Run the Frontend Agent: call LLM and update artifacts.

        Args:
            state: Current pipeline state (reads api_spec_openapi).
            model_config: Optional model configuration.

        Returns:
            Updated state with frontend_code populated.
        """
        logger.info("Frontend Agent: generating frontend for project %s", state.project_id)

        import json

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

    @staticmethod
    def _extract_files(content: str) -> dict[str, str]:
        """Extract filename→code dict from LLM response.

        Parses blocks formatted as:
        ```filepath=src/components/Table.tsx
        code here
        ```
        """
        import re

        files: dict[str, str] = {}
        pattern = r"```(?:filepath=)?([^\s]+)\s*\n?(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        for filepath, code in matches:
            files[filepath.strip()] = code.strip()
        return files

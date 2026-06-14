"""Backend Agent — generates FastAPI application code from DB schema using LLM."""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from src.agents.base import BaseAgent
from src.orchestrator.llm_adapter import call_llm
from src.orchestrator.state import ProjectState

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "backend.md"


def _load_system_prompt() -> str:
    """Load the Backend Agent system prompt from file."""
    return _PROMPT_PATH.read_text()


class BackendAgent(BaseAgent):
    """Generates FastAPI backend code from PostgreSQL schema and product brief.

    Reads: db_schema_ddl, product_spec, db_credentials from state.
    Writes: backend_code (dict of filename→code), api_spec_openapi into artifacts.
    """

    def __init__(self) -> None:
        super().__init__("backend_agent")
        self.system_prompt = _load_system_prompt()

    async def run(
        self,
        state: ProjectState,
        model_config: Optional[Any] = None,
    ) -> ProjectState:
        """Run the Backend Agent: call LLM and update artifacts.

        Args:
            state: Current pipeline state (reads db_schema_ddl, product_spec).
            model_config: Optional model configuration.

        Returns:
            Updated state with backend_code and api_spec_openapi populated.
        """
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

    @staticmethod
    def _extract_files(content: str) -> dict[str, str]:
        """Extract filename→code dict from LLM response.

        Parses blocks formatted as:
        ```filepath=app/main.py
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

    @staticmethod
    def _extract_openapi(content: str) -> Optional[dict]:
        """Try to extract an OpenAPI spec dict from the LLM response."""
        import re

        pattern = r"```(?:json|yaml)?\s*\n?(\{[\s\S]*?\"openapi\"[\s\S]*?\})```"
        matches = re.findall(pattern, content, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[0])
            except (json.JSONDecodeError, KeyError):
                pass
        return None

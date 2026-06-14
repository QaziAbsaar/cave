"""Database Agent — generates PostgreSQL DDL from a product brief using LLM."""

import logging
from pathlib import Path
from typing import Optional

from src.agents.base import BaseAgent
from src.orchestrator.llm_adapter import call_llm
from src.orchestrator.state import ProjectState, Artifacts

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "database.md"


def _load_system_prompt() -> str:
    """Load the Database Agent system prompt from file."""
    return _PROMPT_PATH.read_text()


class DatabaseAgent(BaseAgent):
    """Generates PostgreSQL schema DDL from a plain-language project brief.

    Reads: initial_prompt, product_spec from state slice.
    Writes: db_schema_ddl, db_credentials into state.artifacts.
    """

    def __init__(self) -> None:
        super().__init__("database_agent")
        self.system_prompt = _load_system_prompt()

    async def run(
        self,
        state: ProjectState,
        model_config: Optional["ModelConfig"] = None,  # noqa: F821
    ) -> ProjectState:
        """Run the Database Agent: call LLM and update artifacts.

        Args:
            state: Current pipeline state (reads initial_prompt, product_spec).
            model_config: Optional model configuration (uses default if None).

        Returns:
            Updated state with db_schema_ddl and db_credentials populated.
        """
        logger.info("Database Agent: generating schema for project %s", state.project_id)

        # Build messages
        user_content = f"## Project Brief\n\n{state.initial_prompt}\n"
        if state.artifacts.product_spec:
            user_content += f"\n## Product Spec\n\n{state.artifacts.product_spec}\n"

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]

        # For now, use a simple dict as model config stub
        # In production, this comes from the model_configs DB table
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

            # Parse response — extract DDL between SQL fences or use raw content
            ddl = self._extract_ddl(content)

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

    @staticmethod
    def _extract_ddl(content: str) -> str:
        """Extract SQL DDL from LLM response, handling markdown fences."""
        import re

        # Try to extract SQL between ```sql ... ``` fences
        pattern = r"```(?:sql)?\s*\n?(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        if matches:
            return matches[0].strip()

        # Fall back to raw content if no fences found
        return content.strip()

"""Security/QA Agent — reviews artifacts for security and quality issues.

Implements retry logic: on failure, routes back to the offending agent
with specific feedback. Max 3 retries per agent before INTERVENTION_NEEDED.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.agents.base import BaseAgent
from src.orchestrator.llm_adapter import call_llm
from src.orchestrator.state import ProjectState, AgentStatus, AgentIteration

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "security.md"

MAX_RETRIES_PER_AGENT = 3


def _load_system_prompt() -> str:
    """Load the Security/QA Agent system prompt from file."""
    return _PROMPT_PATH.read_text()


class SecurityAgent(BaseAgent):
    """Reviews all generated artifacts for security vulnerabilities and code quality issues.

    Determines pass/fail and routes back to offending agents on failure.
    Tracks retry count per agent via state.iteration_counts.

    Reads: All artifacts (db_schema_ddl, backend_code, frontend_code, api_spec_openapi).
    Writes: test_report into artifacts.
    Mutates: status, current_agent, security_history, iteration_counts.
    """

    def __init__(self) -> None:
        super().__init__("security_agent")
        self.system_prompt = _load_system_prompt()

    async def run(
        self,
        state: ProjectState,
        model_config: Optional[Any] = None,
    ) -> ProjectState:
        """Run the Security/QA Agent.

        Args:
            state: Current pipeline state (reads all artifacts).
            model_config: Optional model configuration.

        Returns:
            Updated state with test_report and possibly modified status.
        """
        logger.info("Security Agent: reviewing project %s", state.project_id)

        # Build review context
        review_data = {
            "db_schema_ddl": state.artifacts.db_schema_ddl or "(empty)",
            "api_spec_openapi": state.artifacts.api_spec_openapi or {},
            "backend_code": state.artifacts.backend_code,
            "frontend_code": state.artifacts.frontend_code,
            "dependencies": state.artifacts.dependencies,
            "security_history": [h.model_dump() for h in state.security_history],
        }

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": json.dumps(review_data, indent=2)},
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

            test_report = self._parse_report(content)
            state.artifacts.test_report = test_report

            if not test_report:
                # No issues — pass
                state.status = AgentStatus.SUCCESS
                logger.info("Security Agent: project %s PASSED", state.project_id)
                return state

            # Issues found — determine offending agent and retry
            offending_agent = self._determine_offending_agent(test_report)
            attempt = state.iteration_counts.get(offending_agent, 0) + 1
            state.iteration_counts[offending_agent] = attempt

            # Record this iteration
            state.security_history.append(
                AgentIteration(
                    agent=offending_agent,
                    attempt=attempt,
                    feedback=json.dumps(test_report, indent=2),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )

            if attempt >= MAX_RETRIES_PER_AGENT:
                # Exhausted retries — signal intervention needed
                state.status = AgentStatus.INTERVENTION_NEEDED
                state.current_agent = offending_agent
                logger.warning(
                    "Security Agent: %s failed after %d retries — intervention needed",
                    offending_agent,
                    attempt,
                )
            else:
                # Route back to offending agent for fixes
                state.current_agent = offending_agent
                logger.info(
                    "Security Agent: routing back to %s (attempt %d/%d)",
                    offending_agent,
                    attempt,
                    MAX_RETRIES_PER_AGENT,
                )

        except Exception as exc:
            logger.exception("Security Agent failed: %s", exc)
            state.error_log.append(f"Security Agent error: {exc}")
            raise

        return state

    @staticmethod
    def _parse_report(content: str) -> Optional[dict]:
        """Parse JSON test_report from LLM response."""
        import re

        pattern = r'```(?:json)?\s*\n?(\{[^`]*?"test_report"[^`]*?\})```'
        matches = re.findall(pattern, content, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[0])
            except json.JSONDecodeError:
                pass

        # Try parsing entire response as JSON
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            pass

        # Return minimal report with raw content
        return {
            "passed": False,
            "issues": [{
                "severity": "medium",
                "category": "quality",
                "agent": "unknown",
                "description": f"Raw review output (parse failed): {content[:200]}",
                "recommendation": "Manual review required",
            }],
            "summary": {"total_issues": 1, "critical": 0, "high": 0, "medium": 1, "low": 0},
        }

    @staticmethod
    def _determine_offending_agent(report: dict) -> str:
        """Determine which agent caused the most severe issues."""
        issues = report.get("issues", [])
        if not issues:
            return "backend_agent"

        # Count issues per agent, weighted by severity
        severity_weight = {"critical": 10, "high": 5, "medium": 2, "low": 1}
        agent_scores: dict[str, int] = {}

        for issue in issues:
            agent = issue.get("agent", "backend_agent")
            sev = issue.get("severity", "medium")
            weight = severity_weight.get(sev, 1)
            agent_scores[agent] = agent_scores.get(agent, 0) + weight

        # Return the agent with highest weighted score
        return max(agent_scores, key=agent_scores.get)

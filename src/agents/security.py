"""Security/QA Agent — reviews artifacts for security and quality issues.

Implements retry logic: on failure, routes back to the offending agent
with specific feedback. Max 3 retries per agent before INTERVENTION_NEEDED.

Phase 3: runs semgrep SAST and linter via MCP in addition to LLM review.
Real SAST results are merged into the test_report.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from src.agents.base import BaseAgent
from src.orchestrator.llm_adapter import call_llm
from src.orchestrator.state import ProjectState, AgentStatus, AgentIteration

if TYPE_CHECKING:
    from src.mcp_gateway.gateway import MCPGateway

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

    Reads: All artifacts.
    Writes: test_report into artifacts.
    Phase 3: merges real SAST/linter findings from MCP into the report.
    """

    def __init__(self) -> None:
        super().__init__("security_agent")
        self.system_prompt = _load_system_prompt()

    async def run(
        self,
        state: ProjectState,
        gateway: Optional[MCPGateway] = None,
    ) -> ProjectState:
        """Run the Security/QA Agent: LLM review + optional MCP SAST scan."""
        logger.info("Security Agent: reviewing project %s", state.project_id)

        # ── Phase 3: Run SAST tools via MCP ────────────────────────────
        mcp_findings: list[dict] = []
        if gateway is not None:
            mcp_findings = await self._run_sast_tools(state, gateway)
        # ────────────────────────────────────────────────────────────────

        # Build review context for LLM (include MCP findings if any)
        review_data = {
            "db_schema_ddl": state.artifacts.db_schema_ddl or "(empty)",
            "api_spec_openapi": state.artifacts.api_spec_openapi or {},
            "backend_code": state.artifacts.backend_code,
            "frontend_code": state.artifacts.frontend_code,
            "dependencies": state.artifacts.dependencies,
            "security_history": [h.model_dump() for h in state.security_history],
        }
        if mcp_findings:
            review_data["sast_findings"] = mcp_findings

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
                state.status = AgentStatus.SUCCESS
                logger.info("Security Agent: project %s PASSED", state.project_id)
                return state

            # Issues found — determine offending agent and retry
            offending_agent = self._determine_offending_agent(test_report)
            attempt = state.iteration_counts.get(offending_agent, 0) + 1
            state.iteration_counts[offending_agent] = attempt

            state.security_history.append(
                AgentIteration(
                    agent=offending_agent,
                    attempt=attempt,
                    feedback=json.dumps(test_report, indent=2),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )

            if attempt >= MAX_RETRIES_PER_AGENT:
                state.status = AgentStatus.INTERVENTION_NEEDED
                state.current_agent = offending_agent
                logger.warning(
                    "Security Agent: %s failed after %d retries — intervention needed",
                    offending_agent,
                    attempt,
                )
            else:
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

    # ------------------------------------------------------------------
    # Phase 3: MCP SAST integration
    # ------------------------------------------------------------------

    async def _run_sast_tools(
        self,
        state: ProjectState,
        gateway: MCPGateway,
    ) -> list[dict]:
        """Run semgrep and linter via MCP, return merged findings."""
        findings: list[dict] = []
        target_dir = f"projects/{state.project_id}"

        # 1. Run semgrep
        try:
            semgrep_result = await gateway.call_tool_text(
                "run_semgrep",
                {"target_dir": target_dir, "rules": "p/default"},
            )
            parsed = json.loads(semgrep_result)
            results = parsed.get("results", [])
            for r in results:
                findings.append({
                    "tool": "semgrep",
                    "severity": r.get("extra", {}).get("severity", "medium"),
                    "rule": r.get("check_id", "unknown"),
                    "path": r.get("path", ""),
                    "line": r.get("start", {}).get("line", 0),
                    "message": r.get("extra", {}).get("message", r.get("short", "")),
                })

            logger.info("Semgrep found %d findings for project %s", len(results), state.project_id)
        except Exception as exc:
            logger.warning("Semgrep MCP scan failed (continuing): %s", exc)

        # 2. Run linter
        try:
            lint_result = await gateway.call_tool_text(
                "run_linter",
                {"target_dir": target_dir, "tool": "ruff"},
            )
            parsed = json.loads(lint_result)
            lint_findings = parsed.get("findings", [])
            for r in lint_findings:
                findings.append({
                    "tool": "ruff",
                    "severity": r.get("level", r.get("type", "medium")),
                    "rule": r.get("rule", r.get("code", "unknown")),
                    "path": r.get("filename", ""),
                    "line": r.get("line", r.get("location", {}).get("line", 0)),
                    "message": r.get("message", r.get("text", "")),
                })

            logger.info("Linter found %d findings for project %s", len(lint_findings), state.project_id)
        except Exception as exc:
            logger.warning("Linter MCP scan failed (continuing): %s", exc)

        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_report(content: str) -> Optional[dict]:
        """Parse JSON test_report from LLM response."""
        pattern = r'```(?:json)?\s*\n?(\{[^`]*?"test_report"[^`]*?\})```'
        matches = re.findall(pattern, content, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[0])
            except json.JSONDecodeError:
                pass

        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            pass

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

        severity_weight = {"critical": 10, "high": 5, "medium": 2, "low": 1}
        agent_scores: dict[str, int] = {}

        for issue in issues:
            agent = issue.get("agent", "backend_agent")
            sev = issue.get("severity", "medium")
            weight = severity_weight.get(sev, 1)
            agent_scores[agent] = agent_scores.get(agent, 0) + weight

        return max(agent_scores, key=agent_scores.get)

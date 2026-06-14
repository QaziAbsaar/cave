"""Edge routing logic for the LangGraph DAG.

Phase 2 routing supports:
- Linear pass-through (standard flow)
- Security retry loop — if security_agent detects issues, routes back to offending agent
- Intervention detection — stops pipeline when INTERVENTION_NEEDED
"""

from src.orchestrator.state import ProjectState, AgentStatus


# Agent execution order for Phase 2
AGENT_ORDER: list[str] = [
    "database_agent",
    "backend_agent",
    "frontend_agent",
    "security_agent",
]


def decide_next_agent(state: ProjectState) -> str:
    """Return the next node name, or '__end__' when the pipeline is complete.

    Routing logic:
    1. If status is FAILED or INTERVENTION_NEEDED → end
    2. If current_agent is not in AGENT_ORDER (e.g., security rerouted to another) → follow it
    3. If current_agent is security_agent and SUCCESS → end
    4. Otherwise → linear progression through AGENT_ORDER

    Args:
        state: Current pipeline state (checks current_agent, status).

    Returns:
        Name of the next LangGraph node to execute, or '__end__'.
    """
    # Terminal states
    if state.status in (AgentStatus.FAILED, AgentStatus.INTERVENTION_NEEDED):
        return "__end__"

    if state.status == AgentStatus.SUCCESS:
        return "__end__"

    current = state.current_agent

    # Security agent rerouted: follow the reroute to the offending agent
    # (security_agent sets current_agent to the failing agent)
    if current not in AGENT_ORDER:
        # Unknown agent — go back to start of pipeline
        return AGENT_ORDER[0]

    # If security agent ran and found no issues, router points to itself
    # Check if we should continue to next agent
    if current == "security_agent":
        # Security agent may have set status to SUCCESS (pass) or
        # rerouted current_agent to a different agent (retry)
        if state.status == AgentStatus.SUCCESS:
            return "__end__"
        # If security_agent rerouted, current_agent is already changed
        # The next invocation will pick up the new agent
        return current

    # Linear progression
    try:
        idx = AGENT_ORDER.index(current)
        return AGENT_ORDER[idx + 1] if idx + 1 < len(AGENT_ORDER) else "__end__"
    except ValueError:
        return "__end__"

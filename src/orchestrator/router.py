"""Edge routing logic for the LangGraph DAG.

In Phase 1 (mock agents), routing is a simple linear pass-through.
Phase 2+ will include retry loops, conditional branching for security/QA failures,
and human-in-the-loop intervention checks.
"""

from src.orchestrator.state import ProjectState, AgentStatus


# Linear agent order for Phase 1
AGENT_ORDER: list[str] = [
    "database_agent",
    "backend_agent",
    "frontend_agent",
    "security_agent",
]


def decide_next_agent(state: ProjectState) -> str:
    """Return the next node name, or '__end__' when the pipeline is complete.

    Args:
        state: The current pipeline state, including current_agent and step_number.

    Returns:
        Name of the next agent node to execute, or '__end__'.
    """
    if state.status in (AgentStatus.FAILED, AgentStatus.INTERVENTION_NEEDED):
        return "__end__"

    current = state.current_agent

    # If at 'orchestrator', start the first agent
    if current == "orchestrator":
        return AGENT_ORDER[0]

    # Find current agent in order and return the next one
    try:
        idx = AGENT_ORDER.index(current)
        if idx + 1 < len(AGENT_ORDER):
            return AGENT_ORDER[idx + 1]
        return "__end__"
    except ValueError:
        return "__end__"

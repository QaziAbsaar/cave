"""LangGraph DAG definition — 4-agent pipeline with real LLM agents and MCP tool integration.

Phase 2: agents call LLM via LiteLLM to generate real artifacts.
Phase 3: agents optionally use MCP gateway for tool calls (filesystem, supabase, SAST).
Checkpoints are saved after every agent step.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Optional

from langgraph.graph import StateGraph

from src.orchestrator.state import ProjectState, AgentStatus
from src.orchestrator.router import decide_next_agent
from src.agents.database import DatabaseAgent
from src.agents.backend import BackendAgent
from src.agents.frontend import FrontendAgent
from src.agents.security import SecurityAgent

if TYPE_CHECKING:
    from src.mcp_gateway.gateway import MCPGateway

logger = logging.getLogger(__name__)

REDIS_PUBSUB_URL: str = os.getenv("REDIS_PUBSUB_URL", "redis://localhost:6379/1")

# Optional external callbacks injected by the worker
_save_checkpoint_cb: Optional[Callable[[ProjectState], None]] = None
_mcp_gateway: Optional[MCPGateway] = None


def set_checkpoint_callback(cb: Callable[[ProjectState], None]) -> None:
    """Inject a checkpoint save callback into the graph runner."""
    global _save_checkpoint_cb
    _save_checkpoint_cb = cb


def set_mcp_gateway(gateway: MCPGateway) -> None:
    """Inject the MCP gateway into the graph runner (Phase 3)."""
    global _mcp_gateway
    _mcp_gateway = gateway


def _publish_event(project_id: str, event: str, data: dict[str, Any]) -> None:
    """Publish a progress event to the Redis pub/sub channel for this project."""
    import redis as sync_redis
    try:
        r = sync_redis.from_url(REDIS_PUBSUB_URL)
        r.publish(
            f"project:{project_id}",
            json.dumps({
                "event": event,
                "project_id": project_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "data": data,
            }),
        )
    except Exception as exc:
        logger.warning("Redis pub unavailable (event=%s project=%s): %s", event, project_id, exc)


async def _run_agent_node(state: ProjectState, agent_name: str) -> ProjectState:
    """Generic agent node runner: instantiates agent, publishes events, checkpoints.

    Maps agent_name to the correct agent class, passes the MCP gateway,
    and runs it.
    """
    project_id = state.project_id

    # Notify: agent started
    _publish_event(project_id, "agent_started", {
        "agent": agent_name,
        "step": state.step_number + 1,
    })

    # Instantiate the correct agent and run with optional MCP gateway
    agent = _create_agent(agent_name)
    updated_state = await agent.run(state, gateway=_mcp_gateway)

    # Update tracking fields
    updated_state.current_agent = agent_name
    updated_state.step_number += 1

    # Save checkpoint after each agent
    if _save_checkpoint_cb is not None:
        _save_checkpoint_cb(updated_state)
        _publish_event(project_id, "checkpoint_saved", {"version": updated_state.version})

    # Notify: agent completed (or project_completed for final)
    if updated_state.status in (AgentStatus.SUCCESS, AgentStatus.INTERVENTION_NEEDED):
        _publish_event(project_id, "project_completed", {
            "download_url": "",
            "total_cost": 0.0,
            "status": updated_state.status.value,
        })
    else:
        _publish_event(project_id, "agent_completed", {
            "agent": agent_name,
            "step": updated_state.step_number,
        })

    return updated_state


def _create_agent(agent_name: str):
    """Factory: returns the right agent class for a given name."""
    agents = {
        "database_agent": DatabaseAgent(),
        "backend_agent": BackendAgent(),
        "frontend_agent": FrontendAgent(),
        "security_agent": SecurityAgent(),
    }
    agent = agents.get(agent_name)
    if agent is None:
        raise ValueError(f"Unknown agent: {agent_name}")
    return agent


# ---- LangGraph node functions (thin wrappers that delegate to _run_agent_node) ----


async def database_agent(state: ProjectState) -> ProjectState:
    """Database Agent node."""
    return await _run_agent_node(state, "database_agent")


async def backend_agent(state: ProjectState) -> ProjectState:
    """Backend Agent node."""
    return await _run_agent_node(state, "backend_agent")


async def frontend_agent(state: ProjectState) -> ProjectState:
    """Frontend Agent node."""
    return await _run_agent_node(state, "frontend_agent")


async def security_agent(state: ProjectState) -> ProjectState:
    """Security/QA Agent node."""
    return await _run_agent_node(state, "security_agent")


# ---- Build the graph ----


def build_graph() -> StateGraph:
    """Construct and compile the agent pipeline graph.

    Returns:
        A compiled LangGraph StateGraph that accepts and returns ProjectState.
    """
    workflow = StateGraph(ProjectState)

    # Register nodes
    workflow.add_node("database_agent", database_agent)
    workflow.add_node("backend_agent", backend_agent)
    workflow.add_node("frontend_agent", frontend_agent)
    workflow.add_node("security_agent", security_agent)

    # Entry point
    workflow.set_entry_point("database_agent")

    # Edges — route via decide_next_agent (handles retry routing dynamically)
    for agent_node in ("database_agent", "backend_agent", "frontend_agent", "security_agent"):
        workflow.add_conditional_edges(agent_node, decide_next_agent)

    return workflow.compile()

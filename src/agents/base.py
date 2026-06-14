"""Abstract base agent class for the pipeline.

Phase 1: mock agents.
Phase 2: real LLM agents.
Phase 3: agents with MCP tool integration (optional gateway).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from src.orchestrator.state import ProjectState

if TYPE_CHECKING:
    from src.mcp_gateway.gateway import MCPGateway


class BaseAgent(ABC):
    """Base class for all pipeline agents.

    Each agent receives a slice of ProjectState, performs its work,
    and returns the updated state.

    If a MCPGateway is provided, the agent can call external tools
    (filesystem, supabase, SAST) after generating artifacts via LLM.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    async def run(
        self,
        state: ProjectState,
        gateway: Optional[MCPGateway] = None,
    ) -> ProjectState:
        """Execute the agent's task and return updated state.

        Args:
            state: Current pipeline state slice.
            gateway: Optional MCPGateway for tool calls (Phase 3+).
        """
        ...

"""Abstract base agent class for the pipeline.

Phase 1 uses mock agents. Real agent implementations come in Phase 2.
"""

from abc import ABC, abstractmethod

from src.orchestrator.state import ProjectState


class BaseAgent(ABC):
    """Base class for all pipeline agents.

    Each agent receives a slice of ProjectState, performs its work,
    and returns the updated state.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    async def run(self, state: ProjectState) -> ProjectState:
        """Execute the agent's task and return updated state."""
        ...

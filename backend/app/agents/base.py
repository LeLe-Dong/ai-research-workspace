from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class ResearchRequest:
    research_id: str
    title: str
    goal: str
    constraints: str
    expected_output: str
    depth: str
    priority: str


@dataclass
class AgentEvent:
    """Pushed from agent → UI via SSE."""
    phase: str          # understand / decompose / search / read / analyze / derive / summarize
    level: str          # info / warn / error / success
    title: str
    detail: str = ""
    task_id: str | None = None
    task_progress: int | None = None
    artifact: dict | None = None   # {kind, title, content}


class AgentClient(ABC):
    """Interface; swap implementations by config."""

    @abstractmethod
    async def run_research(
        self, req: ResearchRequest
    ) -> AsyncIterator[AgentEvent]:
        """Yield events throughout the research lifecycle."""
        if False:
            yield  # pragma: no cover

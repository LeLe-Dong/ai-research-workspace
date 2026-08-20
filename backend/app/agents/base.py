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
    # 0=auto (default), 1=force on, -1=force off — see services/decision.py
    requires_k8s_validation: int = 0
    # Personalized style: 1 = inject a KnowledgeStyle into prompt
    use_custom_style: int = 0
    # NULL = use currently active style; non-null = bind to specific style
    style_id: str | None = None


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

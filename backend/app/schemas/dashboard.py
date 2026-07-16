from datetime import datetime
from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_researches: int
    completed: int
    running: int
    today_completed: int
    average_score: float
    kb_count: int = 0


class RecentResearch(BaseModel):
    id: str
    title: str
    status: str
    priority: str
    depth: str
    score: float | None = None
    updated_at: datetime


class PopularKnowledge(BaseModel):
    id: str
    research_id: str
    title: str
    excerpt: str
    tags: list[str]
    score: float
    updated_at: datetime


class AgentStatus(BaseModel):
    engine: str
    mode: str
    version: str
    online: bool
    last_active: str | None = None


class DashboardData(BaseModel):
    stats: DashboardStats
    recent: list[RecentResearch]
    popular: list[PopularKnowledge]
    agent: AgentStatus

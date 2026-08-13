from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


# --- Request schemas ---
class ResearchCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1)
    constraints: str = ""
    expected_output: str = ""
    depth: Literal["quick", "standard", "deep"] = "standard"
    priority: Literal["low", "medium", "high"] = "medium"
    estimated_cost: float = 0.0
    # Smart K8s validation: 0=auto (default), 1=force on, -1=force off
    requires_k8s_validation: int = 0
    # Personalized research style (Phase A/B): when 1, the agent injects a
    # KnowledgeStyle into the research prompt. `style_id` (optional) names
    # a SPECIFIC style; if absent, the currently active style is used.
    use_custom_style: int = 0
    style_id: str | None = None  # binds to a specific KnowledgeStyle
    tag_names: list[str] = []  # Optional tags to attach on create
    # Research-topic aggregation (iterative baseline): attach this research
    # to a topic so it counts as one iteration of that subject.
    topic_id: str | None = None


# --- Response schemas ---
class ResearchSummary(BaseModel):
    id: str
    title: str
    status: str
    priority: str
    depth: str
    score: float | None = None
    error_message: str | None = None
    tags: list[TagOut] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TagOut(BaseModel):
    id: str
    name: str
    color: str

    class Config:
        from_attributes = True


class ResearchDetail(BaseModel):
    id: str
    title: str
    goal: str
    constraints: str
    expected_output: str
    depth: str
    priority: str
    estimated_cost: float
    status: str
    error_message: str | None = None
    topic_id: str | None = None
    iteration: int | None = None
    created_at: datetime
    updated_at: datetime
    tags: list[TagOut] = []

    class Config:
        from_attributes = True


class TaskProgress(BaseModel):
    """One row of progress info from the `tasks` table."""
    id: str
    name: str
    phase: str
    status: str  # pending | running | done | failed
    progress: int  # 0-100
    started_at: datetime | None = None
    finished_at: datetime | None = None
    order_index: int


class ReviewSummary(BaseModel):
    overall_score: float
    dimensions: dict
    strengths: str
    weaknesses: str
    suggestions: str
    threshold: float


class ResearchProgress(BaseModel):
    """Aggregated view of a single research's execution state.

    Single round-trip replaces the previous 7-call pattern
    (researches + tasks + timeline + artifacts + report + review + versions).

    When a research was killed or crashed mid-flight, the `progress_*`
    counters reflect what was actually recorded up to the moment the asyncio
    task died. Anything recorded afterwards is missing — that's the gap
    this endpoint surfaces explicitly via `coverage_gaps`.
    """
    # Top-level metadata
    id: str
    title: str
    status: str
    priority: str
    depth: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    duration_sec: float | None = None  # updated - created

    # Aggregated progress counters
    progress_tasks_done: int = 0
    progress_tasks_total: int = 0
    progress_tasks_pct: float = 0.0  # 0..100 (count done / total)
    progress_timeline_events: int = 0
    progress_timeline_first: datetime | None = None
    progress_timeline_last: datetime | None = None
    progress_timeline_gap_sec: float | None = None  # last - first; large gap = stalled

    # Score
    score: float | None = None
    review: ReviewSummary | None = None

    # Content
    artifacts: list[dict] = []  # [{"kind": "...", "title": "...", "version": 1, "size_bytes": N}]
    report_length_chars: int = 0
    versions_count: int = 0

    # Coverage analysis
    coverage_gaps: list[str] = []  # human-readable list of missing/likely-broken fields


class TaskNode(BaseModel):
    id: str
    parent_id: str | None
    name: str
    phase: str
    status: str
    progress: int
    order_index: int

    class Config:
        from_attributes = True


class TimelineEventOut(BaseModel):
    id: str
    ts: datetime
    phase: str
    level: str
    title: str
    detail: str
    sequence: int
    # Optional link to Task. Null when the event is not associated with a
    # specific task (e.g. mock per-phase events, LLM trace events, hermes
    # stdout lines). Powers the "click task → filter console" feature.
    task_id: str | None = None

    class Config:
        from_attributes = True


class ArtifactOut(BaseModel):
    id: str
    kind: str
    title: str
    content: str
    version: int
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewOut(BaseModel):
    overall_score: float
    dimensions: dict
    strengths: str
    weaknesses: str
    suggestions: str
    threshold: float

    class Config:
        from_attributes = True

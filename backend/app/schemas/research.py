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
    tag_names: list[str] = []  # Optional tags to attach on create


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
    created_at: datetime
    updated_at: datetime
    tags: list[TagOut] = []

    class Config:
        from_attributes = True


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

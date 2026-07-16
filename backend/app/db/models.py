from datetime import datetime
from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid

from app.db.database import Base


def gen_id() -> str:
    return uuid.uuid4().hex[:12]


class Research(Base):
    __tablename__ = "researches"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    title: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str] = mapped_column(Text)
    constraints: Mapped[str] = mapped_column(Text, default="")
    expected_output: Mapped[str] = mapped_column(Text, default="")
    depth: Mapped[str] = mapped_column(String(20), default="standard")  # quick / standard / deep
    priority: Mapped[str] = mapped_column(String(20), default="medium")  # low / medium / high
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)  # Set when status='failed'
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending / running / completed / failed

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tasks: Mapped[list["Task"]] = relationship(back_populates="research", cascade="all, delete-orphan", order_by="Task.order_index")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="research", cascade="all, delete-orphan")


    # Version control
    versions: Mapped[list["ResearchVersion"]] = relationship("ResearchVersion", order_by="ResearchVersion.version", back_populates="research")
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="research", cascade="all, delete-orphan", lazy="selectin")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    research_id: Mapped[str] = mapped_column(String(12), ForeignKey("researches.id"))
    parent_id: Mapped[str | None] = mapped_column(String(12), ForeignKey("tasks.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    phase: Mapped[str] = mapped_column(String(50))  # requirement / research / comparison / evaluation / report
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending / running / done / failed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    research: Mapped["Research"] = relationship(back_populates="tasks")





class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    research_id: Mapped[str] = mapped_column(String(12), ForeignKey("researches.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    phase: Mapped[str] = mapped_column(String(50))  # understand / decompose / search / read / analyze / derive / summarize
    level: Mapped[str] = mapped_column(String(20), default="info")  # info / warn / error / success
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    sequence: Mapped[int] = mapped_column(Integer, default=0)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    research_id: Mapped[str] = mapped_column(String(12), ForeignKey("researches.id"))
    kind: Mapped[str] = mapped_column(String(50))  # mermaid / markdown / table / architecture
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    research: Mapped["Research"] = relationship(back_populates="artifacts")



class ResearchVersion(Base):
    """Git-like version snapshot of a research run."""
    __tablename__ = "research_versions"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=lambda: str(__import__("uuid").uuid4().hex[:12]))
    research_id: Mapped[str] = mapped_column(String(12), ForeignKey("researches.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, index=True)  # 1, 2, 3... per research
    title: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str] = mapped_column(Text)
    constraints: Mapped[str] = mapped_column(Text, default="")
    expected_output: Mapped[str] = mapped_column(Text, default="")
    depth: Mapped[str] = mapped_column(String(20))
    priority: Mapped[str] = mapped_column(String(20))
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20))  # pending/running/completed/failed
    report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)  # Snapshot of report
    review_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # Snapshot of review
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "user" or "system"
    commit_message: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Previous version number

    # Relationship
    research: Mapped["Research"] = relationship("Research", back_populates="versions")



class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    research_id: Mapped[str] = mapped_column(String(12), ForeignKey("researches.id"), unique=True)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict)
    strengths: Mapped[str] = mapped_column(Text, default="")
    weaknesses: Mapped[str] = mapped_column(Text, default="")
    suggestions: Mapped[str] = mapped_column(Text, default="")
    threshold: Mapped[float] = mapped_column(Float, default=7.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    research: Mapped["Research"] = relationship(back_populates="reviews")


class AppConfig(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class Tag(Base):
    """Tag for categorizing researches (e.g., 'langchain', 'database', 'urgent')."""
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    color: Mapped[str] = mapped_column(String(20), default="blue")  # blue/green/red/amber/purple
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Many-to-many
    researches: Mapped[list["Research"]] = relationship(
        "Research", secondary="research_tags", back_populates="tags"
    )


class ResearchTag(Base):
    """Many-to-many join table between Research and Tag."""
    __tablename__ = "research_tags"

    research_id: Mapped[str] = mapped_column(String(12), ForeignKey("researches.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(String(12), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# Add tags relationship to Research
Research.tags = relationship("Tag", secondary="research_tags", back_populates="researches")

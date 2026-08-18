from datetime import datetime
from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid

from app.db.base import Base


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
    # Smart K8s validation trigger:
    #   0  = auto (multi-signal decision: goal/title/output + depth)
    #   1  = force on (user explicitly wants k8s pod validation)
    #  -1  = force off (user explicitly opted out)
    requires_k8s_validation: Mapped[int] = mapped_column(Integer, default=0)
    # When 1, the agent injects a KnowledgeStyle into the research prompt.
    # `style_id` (nullable) names the SPECIFIC style to use. When null,
    # the active style is used as fallback. Different research tasks can
    # bind to different styles (e.g. "数据库" vs "安全" vs "架构").
    use_custom_style: Mapped[int] = mapped_column(Integer, default=0)
    style_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)  # Set when status='failed'
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending / running / completed / failed

    # Topic aggregation: a research belongs to a "research topic" so the same
    # subject can be studied multiple times (iterations) with the user
    # reviewing + adjusting the research boundary each round. Nullable for
    # standalone researches.
    topic_id: Mapped[str | None] = mapped_column(String(12), ForeignKey("research_topics.id"), nullable=True, index=True)
    iteration: Mapped[int] = mapped_column(Integer, default=1)  # 1-based round within its topic
    # Reference to the iteration this round was launched from (for traceable
    # "based on round N, adjusted X" iteration chains).
    prev_iteration_id: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tasks: Mapped[list["Task"]] = relationship(back_populates="research", cascade="all, delete-orphan", order_by="Task.order_index")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="research", cascade="all, delete-orphan")


    # Version control — cascade delete so removing a research (or its topic)
    # also cleans up its version snapshots (otherwise research_versions.research_id
    # is set to NULL, violating NOT NULL).
    versions: Mapped[list["ResearchVersion"]] = relationship(
        "ResearchVersion", order_by="ResearchVersion.version",
        back_populates="research", cascade="all, delete-orphan",
    )
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="research", cascade="all, delete-orphan", lazy="selectin")
    topic: Mapped["ResearchTopic | None"] = relationship("ResearchTopic", back_populates="researches")


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
    # Optional FK to Task. Nullable because:
    # - Mock-agent per-phase events (TIMELINE_PHASES) don't carry task context
    # - All stepfun _llm_event traces are task-less
    # - All hermes _on_log lines are task-less
    # Final artifact / review events are also task-less by design.
    task_id: Mapped[str | None] = mapped_column(
        String(12), ForeignKey("tasks.id"), nullable=True, index=True
    )


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
    # Legacy single-string fields (kept for backwards compat with old reviews)
    strengths: Mapped[str] = mapped_column(Text, default="")
    weaknesses: Mapped[str] = mapped_column(Text, default="")
    suggestions: Mapped[str] = mapped_column(Text, default="")
    # New structured fields (Phase 25: upgraded reviewer)
    verdict: Mapped[str] = mapped_column(Text, default="")  # one-sentence conclusion
    strengths_list: Mapped[str] = mapped_column(Text, default="")  # JSON-encoded list of strings
    weaknesses_list: Mapped[str] = mapped_column(Text, default="")  # JSON-encoded list of strings
    improvements: Mapped[str] = mapped_column(Text, default="")  # JSON-encoded list of strings
    critical_questions: Mapped[str] = mapped_column(Text, default="")  # JSON-encoded list of strings
    next_steps: Mapped[str] = mapped_column(Text, default="")  # JSON-encoded list of strings
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

class K8sCluster(Base):
    """User-configured Kubernetes cluster connection for environment validation.

    Secrets (bearer_token, ca_cert) are Fernet-encrypted before being persisted.
    """
    __tablename__ = "k8s_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    api_server: Mapped[str] = mapped_column(String(512), nullable=False)
    default_namespace: Mapped[str] = mapped_column(String(64), nullable=False, default="airw-research")
    skip_tls_verify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bearer_token_enc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ca_cert_enc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kubeconfig_yaml: Mapped[str] = mapped_column(Text, nullable=False, default="")

    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ResearchResource(Base):
    """K8s resources created on behalf of a research's validate phase.

    Why this table exists
    ---------------------
    Before this table, the only cleanup mechanism for K8s resources created
    during research validation was a kubectl delete with the `app=airw-validate`
    label selector (see app.agents.k8s._safety_net_cleanup). That worked when
    the only resource created was the test pod — but once we let the AI
    submit arbitrary manifests (post ADR-002), we lose the ability to know
    what was created. This table is the authoritative list: every manifest
    the backend validates + applies gets one row here, with the full YAML
    preserved for diff/audit. Cleanup is then "iterate rows for this
    research_id, kubectl delete each, mark deleted_at when gone".

    Rows are created at apply time (kind='Namespace' is the per-research
    experimental ns) and soft-deleted (deleted_at + cleanup_status='done')
    once kubectl confirms the resource is gone. If a backend crash orphans
    rows (cleanup_status='pending' with no deleted_at), the next research
    run on the same id — or a manual sweep job — can re-attempt cleanup
    from this table instead of relying on labels alone.
    """
    __tablename__ = "research_resources"
    __table_args__ = (
        Index("ix_research_resources_research_cleanup",
              "research_id", "cleanup_status"),
        Index("ix_research_resources_namespace",
              "namespace"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("researches.id", ondelete="CASCADE"), nullable=False,
    )
    # Pod / Deployment / StatefulSet / Service / ConfigMap / PVC / Secret / Namespace
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    namespace: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cluster_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cleanup_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending",
    )  # pending / running / done / failed
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class KnowledgeDocument(Base):
    """User-uploaded pre-research document used for personalization.

    Stores the original file path + parsed sections. Style extraction is
    cached on a separate KnowledgeStyle row so we don't re-run the LLM
    every time the user creates a new research.
    """
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    filename: Mapped[str] = mapped_column(String(200))
    storage_path: Mapped[str] = mapped_column(String(500))  # absolute path on disk
    content: Mapped[str] = mapped_column(Text)  # full text
    sections_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of {heading, level, body}
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeStyle(Base):
    """LLM-extracted style profile from one or more uploaded documents.

    `dimensions` is a JSON list of section names the user prefers (e.g.
    ["产品/方案定位","技术架构","数据流与生命周期"]).
    `tone`, `length_pref`, `quantification` capture qualitative preferences.
    `source_doc_ids` links back to the documents this style was learned from.
    `is_active` flags the currently-in-use style (singleton per user for v1).
    """
    __tablename__ = "knowledge_styles"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    name: Mapped[str] = mapped_column(String(200))
    dimensions_json: Mapped[str] = mapped_column(Text, default="[]")  # ordered list of section names
    tone: Mapped[str] = mapped_column(String(50), default="")  # "formal" / "casual" / "technical" / etc.
    length_pref: Mapped[str] = mapped_column(String(50), default="medium")  # "concise" / "medium" / "extensive"
    quantification: Mapped[str] = mapped_column(String(50), default="balanced")  # "narrative" / "balanced" / "metric-heavy"
    custom_instructions: Mapped[str] = mapped_column(Text, default="")  # free-form LLM-extracted guidance
    source_doc_ids: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    is_active: Mapped[int] = mapped_column(Integer, default=0)  # 1 = currently used
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResearchTopic(Base):
    """Aggregates multiple research runs on the same subject.

    A topic is the "baseline" container for iterative research: the user
    studies a subject once, reviews the result, adjusts the research
    boundary (goal / constraints / expected_output), and launches another
    round. Each round is a separate Research row linked via topic_id, with
    an incrementing `iteration` number.

    Iteration history is preserved as the list of Research.iteration, so the
    UI can render a timeline of boundary changes + conclusions.
    """
    __tablename__ = "research_topics"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_id)
    name: Mapped[str] = mapped_column(String(200))  # e.g. "Redis 集群高可用方案"
    description: Mapped[str] = mapped_column(Text, default="")  # one-line subject summary
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Iterations of this topic (order by iteration number)
    researches: Mapped[list["Research"]] = relationship(
        "Research", back_populates="topic",
        cascade="all, delete-orphan", order_by="Research.iteration",
    )

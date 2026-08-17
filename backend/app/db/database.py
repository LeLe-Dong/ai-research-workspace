from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from typing import AsyncIterator

from app.core.config import settings
from app.db.base import Base


# `Base` lives in `app.db.base` (isolated leaf module) to break a 3-way
# import cycle between `database` <-> `core.config` <-> `models`. See
# app/db/base.py for the rationale.


engine = create_async_engine(
    f"sqlite+aiosqlite:///{settings.db_path}",
    echo=False,
    future=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create all tables + ensure custom indexes exist.

    create_all only handles NEW tables, not new indexes on existing tables.
    We explicitly create custom indexes via raw SQL (idempotent).
    """
    from app.db import models  # noqa: F401 (register models)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Custom indexes (idempotent: IF NOT EXISTS)
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_researches_updated_at ON researches(updated_at)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_researches_status ON researches(status)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_timeline_events_ts ON timeline_events(ts)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_timeline_events_research_ts ON timeline_events(research_id, ts)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_tasks_research_status ON tasks(research_id, status)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_artifacts_research_kind ON artifacts(research_id, kind)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_reviews_research_id ON reviews(research_id)"
        ))

        # Add error_message column to researches (added in Phase 21)
        # SQLite doesn't support IF NOT EXISTS for ALTER, so check first
        pragma_result = await conn.execute(text("PRAGMA table_info(researches)"))
        cols = pragma_result.all()
        if not any(c[1] == 'error_message' for c in cols):
            await conn.execute(text(
                "ALTER TABLE researches ADD COLUMN error_message TEXT"
            ))

        # Phase 25: add structured review columns (verdict, improvements, etc.)
        review_cols = await conn.execute(text("PRAGMA table_info(reviews)"))
        review_col_names = {c[1] for c in review_cols.all()}
        for col in ['verdict', 'strengths_list', 'weaknesses_list', 'improvements', 'critical_questions', 'next_steps']:
            if col not in review_col_names:
                await conn.execute(text(f"ALTER TABLE reviews ADD COLUMN {col} TEXT DEFAULT ''"))

        # Add task_id column to timeline_events for task-scoped console filtering.
        # Nullable: most events (LLM traces, mock per-phase, hermes stdout) are
        # legitimately task-less. Migrations use PRAGMA + ALTER (no alembic).
        te_cols = await conn.execute(text("PRAGMA table_info(timeline_events)"))
        te_col_names = {c[1] for c in te_cols.all()}
        if 'task_id' not in te_col_names:
            await conn.execute(text(
                "ALTER TABLE timeline_events ADD COLUMN task_id TEXT"
            ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_timeline_events_task_id ON timeline_events(task_id)"
        ))

        # Smart K8s validation trigger (3-state: auto/on/off)
        r_cols = await conn.execute(text("PRAGMA table_info(researches)"))
        r_col_names = {c[1] for c in r_cols.all()}
        if 'requires_k8s_validation' not in r_col_names:
            await conn.execute(text(
                "ALTER TABLE researches ADD COLUMN requires_k8s_validation INTEGER DEFAULT 0"
            ))

        # use_custom_style (Phase A): when 1, hermes_researcher injects the
        # user's active KnowledgeStyle into the research prompt instead of
        # the default 14-dimension framework.
        if 'use_custom_style' not in r_col_names:
            await conn.execute(text(
                "ALTER TABLE researches ADD COLUMN use_custom_style INTEGER DEFAULT 0"
            ))

        # style_id (Phase B): per-research style binding. NULL means "use the
        # currently active style". A non-null value binds this research to a
        # specific KnowledgeStyle, enabling different research tasks to use
        # different user-defined styles (e.g. DB-style vs security-style).
        if 'style_id' not in r_col_names:
            await conn.execute(text(
                "ALTER TABLE researches ADD COLUMN style_id VARCHAR(12)"
            ))

        # Research topics (iterative baseline): researches.topic_id FK +
        # iteration counter. The research_topics table itself is created by
        # create_all (new table); only the column additions need migration.
        if 'topic_id' not in r_col_names:
            await conn.execute(text(
                "ALTER TABLE researches ADD COLUMN topic_id VARCHAR(12)"
            ))
        if 'iteration' not in r_col_names:
            await conn.execute(text(
                "ALTER TABLE researches ADD COLUMN iteration INTEGER DEFAULT 1"
            ))
        if 'prev_iteration_id' not in r_col_names:
            await conn.execute(text(
                "ALTER TABLE researches ADD COLUMN prev_iteration_id VARCHAR(12)"
            ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_researches_topic_id ON researches(topic_id)"
        ))


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Async context manager. Works with `async with get_session() as s:`."""
    async with SessionLocal() as session:
        yield session


async def get_session_dep() -> AsyncIterator[AsyncSession]:
    """FastAPI Depends-compatible async generator. Use as Depends(get_session_dep)."""
    async with SessionLocal() as session:
        yield session

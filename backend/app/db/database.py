from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncIterator

from app.core.config import settings


class Base(DeclarativeBase):
    pass


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


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Async context manager. Works with `async with get_session() as s:`."""
    async with SessionLocal() as session:
        yield session


async def get_session_dep() -> AsyncIterator[AsyncSession]:
    """FastAPI Depends-compatible async generator. Use as Depends(get_session_dep)."""
    async with SessionLocal() as session:
        yield session

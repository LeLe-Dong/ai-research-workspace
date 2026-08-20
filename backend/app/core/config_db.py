"""Sync SQLite engine + session factory for startup-time reads.

Lives in `app.core` (not `app.db`) so `app.core.config.load_runtime_overrides`
can import it without triggering a circular import.

This module is deliberately decoupled from `app.core.config.settings`:
`get_sync_session(db_path)` takes the DB path explicitly so the import graph is
`config_db -> (nothing app-level)` rather than the previous `config_db -> config`.
If anything else in this project needs the sync session, route through the
`get_sync_session()` factory below — never import settings from this file.

Production async traffic still uses `app.db.database.SessionLocal`.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def get_sync_session_factory(db_path: str):
    """Return a sync SessionLocal factory pointing at db_path.

    Lazy: the engine is only created on first use. Avoids binding to a
    not-yet-imported `app.core.config` and survives circular scenarios.
    """
    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )
    return sessionmaker(engine, expire_on_commit=False, autoflush=False)


# Module-level aliases used by callers that already know the db_path.
# The default reads from AIRW_DB_PATH env (matching pydantic_settings default).
import os as _os
_DEFAULT_DBPATH = _os.environ.get("AIRW_DB_PATH", "storage/airw.db")
SyncSessionLocal = get_sync_session_factory(_DEFAULT_DBPATH)

"""SQLAlchemy declarative base, isolated to break an import cycle.

If `Base` lived next to the engine in `app.db.database`, then
`app.db.models` couldn't import it without dragging `app.core.config`
back in mid-import (since `database` imports `settings` at module top).
This leaf module imports nothing from the project, so no cycle can form.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

"""Test env setup BEFORE any app imports."""
import sys
import os

TEST_DB_PATH = "/tmp/airw_pytest_test.db"
# Don't delete at start - we'll use a separate test DB file per test session

os.environ["AIRW_DB_PATH"] = TEST_DB_PATH
os.environ["AIRW_AGENT_MODE"] = "mock"

for mod_name in list(sys.modules.keys()):
    if mod_name.startswith("app."):
        del sys.modules[mod_name]

from app.db import database as _db

import asyncio
import pytest
import pytest_asyncio
from sqlalchemy import text


async def _reset_tables():
    """Drop all tables and recreate them."""
    from app.db.database import init_db
    # Drop all tables
    async with _db.engine.begin() as conn:
        # Get all tables
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = [r[0] for r in result.all()]
        for table in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
    # Recreate
    await init_db()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def fresh_db():
    """Reset DB tables before each test (faster than delete+recreate)."""
    await _reset_tables()
    yield


@pytest_asyncio.fixture
async def client(fresh_db):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

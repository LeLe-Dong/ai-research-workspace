"""Application settings with DB-backed runtime overrides.

Hierarchy (later wins):
  1. defaults in this class
  2. AIRW_* environment variables (incl. .env)
  3. SQLite app_config table (for runtime overrides set via /admin/agent-mode)
"""
import logging
from sqlalchemy import select
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIRW_", env_file=".env", extra="ignore")

    app_name: str = "AI 预研工作台"
    debug: bool = False  # Set AIRW_DEBUG=true in .env to enable debug logs

    # Storage
    db_path: str = "storage/airw.db"
    artifacts_dir: str = "storage/artifacts"

    # Agent mode: mock | stepfun | hermes-researcher
    agent_mode: str = "mock"
    mock_duration_seconds: float = 4.0

    # Stepfun (OpenAI-compatible endpoint)
    stepfun_api_key: str = ""
    stepfun_model: str = "step-3.7-flash"
    stepfun_base_url: str = "https://api.stepfun.com/step_plan/v1"

    # MiniMax (web_search API — Chinese-first search)
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimaxi.com"

    # Hermes Researcher (shell out hermes chat --cli)
    hermes_bin: str = "/root/.local/bin/hermes"
    hermes_profile: str = "researcher"  # pre-research expert
    hermes_skills: str = "arxiv,feeds"
    hermes_timeout_seconds: int = 300

    # CORS
    cors_origins: list[str] = ["*"]


def load_runtime_overrides(settings_obj: Settings) -> Settings:
    """Read app_config table and patch relevant fields. Called at startup."""
    try:
        # Import here to avoid circular import
        from app.db.database import init_db, get_session_dep

        # Make sure DB schema is up-to-date
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In a running event loop — schedule directly
                return _apply_overrides_sync(settings_obj)
        except RuntimeError:
            pass

        asyncio.run(init_db())

        async def _read():
            async with get_session_dep() as session:
                from app.db.models import AppConfig
                rows = (await session.execute(select(AppConfig))).scalars().all()
                return {r.key: r.value for r in rows}

        try:
            overrides = asyncio.run(_read())
        except RuntimeError:
            overrides = _read_sync()

        if "agent_mode" in overrides:
            new_mode = overrides["agent_mode"]
            if new_mode in ("mock", "stepfun", "hermes-researcher"):
                logger.info(f"DB override: agent_mode = {new_mode} (was {settings_obj.agent_mode})")
                settings_obj.agent_mode = new_mode
        if "stepfun_api_key" in overrides and overrides["stepfun_api_key"]:
            settings_obj.stepfun_api_key = overrides["stepfun_api_key"]
            logger.info("DB override: stepfun_api_key set")
        if "stepfun_model" in overrides and overrides["stepfun_model"]:
            settings_obj.stepfun_model = overrides["stepfun_model"]

    except Exception as e:
        logger.warning(f"Could not load runtime overrides: {e}")

    return settings_obj


def _apply_overrides_sync(settings_obj: Settings) -> Settings:
    """Apply overrides synchronously (used inside event loop)."""
    from app.db.models import AppConfig
    from app.db.database import SessionLocal
    with SessionLocal() as session:
        rows = session.execute(select(AppConfig)).scalars().all()
        overrides = {r.key: r.value for r in rows}
    if "agent_mode" in overrides and overrides["agent_mode"] in ("mock", "stepfun", "hermes-researcher"):
        settings_obj.agent_mode = overrides["agent_mode"]
    if "stepfun_api_key" in overrides and overrides["stepfun_api_key"]:
        settings_obj.stepfun_api_key = overrides["stepfun_api_key"]
    if "stepfun_model" in overrides and overrides["stepfun_model"]:
        settings_obj.stepfun_model = overrides["stepfun_model"]
    return settings_obj


def _read_sync() -> dict:
    """Sync fallback if async context is broken."""
    from app.db.models import AppConfig
    from app.db.database import SessionLocal
    with SessionLocal() as session:
        rows = session.execute(select(AppConfig)).scalars().all()
    return {r.key: r.value for r in rows}


# Build initial settings, then apply DB overrides
settings = Settings()
settings = load_runtime_overrides(settings)

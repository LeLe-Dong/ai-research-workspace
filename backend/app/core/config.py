"""Application settings with DB-backed runtime overrides.

Hierarchy (later wins):
  1. defaults in this class
  2. AIRW_* environment variables (incl. .env)
  3. SQLite app_config table (for runtime overrides set via /admin/agent-mode)
"""
import asyncio
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
    from app.core.config_db import SyncSessionLocal
    from app.db.models import AppConfig

    try:
        # 1) Make sure DB schema is up-to-date (init_db is async; only run if no loop is running)
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                from app.db.database import init_db
                loop.run_until_complete(init_db())
        except RuntimeError:
            # No event loop at all (script context) — skip init_db.
            pass

        # 2) Read app_config synchronously (safe inside event loop too)
        with SyncSessionLocal() as session:
            rows = session.execute(select(AppConfig)).scalars().all()
            overrides = {r.key: r.value for r in rows}

        if "agent_mode" in overrides:
            new_mode = overrides["agent_mode"]
            if new_mode in ("mock", "llm", "hermes-researcher"):
                logger.info(f"DB override: agent_mode = {new_mode} (was {settings_obj.agent_mode})")
                settings_obj.agent_mode = new_mode
        if "stepfun_api_key" in overrides and overrides["stepfun_api_key"]:
            settings_obj.stepfun_api_key = overrides["stepfun_api_key"]
            logger.info("DB override: stepfun_api_key set")
        if "stepfun_model" in overrides and overrides["stepfun_model"]:
            settings_obj.stepfun_model = overrides["stepfun_model"]

        # ---- LLM 配置覆盖（来自 /api/v1/config/llm 写入的 llm_* 字段）----
        # 仅当 provider != stepfun 时，把 DB 里的 llm_api_key/llm_model/llm_base_url
        # 覆盖到 settings.stepfun_*，让 StepfunAgentClient（OpenAI 协议）能跑任意 provider。
        # provider=stepfun 时不动，避免破坏现有用户的 stepfun 默认路径。
        db_provider = overrides.get("llm_provider")
        if db_provider and db_provider != "stepfun":
            from app.core.crypto import decrypt
            for db_key, env_attr in (
                ("llm_api_key", "stepfun_api_key"),
                ("llm_model", "stepfun_model"),
                ("llm_base_url", "stepfun_base_url"),
            ):
                if db_key in overrides and overrides[db_key]:
                    value = overrides[db_key]
                    if env_attr == "stepfun_api_key":
                        try:
                            value = decrypt(value)
                        except Exception as e:
                            logger.warning(f"Could not decrypt {db_key}: {e}")
                            continue
                    setattr(settings_obj, env_attr, value)
                    logger.info(f"DB override: {env_attr} (from {db_key}, provider={db_provider})")

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
    if "agent_mode" in overrides and overrides["agent_mode"] in ("mock", "llm", "hermes-researcher"):
        settings_obj.agent_mode = overrides["agent_mode"]
    if "stepfun_api_key" in overrides and overrides["stepfun_api_key"]:
        settings_obj.stepfun_api_key = overrides["stepfun_api_key"]
    if "stepfun_model" in overrides and overrides["stepfun_model"]:
        settings_obj.stepfun_model = overrides["stepfun_model"]
    # LLM 配置覆盖：仅当 provider != stepfun 时把 llm_* 映射到 stepfun_*
    db_provider = overrides.get("llm_provider")
    if db_provider and db_provider != "stepfun":
        for db_key, env_attr in (
            ("llm_api_key", "stepfun_api_key"),
            ("llm_model", "stepfun_model"),
            ("llm_base_url", "stepfun_base_url"),
        ):
            if db_key in overrides and overrides[db_key]:
                setattr(settings_obj, env_attr, overrides[db_key])
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

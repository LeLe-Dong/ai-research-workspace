from app.agents.base import AgentClient, AgentEvent, ResearchRequest
from app.agents.mock import MockAgentClient
from app.agents.stepfun import StepfunAgentClient
from app.agents.hermes_researcher import HermesResearcherAgent
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def get_agent_client() -> AgentClient:
    """Get the agent client for the current mode.

    Modes:
    - mock:  no LLM, 4s fake timeline
    - llm:   uses StepfunAgentClient (OpenAI-compatible). Provider/base_url/model/api_key
             come from /api/v1/config/llm via _resolve_llm() — NOT from settings.stepfun_*.
             This lets the LLM card's "kimi / openai_compat / minimax / stepfun" picker
             drive the actual research.
    - hermes-researcher: shell out to hermes CLI.

    Migration note:
        The old "stepfun" mode was just an alias for what's now "llm" with provider=stepfun.
        Existing DB rows with mode=stepfun will not match the Literal -> backend will
        fall back to env default (mock). Users will see this and need to click "llm".
    """
    # Lazy import: app.api.v1.config pulls the whole v1 router tree on import,
    # which can re-enter app.core.config (circular). Import lazily inside the
    # function so startup order is always safe.
    from app.api.v1.config import _resolve_llm

    mode = settings.agent_mode
    if mode == "mock":
        return MockAgentClient(duration_seconds=settings.mock_duration_seconds)

    if mode == "llm":
        provider, base_url, model, api_key, source = _resolve_llm()
        if not api_key:
            raise RuntimeError(
                "llm 模式需要配置 API key。请到「设置 → LLM 模型」填写，"
                "并重启后端使新配置生效。\n"
                "Set API key in /api/v1/config/llm, then restart backend."
            )
        logger.info(
            "llm mode active: provider=%s base_url=%s model=%s key_source=%s",
            provider, base_url, model, source,
        )
        return StepfunAgentClient(
            api_key=api_key,
            model=model,
            base_url=base_url,
            minimax_api_key=settings.minimax_api_key,
            minimax_base_url=settings.minimax_base_url,
        )

    if mode == "hermes-researcher":
        import os
        if not os.path.exists(settings.hermes_bin):
            raise RuntimeError(
                f"hermes-researcher 模式需要 hermes CLI，但未找到 {settings.hermes_bin}。\n"
                f"Install hermes or switch AIRW_AGENT_MODE to 'mock' or 'llm'."
            )
        return HermesResearcherAgent(
            hermes_bin=settings.hermes_bin,
            profile=settings.hermes_profile,
            skills=settings.hermes_skills,
            timeout_seconds=settings.hermes_timeout_seconds,
        )

    raise ValueError(f"Unknown agent_mode: {mode}")


__all__ = [
    "AgentClient", "AgentEvent", "ResearchRequest",
    "MockAgentClient", "StepfunAgentClient", "HermesResearcherAgent",
    "get_agent_client",
]

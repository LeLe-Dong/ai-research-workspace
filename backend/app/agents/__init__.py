from app.agents.base import AgentClient, AgentEvent, ResearchRequest
from app.agents.mock import MockAgentClient
from app.agents.stepfun import StepfunAgentClient
from app.agents.hermes_researcher import HermesResearcherAgent
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def get_agent_client() -> AgentClient:
    """Get the agent client for the current mode.
    
    Falls back gracefully if a mode is misconfigured:
    - stepfun + no API key → falls back to mock (with warning)
    - hermes-researcher + no hermes binary → falls back to mock
    """
    mode = settings.agent_mode
    if mode == "mock":
        return MockAgentClient(duration_seconds=settings.mock_duration_seconds)
    
    if mode == "stepfun":
        api_key = settings.stepfun_api_key
        if not api_key:
            # Don't fallback - real LLM is required for stepfun mode
            # Silent fallback was misleading users into thinking LLM was running
            raise RuntimeError(
                "stepfun 模式需要 AIRW_STEPFUN_API_KEY。\n"
                "请在 backend/.env 中设置后重启，或切换到 mock/hermes-researcher 模式。\n"
                "Set AIRW_STEPFUN_API_KEY in backend/.env and restart, "
                "or switch AIRW_AGENT_MODE to 'mock' or 'hermes-researcher'."
            )
        return StepfunAgentClient(
            api_key=api_key,
            model=settings.stepfun_model,
            base_url=settings.stepfun_base_url,
            minimax_api_key=settings.minimax_api_key,
            minimax_base_url=settings.minimax_base_url,
        )
    
    if mode == "hermes-researcher":
        import os
        if not os.path.exists(settings.hermes_bin):
            raise RuntimeError(
                f"hermes-researcher 模式需要 hermes CLI，但未找到 {settings.hermes_bin}。\n"
                f"Install hermes or switch AIRW_AGENT_MODE to 'mock' or 'stepfun'."
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

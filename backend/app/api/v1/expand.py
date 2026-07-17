"""Goal expansion endpoint: uses LLM to expand a short goal into a detailed one.

Keeps API key on backend (never exposed to frontend).

Uses StepfunClient which properly handles the step-3.7-flash "thinking" pattern
(empty content + reasoning_content field). Applies _strip_thinking to remove
chain-of-thought preambles from the final answer.
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_session_dep
from app.core.cache import TTLCache
from app.agents.llm import StepfunClient, _strip_thinking, LLMError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/expand", tags=["expand"])


class ExpandRequest(BaseModel):
    """Request body for goal expansion."""
    goal: str = Field(..., min_length=2, max_length=2000, description="The short/rough goal to expand")


class ExpandResponse(BaseModel):
    """Response with expanded goal."""
    original: str
    expanded: str
    model: str
    cached: bool = False
    tokens_used: int | None = None


# Cache for 1 hour (same input → same output for LLM)
_expand_cache = TTLCache(default_ttl=3600.0)


EXPAND_SYSTEM_PROMPT = """你是资深研究顾问。用户给你简短的研究目标（1-2 句话），你需要扩展成一个具体、可执行的研究问题。

要求：
1. 明确背景：业务场景、技术栈、约束条件
2. 拆解维度：从 3-5 个角度分析
3. 明确输出：产出形式（对比表、推荐、计划等）
4. 保留意图：不改变用户核心目标
5. 中文输出

字数：300-500 字。"""


@router.post("/goal", response_model=ExpandResponse)
async def expand_goal(
    body: ExpandRequest,
    session: AsyncSession = Depends(get_session_dep),
) -> ExpandResponse:
    """Expand a short research goal into a detailed one using LLM.

    Raises 503 if stepfun is not configured.
    """
    goal = body.goal.strip()
    if not goal:
        raise HTTPException(400, "Goal is required")

    # Check cache
    cache_key = f"expand_goal:{goal}"
    cached = await _expand_cache.get(cache_key)
    if cached:
        return ExpandResponse(
            original=goal,
            expanded=cached["expanded"],
            model=cached["model"],
            cached=True,
            tokens_used=None,
        )

    # Check API key
    api_key = settings.stepfun_api_key
    if not api_key:
        raise HTTPException(
            503,
            "LLM 扩写功能未启用：后端未配置 AIRW_STEPFUN_API_KEY。请在 backend/.env 中设置后重启。",
        )

    # Call stepfun via StepfunClient (handles reasoning fallback + errors)
    client = StepfunClient(
        api_key=api_key,
        base_url=settings.stepfun_base_url or "https://api.stepfun.com/step_plan/v1",
        model=settings.stepfun_model or "step-3.7-flash",
        timeout=60.0,
    )

    try:
        # max_tokens bumped: stepfun thinking can eat 500-1500 tokens before the actual answer
        raw_response = await client.chat(
            system=EXPAND_SYSTEM_PROMPT,
            user=goal,
            temperature=0.7,
            max_tokens=2500,
        )
        # Strip any chain-of-thought preamble ("Got it, ..." / "首先..." / "用户现在...")
        expanded = _strip_thinking(raw_response, is_json=False)
    except LLMError as e:
        logger.error(f"stepfun LLM error: {e}")
        raise HTTPException(502, f"LLM 扩写失败: {e}")

    if not expanded or len(expanded) < 20:
        raise HTTPException(502, "LLM 返回内容过短或为空")

    # Cache (cache the stripped version, not the raw)
    await _expand_cache.set(
        cache_key,
        {"expanded": expanded, "model": client.model},
        ttl=3600.0,
    )

    return ExpandResponse(
        original=goal,
        expanded=expanded,
        model=client.model,
        cached=False,
        tokens_used=None,  # StepfunClient doesn't surface token count yet
    )

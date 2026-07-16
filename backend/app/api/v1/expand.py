"""Goal expansion endpoint: uses LLM to expand a short goal into a detailed one.

Keeps API key on backend (never exposed to frontend).
"""
import logging
import os
import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_session_dep
from app.core.cache import TTLCache

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


EXPAND_SYSTEM_PROMPT = """你是一名资深研究顾问。用户会给你一个简短的研究目标描述（可能只有 1-2 句话），你需要把它扩展成一个结构化、具体、可执行的研究问题。

要求：
1. **明确背景**：研究的业务场景、技术栈、约束条件
2. **拆解维度**：从 3-5 个角度分析（性能、成本、可行性、风险等）
3. **明确输出**：期望的产出形式（对比表、推荐方案、实施计划等）
4. **保留意图**：不改变用户的核心研究目标
5. **用中文**：除非用户用了英文

输出格式：直接给出扩展后的研究目标，不要加解释、不要加"以下是..."等套话。

字数：300-500 字。"""


@router.post("/goal", response_model=ExpandResponse)
async def expand_goal(
    body: ExpandRequest,
    session: AsyncSession = Depends(get_session_dep),
) -> ExpandResponse:
    """Expand a short research goal into a detailed one using LLM.

    Falls back gracefully if stepfun is not configured.
    """
    goal = body.goal.strip()
    if not goal:
        raise HTTPException(400, "Goal is required")

    # Check cache first
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

    # Check if stepfun is configured (check env directly for testability)
    api_key = os.environ.get("AIRW_STEPFUN_API_KEY") or settings.stepfun_api_key
    if not api_key:
        raise HTTPException(
            503,
            "LLM 扩写功能未启用：后端未配置 AIRW_STEPFUN_API_KEY。请在 .env 中设置后重启。",
        )

    # Call stepfun
    base_url = settings.stepfun_base_url or "https://api.stepfun.com/step_plan/v1"
    model = settings.stepfun_model or "step-3.7-flash"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": EXPAND_SYSTEM_PROMPT},
                        {"role": "user", "content": goal},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 1000,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"stepfun HTTP error: {e.response.status_code} {e.response.text[:200]}")
        raise HTTPException(
            502,
            f"LLM 服务返回错误: {e.response.status_code}",
        )
    except httpx.TimeoutException:
        logger.error("stepfun timeout")
        raise HTTPException(504, "LLM 服务超时，请稍后重试")
    except Exception as e:
        logger.error(f"stepfun call failed: {e}")
        raise HTTPException(502, f"LLM 服务调用失败: {type(e).__name__}")

    # Parse response
    try:
        content = data["choices"][0]["message"]["content"].strip()
        tokens_used = data.get("usage", {}).get("total_tokens")
    except (KeyError, IndexError) as e:
        logger.error(f"stepfun response parse error: {data}")
        raise HTTPException(502, "LLM 响应格式异常")

    # Cache the result
    await _expand_cache.set(cache_key, {"expanded": content, "model": model}, ttl=3600.0)

    return ExpandResponse(
        original=goal,
        expanded=content,
        model=model,
        cached=False,
        tokens_used=tokens_used,
    )

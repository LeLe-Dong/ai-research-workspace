#!/usr/bin/env python3
"""Standalone smoke test for StepfunAgentClient.

Run AFTER exporting AIRW_STEPFUN_API_KEY=sk-xxx in your shell.
This does NOT depend on FastAPI / DB — just verifies the LLM call works.

Usage:
    export AIRW_STEPFUN_API_KEY=sk-xxx
    /root/workspace/ai-test-platform/.venv/bin/python scripts/smoke_stepfun.py
"""
import asyncio
import os
import sys

# Allow importing app.agents.* without going through uvicorn
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.llm import StepfunClient, LLMError
from app.agents.prompts import UNDERSTAND_SYSTEM, UNDERSTAND_USER_TEMPLATE
from app.agents.search import DDGSSearch


async def main():
    api_key = os.environ.get("AIRW_STEPFUN_API_KEY") or os.environ.get("STEPFUN_API_KEY")
    if not api_key:
        print("ERROR: AIRW_STEPFUN_API_KEY not set in env")
        sys.exit(1)

    print("=== Smoke test: Stepfun LLM ===")
    llm = StepfunClient(api_key=api_key, model="step-3.7-flash")

    # Test 1: plain chat
    print("\n[1] Plain chat...")
    try:
        text = await llm.chat(
            "You are a helpful assistant. Reply ONLY with 'PONG', nothing else.",
            "Reply with: PONG",
            temperature=0.0,
            max_tokens=200,
        )
        print(f"  response: {text!r}")
    except LLMError as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    # Test 2: JSON chat
    print("\n[2] JSON chat (understand phase)...")
    try:
        result = await llm.chat_json(
            UNDERSTAND_SYSTEM,
            UNDERSTAND_USER_TEMPLATE.format(
                title="PostgreSQL 17 migration",
                goal="Migrate a 5TB production DB from PG 15 to PG 17 with zero downtime.",
                constraints="On-prem; team of 3 engineers; 6-week deadline.",
                expected_output="Migration plan + risk register.",
            ),
            max_tokens=4000,
        )
        print(f"  sub_questions: {result.get('sub_questions')}")
        print(f"  search_queries: {result.get('search_queries')}")
    except LLMError as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    # Test 3: DDGS search
    print("\n[3] DDGS search...")
    s = DDGSSearch(max_results=3)
    hits = s.search("PostgreSQL 17 release notes")
    print(f"  hits: {len(hits)}")
    for h in hits[:3]:
        print(f"    - {h.title[:60]}")
        print(f"      {h.url}")

    print("\n=== ALL SMOKE TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())

# Backend Scripts

## smoke_stepfun.py

Verifies that the StepfunAgentClient can talk to the Stepfun API and DDGS works.

**Setup** (one-time):
```bash
export AIRW_STEPFUN_API_KEY=sk-your-real-key
```

**Run**:
```bash
/root/workspace/ai-test-platform/.venv/bin/python scripts/smoke_stepfun.py
```

Expected output: 3 sections printed, ending with `ALL SMOKE TESTS PASSED`.

If LLM call fails: check API key + endpoint URL.
If DDGS fails: usually transient; retry or use Tavily.

## Switching from mock to stepfun

Once the smoke test passes, you can enable real LLM-driven research:

```bash
# Stop the current uvicorn (mock mode)
# Then start with stepfun mode:
export AIRW_AGENT_MODE=stepfun
export AIRW_STEPFUN_API_KEY=sk-xxx
export AIRW_STEPFUN_MODEL=step-3.7-flash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8003 --log-level warning
```

The frontend doesn't need any changes — it already calls `/api/v1/researches/{id}/start`,
and the backend swaps out the AgentClient based on AIRW_AGENT_MODE.

To go back to mock: `export AIRW_AGENT_MODE=mock` and restart.

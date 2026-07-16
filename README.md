# AI Research Workspace

Enterprise-grade AI pre-research platform. Submit a research goal, the system handles:
requirement analysis -> task decomposition -> multi-step research -> AI review -> scored report.

MVP is wired with a MockAgentClient so the entire UX is clickable today.
Swap in HermesAgentClient for production by changing one config flag.

## Stack

- Frontend: Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui (Radix) + Zustand + TanStack Query + Mermaid + next-themes
- Backend: FastAPI + SQLAlchemy (async) + aiosqlite + Pydantic
- Engine: Pluggable AgentClient (MockAgentClient now, HermesAgentClient v1.1)

## Project Structure

```
ai-research-workspace/
- frontend/  Next.js app
  - app/     App Router routes (/dashboard, /research, /kb, ...)
  - components/  Shared components (sidebar, topbar, ui primitives)
  - features/    Feature-first modules (research, knowledge, ...)
  - lib/     utils, store, hooks
- backend/   FastAPI app
  - app/api/v1/  feature-first routers
  - app/agents/  AgentClient interface + Mock + (Hermes)
  - app/core/    config, logging
  - app/db/      SQLAlchemy models + session
  - app/schemas/ Pydantic schemas
  - storage/     SQLite + artifacts
```

## Local Dev

### Backend (port 8003)

```bash
source /root/workspace/ai-test-platform/.venv/bin/activate   # reuse existing venv
cd backend
AIRW_DB_PATH=storage/airw.db uvicorn app.main:app --port 8003 --reload
```

Health: `curl http://127.0.0.1:8003/health`

### Frontend (port 3000)

```bash
cd frontend
npx next dev -p 3000
```

App: http://localhost:3000  (auto-redirects to /dashboard)

## MVP Roadmap

| Milestone | Status |
| --- | --- |
| M1 Project skeleton + design system | done |
| M2 Dashboard page | next |
| M3 Research creation + list |  |
| M4 Execution view (4-column) |  |
| M5 Report + Reviewer |  |

See ~/.hermes/profiles/platform-builder/knowledge_base/architecture-decisions/ADR-001-ai-research-workspace.md for the full plan.

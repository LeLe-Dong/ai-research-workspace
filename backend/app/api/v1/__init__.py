from fastapi import APIRouter

from app.api.v1 import dashboard, researches, execute, tasks, stream, reports, admin, history, tags, expand

router = APIRouter()
router.include_router(dashboard.router)
router.include_router(researches.router)
router.include_router(execute.router)
router.include_router(tasks.router)
router.include_router(stream.router)
router.include_router(reports.router)
router.include_router(admin.router)
router.include_router(history.router)
router.include_router(tags.router)
router.include_router(expand.router)

from app.api.v1.reports import list_completed
router.add_api_route("/completed-researches", list_completed, methods=["GET"], tags=["archive"])

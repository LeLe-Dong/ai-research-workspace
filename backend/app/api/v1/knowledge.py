"""Knowledge base endpoints: upload, list, extract style, activate.

User uploads one or more prior pre-research documents. Backend parses
section structure, runs LLM-extracted style profile, and stores it as
the active `KnowledgeStyle`. The style is then injected into the research
agent's prompt when `Research.use_custom_style = 1`.
"""
import json
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session_dep
from app.db.models import KnowledgeDocument, KnowledgeStyle
from app.services.knowledge import (
    activate_style,
    delete_document,
    extract_style_from_all_docs,
    get_active_style,
    list_documents,
    list_styles,
    merge_rankings,
    rank_styles_for_goal,
    rerank_styles_with_llm,
    save_upload,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

MAX_UPLOAD_BYTES = 4 * 1024 * 1024  # 4 MiB per doc; small enough to fit in LLM prompts


@router.post("/uploads")
async def upload_document(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session_dep),
) -> dict:
    """Accept a markdown / text / pdf-ish upload, parse it, persist."""
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"文件超过 {MAX_UPLOAD_BYTES // 1024} KiB 上限")
    if not content.strip():
        raise HTTPException(400, "文件为空")
    doc = await save_upload(
        session,
        filename=file.filename or "untitled.md",
        content=content,
    )
    return {
        "id": doc.id,
        "filename": doc.filename,
        "byte_size": doc.byte_size,
        "uploaded_at": doc.uploaded_at.isoformat(),
        "sections_count": len(json.loads(doc.sections_json or "[]")),
    }


@router.get("/documents")
async def list_uploaded_documents(
    session: AsyncSession = Depends(get_session_dep),
) -> dict:
    docs = await list_documents(session)
    return {
        "items": [
            {
                "id": d.id,
                "filename": d.filename,
                "byte_size": d.byte_size,
                "uploaded_at": d.uploaded_at.isoformat(),
                "sections_count": len(json.loads(d.sections_json or "[]")),
            }
            for d in docs
        ],
        "total": len(docs),
    }


@router.delete("/documents/{doc_id}")
async def remove_document(
    doc_id: str,
    session: AsyncSession = Depends(get_session_dep),
) -> dict:
    ok = await delete_document(session, doc_id)
    if not ok:
        raise HTTPException(404, "文档不存在")
    return {"deleted": doc_id}


@router.post("/styles/extract")
async def extract_style(
    name: str | None = None,
    session: AsyncSession = Depends(get_session_dep),
) -> dict:
    """Re-extract a KnowledgeStyle from ALL uploaded documents and mark active.

    `name` optional — if absent or "auto", the backend derives a smart
    default from the first uploaded document's filename + count.
    """
    try:
        style = await extract_style_from_all_docs(session, name=name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _serialize_style(style)


@router.get("/styles")
async def list_all_styles(
    session: AsyncSession = Depends(get_session_dep),
) -> dict:
    items = [_serialize_style(s) for s in await list_styles(session)]
    return {"items": items, "total": len(items)}


@router.get("/styles/current")
async def current_style(
    session: AsyncSession = Depends(get_session_dep),
) -> dict:
    s = await get_active_style(session)
    return {"active": _serialize_style(s) if s else None}


@router.post("/styles/match")
async def match_styles(
    payload: dict,
    session: AsyncSession = Depends(get_session_dep),
) -> dict:
    """Rank existing KnowledgeStyles by relevance to a research goal.

    Body: {goal: str, constraints?: str, use_llm_rerank?: bool}
    Returns top 5 with scores. Used by the research form to auto-suggest
    a style based on what the user is typing.

    When use_llm_rerank=true and goal is non-trivial, also calls the LLM
    to semantically rerank the top-5 keyword candidates.
    """
    goal = (payload or {}).get("goal", "").strip()
    constraints = (payload or {}).get("constraints", "").strip()
    use_llm = bool((payload or {}).get("use_llm_rerank", False))
    all_styles = await list_styles(session)
    keyword_ranked = rank_styles_for_goal(goal, constraints, all_styles)

    # Phase B-3: optionally LLM-rerank top candidates
    llm_ranking: list[dict] | None = None
    if use_llm and len(keyword_ranked) >= 2 and goal:
        llm_ranking = await rerank_styles_with_llm(goal, keyword_ranked[:5])
        keyword_ranked = merge_rankings(keyword_ranked, llm_ranking)

    return {
        "matches": [
            {
                "style": _serialize_style(r["style"]),
                "score": r["score"],
                "matched_keywords": sorted(r["matched_keywords"]),
                "sample_dimensions": r["sample_dimensions"],
                "llm_score": r.get("llm_score"),
                "llm_reason": r.get("llm_reason"),
            }
            for r in keyword_ranked[:5]
        ],
        "total_styles": len(all_styles),
        "used_llm_rerank": use_llm and llm_ranking is not None,
    }


@router.post("/styles/{style_id}/activate")
async def activate(
    style_id: str,
    session: AsyncSession = Depends(get_session_dep),
) -> dict:
    s = await activate_style(session, style_id)
    if s is None:
        raise HTTPException(404, "风格不存在")
    return _serialize_style(s)


def _serialize_style(s: KnowledgeStyle | None) -> dict | None:
    if s is None:
        return None
    return {
        "id": s.id,
        "name": s.name,
        "dimensions": json.loads(s.dimensions_json or "[]"),
        "tone": s.tone,
        "length_pref": s.length_pref,
        "quantification": s.quantification,
        "custom_instructions": s.custom_instructions,
        "source_doc_ids": json.loads(s.source_doc_ids or "[]"),
        "is_active": bool(s.is_active),
        "updated_at": s.updated_at.isoformat(),
    }
"""Knowledge base service: upload, parse, and extract personalized style.

Two responsibilities:

1. **Ingest**: accept markdown/text/PDF uploads, save to disk, parse
   `## heading` sections, persist as a KnowledgeDocument row.

2. **Extract style**: run the LLM over one or more documents to derive
   a KnowledgeStyle row capturing the user's preferred dimensions,
   tone, length, quantification level, and free-form custom instructions.

The LLM call is deliberately cheap (one prompt per active style); we
don't re-extract on every upload — only when the user explicitly
"重新提取" (re-extract) from the knowledge page.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import setup_logging
from app.db.models import KnowledgeDocument, KnowledgeStyle, Research

setup_logging()
import logging
logger = logging.getLogger(__name__)


UPLOAD_DIR = Path("/root/workspace/ai-research-workspace/backend/knowledge_base/research_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ── Markdown section parser ─────────────────────────────────────
# Recognizes ATX headings (#, ##, ###) and extracts heading + body text.
# Matches typical pre-research structure: ## N. 标题 / ## N. 标题 / etc.
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.MULTILINE)


def parse_markdown_sections(content: str) -> list[dict[str, Any]]:
    """Parse a markdown document into ordered sections.

    Returns [{heading, level, body}, ...] preserving document order.
    A short preamble before the first heading is captured as a
    pseudo-section with heading="" so the LLM sees context like the
    document title / metadata block.
    """
    matches = list(HEADING_RE.finditer(content))
    if not matches:
        return [{"heading": "", "level": 0, "body": content.strip()}]

    sections: list[dict[str, Any]] = []
    # Preamble
    pre = content[: matches[0].start()].strip()
    if pre:
        sections.append({"heading": "", "level": 0, "body": pre})

    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        level = len(m.group(1))
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[body_start:body_end].strip()
        sections.append({"heading": heading, "level": level, "body": body})

    return sections


# ── Style extractor prompt ──────────────────────────────────────
STYLE_EXTRACT_PROMPT = """你是研究写作风格分析师。我会提供若干预研文档的章节清单（来自 N 个不同主题的预研报告）。

任务：从这 N 个文档中**横向合并**出**作者共有的核心研究维度**（8-14 个），输出一份 JSON。

## 输出格式（必须严格遵守！）

```json
{
  "dimensions": ["维度1", "维度2", "维度3", ...],
  "tone": "formal",
  "length_pref": "medium",
  "quantification": "balanced",
  "custom_instructions": "≤200 字的自定义指引"
}
```

字段约束：
- **dimensions**: 字符串数组，8-14 个元素，按重要性/通用性排序（最常出现的在前）。每个元素是一段研究维度的中文标题（不带数字前缀、不带"##"符号）。
- **tone**: 三个值之一 — `"formal"` / `"casual"` / `"technical"`。
- **length_pref**: 三个值之一 — `"concise"`（每段 <100 字）/ `"medium"`（100-400 字）/ `"extensive"`（>400 字）。
- **quantification**: 三个值之一 — `"narrative"`（少数字）/ `"balanced"` / `"metric-heavy"`（大量 QPS/版本号/硬件配置）。
- **custom_instructions**: ≤200 字的自由文本，描述用户的具体写作偏好。

合并规则：
1. **语义聚类**：把含义相同的不同表述合并为一个维度
   - "产品定位" / "产品定义" / "产品概述" / "1. 产品/方案定位" → 都归为 "产品/方案定位"
   - "技术架构" / "系统架构" / "整体架构" → 拆为 "技术架构"
   - "性能与规模" / "性能测试" / "QPS 表现" → 归为 "性能与规模"
2. **频次优先**：在 2+ 文档中出现的章节应优先于只在一个文档出现的
3. **顺序**：按"研究流程的逻辑顺序"而非某个文档的原始顺序
4. **忽略**：附录/参考/致谢/修订历史/目录/FAQ 列表

**关键：只输出 JSON，不要解释、不要 markdown 代码块包裹（除非用 ```json 包裹）。** 直接以 `{` 开头输出。
"""


async def extract_style_from_docs(
    session: AsyncSession,
    docs: list[KnowledgeDocument],
) -> dict[str, Any]:
    """Call the LLM (or fall back to heuristic) to derive a style profile.

    Returns a dict that can be persisted as a KnowledgeStyle row.
    Heuristic fallback: when LLM is unreachable, derive dimensions from
    the most-common ## headings in the corpus.
    """
    if not docs:
        raise ValueError("extract_style_from_docs requires at least one document")

    # Build a digest of all docs
    digest_lines: list[str] = []
    for d in docs:
        sections = json.loads(d.sections_json or "[]")
        # Only level-2 ## headings, no sub-sections
        headings = [
            s["heading"].strip() for s in sections
            if s.get("level") == 2 and s.get("heading", "").strip()
        ]
        digest_lines.append(f"### {d.filename}")
        digest_lines.append("章节（仅顶级 ##）：")
        digest_lines.extend(f"- {h}" for h in headings[:12])

    digest = "\n".join(digest_lines)[:3500]  # tight cap so LLM has room for JSON

    try:
        from app.core.config import settings
        from app.agents.llm import StepfunClient, LLMError
        client = StepfunClient(
            api_key=settings.stepfun_api_key,
            base_url=settings.stepfun_base_url,
            model=settings.stepfun_model,
            timeout=60.0,
        )
        resp = await client.chat_json(
            STYLE_EXTRACT_PROMPT,
            f"以下是若干预研文档的章节清单：\n\n{digest}",
            max_tokens=2500, temperature=0.1,
        )
        logger.info(f"LLM style extraction raw response: keys={list(resp.keys()) if isinstance(resp, dict) else type(resp).__name__}")
        if isinstance(resp, dict):
            return _normalize_style_dict(resp, docs)
    except Exception as e:
        logger.warning(f"LLM style extraction failed ({type(e).__name__}: {e}); using heuristic fallback")

    return _heuristic_style(docs)


def _normalize_style_dict(d: dict, docs: list[KnowledgeDocument]) -> dict[str, Any]:
    """Coerce / sanitize the LLM-emitted style dict into our schema shape."""
    dims = d.get("dimensions")
    if not isinstance(dims, list):
        dims = []
    dims = [str(x).strip() for x in dims if str(x).strip()][:20]

    tone = str(d.get("tone", "technical")).lower()
    if tone not in ("formal", "casual", "technical"):
        tone = "technical"
    length = str(d.get("length_pref", "medium")).lower()
    if length not in ("concise", "medium", "extensive"):
        length = "medium"
    quant = str(d.get("quantification", "balanced")).lower()
    if quant not in ("narrative", "balanced", "metric-heavy"):
        quant = "balanced"
    custom = str(d.get("custom_instructions", ""))[:500]
    return {
        "dimensions": dims,
        "tone": tone,
        "length_pref": length,
        "quantification": quant,
        "custom_instructions": custom,
        "source_doc_ids": [d.id for d in docs],
    }


def _heuristic_style(docs: list[KnowledgeDocument]) -> dict[str, Any]:
    """Heuristic style extraction when LLM is unavailable.

    Strategy (true cross-doc merge, no doc dominates):
    1. **Level-2 only**: drop level-3+ sub-sub-sections, doc titles, "一、" wrappers.
    2. **Equal weight per doc**: count each heading's doc-frequency, NOT raw
       per-section count. A heading that appears in 1 doc is weighted the
       same regardless of how many times it appears in that doc.
    3. **Semantic clustering**: group headings sharing key terms into a
       canonical name. e.g. "技术架构"/"系统架构" → "技术架构".
    4. **Order by consensus desc, then by mean-position asc**:
       most-agreed headings first; ties broken by earlier average position.
    5. **Style cues** from concatenated body sample.
    """
    if not docs:
        raise ValueError("heuristic style needs at least one document")

    import re as _re
    NUM_PREFIX = _re.compile(r"^\d+(\.\d+)*[\.、\s]+")
    PART_WRAP = _re.compile(r"^(第[一二三四五六七八九十百千]+部分|（.+）)$")
    DOC_TITLE_HINTS = ("预研报告", "预研文档", "研究报告", "技术报告", "调研报告", "技术预研")

    def top_level(d: KnowledgeDocument) -> list[str]:
        out: list[str] = []
        for s in json.loads(d.sections_json or "[]"):
            h = (s.get("heading") or "").strip()
            if not h or s.get("level") != 2:
                continue
            if PART_WRAP.match(h) and h.endswith("部分"):
                continue
            if _re.match(r"^[一二三四五六七八九十]+、", h):
                continue
            if out == [] and any(t in h for t in DOC_TITLE_HINTS):
                continue
            out.append(h)
        return out

    # 2. Per-doc equal weight: dict[normalized_heading, set_of_doc_indices]
    heading_to_docs: dict[str, set[int]] = {}
    heading_positions: dict[str, list[float]] = {}  # for tie-breaking
    for di, d in enumerate(docs):
        for pos, h in enumerate(top_level(d)):
            h_norm = NUM_PREFIX.sub("", h).strip()
            if not h_norm:
                continue
            heading_to_docs.setdefault(h_norm, set()).add(di)
            heading_positions.setdefault(h_norm, []).append(pos / max(1, len(top_level(d))))

    # 3. Semantic clustering: group headings with shared key terms
    SYNONYM_GROUPS: list[tuple[set[str], str]] = [
        ({"产品定位", "产品定义", "产品概述", "产品概览", "方案定位", "产品/方案定位", "产品/方案"}, "产品/方案定位"),
        ({"技术架构", "系统架构", "整体架构", "技术总览", "架构设计", "技术方案", "架构"}, "技术架构"),
        ({"部署架构", "部署方案", "部署实施", "安装部署", "部署"}, "部署架构"),
        ({"性能与规模", "性能测试", "性能评估", "性能基准", "性能表现", "性能", "QPS", "TPS", "数据量", "延迟", "性能与扩展性"}, "性能与规模"),
        ({"高可用", "容错设计", "高可用架构", "高可用/容错", "HA", "容灾", "容灾能力", "高可用与容错"}, "高可用 / 容错设计"),
        ({"兼容性", "标准化", "兼容性与标准化", "SQL 兼容性", "协议支持", "生态兼容性"}, "兼容性 / 标准化"),
        ({"安全", "合规", "安全与合规", "安全/合规", "信创合规", "认证", "加密", "审计"}, "安全 / 合规"),
        ({"运维", "运维管理", "运维实践", "可运维性", "监控告警", "运维复杂度", "升级"}, "运维管理"),
        ({"生态", "生态集成", "上下游", "SDK", "工具链"}, "生态集成"),
        ({"适用场景", "场景与选型", "选型建议", "最佳实践", "使用场景", "推荐场景"}, "适用场景"),
        ({"风险", "风险点", "风险评估", "生产风险", "注意事项", "局限性"}, "风险与注意事项"),
        ({"结论", "结论建议", "总结", "总结与建议", "推荐结论", "结论与展望", "结论与推荐"}, "结论建议"),
        ({"关键能力对比", "能力对比", "核心特性", "对比", "对比分析", "对比矩阵", "横向对比"}, "关键能力对比"),
        ({"数据流", "数据流与生命周期", "数据管理", "数据生命周期", "分片", "数据迁移"}, "数据流与生命周期"),
    ]
    KEY_TO_CANONICAL: dict[str, str] = {}
    for variants, canonical in SYNONYM_GROUPS:
        for v in variants:
            KEY_TO_CANONICAL[v] = canonical

    def canonicalize(h: str) -> str:
        # 1. Exact match in synonym table
        if h in KEY_TO_CANONICAL:
            return KEY_TO_CANONICAL[h]
        # 2. Substring match: if heading contains a known key term, use canonical
        lo = h.lower()
        for variants, canonical in SYNONYM_GROUPS:
            for v in variants:
                if v in h or v.lower() in lo:
                    return canonical
        # 3. Fall back: strip number prefix, use as-is
        return NUM_PREFIX.sub("", h).strip()

    # 4. Apply clustering
    canonical_to_docs: dict[str, set[int]] = {}
    canonical_positions: dict[str, list[float]] = {}
    for h_norm, doc_set in heading_to_docs.items():
        canon = canonicalize(h_norm)
        canonical_to_docs.setdefault(canon, set()).update(doc_set)
        canonical_positions.setdefault(canon, []).extend(heading_positions[h_norm])

    # 5. Rank by doc-frequency desc, then mean position asc, then name
    ranked: list[tuple[str, int, float, str]] = []
    for canon, doc_set in canonical_to_docs.items():
        doc_count = len(doc_set)
        mean_pos = sum(canonical_positions[canon]) / len(canonical_positions[canon])
        ranked.append((canon, doc_count, mean_pos, canon))
    ranked.sort(key=lambda x: (-x[1], x[2], x[3]))

    # 6. Keep headings with consensus (>=2 doc occurrences) first
    final: list[str] = []
    for canon, count, _pos, _name in ranked:
        if count >= 2:
            final.append(canon)
    # 7. If consensus < 8, pad with single-doc headings (in rank order)
    if len(final) < 8:
        for canon, count, _pos, _name in ranked:
            if canon not in final:
                final.append(canon)
            if len(final) >= 10:
                break
    # 8. Cap at 14
    final = final[:14]

    # 9. Style cues from concatenated body sample (equal-weight across docs)
    body = "\n".join(d.content or "" for d in docs)
    # Quantification: ratio of digits in body (excluding whitespace)
    digits = sum(c.isdigit() for c in body)
    quantification = (
        "metric-heavy" if digits / max(len(body), 1) > 0.05
        else "narrative" if digits / max(len(body), 1) < 0.01
        else "balanced"
    )
    # Length preference: average chars per top-level section across all docs
    total_top_sections = sum(len(top_level(d)) for d in docs)
    avg_section = len(body) // max(total_top_sections, 1)
    length_pref = (
        "extensive" if avg_section > 800
        else "concise" if avg_section < 300
        else "medium"
    )
    # Tone: presence of code blocks / formal punctuation
    code_blocks = body.count("```")
    tone = "technical" if code_blocks > 2 else "formal"

    # 10. Custom instructions
    notes: list[str] = []
    if code_blocks > 0:
        notes.append(f"倾向用代码块/表格呈现方案（{code_blocks // 2} 处）")
    if quantification == "metric-heavy":
        notes.append("倾向给出具体数字/版本号/硬件配置")
    if "Kubernetes" in body or "K8s" in body:
        notes.append("覆盖 K8s/集群维度")
    # Filter noise words from appendix-like sections
    if final and any(w in final[-1] for w in ("附录", "参考", "致谢", "修订", "FAQ")):
        final = [h for h in final if not any(w in h for w in ("附录", "参考", "致谢", "修订"))]
    custom = "；".join(notes) or "（启发式提取，建议在 /knowledge 重新提取以获得 LLM 分析）"

    return {
        "dimensions": final[:18],  # cap at 18 to avoid noise
        "tone": tone,
        "length_pref": length_pref,
        "quantification": quantification,
        "custom_instructions": custom,
        "source_doc_ids": [d.id for d in docs],
    }


# ── Document CRUD ─────────────────────────────────────────────

async def save_upload(
    session: AsyncSession,
    filename: str,
    content: bytes,
) -> KnowledgeDocument:
    """Persist an uploaded file: write to disk + insert row."""
    safe_name = re.sub(r"[^A-Za-z0-9._\-]+", "_", filename)[:120] or "upload.md"
    storage_path = UPLOAD_DIR / f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{safe_name}"
    storage_path.write_bytes(content)

    text = content.decode("utf-8", errors="replace")
    sections = parse_markdown_sections(text)

    doc = KnowledgeDocument(
        filename=filename,
        storage_path=str(storage_path),
        content=text,
        sections_json=json.dumps(sections, ensure_ascii=False),
        byte_size=len(content),
    )
    session.add(doc)
    await session.commit()
    return doc


async def list_documents(session: AsyncSession) -> list[KnowledgeDocument]:
    res = await session.execute(
        select(KnowledgeDocument).order_by(KnowledgeDocument.uploaded_at.desc())
    )
    return list(res.scalars())


async def delete_document(session: AsyncSession, doc_id: str) -> bool:
    res = await session.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
    )
    doc = res.scalar_one_or_none()
    if doc is None:
        return False
    try:
        os.remove(doc.storage_path)
    except OSError:
        pass
    await session.delete(doc)
    await session.commit()
    return True


async def extract_style_from_all_docs(
    session: AsyncSession,
    name: str | None = None,
) -> KnowledgeStyle:
    """Build a KnowledgeStyle row from every uploaded document.

    If `name` is omitted (None or "auto"), generate a smart default:
    the most common first-## heading across docs, plus a date stamp.
    """
    docs = await list_documents(session)
    if not docs:
        raise ValueError("no documents uploaded yet")

    if not name or name.strip().lower() == "auto":
        # Auto-name: derive from the first doc's filename + count
        first = docs[0]
        stem = re.sub(r"\.[^.]+$", "", first.filename)[:20]
        if len(docs) > 1:
            name = f"{stem}+{len(docs) - 1} 篇"
        else:
            name = stem

    payload = await extract_style_from_docs(session, docs)

    # Mark any current active style as inactive (singleton active)
    active = (await session.execute(
        select(KnowledgeStyle).where(KnowledgeStyle.is_active == 1)
    )).scalars().all()
    for s in active:
        s.is_active = 0

    style = KnowledgeStyle(
        name=name,
        dimensions_json=json.dumps(payload["dimensions"], ensure_ascii=False),
        tone=payload["tone"],
        length_pref=payload["length_pref"],
        quantification=payload["quantification"],
        custom_instructions=payload["custom_instructions"],
        source_doc_ids=json.dumps(payload["source_doc_ids"]),
        is_active=1,
    )
    session.add(style)
    await session.commit()
    return style


async def get_active_style(session: AsyncSession) -> KnowledgeStyle | None:
    return (await session.execute(
        select(KnowledgeStyle).where(KnowledgeStyle.is_active == 1)
        .order_by(KnowledgeStyle.updated_at.desc())
    )).scalars().first()


async def get_style_by_id(session: AsyncSession, style_id: str) -> KnowledgeStyle | None:
    """Fetch a specific KnowledgeStyle by id (Phase B: per-research binding)."""
    return (await session.execute(
        select(KnowledgeStyle).where(KnowledgeStyle.id == style_id)
    )).scalars().first()


# ── Style matching (Phase B-2) ───────────────────────────────
# Lightweight keyword-overlap scorer. For each candidate style we count
# keyword hits across the goal text against (a) the style name and (b)
# each dimension title. We deliberately avoid LLM calls here — matching
# runs on every keystroke in the form, so it must be sub-100ms.

import re as _re_match
_STOP_WORDS = set("的 是 在 有 和 与 或 等 及 于 为 把 被 让 使 由 从 到 不 没 也 很 就 都 还 已".split())


def _tokenize(text: str) -> set[str]:
    """CJK-aware tokenizer: returns set of meaningful tokens.

    Strategy:
    - Lowercase
    - Split into ASCII words and CJK-character runs
    - Group consecutive CJK chars into single tokens (e.g. "数据库部署"
      → ["数据库", "部署"] via 2-gram shingle, plus single chars for short)
    - Drop stopwords and 1-char Latin noise
    """
    if not text:
        return set()
    text = text.lower()
    # Insert spaces around each CJK char so we can split by whitespace
    spaced = _re_match.sub(r"([一-鿿])", r" \1 ", text)
    raw_toks = spaced.split()
    out: set[str] = set()
    cjk_run: list[str] = []
    def flush_run():
        if not cjk_run:
            return
        run = "".join(cjk_run)
        # Single-char tokens of meaningful CJK
        if len(run) == 1:
            out.add(run)
        else:
            # Add the whole run (most informative) plus 2-grams for overlap matching
            out.add(run)
            for i in range(len(run) - 1):
                out.add(run[i:i + 2])
            if len(run) >= 3:
                # Also add 3-grams for longer keyword matches
                for i in range(len(run) - 2):
                    out.add(run[i:i + 3])
        cjk_run.clear()
    for tok in raw_toks:
        # If token is a single CJK char (after regex split), it's a Chinese char
        if len(tok) == 1 and _re_match.match(r"[一-鿿]", tok):
            cjk_run.append(tok)
        else:
            flush_run()
            if tok and tok not in _STOP_WORDS and len(tok) > 1:
                out.add(tok)
    flush_run()
    return out


def _score_match(query: str, candidate_texts: list[str]) -> tuple[int, set[str]]:
    """Return (overlap_count, matched_keywords) between query tokens and candidate texts."""
    q = _tokenize(query)
    matched: set[str] = set()
    score = 0
    for ct in candidate_texts:
        for tok in _tokenize(ct):
            if tok in q:
                score += 1
                matched.add(tok)
    return score, matched


def rank_styles_for_goal(
    goal: str,
    constraints: str = "",
    styles: list[KnowledgeStyle] | None = None,
) -> list[dict]:
    """Rank KnowledgeStyles by relevance to a research goal.

    Returns a list of {style, score, matched_keywords, sample_dimensions}.
    Empty goal → return all styles in recency order with score 0.

    Heuristic scoring:
      - +3 for each style-name keyword hit
      - +2 for each dimension keyword hit
      - +1 for each constraint keyword hit
    """
    full_query = f"{goal} {constraints}".strip()
    if not full_query:
        return [
            {"style": s, "score": 0, "matched_keywords": set(), "sample_dimensions": s.dimensions[:5]}
            for s in (styles or [])
        ]

    if not styles:
        return []

    # Pull style rows once
    rows: list[tuple[KnowledgeStyle, list[str], list[str]]] = []
    for s in styles:
        try:
            dims = json.loads(s.dimensions_json or "[]")
        except Exception:
            dims = []
        rows.append((s, [s.name or ""], dims))

    scored: list[dict] = []
    for s, name_list, dims in rows:
        score_name, mk_name = _score_match(full_query, name_list)
        score_dims, mk_dims = _score_match(full_query, dims)
        score = score_name * 3 + score_dims * 2 + (1 if constraints else 0) * 0  # (no separate scoring for now)
        matched = mk_name | mk_dims
        if score > 0:
            scored.append({
                "style": s,
                "score": score,
                "matched_keywords": matched,
                "sample_dimensions": dims[:5],
            })
    scored.sort(key=lambda r: (-r["score"], r["style"].updated_at), reverse=False)
    scored.sort(key=lambda r: r["score"], reverse=True)

    # Always include the active style at the top if it has score 0
    if not scored:
        for s in styles:
            if s.is_active:
                scored.insert(0, {
                    "style": s, "score": 0, "matched_keywords": set(),
                    "sample_dimensions": json.loads(s.dimensions_json or "[]")[:5],
                })

    return scored


async def list_styles(session: AsyncSession) -> list[KnowledgeStyle]:
    res = await session.execute(
        select(KnowledgeStyle).order_by(KnowledgeStyle.updated_at.desc())
    )
    return list(res.scalars())


async def activate_style(session: AsyncSession, style_id: str) -> KnowledgeStyle | None:
    style = (await session.execute(
        select(KnowledgeStyle).where(KnowledgeStyle.id == style_id)
    )).scalar_one_or_none()
    if style is None:
        return None
    for s in (await list_styles(session)):
        s.is_active = (1 if s.id == style_id else 0)
    await session.commit()
    return style


# ── LLM-based reranking (Phase B-3) ───────────────────────────
# Use the LLM to break ties when keyword scoring gives ambiguous results
# (e.g. scores 35 vs 27 — both look like DB styles). The LLM sees the
# goal + each candidate's name + dimension list + score and returns
# a refined ranking with a 1-line reason for each.

RERANK_PROMPT = """你是研究风格匹配器。我会给你一个研究目标（goal）和 N 个候选风格。每个候选都有：
- name（用户起的名字）
- dimensions（用户上传预研文档抽取出的研究维度）

任务：根据 goal 与每个风格的契合度，**重新排序**，输出 JSON 数组（按推荐顺序）：

```json
[
  {"id": "<style_id>", "score": 0-100, "reason": "一句话理由（中文 ≤ 30 字）"},
  ...
]
```

排序原则：
1. **场景契合**：研究的目标领域（数据库？安全？AI？架构？）与风格维度覆盖度是否匹配
2. **维度覆盖**：goal 中提到的关键词，应该在 dimensions 中有对应维度
3. **不要被名字误导**：用户起的名字可能不准确，以 dimensions 为准

只输出 JSON 数组，不要其他文字。
"""


async def rerank_styles_with_llm(
    goal: str,
    candidates: list[dict],
    timeout_sec: float = 30.0,
) -> list[dict] | None:
    """Rerank style candidates using LLM. Returns None if LLM unavailable.

    Args:
        goal: research goal string
        candidates: list of {style: KnowledgeStyle, score: int} from
                    rank_styles_for_goal(); only top 5 are sent to LLM.

    Returns: list of {id, score, reason} sorted by LLM preference, or
             None if LLM call fails (caller should fall back to keyword).
    """
    if not candidates:
        return None
    try:
        from app.core.config import settings
        from app.agents.llm import StepfunClient
        client = StepfunClient(
            api_key=settings.stepfun_api_key,
            base_url=settings.stepfun_base_url,
            model=settings.stepfun_model,
            timeout=timeout_sec,
        )
        # Build a compact candidate list (id, name, dimensions)
        compact: list[dict] = []
        for c in candidates[:5]:
            try:
                dims = json.loads(c["style"].dimensions_json or "[]")
            except Exception:
                dims = []
            compact.append({
                "id": c["style"].id,
                "name": c["style"].name,
                "dimensions": dims[:15],  # cap to keep prompt small
            })
        user_msg = f"研究目标：{goal}\n\n候选风格（最多 5 个）：\n" + \
                   "\n".join(f"- id={c['id']}, name={c['name']}, dimensions={c['dimensions']}" for c in compact)
        resp = await client.chat_json(
            RERANK_PROMPT,
            user_msg,
            max_tokens=800, temperature=0.1,
        )
        if not isinstance(resp, list):
            return None
        # Normalize and sort by LLM score desc
        out = []
        for item in resp:
            if not isinstance(item, dict) or "id" not in item:
                continue
            out.append({
                "id": str(item["id"]),
                "score": int(item.get("score", 0)),
                "reason": str(item.get("reason", ""))[:120],
            })
        out.sort(key=lambda r: -r["score"])
        return out
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning(f"LLM rerank failed: {e}")
        return None


def merge_rankings(
    keyword_ranked: list[dict],
    llm_ranked: list[dict] | None,
) -> list[dict]:
    """Merge keyword + LLM rankings. LLM wins ties; we keep keyword order otherwise.

    Returns the original keyword_ranked list with style_id re-ordered to
    match LLM preference when LLM is available.
    """
    if not llm_ranked:
        return keyword_ranked

    # Build a map: style_id → LLM score + reason
    llm_map = {r["id"]: r for r in llm_ranked}
    # Reorder the keyword-ranked items according to LLM's preference.
    # Items in keyword_ranked not in LLM keep their relative order at the
    # end.
    in_llm = [r for r in keyword_ranked if r["style"].id in llm_map]
    not_in_llm = [r for r in keyword_ranked if r["style"].id not in llm_map]
    in_llm.sort(key=lambda r: -llm_map[r["style"].id]["score"])

    # Attach LLM reason for transparency
    for r in in_llm:
        r["llm_score"] = llm_map[r["style"].id]["score"]
        r["llm_reason"] = llm_map[r["style"].id]["reason"]
    return in_llm + not_in_llm


def render_style_block(style: KnowledgeStyle) -> str:
    """Render a style row as a prompt section to inject into the agent.

    Used by hermes_researcher._build_prompt() when ResearchRequest
    .use_custom_style is True.
    """
    dims = json.loads(style.dimensions_json or "[]")
    if not dims:
        return ""
    lines = [
        "## 个性化研究维度（用户上传预研文档总结）",
        "",
        "本研究的章节结构与写作风格按用户历史文档定制：",
        "",
        "**章节顺序**：",
    ]
    for i, d in enumerate(dims, 1):
        lines.append(f"{i}. **{d}**")
    lines += [
        "",
        f"**写作风格**：{style.tone} · {style.length_pref} · {style.quantification}",
        "",
        "**额外指引**：",
        style.custom_instructions or "（无）",
    ]
    return "\n".join(lines)
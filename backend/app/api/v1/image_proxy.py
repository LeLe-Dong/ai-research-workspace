"""Image proxy: server-side fetch hotlink-protected images for the report viewer.

Usage: /api/v1/image-proxy?url=<encoded-image-url>

Behavior:
- Server fetches with Mozilla User-Agent (bypasses many bot blocks)
- No Referer header (bypasses CSDN/uml.org.cn style checks)
- Caches successful responses in /tmp/airw_image_cache/ for 7 days
- Returns the original image bytes with original Content-Type

This endpoint exists because browsers cannot reliably load:
- CSDN (i-blog.csdnimg.cn): blocks requests with non-browser Referer
- uml.org.cn: blocks based on IP / User-Agent
- Wikipedia (upload.wikimedia.org): SSL handshake issues from some networks

When the LLM embeds an image URL like:
    https://i-blog.csdnimg.cn/img_convert/abc.jpeg

We rewrite it to:
    /api/v1/image-proxy?url=https%3A%2F%2Fi-blog.csdnimg.cn%2Fimg_convert%2Fabc.jpeg
and our server fetches it instead of the browser.
"""
import hashlib
import logging
import os
from pathlib import Path
from urllib.parse import unquote

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/image-proxy", tags=["image-proxy"])

CACHE_DIR = Path("/tmp/airw_image_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL_SEC = 7 * 24 * 3600  # 7 days
MAX_BYTES = 10 * 1024 * 1024    # 10 MB hard cap
FETCH_TIMEOUT = 15.0

# Block private/loopback to avoid SSRF
BLOCKED_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "169.254.", "10.", "192.168.", "::1")


def _safe_cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


@router.get("/svg/{svg_b64:path}.svg")
async def proxy_svg(svg_b64: str) -> Response:
    """Serve a SVG that was base64url-encoded in the path.

    Used by the search backend to ship SVG placeholders to the LLM as opaque
    URLs (so the model doesn't try to "fix" the SVG and break its quoting).
    The LLM sees `/api/v1/image-proxy/svg/xxx.svg` and passes it through unchanged;
    the browser decodes the base64 and renders the SVG.
    """
    import base64
    # base64url uses - and _ instead of + and /
    try:
        # Pad to multiple of 4
        padded = svg_b64 + "=" * ((4 - len(svg_b64) % 4) % 4)
        # Translate base64url to standard base64
        standard = padded.replace("-", "+").replace("_", "/")
        svg_bytes = base64.b64decode(standard)
    except Exception as e:
        raise HTTPException(400, f"Invalid base64 SVG: {e}")
    if len(svg_bytes) > 50_000:
        raise HTTPException(413, "SVG too large")
    return Response(
        content=svg_bytes,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("")
async def proxy(url: str = Query(..., min_length=10, max_length=2000)) -> Response:
    """Server-side fetch an external image and stream it back."""
    real_url = unquote(url).strip()
    if not real_url.startswith(("http://", "https://")):
        raise HTTPException(400, "Only http/https URLs are supported")
    for blocked in BLOCKED_HOSTS:
        if blocked in real_url:
            raise HTTPException(403, f"Blocked host: {blocked}")

    cache_file = CACHE_DIR / _safe_cache_key(real_url)
    cache_meta = CACHE_DIR / (cache_file.name + ".meta")

    # Cache hit?
    if cache_file.exists() and cache_meta.exists():
        import time as _t
        try:
            age = _t.time() - float(cache_meta.read_text().strip())
            if age < CACHE_TTL_SEC:
                content = cache_file.read_bytes()
                ct = (cache_meta.name.split(".")[-2])  # not great, just read below
                ct = "image/jpeg"  # default
                # Better: store ct in a sibling file
                ct_file = CACHE_DIR / (cache_file.name + ".ct")
                if ct_file.exists():
                    ct = ct_file.read_text().strip()
                return Response(content=content, media_type=ct, headers={"Cache-Control": "public, max-age=86400"})
        except Exception:
            pass

    # Fetch
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(real_url, headers=headers)
    except httpx.TimeoutException:
        raise HTTPException(504, f"Upstream timeout: {real_url[:100]}")
    except Exception as e:
        raise HTTPException(502, f"Upstream fetch failed: {type(e).__name__}")

    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"Upstream returned {resp.status_code}")
    content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    if not content_type.startswith("image/"):
        # SVG served as text/html by some sites — pass through but warn
        logger.warning("non-image content-type from %s: %s", real_url[:80], content_type)
    body = resp.content
    if len(body) > MAX_BYTES:
        raise HTTPException(413, f"Image too large ({len(body)} bytes, max {MAX_BYTES})")

    # Persist to cache
    try:
        cache_file.write_bytes(body)
        cache_meta.write_text(str(__import__("time").time()))
        ct_file = CACHE_DIR / (cache_file.name + ".ct")
        ct_file.write_text(content_type)
    except OSError as e:
        logger.warning("cache write failed: %s", e)

    return Response(
        content=body,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Proxied-From": real_url[:100],
        },
    )

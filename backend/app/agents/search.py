"""Web search via MiniMax (primary) or DDGS (fallback).

Primary: MiniMax web_search API — Chinese-first, high quality, requires AIRW_MINIMAX_API_KEY.
Fallback: DDGS DuckDuckGo — free, no API key, often blocked in China.
"""
import logging
import os
from dataclasses import dataclass
import httpx

logger = logging.getLogger(__name__)


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str


class MiniMaxSearch:
    """Calls api.minimaxi.com/v1/coding_plan/search (web_search MCP tool)."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.minimaxi.com",
        max_results: int = 5,
        timeout: float = 10.0,
    ):
        self.api_key = api_key or os.getenv("AIRW_MINIMAX_API_KEY", "")
        self.base_url = base_url or os.getenv("AIRW_MINIMAX_BASE_URL", "https://api.minimaxi.com")
        self.max_results = max_results
        self.timeout = timeout

    def search(self, query: str) -> list[SearchHit]:
        if not self.api_key:
            logger.debug("MiniMax API key not set")
            return []
        try:
            r = httpx.post(
                f"{self.base_url}/v1/coding_plan/search",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "MM-API-Source": "Minimax-MCP",
                    "Content-Type": "application/json",
                },
                json={"q": query},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.warning("MiniMax search failed for %r: %s", query, e)
            return []
        hits: list[SearchHit] = []
        for item in (data.get("organic") or [])[: self.max_results]:
            hits.append(SearchHit(
                title=item.get("title", "")[:200],
                url=item.get("link", ""),
                snippet=item.get("snippet", "")[:500],
            ))
        return hits


class DDGSSearch:
    """Wraps ddgs. Free, no API key, often blocked in China."""

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    def search(self, query: str) -> list[SearchHit]:
        try:
            from ddgs import DDGS
        except ImportError:
            logger.error("ddgs not installed")
            return []
        try:
            with DDGS(timeout=8) as ddgs:
                results = list(ddgs.text(query, max_results=self.max_results))
            return [
                SearchHit(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                )
                for r in results
            ]
        except Exception as e:
            logger.warning("DDGS search failed for %r: %s", query, e)
            return []


class WebSearcher:
    """Tries MiniMax first, falls back to DDGS. Never raises — always returns a list."""

    def __init__(self, max_results: int = 5, prefer: str = "minimax"):
        self.max_results = max_results
        self.prefer = prefer
        self._minimax = MiniMaxSearch(max_results=max_results)
        self._ddgs = DDGSSearch(max_results=max_results)

    def search(self, query: str) -> list[SearchHit]:
        """Returns search results. Tries MiniMax → DDGS → empty list."""
        if self.prefer in ("minimax", "auto"):
            hits = self._minimax.search(query)
            if hits:
                return hits
            if self.prefer == "minimax":
                logger.debug("MiniMax returned empty, trying DDGS")
                hits = self._ddgs.search(query)
                return hits
        if self.prefer in ("ddgs", "auto"):
            hits = self._ddgs.search(query)
            if hits:
                return hits
            if self.prefer == "auto":
                return self._minimax.search(query)
        return []

    @property
    def backend(self) -> str:
        """Returns which backend is configured ('minimax' or 'ddgs')."""
        return "minimax" if self._minimax.api_key else "ddgs"

    # Pass-through methods for backward compatibility
    def __getattr__(self, name):
        # Forward unknown attribute access to DDGSSearch for legacy code
        return getattr(self._ddgs, name)

    def search_many(self, queries: list[str]) -> list[tuple[str, SearchHit]]:
        """Returns [(query, hit), ...] deduplicated by URL."""
        seen: set[str] = set()
        out: list[tuple[str, SearchHit]] = []
        for q in queries:
            for hit in self.search(q):
                if hit.url and hit.url not in seen:
                    seen.add(hit.url)
                    out.append((q, hit))
        return out

    def search_images(self, query: str, max_results: int = 4) -> list[dict]:
        """Search for images. Tries DDGS first, falls back to curated topic images + SVG placeholders.

        Returns at most max_results images. Never raises — always returns a list.
        """
        hits: list[dict] = []

        # 1. Try DDGS (may fail in some networks)
        try:
            from ddgs import DDGS
            with DDGS(timeout=8) as ddgs:
                results = list(ddgs.images(query, max_results=max_results))
            for r in results:
                img_url = r.get("image", "")
                if not img_url:
                    continue
                # Validate URL with HEAD request (skip if can't verify)
                if not self._url_alive(img_url):
                    continue
                hits.append({
                    "title": r.get("title", ""),
                    "image_url": img_url,
                    "source_url": r.get("url", r.get("source", "")),
                    "width": r.get("width"),
                    "height": r.get("height"),
                })
                if len(hits) >= max_results:
                    return hits
        except Exception as e:
            logger.info("DDGS image search unavailable (%s), using fallback", type(e).__name__)

        # 2. Curated topic match — common dev terms have known logos
        curated = self._curated_image_for(query)
        if curated and len(hits) < max_results:
            hits.append(curated)

        # 3. SVG placeholder (always works, no network)
        if len(hits) < max_results:
            hits.append(self._svg_placeholder(query))

        return hits[:max_results]

    # Common tech topics with publicly-available logo URLs
    _CURATED = {
        "react": ("React", "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/React-icon.svg/120px-React-icon.svg.png"),
        "vue": ("Vue.js", "https://upload.wikimedia.org/wikipedia/commons/thumb/9/95/Vue.js_Logo_2.svg/120px-Vue.js_Logo_2.svg.png"),
        "angular": ("Angular", "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cf/Angular_full_color_logo.svg/120px-Angular_full_color_logo.svg.png"),
        "python": ("Python", "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/120px-Python-logo-notext.svg.png"),
        "fastapi": ("FastAPI", "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"),
        "django": ("Django", "https://upload.wikimedia.org/wikipedia/commons/thumb/7/75/Django_logo.svg/120px-Django_logo.svg.png"),
        "rust": ("Rust", "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/Rust_programming_language_black_logo.svg/120px-Rust_programming_language_black_logo.svg.png"),
        "go": ("Go", "https://upload.wikimedia.org/wikipedia/commons/thumb/0/05/Go_Logo_Blue.svg/120px-Go_Logo_Blue.svg.png"),
        "kubernetes": ("Kubernetes", "https://upload.wikimedia.org/wikipedia/commons/thumb/3/39/Kubernetes_logo_without_workmark.svg/120px-Kubernetes_logo_without_workmark.svg.png"),
        "docker": ("Docker", "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Docker_%28container_engine%29_logo.svg/120px-Docker_%28container_engine%29_logo.svg.png"),
        "postgresql": ("PostgreSQL", "https://upload.wikimedia.org/wikipedia/commons/thumb/2/29/Postgresql_elephant.svg/120px-Postgresql_elephant.svg.png"),
        "mongodb": ("MongoDB", "https://upload.wikimedia.org/wikipedia/commons/thumb/9/93/MongoDB_Logo.svg/120px-MongoDB_Logo.svg.png"),
        "redis": ("Redis", "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6b/Redis_Logo.svg/120px-Redis_Logo.svg.png"),
        "github": ("GitHub", "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"),
    }

    def _url_alive(self, url: str, timeout: float = 4.0) -> bool:
        """Quick HEAD check to verify image URL is reachable."""
        import httpx
        try:
            r = httpx.head(url, timeout=timeout, follow_redirects=True)
            return r.status_code < 400 and "image" in r.headers.get("content-type", "")
        except Exception:
            return False

    def _curated_image_for(self, query: str) -> dict | None:
        q_lower = query.lower()
        for key, (title, url) in self._CURATED.items():
            if key in q_lower:
                return {
                    "title": title,
                    "image_url": url,
                    "source_url": url,
                    "width": 120,
                    "height": 120,
                    "curated": True,
                }
        return None

    def _svg_placeholder(self, query: str) -> dict:
        """Generate an inline SVG placeholder image — works without network."""
        import hashlib
        h = hashlib.md5(query.encode()).hexdigest()
        # Pick a color from the hash
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        # Soften the color
        r, g, b = (r + 255) // 2, (g + 255) // 2, (b + 255) // 2
        # Initials
        words = query.split()[:2]
        initials = "".join(w[0].upper() for w in words if w)[:3] or "?"
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="240" viewBox="0 0 400 240">'
            f'<rect width="400" height="240" fill="rgb({r},{g},{b})"/>'
            f'<text x=\"200\" y=\"135\" font-family=\"Inter,system-ui,sans-serif\" font-size=\"80\" '
            f'font-weight="700" fill="white" text-anchor="middle">{initials}</text>'
            f'</svg>'
        )
        import base64
        b64_std = base64.b64encode(svg.encode()).decode()
        b64_url = b64_std.replace("+", "-").replace("/", "_").rstrip("=")
        return {
            "title": f"{query} (示意)",
            "image_url": f"/api/v1/image-proxy/svg/{b64_url}.svg",
            "source_url": "",
            "width": 400,
            "height": 240,
            "placeholder": True,
        }

    def search_images_many(self, queries: list[str], max_per_query: int = 2) -> list[dict]:
        """Search images for many queries, dedup by image_url."""
        seen: set[str] = set()
        out: list[dict] = []
        for q in queries:
            for img in self.search_images(q, max_results=max_per_query):
                if img["image_url"] and img["image_url"] not in seen:
                    seen.add(img["image_url"])
                    out.append(img)
        return out

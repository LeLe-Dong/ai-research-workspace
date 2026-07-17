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
        """Search for images relevant to query.

        Strategy (in order):
        1. DDGS image search — filter results by title relevance (drop Bengal-cat-for-K8s)
        2. Curated topic match — common dev terms have known logos
        3. SVG concept placeholder — works without network, shows query as label

        Returns at most max_results images. Never raises — always returns a list.
        """
        hits: list[dict] = []
        # Build keyword set for relevance filtering (>= 2 char words)
        keywords = {w.lower() for w in query.split() if len(w) >= 2}

        def _is_relevant(title: str) -> bool:
            """Image is relevant if its title shares any keyword with the query."""
            if not keywords:
                return True
            title_lower = title.lower()
            return any(kw in title_lower for kw in keywords)

        # 1. Skip DDGS — image search returns too much noise (Bengal cats for "Kubernetes")
        #    and HEAD-check latency makes research hang. Use curated + SVG instead.
        #    To re-enable: uncomment below.
        #
        # try:
        #     from ddgs import DDGS
        #     with DDGS(timeout=5) as ddgs:
        #         results = list(ddgs.images(query, max_results=max_results + 1))
        #     for r in results:
        #         img_url = r.get("image", "")
        #         if not img_url or "wikimedia.org" in img_url:
        #             continue
        #         if not _is_relevant(r.get("title", "")):
        #             continue
        #         if not self._url_alive(img_url, timeout=2):
        #             continue
        #         hits.append({...})
        #         if len(hits) >= max_results: return hits
        # except Exception as e:
        #     logger.info("DDGS image search unavailable (%s)", type(e).__name__)
        logger.debug("Skipping DDGS image search for query %r (using curated+SVG only)", query)

        # 2. Curated topic match — common dev terms have known logos
        curated = self._curated_image_for(query)
        if curated and len(hits) < max_results:
            hits.append(curated)

        # 3. SVG concept placeholder (always works, shows query as label)
        while len(hits) < max_results:
            hits.append(self._svg_placeholder(query))

        return hits[:max_results]

    # Common tech topics with publicly-available logo URLs
        # Common tech topics. These point to OFFICIAL sources only — never wikimedia
    # (the backend server can't reach wikimedia.org due to SSL issues).
    # Format: query-keyword → (display-name, official-logo-URL)
    _CURATED = {
        "fastapi": ("FastAPI", "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"),
        "github": ("GitHub", "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"),
        "kubernetes": ("Kubernetes", "https://raw.githubusercontent.com/kubernetes/community/master/icons/svg/infrastructure_components/labeled/kubernetes.svg"),
        "k8s": ("Kubernetes", "https://raw.githubusercontent.com/kubernetes/community/master/icons/svg/infrastructure_components/labeled/kubernetes.svg"),
        "docker": ("Docker", "https://www.docker.com/wp-content/uploads/2022/03/Moby-logo.png"),
        "rust": ("Rust", "https://www.rust-lang.org/static/images/rust-logo-blk.svg"),
        "go": ("Go", "https://go.dev/blog/go-brand/Go-Logo/PNG/Go-Logo_Blue.png"),
        "golang": ("Go", "https://go.dev/blog/go-brand/Go-Logo/PNG/Go-Logo_Blue.png"),
        "python": ("Python", "https://www.python.org/static/community_logos/python-logo-master-v3-TM.png"),
        "react": ("React", "https://reactjs.org/logo-180x180.png"),
        "reactjs": ("React", "https://reactjs.org/logo-180x180.png"),
        "node": ("Node.js", "https://nodejs.org/static/images/logos/nodejs-new-pantone-black.png"),
        "nodejs": ("Node.js", "https://nodejs.org/static/images/logos/nodejs-new-pantone-black.png"),
        "vue": ("Vue.js", "https://vuejs.org/images/logo.png"),
        "vuejs": ("Vue.js", "https://vuejs.org/images/logo.png"),
        "openai": ("OpenAI", "https://upload.wikimedia.org/wikipedia/commons/thumb/0/04/ChatGPT_logo.svg/240px-ChatGPT_logo.svg.png"),
    }
    

    def _url_alive(self, url: str, timeout: float = 2.0) -> bool:
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
        """Generate a descriptive SVG placeholder image — works without network.

        Shows the query text as a label so the reader knows what concept the image
        represents, even when no real photo is available.
        """
        import hashlib
        h = hashlib.md5(query.encode()).hexdigest()
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        # Soften the color
        r, g, b = (r + 255) // 2, (g + 255) // 2, (b + 255) // 2
        color = f"rgb({r},{g},{b})"

        # Truncate query to fit nicely in the SVG (CJK chars count as 2 wide)
        display_text = query.strip()
        if len(display_text) > 14:
            display_text = display_text[:13] + "…"

        # Escape XML entities
        display_text = (
            display_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="240" viewBox="0 0 400 240">'
            f'<defs><linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">'
            f'<stop offset="0%" stop-color="{color}"/>'
            f'<stop offset="100%" stop-color="white"/>'
            f'</linearGradient></defs>'
            f'<rect width="400" height="240" fill="url(#bg)" opacity="0.9"/>'
            f'<rect x="0" y="0" width="400" height="240" fill="none" stroke="rgb({(r+128)%256},{(g+128)%256},{(b+128)%256})" stroke-width="2" stroke-dasharray="6,4"/>'
            f'<text x="200" y="120" font-family="Inter,system-ui,sans-serif" font-size="44" '
            f'font-weight="700" fill="white" text-anchor="middle" stroke="rgba(0,0,0,0.25)" stroke-width="1">'
            f'📊 {display_text}</text>'
            f'<text x="200" y="170" font-family="Inter,system-ui,sans-serif" font-size="14" '
            f'font-weight="500" fill="rgba(255,255,255,0.85)" text-anchor="middle">'
            f'概念示意 · placeholder</text>'
            f'</svg>'
        )
        import base64
        b64_std = base64.b64encode(svg.encode()).decode()
        b64_url = b64_std.replace("+", "-").replace("/", "_").rstrip("=")
        return {
            "title": f"{query} (概念示意)",
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

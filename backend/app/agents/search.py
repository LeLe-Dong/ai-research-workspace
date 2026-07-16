"""Web search via DuckDuckGo (free, no API key)."""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str


class DDGSSearch:
    """Wraps ddgs. Falls back gracefully on transient errors."""

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    def search(self, query: str) -> list[SearchHit]:
        try:
            from ddgs import DDGS
        except ImportError:
            logger.error("ddgs not installed")
            return []
        try:
            with DDGS() as ddgs:
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
            f'<text x="200" y="135" font-family="Inter,system-ui,sans-serif" font-size="80" '
            f'font-weight="700" fill="white" text-anchor="middle">{initials}</text>'
            f'</svg>'
        )
        import base64
        b64 = base64.b64encode(svg.encode()).decode()
        return {
            "title": f"{query} (示意)",
            "image_url": f"data:image/svg+xml;base64,{b64}",
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

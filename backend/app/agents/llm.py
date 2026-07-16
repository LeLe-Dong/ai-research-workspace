"""Stepfun LLM client (OpenAI-compatible endpoint)."""
import os
import json
import logging
import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.stepfun.com/step_plan/v1"
DEFAULT_MODEL = "step-3.7-flash"


class LLMError(Exception):
    pass





def _strip_thinking(text: str, is_json: bool = False) -> str:
    """Strip chain-of-thought preamble that step-3.7-flash sometimes prepends.

    For JSON mode: cut at first '{' (start of actual JSON).
    For Markdown: cut at first '#' heading or "## " subheading.
    Fallback: return text unchanged.
    """
    import re
    t = text.strip()
    if not t:
        return t
    if is_json:
        first = t.find("{")
        if first > 0:
            return t[first:]
        return t
    # Markdown mode: look for first heading or significant content marker
    m = re.search(r"\n(#{1,6}\s|\*\*[A-Z])", t)
    if m and m.start() < 500:
        return t[m.start():].lstrip("\n")
    # If text starts with prose that looks like thinking, try to find where the actual answer starts
    thinking_prefixes = (
        "Let me ", "Got it,", "Got it ", "Sure,", "Sure ", "Alright,", "Alright ",
        "First,", "First ", "Okay,", "Okay ", "I should", "I need", "I'll ",
        "Now,", "Now ", "The user", "用户现在", "首先", "好的", "现在",
    )
    if t.startswith(thinking_prefixes):
        # Try multiple split strategies
        # 1. Blank line followed by content
        parts = t.split("\n\n", 1)
        if len(parts) == 2 and len(parts[1].strip()) > 50:
            return parts[1].strip()
        # 2. Look for first heading
        m2 = re.search(r"\n(#{1,6}\s|\*\*[A-Z]|\d+\.\s|Section \d+)", t)
        if m2:
            return t[m2.start():].lstrip("\n")
        # 3. If still thinking, try to find where Chinese thinking ends
        # Pattern: "首先...哦对...然后...哦...等下..." - thinking often has "哦" / "等下"
        m3 = re.search(r"\n\n(.+)", t)
        if m3 and len(m3.group(1).strip()) > 50:
            return m3.group(1).strip()
        # 4. If text starts with Chinese thinking, find first newline followed by Chinese content
        if any(t.startswith(p) for p in ("首先", "好的", "现在", "用户")):
            for sep in ["\n\n", "\n1. ", "\n## ", "\n# ", "\n**"]:
                idx = t.find(sep)
                if idx > 0:
                    return t[idx:].lstrip("\n")
    return t


class StepfunClient:
    """Thin wrapper around the Stepfun chat completions endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 180.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.4,
        max_tokens: int = 4000,
        response_format_json: bool = False,
    ) -> str:
        """Send a single chat completion request. Returns the assistant text content.

        Note on step-3.7-flash behavior: the model often prepends a chain-of-thought
        to its reply (e.g. "Got it, the user wants..."). We mitigate by:
        - Using higher max_tokens (thinking consumes tokens before the actual answer)
        - Adding stop sequences that cut off common thinking preambles
        - The caller is responsible for stripping leading thinking via _strip_thinking()
        """
        if not self.api_key:
            raise LLMError("API key not set")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format_json:
            body["response_format"] = {"type": "json_object"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=body, headers=headers)
                if resp.status_code != 200:
                    raise LLMError(f"Stepfun {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise LLMError("No choices in response")
                choice = choices[0]
                msg = choice.get("message") or {}
                content = msg.get("content") or ""
                finish_reason = choice.get("finish_reason", "stop")
                # Some models return empty content but populate reasoning_content
                if not content.strip() and msg.get("reasoning_content"):
                    content = msg["reasoning_content"]
                if not content.strip():
                    raise LLMError(f"Empty content from LLM (finish_reason={finish_reason})")
                if finish_reason == "length":
                    # Truncated — append a marker so downstream knows
                    content = content + "\n\n[truncated: max_tokens reached]"
                return content
        except httpx.HTTPError as e:
            raise LLMError(f"{type(e).__name__}: {e}") from e

    async def chat_json(self, system: str, user: str, **kwargs) -> dict:
        """Convenience: chat + parse JSON. Tries hard to extract JSON from prose-wrapped output.

        Note: step-3.7-flash is more reliable WITHOUT response_format=json_object,
        which tends to trigger chain-of-thought preamble. We rely on prompt
        instructions + post-hoc brace extraction.
        """
        text = await self.chat(system, user, **kwargs)

        candidates = []

        # 1. Direct
        candidates.append(text.strip())

        # 2. Strip fences
        t = text.strip()
        if t.startswith("```"):
            lines = t.split("\n")
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            candidates.append("\n".join(lines).strip())

        # 3. Find first '{' and matching balanced '}'
        first = text.find("{")
        if first >= 0:
            depth = 0
            last = -1
            for i in range(first, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        last = i
                        break
            if last > first:
                candidates.append(text[first:last + 1].strip())

        # 4. Try each { ... } group in the text (handles thinking + JSON mixed)
        for j in range(len(text)):
            if text[j] == "{":
                depth = 0
                end = -1
                for k in range(j, len(text)):
                    if text[k] == "{":
                        depth += 1
                    elif text[k] == "}":
                        depth -= 1
                        if depth == 0:
                            end = k
                            break
                if end > j:
                    cand = text[j:end + 1].strip()
                    if cand not in candidates and len(cand) > 50:  # skip tiny {}
                        candidates.append(cand)

        last_err = None
        for c in candidates:
            try:
                return json.loads(c)
            except json.JSONDecodeError as e:
                last_err = e

        logger.error("LLM JSON parse failed: %s / text=%s", last_err, text[:500])
        raise LLMError(f"Bad JSON from LLM: {last_err}") from last_err

"""Google Gemini client (REST API, no extra dependencies).

- The key is sent in the x-goog-api-key header, never in the URL, so it
  cannot leak into logs that record URLs.
- Temporary failures (timeouts, 429, 5xx) are retried with exponential
  backoff and jitter (workflow section 15.2). Permanent ones are not.
"""

import json
import random
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from app.llm.base import LLMConfigError, LLMInvalidOutputError, LLMUnavailableError

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
BACKOFF_SECONDS = (2, 5, 15, 30)  # then 30 for any further attempts
# A 429 asking us to wait longer than this is a quota, not a burst limit.
MAX_QUOTA_WAIT_SECONDS = 60

# (url, body bytes, headers, timeout) -> (status code, response bytes)
Transport = Callable[[str, bytes, dict[str, str], float], tuple[int, bytes]]


def _urllib_transport(url: str, body: bytes, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
        max_retries: int = 3,
        min_interval_seconds: float = 0.0,
        max_output_tokens: int = 16384,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.strip():
            raise LLMConfigError("LLM_API_KEY is empty")
        self._api_key = api_key.strip()
        self.model = model
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._min_interval = min_interval_seconds
        self._max_output_tokens = max_output_tokens
        self._transport = transport or _urllib_transport
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_call = 0.0

    def __repr__(self) -> str:  # never show the key
        return f"GeminiClient(model={self.model!r})"

    def generate_json(self, *, system: str, user: str, schema: dict[str, Any]) -> Any:
        body = json.dumps(
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": 0,
                    "responseMimeType": "application/json",
                    "responseJsonSchema": schema,
                    "maxOutputTokens": self._max_output_tokens,
                },
            }
        ).encode("utf-8")
        status, payload = self._post(body)
        return self._parse(status, payload)

    # ------------------------------------------------------------ internals

    def _post(self, body: bytes) -> tuple[int, bytes]:
        url = f"{API_BASE}/{self.model}:generateContent"
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}
        last_problem = ""
        for attempt in range(self._max_retries + 1):
            if attempt:
                delay = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
                self._sleep(delay + random.uniform(0, delay / 2))  # jitter
            self._respect_min_interval()
            try:
                status, payload = self._transport(url, body, headers, self._timeout)
            except OSError as exc:  # covers timeouts, URLError and connection errors
                last_problem = f"{type(exc).__name__}: {exc}"
                continue
            if status == 429:
                wait = _retry_delay_seconds(payload)
                if wait is not None and wait > MAX_QUOTA_WAIT_SECONDS:
                    # A daily quota, not a momentary rate limit: retrying is pointless.
                    raise LLMUnavailableError(
                        f"{self.model} quota exhausted; resets in about {wait / 3600:.1f} h "
                        f"({_error_message(payload)[:160]})"
                    )
            if status in RETRYABLE_STATUS:
                last_problem = f"HTTP {status}: {_error_message(payload)}"
                continue
            return status, payload
        raise LLMUnavailableError(
            f"{self.model} unavailable after {self._max_retries + 1} attempts ({last_problem})"
        )

    def _respect_min_interval(self) -> None:
        if not self._min_interval:
            return
        with self._lock:
            wait = self._last_call + self._min_interval - time.monotonic()
            if wait > 0:
                self._sleep(wait)
            self._last_call = time.monotonic()

    def _parse(self, status: int, payload: bytes) -> Any:
        if status != 200:
            raise LLMConfigError(f"HTTP {status} from {self.model}: {_error_message(payload)}")
        data = json.loads(payload)
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise LLMInvalidOutputError(f"{self.model} returned no answer ({reason})")
        candidate = candidates[0]
        finish = candidate.get("finishReason", "STOP")
        if finish != "STOP":
            raise LLMInvalidOutputError(f"{self.model} stopped early (finishReason={finish})")
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMInvalidOutputError(f"{self.model} returned invalid JSON: {exc}") from exc


def _retry_delay_seconds(payload: bytes) -> float | None:
    """The provider's suggested wait (e.g. "79194s"), if it gave one."""
    try:
        details = json.loads(payload).get("error", {}).get("details", [])
    except (json.JSONDecodeError, AttributeError):
        return None
    for detail in details:
        delay = str(detail.get("retryDelay", ""))
        if delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                return None
    return None


def _error_message(payload: bytes) -> str:
    try:
        error = json.loads(payload).get("error", {})
        return f"{error.get('status', '')} {error.get('message', '')}".strip()[:300]
    except (json.JSONDecodeError, AttributeError):
        return payload[:300].decode("utf-8", "replace")

"""The only way research code reaches the internet.

Requests may go ONLY to a fixed allowlist of API hosts over HTTPS. User input
never becomes a URL host, so the server cannot be tricked into fetching
internal addresses (SSRF, workflow section 16.2).
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

ALLOWED_HOSTS = frozenset({
    "en.wikipedia.org",
    "openlibrary.org",
    "www.googleapis.com",
})
USER_AGENT = "AILessonStudio/0.1 (educational research tool)"


class ResearchSourceError(Exception):
    """A research provider could not be reached or returned bad data."""


def get_json(url: str, params: dict[str, Any], *, timeout: float = 20, retries: int = 2) -> Any:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ResearchSourceError(f"blocked request to non-allowlisted host: {parsed.hostname}")
    full = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
    last = ""
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(2 * attempt)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except (OSError, json.JSONDecodeError) as exc:
            last = f"{type(exc).__name__}: {exc}"
    raise ResearchSourceError(f"{parsed.hostname}: {last}")

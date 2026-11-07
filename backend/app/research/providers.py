"""Research providers: Wikipedia (websites), Open Library (books), YouTube (videos).

- Wikipedia articles are read in full; relevant paragraphs are kept VERBATIM
  as evidence passages, so QC1 can check claims against exact text.
- Books and videos are METADATA ONLY: we know their title and author, not
  their content, so they are references and supplementary resources, never
  evidence (workflow section 5.3).
"""

import re
from datetime import date, datetime

from app.research.http import ResearchSourceError, get_json
from app.schemas.enums import AccessStatus, AuthorityCategory, ContentAccess, SourceType

WIKI_API = "https://en.wikipedia.org/w/api.php"
OPENLIBRARY_API = "https://openlibrary.org/search.json"
YOUTUBE_SEARCH = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"

_STOPWORDS = set(
    "a an and are as at be between by can de del distinguish do does explain for from how "
    "identify in into is it its of on or that the their this to understand using what when "
    "which with within".split()
)


def keywords(*texts: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", " ".join(texts).lower())
    return {w for w in words if len(w) > 1 and w not in _STOPWORDS}


def _paragraphs(extract: str) -> list[str]:
    """Plain-text paragraphs, without headings, split into chunks of at most ~700 chars."""
    chunks = []
    for para in extract.split("\n"):
        para = para.strip()
        if len(para) < 80 or para.startswith("=="):
            continue
        while len(para) > 700:  # split long paragraphs at a sentence boundary
            cut = para.rfind(". ", 0, 700)
            cut = cut + 1 if cut > 200 else 700
            chunks.append(para[:cut].strip())
            para = para[cut:].strip()
        if len(para) >= 80:
            chunks.append(para)
    return chunks


def wikipedia_articles(query: str, limit: int = 2) -> list[str]:
    data = get_json(WIKI_API, {"action": "query", "list": "search", "srsearch": query,
                               "srlimit": limit, "format": "json"})
    return [hit["title"] for hit in data.get("query", {}).get("search", [])]


def wikipedia_source(title: str, retrieved: date) -> dict | None:
    """The whole article as candidate paragraphs; the engine picks the evidence."""
    data = get_json(WIKI_API, {
        "action": "query", "prop": "extracts|info|revisions", "explaintext": 1, "inprop": "url",
        "rvprop": "timestamp", "redirects": 1, "titles": title, "format": "json",
    })
    pages = list(data.get("query", {}).get("pages", {}).values())
    if not pages or "missing" in pages[0]:
        return None
    page = pages[0]
    paragraphs = _paragraphs(page.get("extract", ""))
    if not paragraphs:
        return None
    edited = page.get("revisions", [{}])[0].get("timestamp")
    return {
        "source_type": SourceType.WEBSITE,
        "title": page["title"] + " (Wikipedia)",
        "publisher": "Wikipedia",
        "url": page.get("fullurl"),
        "published_at": datetime.fromisoformat(edited.replace("Z", "+00:00")).date() if edited else None,
        "retrieved_at": retrieved,
        "access_status": AccessStatus.ACCESSIBLE,
        "content_access": ContentAccess.EXCERPT,
        "authority_category": AuthorityCategory.REFERENCE,
        "candidates": paragraphs,
        "passages": [],
    }


def open_library_books(query: str, limit: int, retrieved: date) -> list[dict]:
    data = get_json(OPENLIBRARY_API, {"q": query, "limit": limit,
                                      "fields": "key,title,author_name,first_publish_year"})
    books = []
    for doc in data.get("docs", []):
        if not doc.get("key") or not doc.get("title"):
            continue
        year = doc.get("first_publish_year")
        books.append({
            "source_type": SourceType.BOOK,
            "title": doc["title"] + (f" ({year})" if year else ""),
            "author": ", ".join(doc.get("author_name", [])[:3]) or None,
            "publisher": "Open Library record",
            "url": f"https://openlibrary.org{doc['key']}",
            "retrieved_at": retrieved,
            "access_status": AccessStatus.ACCESSIBLE,
            "content_access": ContentAccess.METADATA_ONLY,
            "authority_category": AuthorityCategory.UNKNOWN,
            "passages": [],
        })
    return books


def _minutes(iso_duration: str) -> int:
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration or "")
    if not match:
        return 0
    d, h, m, s = (int(x or 0) for x in match.groups())
    return max(1, round(d * 1440 + h * 60 + m + s / 60))


def youtube_videos(query: str, api_key: str, limit: int, retrieved: date) -> list[dict]:
    if not api_key:
        raise ResearchSourceError("YOUTUBE_API_KEY is not set")
    found = get_json(YOUTUBE_SEARCH, {
        "part": "snippet", "q": query, "type": "video", "maxResults": limit,
        "safeSearch": "strict", "relevanceLanguage": "en", "videoEmbeddable": "true", "key": api_key,
    })
    items = [i for i in found.get("items", []) if i.get("id", {}).get("videoId")]
    if not items:
        return []
    ids = [i["id"]["videoId"] for i in items]
    details = get_json(YOUTUBE_VIDEOS, {"part": "contentDetails", "id": ",".join(ids), "key": api_key})
    duration = {v["id"]: _minutes(v["contentDetails"]["duration"]) for v in details.get("items", [])}
    videos = []
    for item in items:
        vid, snip = item["id"]["videoId"], item["snippet"]
        videos.append({
            "source_type": SourceType.VIDEO,
            "title": snip["title"],
            "publisher": snip.get("channelTitle"),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "published_at": datetime.fromisoformat(snip["publishedAt"].replace("Z", "+00:00")).date(),
            "retrieved_at": retrieved,
            "access_status": AccessStatus.ACCESSIBLE,
            "content_access": ContentAccess.METADATA_ONLY,
            "authority_category": AuthorityCategory.UNKNOWN,
            "duration_minutes": duration.get(vid, 0),
            "passages": [],
        })
    return videos


__all__ = ["ResearchSourceError", "keywords", "wikipedia_articles", "wikipedia_source",
           "open_library_books", "youtube_videos"]

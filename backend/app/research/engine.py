"""Builds a ResearchPackage from a lesson title and learning objective.

1. The LLM plans queries (it never sees or produces URLs).
2. Code searches Wikipedia, Open Library and YouTube.
3. Wikipedia passages are kept verbatim and numbered EV-001, EV-002, ...

A provider that fails is recorded in `limitations`. If no evidence passages
are found at all, research is INSUFFICIENT and the step fails honestly.
"""

from dataclasses import dataclass, field
from datetime import date

from pydantic import Field

from app.llm.base import LLMClient, call_structured, to_prompt_json
from app.llm.prompts import load_prompt
from app.research import providers
from app.research.http import ResearchSourceError
from app.schemas.common import ContractModel, NonEmptyStr
from app.schemas.research import ResearchPackage

MAX_WIKI_ARTICLES = 4
PER_CONCEPT = 2
MAX_PASSAGES = 28
MAX_EXTRA_SEARCHES = 3
MAX_BOOKS = 3
MAX_VIDEOS = 3


class InsufficientResearchError(Exception):
    """No usable evidence was found. Change the inputs or retry later."""


class ResearchPlan(ContractModel):
    key_concepts: list[NonEmptyStr] = Field(min_length=1, max_length=10)
    wikipedia_queries: list[NonEmptyStr] = Field(min_length=1, max_length=5)
    book_query: NonEmptyStr
    video_queries: list[NonEmptyStr] = Field(min_length=1, max_length=3)


_LIST = {"type": "array", "items": {"type": "string"}}
PLAN_SCHEMA = {
    "type": "object",
    "properties": {"key_concepts": _LIST, "wikipedia_queries": _LIST,
                   "book_query": {"type": "string"}, "video_queries": _LIST},
    "required": ["key_concepts", "wikipedia_queries", "book_query", "video_queries"],
}


@dataclass
class ResearchResult:
    plan: ResearchPlan
    package: ResearchPackage
    video_minutes: dict[str, int] = field(default_factory=dict)  # source_id -> duration
    prompt_version: str = ""


def _select_passages(articles: list[dict], concepts: list[str], terms: set[str]) -> None:
    """Choose verbatim evidence: the best paragraphs for EACH key concept first,
    then the best remaining paragraphs overall, up to MAX_PASSAGES."""
    pool = [(a, i, text, providers.keywords(text)) for a in articles
            for i, text in enumerate(a["candidates"])]
    chosen: set[tuple[int, int]] = set()

    def take(entry) -> None:
        article, index, text, _ = entry
        if (id(article), index) not in chosen and len(chosen) < MAX_PASSAGES:
            chosen.add((id(article), index))
            article["passages"].append((index, text))

    for concept in concepts:
        words = providers.keywords(concept)
        ranked = sorted(pool, key=lambda e: (len(words & e[3]) / max(1, len(words)),
                                             len(terms & e[3])), reverse=True)
        for entry in ranked[:PER_CONCEPT]:
            if words & entry[3]:
                take(entry)
    for entry in sorted(pool, key=lambda e: len(terms & e[3]), reverse=True):
        if terms & entry[3]:
            take(entry)
    for article in articles:
        article["passages"] = [text for _, text in sorted(article["passages"])]
        best = max((len(terms & providers.keywords(p)) for p in article["passages"]), default=0)
        article["relevance_score"] = min(100, 40 + 8 * best)


def _uncovered(articles: list[dict], concepts: list[str]) -> list[str]:
    """Concepts for which no chosen passage contains at least half of their key words."""
    chosen = [providers.keywords(text) for a in articles for _, text in _as_pairs(a["passages"])]
    missing = []
    for concept in concepts:
        words = providers.keywords(concept)
        if not any(len(words & p) * 2 >= len(words) for p in chosen):
            missing.append(concept)
    return missing


def _as_pairs(passages: list) -> list[tuple[int, str]]:
    return [p if isinstance(p, tuple) else (0, p) for p in passages]


def plan_research(title: str, objective: str, client: LLMClient) -> tuple[ResearchPlan, str]:
    prompt = load_prompt("research/plan.md")
    plan = call_structured(
        client, system=prompt.text,
        user="INPUT:\n" + to_prompt_json({"lesson_title": title, "learning_objective": objective}),
        schema=PLAN_SCHEMA, output_model=ResearchPlan,
    )
    return plan, prompt.version


def run_research(
    title: str, objective: str, client: LLMClient, *, youtube_api_key: str = "", today: date | None = None
) -> ResearchResult:
    today = today or date.today()
    plan, prompt_version = plan_research(title, objective, client)
    terms = providers.keywords(title, objective, *plan.key_concepts)
    raw: list[dict] = []
    limitations: list[str] = []

    # Websites (evidence): articles round-robin across queries, so every query
    # contributes its best match before any query contributes a second one.
    # The query itself is tried first as an exact article title (Wikipedia
    # resolves redirects), because full-text search often ranks it lower.
    hits: list[list[str]] = []
    for query in plan.wikipedia_queries:
        try:
            hits.append([query] + providers.wikipedia_articles(query, limit=2))
        except ResearchSourceError as exc:
            limitations.append(f"Wikipedia search failed for '{query}': {exc}")
    titles: list[str] = []
    for rank in range(3):
        for found in hits:
            if rank < len(found) and found[rank] not in titles:
                titles.append(found[rank])

    articles: list[dict] = []

    def read(article: str) -> None:
        try:
            source = providers.wikipedia_source(article, today)
        except ResearchSourceError as exc:
            limitations.append(f"Could not read Wikipedia article '{article}': {exc}")
            return
        if source and source["title"] not in {a["title"] for a in articles}:  # redirects dedupe
            articles.append(source)

    for article in titles:
        if len(articles) >= MAX_WIKI_ARTICLES:
            break
        read(article)
    _select_passages(articles, plan.key_concepts, terms)

    # Coverage check: a key concept with no evidence gets its own search.
    for concept in _uncovered(articles, plan.key_concepts)[:MAX_EXTRA_SEARCHES]:
        try:
            for article in [concept] + providers.wikipedia_articles(concept, limit=1):
                before = len(articles)
                read(article)
                if len(articles) > before:
                    break
        except ResearchSourceError as exc:
            limitations.append(f"Wikipedia search failed for '{concept}': {exc}")
    for a in articles:
        a["passages"] = []
    _select_passages(articles, plan.key_concepts, terms)
    for concept in _uncovered(articles, plan.key_concepts):
        limitations.append(f"No evidence found for key concept '{concept}'.")
    raw += [a for a in articles if a["passages"]]
    for a in raw:
        a.pop("candidates", None)

    # Books (metadata only)
    try:
        raw += providers.open_library_books(plan.book_query, MAX_BOOKS, today)
    except ResearchSourceError as exc:
        limitations.append(f"Book search failed: {exc}")

    # Videos (metadata only)
    seen_urls: set[str] = set()
    for query in plan.video_queries:
        try:
            for video in providers.youtube_videos(query, youtube_api_key, MAX_VIDEOS, today):
                if video["url"] not in seen_urls and len(seen_urls) < MAX_VIDEOS:
                    seen_urls.add(video["url"])
                    raw.append(video)
        except ResearchSourceError as exc:
            limitations.append(f"YouTube search failed for '{query}': {exc}")
            break

    if not any(s["passages"] for s in raw):
        raise InsufficientResearchError(
            "No evidence passages were found for this topic. "
            + (" ".join(limitations) or "Try a more specific title or objective.")
        )

    limitations.append("Books and videos are metadata only (title, author/channel): their "
                       "content was not read, so they are references, never evidence.")
    sources, video_minutes, passage_no = [], {}, 0
    for number, item in enumerate(raw, start=1):
        source_id = f"SRC-{number:03d}"
        passages = []
        for text in item.pop("passages"):
            passage_no += 1
            passages.append({"passage_id": f"EV-{passage_no:03d}", "text": text})
        if "duration_minutes" in item:
            video_minutes[source_id] = item.pop("duration_minutes")
        sources.append(item | {"source_id": source_id, "evidence_passages": passages})

    package = ResearchPackage.model_validate({"sources": sources, "limitations": limitations})
    return ResearchResult(plan=plan, package=package, video_minutes=video_minutes,
                          prompt_version=prompt_version)

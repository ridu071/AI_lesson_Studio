"""What changed between two lesson versions (for the instructor's version history)."""

import difflib
import re
from dataclasses import dataclass

from app.generation.render import render_lesson_markdown
from app.schemas.lesson import LessonVersion
from app.schemas.research import ResearchPackage


_VERSION = re.compile(r"Version \d+\*$")


def _comparable(markdown: str) -> list[str]:
    """The version number in the header always differs; it is not a content change."""
    return [_VERSION.sub("Version*", line) for line in markdown.splitlines()]


@dataclass(frozen=True)
class VersionDiff:
    added: int
    removed: int
    text: str  # unified diff of the rendered lessons ("" when identical)

    @property
    def identical(self) -> bool:
        return not self.text


def diff_versions(old: LessonVersion, new: LessonVersion, research: ResearchPackage) -> VersionDiff:
    """Compare two versions as the readable lesson text, so the diff shows what a
    reader would notice (wording, questions, answers), not JSON noise."""
    before = _comparable(render_lesson_markdown(old, research))
    after = _comparable(render_lesson_markdown(new, research))
    lines = list(difflib.unified_diff(before, after, fromfile=f"version {old.version}",
                                      tofile=f"version {new.version}", lineterm="", n=1))
    body = [l for l in lines if not l.startswith(("---", "+++"))]
    added = sum(1 for l in body if l.startswith("+"))
    removed = sum(1 for l in body if l.startswith("-"))
    return VersionDiff(added, removed, "\n".join(lines) if added or removed else "")

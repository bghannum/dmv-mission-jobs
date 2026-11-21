"""Keyword tags (clearance, public_sector, ...) from config/tags.yaml.

Tags are matched as whole words/phrases on the title and department/team, plus a stricter
phrase list on the plain-text description (optionally needing several hits), plus
company-level industry tags (e.g. every job at a `deftech` company is `public_sector`).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from functools import cache

from .models import Job

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class TagRule:
    key: str
    label: str
    keywords: tuple[str, ...]
    description_keywords: tuple[str, ...]
    exclude: tuple[str, ...]
    industries: frozenset[str]
    # Description phrase hits needed (counting repeats). >1 ignores one-off "about us" lines.
    description_min_hits: int = 1


@cache
def _phrase_re(phrase: str) -> re.Pattern[str]:
    # Whole-word/phrase match: no letter or digit directly before or after.
    return re.compile(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])")


def html_to_text(raw: str | None) -> str:
    """Plain lowercase text from description HTML (handles entity-escaped HTML too)."""
    if not raw:
        return ""
    text = html.unescape(raw)  # Greenhouse returns entity-escaped HTML
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _clean(text: str, exclude: tuple[str, ...]) -> str:
    low = re.sub(r"\s+", " ", (text or "").lower())
    for phrase in exclude:
        low = low.replace(phrase, " ")
    return low


def _any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(_phrase_re(p).search(text) for p in phrases)


def _hits(text: str, phrases: tuple[str, ...]) -> int:
    return sum(len(_phrase_re(p).findall(text)) for p in phrases)


def tags_for(
    rules: list[TagRule],
    *,
    title: str | None,
    department: str | None = None,
    description: str | None = None,
    industries: list[str] | tuple[str, ...] = (),
) -> list[str]:
    """Return the tag keys that apply. `description` is plain text (see html_to_text)."""
    found: list[str] = []
    for rule in rules:
        head = _clean(f"{title or ''} | {department or ''}", rule.exclude)
        body = _clean(description or "", rule.exclude)
        if (
            _any(head, rule.keywords)
            or (body and _hits(body, rule.description_keywords) >= rule.description_min_hits)
            or bool(rule.industries & set(industries))
        ):
            found.append(rule.key)
    return found


def apply_tags(job: Job, rules: list[TagRule]) -> Job:
    job.tags = tags_for(
        rules,
        title=job.title,
        department=job.department,
        description=html_to_text(job.description_html),
        industries=job.industries,
    )
    return job

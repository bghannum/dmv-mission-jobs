"""Common data models shared across adapters and the pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

INDUSTRY_VOCAB = {
    # original (crsh-ovr/jobs)
    "cybersecurity", "deftech", "cspm", "finops", "grc", "healthtech",
    # PLAN.md Phase 2
    "govtech", "gov-it", "space", "ai", "bigtech", "saas",
    # a16z portfolio sectors (scripts/seed_a16z.py)
    "american-dynamism", "fintech", "crypto", "consumer", "games",
}
# Neutral priority tiers; lower sorts first. Drives ordering only (no public meaning).
PRIORITIES = {1, 2, 3}
DEFAULT_PRIORITY = 3


@dataclass
class Company:
    """One vetted company from the allowlist."""

    name: str
    ats: str
    identifier: str
    industry: list[str]
    priority: int = DEFAULT_PRIORITY
    homepage: str | None = None


@dataclass
class RoleUmbrella:
    """A role grouping (umbrella) with its roles and keyword rules."""

    key: str
    label: str
    # role_key -> {"label", "include_keywords", "exclude_keywords"}
    roles: dict[str, dict]


@dataclass
class Job:
    """A normalized job posting. Every adapter emits this shape."""

    id: str
    title: str
    company: str
    industries: list[str]
    url: str
    source_ats: str
    # Set from the company after normalization (see main.scrape_company).
    priority: int = DEFAULT_PRIORITY
    # Filled in by matching.py
    umbrellas: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    level: str = "mid"
    # Best-effort fields; may be None/empty depending on the ATS.
    location: str | None = None
    remote: bool = False
    # Normalized ATS workplace field when the ATS has one: "remote" | "hybrid" | "onsite".
    workplace_type: str | None = None
    # Set by location.classify_location_type: dmv_onsite | dmv_hybrid | remote_us | unknown
    # (bare "Washington") | other (only when drop_out_of_area is off).
    location_type: str | None = None
    # Set by tagging.py, e.g. ["clearance", "public_sector"].
    tags: list[str] = field(default_factory=list)
    department: str | None = None
    description_html: str | None = None
    description_available: bool = True
    compensation: str | None = None
    posted_at: str | None = None
    # Maintained by writer.py across runs.
    first_seen: str | None = None
    last_seen: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

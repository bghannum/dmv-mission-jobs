"""Load and validate the YAML config into typed objects. Fails loudly on bad config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .location import LocationRules
from .models import INDUSTRY_VOCAB, Company, RoleUmbrella
from .tagging import TagRule

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class ConfigError(ValueError):
    """Raised when the config is structurally invalid."""


@dataclass
class Settings:
    timeout_seconds: float
    max_retries: int
    backoff_seconds: float
    politeness_delay_seconds: float
    user_agent: str
    getro_enabled: bool
    jobs_path: str
    meta_path: str
    stale_after_days: int
    max_shrink_fraction: float
    drop_out_of_area: bool


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Missing config file: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ConfigError(f"Expected a mapping at the top of {path.name}")
    return data


def load_companies(path: Path | None = None, *, valid_ats: set[str] | None = None) -> list[Company]:
    path = path or CONFIG_DIR / "companies.yaml"
    data = _load_yaml(path)
    raw = data.get("companies")
    if not isinstance(raw, list) or not raw:
        raise ConfigError("companies.yaml must contain a non-empty 'companies' list")

    companies: list[Company] = []
    seen: set[tuple[str, str]] = set()
    for i, entry in enumerate(raw):
        where = f"companies[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where} must be a mapping")
        for required in ("name", "ats", "identifier", "industry"):
            if not entry.get(required):
                raise ConfigError(f"{where} is missing required field '{required}'")

        ats = str(entry["ats"]).strip().lower()
        if valid_ats is not None and ats not in valid_ats:
            raise ConfigError(f"{where} '{entry['name']}' has unknown ats '{ats}'")

        industry = entry["industry"]
        if isinstance(industry, str):
            industry = [industry]
        if not isinstance(industry, list) or not industry:
            raise ConfigError(f"{where} 'industry' must be a non-empty list")
        bad = [x for x in industry if x not in INDUSTRY_VOCAB]
        if bad:
            raise ConfigError(
                f"{where} has unknown industry {bad}; allowed: {sorted(INDUSTRY_VOCAB)}"
            )

        if "priority" in entry:
            # Removed 2026-11-22: the tiers were inherited from upstream and pinned a few
            # companies to the top of the board. The site now orders jobs itself.
            raise ConfigError(f"{where} has 'priority', which is no longer supported")

        key = (ats, str(entry["identifier"]).strip().lower())
        if key in seen:
            raise ConfigError(f"{where} duplicates an earlier company ({key[0]}:{key[1]})")
        seen.add(key)

        companies.append(
            Company(
                name=str(entry["name"]).strip(),
                ats=ats,
                identifier=str(entry["identifier"]).strip(),
                industry=list(industry),
                homepage=entry.get("homepage"),
            )
        )
    return companies


def load_roles(path: Path | None = None) -> tuple[list[RoleUmbrella], dict]:
    path = path or CONFIG_DIR / "roles.yaml"
    data = _load_yaml(path)
    raw_umbrellas = data.get("umbrellas")
    if not isinstance(raw_umbrellas, dict) or not raw_umbrellas:
        raise ConfigError("roles.yaml must contain a non-empty 'umbrellas' mapping")

    umbrellas: list[RoleUmbrella] = []
    for key, u in raw_umbrellas.items():
        if not isinstance(u, dict):
            raise ConfigError(f"umbrella '{key}' must be a mapping")
        umbrellas.append(
            RoleUmbrella(
                key=key,
                label=u.get("label", key),
                roles=u.get("roles") or {},
            )
        )

    levels = data.get("levels")
    if not isinstance(levels, dict) or "detection" not in levels or "order" not in levels:
        raise ConfigError("roles.yaml must contain a 'levels' block with 'order' and 'detection'")
    return umbrellas, levels


def load_settings(path: Path | None = None) -> Settings:
    path = path or CONFIG_DIR / "settings.yaml"
    data = _load_yaml(path)
    http = data.get("http", {})
    output = data.get("output", {})
    filters = data.get("filters", {}) or {}
    getro = (data.get("adapters", {}) or {}).get("getro", {}) or {}
    return Settings(
        timeout_seconds=float(http.get("timeout_seconds", 15)),
        max_retries=int(http.get("max_retries", 2)),
        backoff_seconds=float(http.get("backoff_seconds", 2.0)),
        politeness_delay_seconds=float(http.get("politeness_delay_seconds", 1.0)),
        user_agent=str(http.get("user_agent", "brians-job-bot/1.0")),
        getro_enabled=bool(getro.get("enabled", False)),
        jobs_path=str(output.get("jobs_path", "data/jobs.json")),
        meta_path=str(output.get("meta_path", "data/meta.json")),
        stale_after_days=int(output.get("stale_after_days", 30)),
        max_shrink_fraction=float(output.get("max_shrink_fraction", 0.8)),
        drop_out_of_area=bool(filters.get("drop_out_of_area", True)),
    )


def _str_list(value, where: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ConfigError(f"{where} must be a list of non-empty strings")
    return [v.strip().lower() for v in value]


_STATE_LONG = {", va": ", virginia", ", md": ", maryland"}


def load_locations(path: Path | None = None) -> LocationRules:
    """Load the DMV metro definition plus remote/hybrid keywords."""
    path = path or CONFIG_DIR / "locations.yaml"
    data = _load_yaml(path)
    dmv = ((data.get("metros") or {}).get("dmv")) or {}
    match = _str_list(dmv.get("match"), "locations.yaml metros.dmv.match")
    if not match:
        raise ConfigError("locations.yaml must define a non-empty metros.dmv.match list")
    expanded = list(match)
    for m in match:  # "laurel, md" also matches "laurel, maryland"
        for short, long in _STATE_LONG.items():
            if m.endswith(short):
                expanded.append(m[: -len(short)] + long)
    remote = _str_list(data.get("remote_keywords"), "locations.yaml remote_keywords")
    hybrid = _str_list(data.get("hybrid_keywords"), "locations.yaml hybrid_keywords")
    if not remote or not hybrid:
        raise ConfigError("locations.yaml needs non-empty remote_keywords and hybrid_keywords")
    return LocationRules(
        dmv_match=tuple(expanded),
        dmv_exclude=tuple(_str_list(dmv.get("exclude"), "locations.yaml metros.dmv.exclude")),
        remote_keywords=tuple(remote),
        hybrid_keywords=tuple(hybrid),
    )


def load_tags(path: Path | None = None) -> list[TagRule]:
    """Load tag rules (clearance, public_sector, ...)."""
    path = path or CONFIG_DIR / "tags.yaml"
    data = _load_yaml(path)
    raw = data.get("tags")
    if not isinstance(raw, dict) or not raw:
        raise ConfigError("tags.yaml must contain a non-empty 'tags' mapping")
    rules: list[TagRule] = []
    for key, t in raw.items():
        where = f"tags.yaml '{key}'"
        if not isinstance(t, dict):
            raise ConfigError(f"{where} must be a mapping")
        industries = _str_list(t.get("industries"), f"{where} industries")
        bad = [i for i in industries if i not in INDUSTRY_VOCAB]
        if bad:
            raise ConfigError(f"{where} has unknown industries {bad}")
        keywords = _str_list(t.get("keywords"), f"{where} keywords")
        if not keywords:
            raise ConfigError(f"{where} needs at least one keyword")
        rules.append(
            TagRule(
                key=key,
                label=str(t.get("label", key)),
                keywords=tuple(keywords),
                description_keywords=tuple(
                    _str_list(t.get("description_keywords"), f"{where} description_keywords")
                ),
                exclude=tuple(_str_list(t.get("exclude"), f"{where} exclude")),
                industries=frozenset(industries),
                description_min_hits=int(t.get("description_min_hits", 1)),
            )
        )
    return rules

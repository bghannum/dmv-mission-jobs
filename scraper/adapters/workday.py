"""Workday adapter. Identifier: "{tenant}/{wdN}/{site}", e.g. "leidos/wd5/External".

Search: POST https://{tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
Detail: GET  .../wday/cxs/{tenant}/{site}{externalPath}

Undocumented; see docs/adapters/workday.md for the response shapes, limits and why the
adapter works the way it does. In short: filter server-side to DMV and US-remote location
facets, list 20 at a time, and fetch details (description, full location list) only for
jobs whose title matched a category, caching them between runs.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.robotparser import RobotFileParser

import requests

from ..location import _STATE_ABBREV, _STATE_NAMES, OTHER, classify_location_type
from ..models import Company, Job
from .base import ATSAdapter, join_locations, normalize_workplace

log = logging.getLogger("scraper")

PAGE_SIZE = 20  # Workday rejects larger pages with HTTP 400
RESULT_CAP = 2000  # some tenants never report (or page past) more than this per query
MAX_PAGES = 100  # per query; a safety cap
CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "workday"
CACHE_DAYS = 14
_CA_PROVINCES = {
    "alberta", "british columbia", "manitoba", "new brunswick", "newfoundland", "nova scotia",
    "ontario", "prince edward island", "quebec", "saskatchewan",
}
_IDENT_RE = re.compile(r"^([A-Za-z0-9_-]+)/(wd\d+)/([A-Za-z0-9_-]+)$")


class RobotsDisallowed(RuntimeError):
    """The tenant's robots.txt disallows the career site; we don't scrape it."""


def parse_identifier(identifier: str) -> tuple[str, str, str]:
    m = _IDENT_RE.match(identifier.strip())
    if not m:
        raise ValueError(f"Workday identifier must be tenant/wdN/site, got '{identifier}'")
    return m.group(1), m.group(2), m.group(3)


def normalize_location(descriptor: str | None) -> str | None:
    """Rewrite a tenant's location name into "City, ST" style for scraper/location.py.

    Handles the formats in docs/adapters/workday.md: leading site numbers ("0411 Vienna VA"),
    GDIT ("USA VA Reston - 12310 Sunrise Valley Dr (VAC074)"), Northrop Grumman
    ("United States-Virginia-McLean"), CrowdStrike ("USA - Remote, VA") and Salesforce
    ("Virginia - Herndon"), Amentum ("US-VA-Reston") and Guidehouse ("US - VA, McLean").
    "Home Office" (telework from that place) gets "(remote)".
    Anything else passes through unchanged.
    """
    if not descriptor:
        return None
    s = re.sub(r"\s+", " ", descriptor).strip()
    s = re.sub(r"^\d+\s+", "", s)  # Leidos site number
    s = re.sub(r"\s*\([A-Z0-9]+\)$", "", s)  # GDIT site code
    home = bool(re.search(r"\sHome Office$", s))
    s = re.sub(r"\s+Home Office$", "", s)
    out = _rewrite(s)
    return f"{out} (remote)" if home else out


def _rewrite(s: str) -> str:
    m = re.match(r"^USA ([A-Z]{2})$", s)  # GDIT state only (after "Home Office" is cut)
    if m:
        return m.group(1)
    m = re.match(r"^USA ([A-Z]{2}) (.+?)(?: - .*)?$", s)  # GDIT
    if m:
        return f"{m.group(2)}, {m.group(1)}"
    m = re.match(r"^United States-([^-]+)-(.+)$", s)  # Northrop Grumman
    if m:
        state, city = m.group(1), m.group(2)
        city = "" if city == "Unknown City" else city
        return f"{city}, {state}" if city else state
    if s == "United States-Remote":
        return "Remote, US"
    m = re.match(r"^US-([A-Z]{2})-(.+)$", s)  # Amentum: "US-VA-Reston"
    if m:
        return f"{m.group(2)}, {m.group(1)}"
    if s in ("US-Remote", "US - Remote"):
        return "Remote, US"
    m = re.match(r"^US - ([A-Z]{2}), (.+)$", s)  # Guidehouse: "US - VA, McLean"
    if m:
        return f"{m.group(2)}, {m.group(1)}"
    m = re.match(r"^USA - (.+)$", s)  # CrowdStrike
    if m:
        rest = m.group(1)
        return "Remote, US" if rest == "Remote" else rest
    m = re.match(r"^([A-Za-z .]+?) - (.+)$", s)  # Salesforce: "<state or province> - <place>"
    if m and m.group(1).strip().lower() in _CA_PROVINCES:
        return f"{m.group(2)}, {m.group(1)}, Canada"
    if m and m.group(1).strip().lower() in _STATE_NAMES:
        return f"{m.group(2)}, {m.group(1)}"
    m = re.match(r"^([A-Za-z .'-]+?) ([A-Z]{2})$", s)  # "Vienna VA" -> "Vienna, VA"
    if m and "," not in s and m.group(2) in _STATE_ABBREV:
        return f"{m.group(1)}, {m.group(2)}"
    return s


def posted_from_relative(text: str | None, today: date) -> str | None:
    """"Posted Today" / "Posted Yesterday" / "Posted 3 Days Ago" -> ISO date. "30+" -> None."""
    low = (text or "").lower()
    if "today" in low:
        return today.isoformat()
    if "yesterday" in low:
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+) days? ago", low)
    if m and "+" not in low:
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    return None


def _leaf_facets(facets: list[dict]):
    """Yield (facetParameter, value) for every selectable value, flattening groups."""
    for f in facets or []:
        for v in f.get("values", []):
            if "values" in v:
                yield from _leaf_facets([v])
            else:
                yield f.get("facetParameter"), v


def in_area_location_facets(facets: list[dict], rules) -> tuple[str | None, list[str]]:
    """The location facet parameter and the value ids that are in the DMV or US remote."""
    by_param: dict[str, list[str]] = {}
    for param, value in _leaf_facets(facets):
        if not param or "location" not in param.lower() or "country" in param.lower():
            continue
        loc = normalize_location(value.get("descriptor"))
        kind = classify_location_type(loc, False, rules, None, "")
        if kind and kind != OTHER:
            by_param.setdefault(param, []).append(value["id"])
    if not by_param:
        return None, []
    param = max(by_param, key=lambda k: len(by_param[k]))
    return param, by_param[param]


class WorkdayAdapter(ATSAdapter):
    key = "workday"

    def __init__(self, client=None, *, location_rules=None, cache_dir: Path | None = CACHE_DIR,
                 today: date | None = None):
        super().__init__(client)
        self._rules = location_rules
        self.cache_dir = cache_dir
        self.today = today or date.today()
        self._cache: dict[str, dict] = {}
        self._cache_path: Path | None = None
        self._seen_paths: set[str] = set()
        self._api = ""
        self._site_url = ""

    # --- helpers -----------------------------------------------------------------------

    def _location_rules(self):
        if self._rules is None:
            from ..config_loader import load_locations

            self._rules = load_locations()
        return self._rules

    def _check_robots(self, host: str, site: str) -> None:
        try:
            text = self.client.get_text(f"{host}/robots.txt")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return  # no robots.txt: allowed
            raise
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        ua = self.client.session.headers.get("User-Agent", "*")
        for path in (f"{host}/{site}/", f"{self._api}/jobs"):
            if not parser.can_fetch(ua, path):
                raise RobotsDisallowed(f"robots.txt disallows {path}")

    def _first_page(self, applied: dict) -> dict:
        body = {"appliedFacets": applied, "limit": PAGE_SIZE, "offset": 0, "searchText": ""}
        return self.client.post_json(f"{self._api}/jobs", body)

    def _rest(self, applied: dict, first: dict) -> list[dict]:
        """Every posting for a filter, given its first page (total is only on page one)."""
        total = int(first.get("total") or 0)
        postings = list(first.get("jobPostings") or [])
        offset, pages = PAGE_SIZE, 1
        while offset < min(total, RESULT_CAP) and pages < MAX_PAGES:
            body = {"appliedFacets": applied, "limit": PAGE_SIZE, "offset": offset,
                    "searchText": ""}
            batch = self.client.post_json(f"{self._api}/jobs", body).get("jobPostings") or []
            if not batch:
                break
            postings.extend(batch)
            offset += PAGE_SIZE
            pages += 1
        return postings

    def _search_locations(self, param: str, ids: list[str]) -> list[dict]:
        """Search a set of location ids, halving the set while a query hits the result cap."""
        applied = {param: ids}
        first = self._first_page(applied)
        if int(first.get("total") or 0) >= RESULT_CAP and len(ids) > 1:
            mid = len(ids) // 2
            return self._search_locations(param, ids[:mid]) + self._search_locations(
                param, ids[mid:]
            )
        return self._rest(applied, first)

    def _load_cache(self, tenant: str, site: str) -> None:
        if not self.cache_dir:
            return
        self._cache_path = self.cache_dir / f"{tenant}_{site}.json"
        try:
            self._cache = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._cache = {}

    # --- ATSAdapter ----------------------------------------------------------------------

    def fetch(self, company: Company) -> list[dict]:
        tenant, wd, site = parse_identifier(company.identifier)
        host = f"https://{tenant}.{wd}.myworkdayjobs.com"
        self._api = f"{host}/wday/cxs/{tenant}/{site}"
        self._site_url = f"{host}/{site}"
        self._check_robots(host, site)
        self._load_cache(tenant, site)

        first = self._first_page({})
        param, ids = in_area_location_facets(first.get("facets"), self._location_rules())
        if param:
            postings = self._search_locations(param, ids)
        else:
            log.info("%s: no location facet; listing every posting", company.name)
            postings = self._rest({}, first)
        unique: dict[str, dict] = {}
        for p in postings:
            path = p.get("externalPath")
            if path and path not in unique:
                unique[path] = p
        self._seen_paths = set(unique)
        return list(unique.values())

    def normalize(self, raw: list[dict], company: Company) -> list[Job]:
        jobs: list[Job] = []
        for p in raw:
            path = p["externalPath"]
            text = p.get("locationsText") or ""
            multi = bool(re.match(r"^\d+ Locations$", text))
            jobs.append(
                Job(
                    id=f"workday:{company.identifier}:{path.rsplit('/', 1)[-1]}",
                    title=(p.get("title") or "").strip(),
                    company=company.name,
                    industries=list(company.industry),
                    url=f"{self._site_url}{path}",
                    source_ats="workday",
                    location=None if multi else normalize_location(text),
                    description_available=False,
                    posted_at=posted_from_relative(p.get("postedOn"), self.today),
                )
            )
        return jobs

    def enrich(self, job: Job) -> Job:
        """Add the description and full location list from the detail endpoint (cached)."""
        path = job.url[len(self._site_url):]
        cached = self._cache.get(path)
        fresh_after = (self.today - timedelta(days=CACHE_DAYS)).isoformat()
        if cached and cached.get("fetched", "") >= fresh_after:
            info = cached["info"]
        else:
            data = self.client.get_json(f"{self._api}{path}")
            full = data.get("jobPostingInfo") or {}
            info = {k: full.get(k) for k in (
                "location", "additionalLocations", "jobDescription", "startDate", "remoteType",
            )}
            self._cache[path] = {"fetched": self.today.isoformat(), "info": info}
        extra = [normalize_location(x) for x in (info.get("additionalLocations") or [])]
        job.location = join_locations(normalize_location(info.get("location")), extra)
        job.workplace_type = normalize_workplace(info.get("remoteType"))
        job.remote = job.workplace_type == "remote"
        job.description_html = info.get("jobDescription")
        job.description_available = bool(job.description_html)
        job.posted_at = info.get("startDate") or job.posted_at
        return job

    def finish(self) -> None:
        """Save the detail cache, keeping only jobs still listed."""
        if not self._cache_path:
            return
        keep = {k: v for k, v in self._cache.items() if k in self._seen_paths}
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(keep), encoding="utf-8")

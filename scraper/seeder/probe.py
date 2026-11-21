"""Find a company's public ATS board by probing likely slugs (PLAN.md, Phase 4, step 3).

Only the three public, documented job-board APIs are probed (Greenhouse, Lever, Ashby).
All three return 404 for a board that doesn't exist. Results are cached on disk so a slug
is never probed twice, and requests are rate-limited per run.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests

PROBE_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}
GREENHOUSE_BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}"
ATS_ORDER = ("greenhouse", "ashby", "lever")

_GENERIC_HANDLES = {
    "company", "home", "jobs", "careers", "about", "share", "sharer", "intent", "in", "school",
    "showcase", "pages", "profile.php", "groups", "channel", "c", "user", "watch",
}
_SUFFIXES = (" inc", " inc.", " llc", " corp", " corporation", " co", " ltd", " technologies",
             " labs", " hq", " ai", " app", " io")


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _slugs_from_name(name: str) -> list[str]:
    base = re.sub(r"\(.*?\)", " ", _ascii(name)).strip()
    forms = {base}
    for suf in _SUFFIXES:
        if base.endswith(suf):
            forms.add(base[: -len(suf)].strip())
    out = []
    for f in forms:
        words = re.findall(r"[a-z0-9]+", f)
        if not words:
            continue
        out += ["".join(words), "-".join(words)]
    return out


def _domain_label(website: str | None) -> str | None:
    if not website:
        return None
    host = urlparse(website if "//" in website else f"https://{website}").hostname or ""
    host = re.sub(r"^(www\d?|careers|jobs)\.", "", host.lower())
    parts = host.split(".")
    if len(parts) < 2:
        return None
    label = parts[-2]
    # foo.co.uk / foo.com.au
    if label in {"co", "com"} and len(parts) >= 3:
        label = parts[-3]
    return label or None


def _handle(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    segs = [s for s in parsed.path.split("/") if s]
    if not segs:
        return None
    if segs[0] in {"company", "school", "showcase"} and len(segs) > 1:
        cand = segs[1]
    else:
        cand = segs[0]
    cand = cand.lower().lstrip("@")
    if cand in _GENERIC_HANDLES or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,60}", cand):
        return None
    return cand.replace(".", "")


def slug_candidates(name: str, website: str | None = None, social_urls=()) -> list[str]:
    """Likely ATS board slugs, strongest first (domain, social handles, then name forms)."""
    out: list[str] = []
    label = _domain_label(website)
    if label:
        out.append(label)
    for url in social_urls:
        h = _handle(url)
        if h:
            out.append(h)
    out += _slugs_from_name(name)
    seen: set[str] = set()
    result = []
    for s in out:
        s = s.strip("-_")
        if len(s) >= 2 and s not in seen:
            seen.add(s)
            result.append(s)
    return result


def _sample(jobs: list, fields: tuple[str, ...], limit: int = 4000) -> str:
    """A little lowercase job text, used to check a board belongs to the company."""
    parts: list[str] = []
    for job in jobs[:3]:
        if isinstance(job, dict):
            parts += [str(job.get(f) or "") for f in fields]
    text = re.sub(r"<[^>]+>", " ", " ".join(parts))
    return re.sub(r"\s+", " ", text).lower()[:limit]


def verify(hit: dict, name: str, website: str | None) -> bool:
    """Does this board really belong to the company?

    Greenhouse: its board name matches. Ashby/Lever (no name in the API): the job text
    mentions the company name or its web domain. Empty boards can't be verified.
    """
    if hit["ats"] == "greenhouse":
        return bool(hit.get("board_name")) and name_similar(name, hit["board_name"])
    sample = hit.get("sample") or ""
    if not sample:
        return False
    label = _domain_label(website)
    plain_name = re.sub(r"\(.*?\)", " ", _ascii(name)).strip()
    needles = [n for n in {plain_name, label} if n and len(n) >= 3]
    return any(re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", sample)
               for n in needles)


def name_similar(a: str, b: str) -> bool:
    """Loose check that a board's own name matches the company (Greenhouse exposes it)."""
    na = re.sub(r"[^a-z0-9]", "", _ascii(a))
    nb = re.sub(r"[^a-z0-9]", "", _ascii(b))
    if not na or not nb:
        return False
    return na in nb or nb in na or na[:6] == nb[:6]


class Prober:
    """Probe slugs against ATS APIs with an on-disk cache and a fixed delay per request."""

    def __init__(self, *, user_agent: str, cache_path: Path, delay: float = 0.5,
                 timeout: float = 15.0, session: requests.Session | None = None, sleep=time.sleep):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
        self.cache_path = cache_path
        self.delay = delay
        self.timeout = timeout
        self._sleep = sleep
        self.requests_made = 0
        try:
            self.cache: dict = json.loads(cache_path.read_text())
        except (OSError, ValueError):
            self.cache = {}

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=1, sort_keys=True))

    def _get(self, url: str):
        for attempt in range(2):
            self._sleep(self.delay)
            self.requests_made += 1
            try:
                resp = self.session.get(url, timeout=self.timeout)
            except requests.RequestException:
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code >= 500 or resp.status_code == 429:
                self._sleep(5 * (attempt + 1))
                continue
            if resp.ok:
                try:
                    return resp.json()
                except ValueError:
                    return None
            return None
        raise RuntimeError(f"probe failed: {url}")

    def probe(self, ats: str, slug: str) -> dict | None:
        """{"ats", "slug", "jobs", "board_name"} when the board exists, else None."""
        key = f"{ats}:{slug}"
        if key in self.cache:
            return self.cache[key]
        data = self._get(PROBE_URLS[ats].format(slug=slug))
        result = None
        if data is not None:
            if ats == "greenhouse":
                jobs = len(data.get("jobs", [])) if isinstance(data, dict) else 0
                meta = self._get(GREENHOUSE_BOARD_URL.format(slug=slug)) or {}
                result = {"ats": ats, "slug": slug, "jobs": jobs, "board_name": meta.get("name")}
            elif ats == "lever":
                jobs = data if isinstance(data, list) else []
                result = {"ats": ats, "slug": slug, "jobs": len(jobs), "board_name": None,
                          "sample": _sample(jobs, ("descriptionPlain", "additionalPlain"))}
            else:
                jobs = data.get("jobs", []) if isinstance(data, dict) else []
                result = {"ats": ats, "slug": slug, "jobs": len(jobs), "board_name": None,
                          "sample": _sample(jobs, ("descriptionPlain", "descriptionHtml"))}
        self.cache[key] = result
        return result

    def find_board(self, name: str, slugs: list[str], *, website: str | None = None,
                   max_slugs: int = 4) -> dict | None:
        """Best existing board across ATSes for the strongest slugs.

        Every slug is tried on every ATS (one thread per ATS host, each rate-limited), and
        the board with the most jobs wins: some companies have an empty placeholder board
        on one slug and the real one on another (Anduril: `anduril` vs `andurilindustries`).
        A Greenhouse hit must carry a board name similar to the company name, since common
        words ("apex", "nova") are often taken by unrelated companies.
        """
        tried = slugs[:max_slugs]

        def run(ats: str) -> list[dict]:
            hits = []
            for slug in tried:
                hit = self.probe(ats, slug)
                if not hit:
                    continue
                if ats == "greenhouse" and hit.get("board_name") and not name_similar(
                    name, hit["board_name"]
                ):
                    continue
                hits.append(hit)
            return hits

        with ThreadPoolExecutor(max_workers=len(ATS_ORDER)) as pool:
            hits = [h for found in pool.map(run, ATS_ORDER) for h in found]
        if not hits:
            return None
        hits = [{**h, "verified": verify(h, name, website)} for h in hits]
        # Verified boards first, then most jobs, then the stronger slug, then ATS order.
        best = max(hits, key=lambda h: (h["verified"], h["jobs"], -tried.index(h["slug"]),
                                        -ATS_ORDER.index(h["ats"])))
        best.pop("sample", None)
        return best

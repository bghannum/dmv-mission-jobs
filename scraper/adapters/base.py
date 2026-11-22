"""Adapter contract shared by every ATS implementation."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import requests

from ..models import Company, Job


class HTTPClient:
    """Small requests wrapper with a shared UA, timeout, retries, and politeness delay."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float = 15.0,
        max_retries: int = 2,
        backoff: float = 2.0,
        politeness_delay: float = 1.0,
        sleep=time.sleep,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.politeness_delay = politeness_delay
        self._sleep = sleep
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})

    def _request(self, method: str, url: str, parse, **kwargs) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
                resp.raise_for_status()
                data = parse(resp)
                if self.politeness_delay:
                    self._sleep(self.politeness_delay)
                return data
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    self._sleep(self.backoff * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    def get_json(self, url: str, **kwargs) -> Any:
        return self._request("GET", url, lambda r: r.json(), **kwargs)

    def post_json(self, url: str, payload: dict, **kwargs) -> Any:
        return self._request("POST", url, lambda r: r.json(), json=payload, **kwargs)

    def get_text(self, url: str, **kwargs) -> str:
        # The session asks for JSON; some servers answer 406 to that for robots.txt.
        kwargs.setdefault("headers", {"Accept": "text/plain, */*"})
        return self._request("GET", url, lambda r: r.text, **kwargs)


class ATSAdapter(ABC):
    """Fetch raw postings for a company and normalize them to Job objects."""

    key: str = ""

    def __init__(self, client: HTTPClient | None = None):
        self.client = client

    @abstractmethod
    def fetch(self, company: Company) -> list[dict]:
        """Return the raw list of posting dicts from the ATS."""

    @abstractmethod
    def normalize(self, raw: list[dict], company: Company) -> list[Job]:
        """Map raw postings to the common Job schema (no role filtering here)."""

    def run(self, company: Company) -> list[Job]:
        return self.normalize(self.fetch(company), company)

    def enrich(self, job: Job) -> Job:
        """Fill in details the list endpoint lacks. Called only for title-matched jobs,
        before location classification and tagging. Default: nothing to add."""
        return job

    def finish(self) -> None:
        """Called once after a company's jobs are processed (e.g. to save a cache)."""
        return None


def industries_for(company: Company) -> list[str]:
    return list(company.industry)


_WORKPLACE = {
    "remote": "remote", "hybrid": "hybrid",
    "onsite": "onsite", "on-site": "onsite", "on site": "onsite", "in office": "onsite",
}


def normalize_workplace(value) -> str | None:
    """Map an ATS workplace value ("Remote", "OnSite", "on-site", ...) to remote|hybrid|onsite."""
    if not isinstance(value, str):
        return None
    return _WORKPLACE.get(value.strip().lower())


def join_locations(primary, extra) -> str | None:
    """Join a primary location and extra locations into one "A; B; C" string, de-duplicated."""
    parts: list[str] = []
    for loc in [primary, *(extra or [])]:
        if isinstance(loc, dict):
            loc = loc.get("location") or loc.get("name") or loc.get("label")
        if isinstance(loc, str) and loc.strip() and loc.strip() not in parts:
            parts.append(loc.strip())
    return "; ".join(parts) or None

"""Ashby adapter. GET https://api.ashbyhq.com/posting-api/job-board/{id}?includeCompensation=true"""

from __future__ import annotations

from ..models import Company, Job
from .base import ATSAdapter, join_locations, normalize_workplace


def _compensation(posting: dict) -> str | None:
    comp = posting.get("compensation")
    if isinstance(comp, dict):
        summary = comp.get("compensationTierSummary") or comp.get("summaryComponents")
        if isinstance(summary, str):
            return summary
    return None


class AshbyAdapter(ATSAdapter):
    key = "ashby"

    def fetch(self, company: Company) -> list[dict]:
        url = (
            f"https://api.ashbyhq.com/posting-api/job-board/{company.identifier}"
            "?includeCompensation=true"
        )
        data = self.client.get_json(url)
        return data.get("jobs", []) if isinstance(data, dict) else []

    def normalize(self, raw: list[dict], company: Company) -> list[Job]:
        jobs: list[Job] = []
        for p in raw:
            if p.get("isListed") is False:
                continue
            source_id = str(p.get("id") or p.get("jobUrl") or p.get("title", ""))
            workplace = normalize_workplace(p.get("workplaceType"))
            primary = p.get("location") or (p.get("address") or {}).get("postalAddress")
            location = join_locations(primary, p.get("secondaryLocations"))
            jobs.append(
                Job(
                    id=f"ashby:{company.identifier}:{source_id}",
                    title=p.get("title", "").strip(),
                    company=company.name,
                    industries=list(company.industry),
                    url=p.get("applyUrl") or p.get("jobUrl", ""),
                    source_ats="ashby",
                    location=location,
                    # isRemote is also true for Hybrid roles; prefer workplaceType when present.
                    remote=workplace == "remote" if workplace else bool(p.get("isRemote")),
                    workplace_type=workplace,
                    department=p.get("department") or p.get("team"),
                    description_html=p.get("descriptionHtml"),
                    description_available=bool(p.get("descriptionHtml")),
                    compensation=_compensation(p),
                    posted_at=p.get("publishedAt") or p.get("publishedDate"),
                )
            )
        return jobs

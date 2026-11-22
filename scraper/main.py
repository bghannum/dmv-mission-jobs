"""Entry point: load config -> run adapters -> match -> dedup -> write jobs.json."""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from .adapters.base import ATSAdapter, HTTPClient
from .adapters.registry import KNOWN_ATS, get_adapter
from .config_loader import load_companies, load_locations, load_roles, load_settings, load_tags
from .dedup import dedup
from .health import alerts, board_health, load_meta
from .location import OTHER, UNKNOWN, classify_location_type
from .matching import apply_matching
from .models import Company, Job, RoleUmbrella
from .tagging import apply_tags
from .writer import merge_and_write

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("scraper")

ROOT = Path(__file__).resolve().parent.parent


def scrape_company(
    company: Company, client: HTTPClient
) -> tuple[list[Job], dict, ATSAdapter | None]:
    """Fetch + normalize one company. Isolated: never raises on network errors."""
    status = {
        "company": company.name, "ats": company.ats, "identifier": company.identifier,
        "ok": False, "count": 0, "error": None,
    }
    try:
        adapter = get_adapter(company.ats, client)
        jobs = adapter.run(company)
        status["ok"] = True
        status["count"] = len(jobs)
        return jobs, status, adapter
    except Exception as exc:  # noqa: BLE001 - isolation: one company must not fail the run
        log.warning("Fetch failed for %s (%s): %s", company.name, company.ats, exc)
        status["error"] = f"{type(exc).__name__}: {exc}"
        return [], status, None


def filter_jobs(
    raw_jobs: list[Job],
    umbrellas: list[RoleUmbrella],
    levels: dict,
    location_rules,
    tag_rules,
    *,
    drop_out_of_area: bool = True,
    ambiguous: list[dict] | None = None,
    adapter: ATSAdapter | None = None,
) -> tuple[list[Job], int]:
    """Match roles, classify location and tag. Returns (kept jobs, number role-matched).

    Bare-"Washington" jobs are appended to `ambiguous` when a list is given. When an
    adapter is given, its `enrich` runs on each role-matched job first (Workday fetches the
    description and full location list there). A job whose enrich fails is dropped.
    """
    matched = [j for j in (apply_matching(j, umbrellas, levels) for j in raw_jobs) if j]
    if adapter is not None:
        enriched = []
        for job in matched:
            try:
                enriched.append(adapter.enrich(job))
            except Exception as exc:  # noqa: BLE001 - one job must not fail the company
                log.warning("Detail fetch failed for %s: %s", job.url, exc)
        matched = enriched
    kept: list[Job] = []
    for job in matched:
        loc_type = classify_location_type(
            job.location, job.remote, location_rules, job.workplace_type, job.title
        )
        if loc_type is None:
            if drop_out_of_area:
                continue
            loc_type = OTHER
        if loc_type == UNKNOWN and ambiguous is not None:
            ambiguous.append({"company": job.company, "title": job.title, "location": job.location})
        job.location_type = loc_type
        kept.append(apply_tags(job, tag_rules))
    return kept, len(matched)


def taxonomy(umbrellas: list[RoleUmbrella], tag_rules) -> dict:
    """Labels the site uses for its filters (written to meta.json)."""
    return {
        "umbrellas": {
            u.key: {
                "label": u.label,
                "roles": {k: r.get("label", k) for k, r in u.roles.items()},
            }
            for u in umbrellas
        },
        "tags": {t.key: t.label for t in tag_rules},
    }


def _carried_status(company: Company, prior_meta: dict) -> dict:
    """Last recorded status for a board this run doesn't scrape (e.g. Workday in the daily run)."""
    for s in prior_meta.get("adapters", []):
        if s.get("ats") == company.ats and s.get("identifier") == company.identifier:
            return {**s, "carried": True}
    return {
        "company": company.name, "ats": company.ats, "identifier": company.identifier,
        "ok": True, "count": 0, "error": "not run yet", "carried": True,
    }


def run(only_ats: set[str] | None = None) -> int:
    """Scrape and write jobs.json/meta.json.

    only_ats: scrape just these ATSs and carry every other board over from the previous run
    (its jobs, status and ambiguous locations). The daily run leaves out the ATSs in
    settings `local_only_ats` (Workday: its servers refuse GitHub's runners); those run from
    a maintainer's machine with scripts/scrape_workday.py.
    """
    settings = load_settings()
    companies = load_companies(valid_ats=KNOWN_ATS)
    umbrellas, levels = load_roles()
    location_rules = load_locations()
    tag_rules = load_tags()
    prior_meta = load_meta(ROOT / settings.meta_path)
    if only_ats is None:
        only_ats = KNOWN_ATS - settings.local_only_ats
    ambiguous: list[dict] = []

    client = HTTPClient(
        user_agent=settings.user_agent,
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
        backoff=settings.backoff_seconds,
        politeness_delay=settings.politeness_delay_seconds,
    )

    all_matched: list[Job] = []
    adapter_status: list[dict] = []
    # Boards whose prior jobs are kept: failed this run, or not scraped in this run.
    retain_prefixes: set[str] = set()
    carried_names: set[str] = set()

    for company in companies:
        prefix = f"{company.ats}:{company.identifier}:"
        if company.ats not in only_ats:
            adapter_status.append(_carried_status(company, prior_meta))
            retain_prefixes.add(prefix)
            carried_names.add(company.name)
            continue
        if company.ats == "getro" and not settings.getro_enabled:
            log.info("Skipping %s: getro adapter disabled", company.name)
            adapter_status.append(
                {
                    "company": company.name,
                    "ats": "getro",
                    "identifier": company.identifier,
                    "ok": True,
                    "count": 0,
                    "error": "disabled",
                }
            )
            continue

        raw_jobs, status, adapter = scrape_company(company, client)
        if not status["ok"]:
            retain_prefixes.add(prefix)
        kept, n_matched = filter_jobs(
            raw_jobs, umbrellas, levels, location_rules, tag_rules,
            drop_out_of_area=settings.drop_out_of_area, ambiguous=ambiguous, adapter=adapter,
        )
        if adapter is not None:
            adapter.finish()
        status["matched"] = n_matched
        status["dropped_out_of_area"] = n_matched - len(kept)
        adapter_status.append(status)
        all_matched.extend(kept)
        log.info("%s: %d fetched, %d kept", company.name, status["count"], len(kept))

    deduped = dedup(all_matched)
    log.info("Total: %d kept, %d after dedup", len(all_matched), len(deduped))

    ambiguous += [a for a in prior_meta.get("ambiguous_locations", [])
                  if a.get("company") in carried_names]
    now = datetime.now(timezone.utc).isoformat()
    last_run_by_ats = dict(prior_meta.get("last_run_by_ats") or {})
    for ats in only_ats:
        if any(c.ats == ats for c in companies):
            last_run_by_ats[ats] = now

    meta = {
        "companies": len(companies),
        "adapters": adapter_status,
        "any_failures": any(not s["ok"] for s in adapter_status),
        "drop_out_of_area": settings.drop_out_of_area,
        "dropped_out_of_area": sum(s.get("dropped_out_of_area", 0) for s in adapter_status),
        # Bare "Washington" locations (DC or the state?). Reviewed at the end of Phase 2.
        "ambiguous_locations": ambiguous,
        "taxonomy": taxonomy(umbrellas, tag_rules),
        # Empty and failing boards, with the day each problem started (scraper/health.py).
        "board_health": board_health(adapter_status, prior_meta, date.today().isoformat()),
        # When each ATS's boards were last scraped. The site shows Workday's, which is
        # refreshed from a maintainer's machine, not daily (scripts/scrape_workday.py).
        "last_run_by_ats": last_run_by_ats,
        "local_only_ats": sorted(settings.local_only_ats),
    }
    for line in alerts(meta["board_health"]):
        log.warning("Board health: %s", line)
    result = merge_and_write(
        deduped,
        meta,
        jobs_path=ROOT / settings.jobs_path,
        meta_path=ROOT / settings.meta_path,
        stale_after_days=settings.stale_after_days,
        max_shrink_fraction=settings.max_shrink_fraction,
        retain_prefixes=retain_prefixes,
    )

    if result.get("shrink_blocked"):
        log.error(
            "Write blocked: fresh count %d shrank too far below prior %d; jobs.json NOT updated",
            result["fresh_job_count"],
            result["prior_job_count"],
        )
        return 1
    log.info("Wrote %d jobs to %s", result["total_job_count"], settings.jobs_path)
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()

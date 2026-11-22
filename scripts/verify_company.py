"""Check a company's job board before adding it to config/companies.yaml.

    python scripts/verify_company.py greenhouse scaleai --name "Scale AI"
    python scripts/verify_company.py --find "Scale AI" --website https://scale.com
    python scripts/verify_company.py workday leidos/wd5/External --name Leidos

The first form fetches a known board. The second probes Greenhouse, Ashby and Lever for the
company's board first (scraper/seeder/probe.py), then fetches it. Either way it prints the
job count, how many jobs pass the role and location filters (the same code the daily scrape
runs), sample titles, and a companies.yaml entry to paste. Nothing is written to config.

Exit status: 0 when a board was found and fetched, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scraper.adapters.base import HTTPClient  # noqa: E402
from scraper.adapters.registry import KNOWN_ATS, get_adapter  # noqa: E402
from scraper.config_loader import (  # noqa: E402
    load_companies,
    load_locations,
    load_roles,
    load_settings,
    load_tags,
)
from scraper.main import filter_jobs  # noqa: E402
from scraper.models import INDUSTRY_VOCAB, Company, Job  # noqa: E402
from scraper.seeder.probe import Prober, slug_candidates  # noqa: E402

CACHE = ROOT / ".cache" / "seeder" / "probe_cache.json"


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def already_listed(companies: list[Company], name: str, ats: str, slug: str) -> str | None:
    """Name of the existing entry with the same name or the same board, if any."""
    for c in companies:
        if _norm(c.name) == _norm(name) or (c.ats, c.identifier.lower()) == (ats, slug.lower()):
            return c.name
    return None


def summarize(raw: list[Job], kept: list[Job], n_matched: int) -> dict:
    return {
        "fetched": len(raw),
        "role_matched": n_matched,
        "kept": len(kept),
        "by_location": dict(Counter(j.location_type for j in kept).most_common()),
        "by_category": dict(Counter(u for j in kept for u in j.umbrellas).most_common()),
    }


def yaml_entry(name: str, ats: str, slug: str, industry: list[str],
               homepage: str | None = None) -> str:
    q = json.dumps  # a JSON string is a valid YAML scalar
    lines = [f"  - name: {q(name)}", f"    ats: {ats}", f"    identifier: {q(slug)}",
             f"    industry: [{', '.join(industry) or 'TODO'}]"]
    if homepage:
        lines.append(f"    homepage: {q(homepage)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ats", nargs="?", help=f"one of: {', '.join(sorted(KNOWN_ATS))}")
    ap.add_argument("slug", nargs="?", help="board slug/token for that ATS")
    ap.add_argument("--find", metavar="NAME", help="probe for this company's board first")
    ap.add_argument("--name", help="company name (defaults to --find or the slug)")
    ap.add_argument("--website", help="company homepage; helps --find pick and confirm a board")
    ap.add_argument("--slug", dest="extra_slugs", action="append", default=[],
                    help="extra slug to try with --find (repeatable)")
    ap.add_argument("--industry", default="",
                    help="comma-separated INDUSTRY_VOCAB values; deftech tags every job "
                         "Public sector")
    ap.add_argument("--samples", type=int, default=15, help="sample titles to show")
    args = ap.parse_args(argv)

    if not args.find and not (args.ats and args.slug):
        ap.error("give <ats> <slug>, or --find NAME")
    industry = [s.strip() for s in args.industry.split(",") if s.strip()]
    bad = [s for s in industry if s not in INDUSTRY_VOCAB]
    if bad:
        ap.error(f"unknown industry {bad}; choose from {sorted(INDUSTRY_VOCAB)}")

    settings = load_settings()
    name = args.name or args.find or args.slug
    ats, slug = (args.ats or "").lower(), args.slug

    if args.find:
        prober = Prober(user_agent=settings.user_agent, cache_path=CACHE)
        slugs = list(dict.fromkeys(args.extra_slugs + slug_candidates(name, args.website)))
        try:
            hit = prober.find_board(name, slugs, website=args.website, max_slugs=6)
        finally:
            prober.save()
        if not hit:
            print(f"{name}: no Greenhouse, Ashby or Lever board found (tried {slugs[:6]}).")
            print("Check the careers page. Rippling or Gem: rerun with <ats> <slug>. "
                  "Anything else: add it to config/needs_adapter.yaml.")
            return 1
        ats, slug = hit["ats"], hit["slug"]
        mark = "confirmed" if hit["verified"] else "NOT confirmed: check it's the right company"
        print(f"{name}: {ats} board '{slug}' ({hit['jobs']} jobs; {mark})")
    elif ats not in KNOWN_ATS:
        ap.error(f"unknown ats '{ats}'; choose from {sorted(KNOWN_ATS)}")

    existing = already_listed(load_companies(), name, ats, slug)
    if existing:
        print(f"Note: already on the board as '{existing}'.")

    company = Company(name=name, ats=ats, identifier=slug, industry=industry or ["saas"])
    client = HTTPClient(user_agent=settings.user_agent, timeout=settings.timeout_seconds,
                        max_retries=settings.max_retries, backoff=settings.backoff_seconds,
                        politeness_delay=settings.politeness_delay_seconds)
    try:
        adapter = get_adapter(ats, client)
        raw = adapter.run(company)
    except Exception as exc:  # noqa: BLE001 - report and exit, like the scraper does
        print(f"Fetch failed for {ats}:{slug}: {type(exc).__name__}: {exc}")
        return 1

    umbrellas, levels = load_roles()
    kept, n_matched = filter_jobs(raw, umbrellas, levels, load_locations(), load_tags(),
                                  drop_out_of_area=True, adapter=adapter)
    adapter.finish()
    s = summarize(raw, kept, n_matched)
    print(f"{s['fetched']} jobs fetched, {s['role_matched']} match a target role, "
          f"{s['kept']} also in the DMV or US remote")
    if kept:
        print("  by location:", ", ".join(f"{k} {v}" for k, v in s["by_location"].items()))
        print("  by category:", ", ".join(f"{k} {v}" for k, v in s["by_category"].items()))
        if args.samples:
            print("Sample kept titles:")
        for j in kept[: args.samples]:
            print(f"  - {j.title}  [{j.location_type}; {j.location or 'no location'}]")
    elif raw and args.samples:
        print("Sample fetched titles (none kept):")
        for j in raw[: args.samples]:
            print(f"  - {j.title}  [{j.location or 'no location'}]")
    print("\ncompanies.yaml entry:")
    print(yaml_entry(name, ats, slug, industry, args.website))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

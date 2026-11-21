"""Add a16z portfolio companies to the board.

    python scripts/seed_a16z.py            # discover + probe, write a report (no config changes)
    python scripts/seed_a16z.py --apply    # also append found companies to companies.yaml
                                           # and unfound ones to needs_adapter.yaml

Steps: read a16z.com/portfolio/ once, skip acquired companies and ones already on the
board, probe Greenhouse/Ashby/Lever for each remaining company's board, and suggest
industries from a16z's description. See docs/seed_sources.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scraper.config_loader import load_companies, load_settings  # noqa: E402
from scraper.seeder.a16z import PORTFOLIO_URL, SECTOR_PAGES, parse_portfolio, parse_sector_ids  # noqa: E402
from scraper.seeder.industry import suggest_industries  # noqa: E402
from scraper.seeder.probe import Prober, slug_candidates  # noqa: E402

CACHE = ROOT / ".cache" / "seeder"
COMPANIES = ROOT / "config" / "companies.yaml"
NEEDS_ADAPTER = ROOT / "config" / "needs_adapter.yaml"
CANDIDATES = ROOT / "config" / "candidates.yaml"


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _yaml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)  # a JSON string is a valid YAML scalar


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--html", type=Path, help="use a saved copy of the portfolio page")
    ap.add_argument("--limit", type=int, default=0, help="only the first N companies (testing)")
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between requests per ATS")
    args = ap.parse_args()

    settings = load_settings()
    pages = CACHE / "pages"
    pages.mkdir(parents=True, exist_ok=True)

    def page(name: str, url: str) -> str:
        """Fetch an a16z page once and keep a copy (reruns don't refetch)."""
        path = pages / f"{name}.html"
        if path.exists():
            return path.read_text(errors="ignore")
        resp = requests.get(url, headers={"User-Agent": settings.user_agent}, timeout=60)
        resp.raise_for_status()
        path.write_text(resp.text)
        return resp.text

    html = args.html.read_text(errors="ignore") if args.html else page("portfolio", PORTFOLIO_URL)
    portfolio = parse_portfolio(html)
    sectors: dict[str, list[str]] = {}
    for sector, url in SECTOR_PAGES.items():
        for cid in parse_sector_ids(page(sector, url)):
            sectors.setdefault(cid, []).append(sector)
    print(f"sectors known for {sum(c['id'] in sectors for c in portfolio)} companies")
    print(f"a16z portfolio: {len(portfolio)} companies, "
          f"{sum(c['acquired'] for c in portfolio)} acquired (skipped)")

    existing = load_companies()
    existing_keys = {(c.ats, c.identifier.lower()) for c in existing}
    existing_names = {_norm(c.name) for c in existing}

    todo = [c for c in portfolio if not c["acquired"]]
    if args.limit:
        todo = todo[: args.limit]

    prober = Prober(user_agent=settings.user_agent, cache_path=CACHE / "probe_cache.json",
                    delay=args.delay)
    found, unverified, missing, already = [], [], [], []
    taken: set[tuple[str, str]] = set(existing_keys)
    try:
        for i, co in enumerate(todo, 1):
            if _norm(co["name"]) in existing_names:
                already.append(co["name"])
                continue
            slugs = slug_candidates(co["name"], co["website"], co["socials"])
            hit = prober.find_board(co["name"], slugs, website=co["website"])
            if hit and (hit["ats"], hit["slug"].lower()) in existing_keys:
                already.append(co["name"])
            elif hit and (hit["ats"], hit["slug"].lower()) not in taken:
                taken.add((hit["ats"], hit["slug"].lower()))
                (found if hit["verified"] else unverified).append({**co, **hit,
                              "sectors": sectors.get(co["id"], []),
                              "industry": suggest_industries(co["name"], co["overview"],
                                                             sectors.get(co["id"], []))})
            else:
                missing.append({**co, "tried": slugs[:4]})
            if i % 25 == 0:
                prober.save()
                print(f"  {i}/{len(todo)}  found={len(found)} missing={len(missing)} "
                      f"requests={prober.requests_made}", flush=True)
    finally:
        prober.save()

    report = {"date": date.today().isoformat(), "found": found, "unverified": unverified,
              "missing": missing, "already_on_board": already}
    (CACHE / "a16z_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"found {len(found)} boards ({sum(f['jobs'] > 0 for f in found)} with open jobs), "
          f"{len(unverified)} unverified, {len(missing)} not on Greenhouse/Lever/Ashby, "
          f"{len(already)} already on the board; "
          f"{prober.requests_made} requests")

    if args.apply:
        today = date.today().isoformat()
        lines = [f"\n  # --- a16z portfolio (scripts/seed_a16z.py, {today}) ---\n"
                 "  # Industries are suggested from a16z's description; review and correct.\n"]
        for f in sorted(found, key=lambda f: f["name"].lower()):
            lines.append(f"  - name: {_yaml_str(f['name'])}\n    ats: {f['ats']}\n"
                         f"    identifier: {_yaml_str(f['slug'])}\n"
                         f"    industry: [{', '.join(f['industry'])}]\n")
            if f.get("website"):
                lines.append(f"    homepage: {_yaml_str(f['website'])}\n")
        with COMPANIES.open("a", encoding="utf-8") as fh:
            fh.writelines(lines)

        data = {}
        if NEEDS_ADAPTER.exists():
            data = yaml.safe_load(NEEDS_ADAPTER.read_text()) or {}
        entries = {e["name"]: e for e in data.get("companies", [])}
        for m in missing:
            entries.setdefault(m["name"], {"name": m["name"], "homepage": m["website"],
                                           "source": "a16z", "ats": "unknown",
                                           "note": "no Greenhouse/Lever/Ashby board found"})
        header = ("# Relevant companies whose jobs we can't fetch yet: their careers site is on\n"
                  "# an unsupported ATS (e.g. Workday) or a custom site, or no board was found.\n"
                  "# Not scraped. See PLAN.md Phases 5-6.\n")
        NEEDS_ADAPTER.write_text(header + yaml.safe_dump(
            {"companies": sorted(entries.values(), key=lambda e: e["name"].lower())},
            sort_keys=False, allow_unicode=True))
        cands = [{"name": u["name"], "ats": u["ats"], "identifier": u["slug"],
                  "industry": u["industry"], "homepage": u["website"], "source": "a16z",
                  "open_jobs": u["jobs"],
                  "why": "board found but couldn't confirm it belongs to this company"}
                 for u in sorted(unverified, key=lambda u: u["name"].lower())]
        CANDIDATES.write_text(
            "# Seeder finds awaiting review. NOT scraped. To approve, move an entry into\n"
            "# companies.yaml (drop source/open_jobs/why); to decline, move it to rejected.yaml.\n"
            + yaml.safe_dump({"companies": cands}, sort_keys=False, allow_unicode=True))
        print(f"appended {len(found)} companies to {COMPANIES.name}; {len(unverified)} to "
              f"{CANDIDATES.name}; {len(missing)} to {NEEDS_ADAPTER.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Board health: spot job boards that fail or go silent.

A board that moves to another ATS usually leaves the old one up and empty, so the scrape
"succeeds" with 0 jobs (Shield AI's Lever board did this in 2026-11). This module records
each empty or failing board in meta.json with the date the problem started, carried over
from the previous meta.json, and flags the ones that are new today.

`python -m scraper.health data/meta.json` prints a report (and GitHub annotations and a
step summary when run in Actions) and exits 1 if any board newly broke today, so the
scheduled workflow fails once per event and GitHub sends an email.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _key(status: dict) -> str:
    return f"{status.get('ats')}:{status.get('identifier') or status.get('company')}"


def load_meta(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def board_health(adapter_status: list[dict], prior_meta: dict, today: str) -> dict:
    """Empty and failing boards, each with `since` (first day seen) and `new` (since today).

    Empty boards also carry `had_jobs`: the board returned jobs before going empty. A board
    that has never had jobs (a small company not hiring) is listed but never alerted on.
    """
    prior_health = prior_meta.get("board_health") or {}
    prior_empty = {_key(e): e for e in prior_health.get("empty", [])}
    prior_failing = {_key(e): e for e in prior_health.get("failing", [])}
    # Older meta.json files have no identifier in adapters; fall back to the company name.
    prior_counts: dict[str, int] = {}
    for s in prior_meta.get("adapters", []):
        prior_counts[_key(s)] = s.get("count") or 0
        prior_counts[f"{s.get('ats')}:{s.get('company')}"] = s.get("count") or 0

    empty, failing = [], []
    for s in adapter_status:
        if s.get("error") in ("disabled", "not run yet"):
            continue
        key = _key(s)
        base = {"company": s.get("company"), "ats": s.get("ats"), "identifier": s.get("identifier")}
        if not s.get("ok"):
            prev = prior_failing.get(key)
            since = prev["since"] if prev else today
            failing.append({**base, "since": since, "new": since == today, "error": s.get("error")})
        elif not s.get("count"):
            prev = prior_empty.get(key)
            if prev:
                since, had_jobs = prev["since"], bool(prev.get("had_jobs"))
            else:
                by_name = prior_counts.get(f"{s.get('ats')}:{s.get('company')}")
                before = prior_counts.get(key, by_name)
                since, had_jobs = today, bool(before)
            empty.append({**base, "since": since, "new": since == today, "had_jobs": had_jobs})
    return {"empty": empty, "failing": failing}


def alerts(health: dict) -> list[str]:
    """One line per board that newly broke today (the events worth an email)."""
    out = []
    for e in health.get("empty", []):
        if e.get("new") and e.get("had_jobs"):
            out.append(
                f"{e['company']} ({e['ats']}:{e['identifier']}) returned 0 jobs after having "
                "jobs. The company may have moved ATS: run "
                f"`python scripts/verify_company.py --find \"{e['company']}\"`."
            )
    for e in health.get("failing", []):
        if e.get("new"):
            out.append(f"{e['company']} ({e['ats']}:{e['identifier']}) failed: {e.get('error')}")
    return out


def summary_markdown(health: dict) -> str:
    lines = ["## Board health", ""]
    went_silent = [e for e in health.get("empty", []) if e.get("had_jobs")]
    never = [e for e in health.get("empty", []) if not e.get("had_jobs")]
    failing = health.get("failing", [])
    if not (went_silent or failing):
        lines.append("No failing boards and no boards that went silent.")
    if failing:
        lines += ["**Failing**", ""]
        lines += [
            f"- {e['company']} ({e['ats']}), since {e['since']}: {e.get('error')}"
            for e in failing
        ]
        lines.append("")
    if went_silent:
        lines += ["**Went silent** (had jobs, now 0)", ""]
        lines += [f"- {e['company']} ({e['ats']}), since {e['since']}" for e in went_silent]
        lines.append("")
    if never:
        lines.append(
            f"{len(never)} other boards have 0 jobs and have had none since tracking began."
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    meta = load_meta(Path(argv[0] if argv else "data/meta.json"))
    health = meta.get("board_health") or {}
    report = summary_markdown(health)
    print(report)
    found = alerts(health)
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for line in found:
        print(f"::error title=Board health::{line}" if in_actions else f"ALERT {line}")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(report)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

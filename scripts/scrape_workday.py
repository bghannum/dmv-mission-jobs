"""Refresh the Workday boards from this machine and merge them into data/.

    python scripts/scrape_workday.py           # scrape and write data/; you commit
    python scripts/scrape_workday.py --push    # pull, scrape, commit and push to main

Workday's servers answer GitHub's Actions runners with HTTP 429, so the daily scrape leaves
the Workday boards out and keeps their last jobs (config/settings.yaml `adapters.workday`).
Run this about once a week. Every other board's jobs and status are carried over unchanged;
the site shows when Workday was last refreshed. Jobs not refreshed for 30 days age out.

A first run fetches every matched job's details (about 15 minutes for six boards); later runs
reuse .cache/workday/ and only fetch new jobs. Exit status: 0 on success, 1 if the write was
blocked, any Workday board failed, or a git step failed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scraper.main import run  # noqa: E402

DATA = ["data/jobs.json", "data/meta.json"]
REMOTE, BRANCH = "origin", "main"


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--push", action="store_true",
                    help=f"pull {BRANCH} first, then commit data/ and push to {REMOTE}/{BRANCH}")
    args = ap.parse_args(argv)

    if args.push:
        if git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() != BRANCH:
            print(f"--push needs the {BRANCH} branch checked out.")
            return 1
        if git("status", "--porcelain", "--", *DATA).stdout.strip():
            print("data/ has uncommitted changes; commit or discard them first.")
            return 1
        pulled = git("pull", "--ff-only", REMOTE, BRANCH)
        if pulled.returncode:
            print(f"git pull failed:\n{pulled.stderr}")
            return 1

    code = run(only_ats={"workday"})
    meta = json.loads((ROOT / "data/meta.json").read_text(encoding="utf-8"))
    boards = [a for a in meta.get("adapters", []) if a.get("ats") == "workday"]
    failed = [a for a in boards if not a.get("ok")]
    print("\nWorkday boards:")
    for a in boards:
        state = "ok" if a.get("ok") else f"FAILED: {a.get('error')}"
        print(f"  {a['company']}: {a.get('count', 0)} fetched, {state}")
    if code:
        print("Write blocked (see the log above); nothing to commit.")
        return 1

    if args.push:
        if not git("status", "--porcelain", "--", *DATA).stdout.strip():
            print("No changes to commit.")
        else:
            git("add", "--", *DATA)
            msg = f"chore: Workday refresh {date.today().isoformat()}"
            for step in (("commit", "-m", msg, "--", *DATA), ("push", REMOTE, BRANCH)):
                done = git(*step)
                if done.returncode:
                    print(f"git {step[0]} failed:\n{done.stderr}")
                    return 1
            print(f"Pushed '{msg}'. The site redeploys from the push.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

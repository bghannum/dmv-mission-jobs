# CLAUDE.md

Follow PLAN.md. Work one phase at a time on a branch, with tests. Run `ruff check .` and
`pytest` before committing. Ask before changing the data model beyond what the plan
describes. For any adapter or seed source that hits an undocumented endpoint, investigate
and document it in docs/ before writing code.

## Project facts

- Repo: `bghannum/dmv-mission-jobs`, public since 2026-11-21 with cleaned history (no personal
  email). The pre-launch private repo is archived as `bghannum/dmv-mission-jobs-archive`.
  `upstream` remote is `crsh-ovr/jobs`, the MIT project this is built on. Keep its LICENSE
  and credit.
- Commit with the GitHub noreply address, never a personal email: this repo is public.
- Board name: **DMV Mission Jobs**. Scraper User-Agent bot name: `brians-job-bot`.
- Python 3.12 (same as CI). Local env: `.venv/` (`uv venv -p 3.12 .venv`).
- Pages deploys are gated on the `PAGES_ENABLED` repo variable (set to `true`).
- A bare "Remote" location with no country counts as `remote_us`.
- A bare "Washington" stays on the board as `location_type: unknown`, shown as "Location uncertain".

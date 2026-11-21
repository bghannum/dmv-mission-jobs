# CLAUDE.md

Follow PLAN.md. Work one phase at a time on a branch, with tests. Run `ruff check .` and
`pytest` before committing. Ask before changing the data model beyond what the plan
describes. For any adapter or seed source that hits an undocumented endpoint, investigate
and document it in docs/ before writing code.

## Project facts

- Repo: `bghannum/dmv-mission-jobs` (private until the end of Phase 2). `upstream` remote is
  `crsh-ovr/jobs`, the MIT project this is built on. Keep its LICENSE and credit.
- Board name: **DMV Mission Jobs**. Scraper User-Agent bot name: `brians-job-bot`.
- Python 3.12 (same as CI). Local env: `.venv/` (`uv venv -p 3.12 .venv`).
- Pages deploys are gated on the `PAGES_ENABLED` repo variable; leave it unset while private.
- A bare "Remote" location with no country counts as `remote_us`.

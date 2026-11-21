# CLAUDE.md

**Start here:** read the **Current status** section at the top of PLAN.md. It has the phase
table, the suggested next steps and where everything lives. Update it at the end of each
piece of work.

Follow PLAN.md. Work one phase at a time on a branch, with tests. Run `ruff check .` and
`pytest` before committing. Ask before changing the data model beyond what the plan
describes. For any adapter or seed source that hits an undocumented endpoint, investigate
and document it in docs/ before writing code.

## Project facts

- Repo: `bghannum/dmv-mission-jobs`, public since 2026-11-21 with cleaned history (no personal
  email). The pre-launch private repo is archived as `bghannum/dmv-mission-jobs-archive`.
  `upstream` remote is `crsh-ovr/jobs`, the MIT project this is built on. Keep its LICENSE
  and credit.
- Live site: https://bghannum.github.io/dmv-mission-jobs/
- Commit with the GitHub noreply address, never a personal email: this repo is public.
- Board name: **DMV Mission Jobs**. Scraper User-Agent bot name: `brians-job-bot`.
- Python 3.12 (same as CI). Local env: `.venv/` (`uv venv -p 3.12 .venv`).
- Pages deploys are gated on the `PAGES_ENABLED` repo variable (set to `true`).
- A bare "Remote" location with no country counts as `remote_us`.
- A bare "Washington" stays on the board as `location_type: unknown`, shown as "Location uncertain".
- Discovery sources must be allowed by robots.txt **and** terms; record each in
  `docs/seed_sources.md`. portfoliojobs.a16z.com (Consider) is not allowed.

## Working notes

- Jobs only come from employers' own ATS boards. Never scrape aggregators (LinkedIn,
  Indeed, VC job boards).
- `data/` is rewritten by the daily Action. After a local scrape, expect to rebase over the
  bot's "daily job refresh" commit.
- Workflows with a `paths` filter don't run on the first push of a new branch or repo.
  Trigger them with `gh workflow run`.
- When merging stacked PRs, retarget the upper PR to `main` *before* merging the lower one
  with `--delete-branch`. Deleting a PR's base branch closes the PR.
- To check the site at phone width in Claude in Chrome, load it in a 390px same-origin
  iframe. Resizing the window doesn't always change the viewport.

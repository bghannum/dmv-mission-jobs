# DMV Mission Jobs

A curated, community-run job board for **mission-driven roles in the DC metro (DC,
Northern Virginia, Maryland) and US remote**, across defense tech, public sector and
commercial tech. It tracks an allowlist of companies and pulls roles from each company's
own public job board. A scraper runs daily via GitHub Actions and the site is plain static
files.

> **Not affiliated with any employer.** This is a personal, community-run project. It is
> not affiliated with, endorsed by, or operated by any company listed here. Listings link
> to each company's official job board.

Built on **[crsh-ovr/jobs](https://github.com/crsh-ovr/jobs)** by Shane Quinlan (MIT).
Thank you, Shane.

## About this version

DMV Mission Jobs is maintained by Brian, who is adapting Shane's board in two ways.

- **Broader role curation, with a focus on GTM-facing roles.** Shane's board centered on
  product, design and engineering. This version adds sales, business development and
  capture, partnerships, solutions architecture, growth and strategy, program management,
  and customer success. The role definitions draw on Brian's experience in defense,
  defense tech and industry more broadly. For example, a "VP of Growth" at a defense
  company usually means business development and capture, not marketing, so the board
  treats it that way.
- **A reworked user experience.** New filters for category, role, DC metro vs. remote,
  clearance and public sector; every filter combination is a shareable link; and a new
  visual design.

See [PLAN.md](PLAN.md) for the roadmap.

## What it tracks

**Categories:** Product, Program Management, Solutions / Architecture, GTM / Sales / BD,
Growth / Strategy, Customer Success, Design and Engineering, each with filterable roles
(`config/roles.yaml`). Marketing roles are out of scope. All levels are kept and tagged,
from intern to VP.

**Companies:** An allowlist in `config/companies.yaml` that started with Shane's original
list and keeps growing, partly through a seeder that proposes companies from public
portfolio and industry lists for review. Industries range from defense tech and govtech to
fintech, health and enterprise software.

**Location:** DC metro (DC, Northern Virginia, Maryland suburbs), on-site or hybrid, plus
US remote (`config/locations.yaml`). Everything else is dropped at scrape time. A bare
"Washington" (DC or the state?) is kept and labelled "Location uncertain".

**Tags:** Clearance and Public sector badges and filters (`config/tags.yaml`).

**Supported ATS platforms:** Ashby, Greenhouse, Lever, Rippling, Gem. Workday and the big
tech careers sites are planned.

## How it works

```
config/*.yaml  →  python -m scraper.main  →  data/jobs.json  →  site/ (static)
   allowlist         daily GitHub Action        committed          no build step
```

The scraper reads the company allowlist, fetches each company's public job-board JSON,
normalizes every posting to a common schema, keeps postings that match a target role and
location, tags category, role, level, location type, clearance and public sector, de-duplicates, and writes `data/jobs.json`.
The static site reads that file in the browser and filters client-side.

`.github/workflows/scrape.yml` runs the scraper **daily at 11:00 UTC** (and on demand) and
commits the refreshed `data/`. `ci.yml` runs ruff and pytest on every pull request.

**Live:** [bghannum.github.io/dmv-mission-jobs](https://bghannum.github.io/dmv-mission-jobs/).
`pages.yml` deploys the site whenever `site/` or `data/` changes on `main` (it runs only when
the `PAGES_ENABLED` repository variable is `true`).

## Add a company

Adding a company is a one-file change to `config/companies.yaml`. To find and check its
board first, run:

```bash
python scripts/verify_company.py --find "Company Name" --website https://company.example
```

It reports how many of the company's jobs would make it onto the board and prints the entry
to add. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Run locally

Requires Python 3.12 (matches CI).

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m scraper.main            # writes data/jobs.json + data/meta.json
python -m http.server 8000        # then open http://localhost:8000/site/
```

## Develop

```bash
ruff check .
pytest
```

## License

[MIT](LICENSE). The original copyright notice from crsh-ovr/jobs is retained, as the
license requires.

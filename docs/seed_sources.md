# Seed sources

Where the board discovers companies, and whether each source may be used. Every source is
checked for robots.txt and terms of use before any code touches it (CLAUDE.md, PLAN.md
Phase 4). Discovery sources only supply company **names**; jobs always come from each
employer's own careers system.

## a16z portfolio: used

| | |
|---|---|
| **Pages** | `https://a16z.com/portfolio/` plus the sector pages `/ai/`, `/american-dynamism/`, `/bio-health/`, `/consumer/`, `/enterprise/`, `/fintech/`, `/infra/` and `/speedrun/` |
| **robots.txt** | Allows all paths for all crawlers (checked 2026-11-21). |
| **Terms** | [a16z.com/terms-of-use](https://a16z.com/terms-of-use) has no restriction on automated access (checked 2026-11-21). |
| **Shape** | Each page embeds company objects as compact JSON (`{"id":"15189","logo_width":"","title":"Anduril",...}`) with `title`, `web` (website), `socials`, `acquirer` and `overview`. Sector pages embed the same objects for their sector, which gives each company's a16z sector. |
| **Volume** | 9 page requests per run, cached in `.cache/seeder/pages/`. |
| **Code** | `scraper/seeder/a16z.py`, `scripts/seed_a16z.py` |

On 2026-11-21: 891 companies, 157 acquired (skipped), 678 with a known sector.

## a16z jobs board (portfoliojobs.a16z.com): NOT used

The board runs on **Consider**. Its robots.txt allows crawling, but
[Consider's terms](https://consider.com/legal/terms) (section 1.4(l)) prohibit using "any
robot, spider, scraper, or other automated means to access the Service" without written
permission. Per PLAN.md, a source whose terms forbid automated access is skipped. The
a16z.com portfolio pages above give the same company list.

## ATS probing (Greenhouse, Lever, Ashby)

For each discovered company, `scraper/seeder/probe.py` tries up to four likely board slugs on
each ATS's public, documented job-board API:

- **Slugs**, in this order: the website's domain label, then social handles (LinkedIn, X, Facebook), then forms of the name.
- **Missing boards:** all three APIs return 404 for a board that doesn't exist, so no retry is made on 404.
- **Choosing a board:** every slug is tried and the board with the most jobs wins. Some companies keep an empty placeholder board under one slug, e.g. Anduril's `anduril` (0 jobs) vs `andurilindustries`.
- **Verification:**
  - **Greenhouse** returns the board's own name, which must resemble the company name.
  - **Ashby and Lever** don't return a name, so the board's job text must mention the company name or its web domain.
  - **Unverified boards** (including empty ones) go to `config/candidates.yaml` for review rather than `companies.yaml`.
- **Politeness:** one thread per ATS host with a fixed delay between requests (default 0.3s), the board's User-Agent, and an on-disk cache (`.cache/seeder/probe_cache.json`) so no slug is probed twice.

Companies with no board on these three ATSs go to `config/needs_adapter.yaml`. Many will
be on Workday or a custom careers site (PLAN.md Phases 5–6).

## Industries

`scraper/seeder/industry.py` maps the a16z sector to a board industry (e.g. Bio + Health →
`healthtech`, Enterprise and Infrastructure → `saas`), then adds detail from keywords in
a16z's description (space, govtech, cybersecurity, crypto, ...). `deftech` is assigned
conservatively because it tags every job at the company `public_sector`:

- Phrases like "national security", "warfighter", "military", "naval" and "defense technology" count.
- Bare "defense" never counts on its own: cybersecurity copy says "threat defense", and a bank lending to "AI, defense, manufacturing" companies isn't a defense company. Specific phrases such as "defense technology", "aerospace and defense" and "naval warfare" do count.

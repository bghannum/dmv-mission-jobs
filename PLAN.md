# DMV Job Board — Project Plan

A curated job board for **DC-area and remote roles** in defense tech, public sector and commercial tech. It is forked from [crsh-ovr/jobs](https://github.com/crsh-ovr/jobs) (MIT) and extended in four ways:

- **Broader role categories**: product, program, architecture, GTM, growth and customer success, all filterable.
- **Big-tech coverage**: Microsoft, Google, AWS and others, which run their own careers sites.
- **Workday coverage**: many defense primes and government IT employers use Workday.
- **Discovery**: a seeder keeps growing the company list automatically.

## Goals

1. **One board for everyone.** There are no per-user profiles. Users narrow it with filters for category, role, industry, level, location type, clearance and public sector, as on Shane's site.
2. **Comprehensive.** Keep all of Shane's companies, then keep adding companies through a seeder that proposes candidates for review.
3. **Free to run.** GitHub Actions plus static hosting, with no server or database.

## Decisions so far

| Topic | Decision |
|---|---|
| Profiles | None. One board, filtered by category. |
| Location | DMV (DC, Northern Virginia, Maryland suburbs) **or** US remote. Other on-site roles are dropped at scrape time. |
| Hybrid | Hybrid roles in the DMV count as DMV. |
| Big tech | Include **all** in-scope roles in the DMV, not just public-sector teams. A `public_sector` tag lets users filter down. |
| Marketing | Excluded for now, including growth marketing. |
| Starting companies | Keep all of Shane's existing list, and add to it. |
| Categories | Keep Shane's Design and Engineering categories alongside the new ones. |
| "Washington" (no state) | Undecided. Measure how often it appears during Phases 1–2, then decide. |
| Repo | Private through Phase 2, then public (see "Repo and hosting" below). |

## Non-goals (for now)

- User accounts, logins or per-user profiles.
- Applying to jobs or tracking applications.
- Marketing roles.
- Scraping aggregator job boards (LinkedIn, Indeed). Jobs only ever come from the employer's own careers system.

---

## How the original works (baseline)

```
config/companies.yaml → python -m scraper.main → data/jobs.json → site/ (GitHub Pages)
   allowlist               daily GitHub Action      committed          static, filters client-side
```

- **Adapters** (`scraper/adapters/`): one per ATS (Greenhouse, Lever, Ashby, Rippling, Gem). Each hits that ATS's public JSON API and normalizes postings to a common `Job` model.
- **Matching** (`scraper/matching.py` + `config/roles.yaml`): include and exclude keywords on titles, grouped into "umbrellas" (categories), plus level detection.
- **Filters**: US-only (`scraper/location.py`) and dedup (`scraper/dedup.py`).
- **Writer** (`scraper/writer.py`):
  - Keeps `first_seen`/`last_seen` and ages out jobs after 30 days.
  - Retains a company's prior jobs if its adapter fails.
  - Refuses to write if the job count shrinks by more than 80%.
- **Site**: vanilla JS. Filters live in URL params (`?umbrella=product&remote=1`).
- **CI**: ruff and pytest. A daily scrape commits data and triggers a deploy.

The design keeps this shape. The changes are mostly config (more categories, a location model, tags) plus new adapters and the seeder.

---

## Target architecture

```
config/
  companies.yaml        # company allowlist (Shane's list + additions)
  candidates.yaml       # seeder output awaiting review (NOT scraped)
  rejected.yaml         # declined in review (never re-proposed)
  needs_adapter.yaml    # relevant companies on unsupported ATSs (Workday, custom)
  roles.yaml            # categories → roles → keyword rules
  locations.yaml        # DMV metro definition
  tags.yaml             # clearance, public_sector keyword rules
  seed_sources.yaml     # where the seeder looks for new companies
scraper/
  adapters/             # + workday.py, + bigtech/{microsoft,google,amazon}.py
  tagging.py            # NEW: location type + clearance + public-sector tags
  seeder/               # NEW: discover → probe ATS slugs → write candidates.yaml
data/
  jobs.json             # matched jobs with category, role, level, location type, tags
  descriptions/         # descriptions split out to keep jobs.json small
site/                   # filters for category, role, industry, level, location type, tags
```

### Categories (`config/roles.yaml`)

These are starter keywords; tune them with tests. **Marketing is excluded everywhere for now.**

```yaml
umbrellas:
  product:
    label: "Product"
    roles:
      product_manager:  { include: ["product manager","product owner","head of product","director of product","vp of product","product lead"],
                          exclude: ["product marketing","product support"] }
  program:
    label: "Program Management"
    roles:
      technical_program_manager: { include: ["technical program manager","tpm"], exclude: [] }
      program_manager:  { include: ["program manager","program director","program lead","program management"],
                          exclude: ["marketing program","technical program"] }
  architecture:
    label: "Solutions / Architecture"
    roles:
      solutions_architect: { include: ["solutions architect","solution architect","solutions engineer","sales engineer",
                                       "forward deployed","field engineer","customer engineer"], exclude: [] }
      enterprise_architect: { include: ["enterprise architect","systems architect","cloud architect","technical architect"], exclude: [] }
  gtm:
    label: "GTM / Sales / BD"
    roles:
      sales:            { include: ["account executive","account manager","sales director","director of sales","vp of sales",
                                    "head of sales","sales lead","territory manager","account director","client executive"],
                          exclude: ["sales engineer","marketing"] }
      business_development: { include: ["business development","capture manager","capture lead","capture director",
                                        "strategic accounts","federal sales","public sector sales"], exclude: ["marketing"] }
      partnerships:     { include: ["partnerships","partner manager","alliances","channel manager","strategic partner"],
                          exclude: ["partner support","marketing"] }
  growth:
    label: "Growth / Strategy"
    roles:
      growth:           { include: ["growth","go-to-market","gtm","revenue operations","revops"],
                          exclude: ["marketing","demand gen","lifecycle","seo","content"] }
      strategy_ops:     { include: ["strategy & operations","strategy and operations","bizops","business operations",
                                    "chief of staff"], exclude: ["content strategy","brand strategy","marketing"] }
  customer:
    label: "Customer Success"
    roles:
      customer_success: { include: ["customer success","client success","customer experience","customer outcomes",
                                    "mission success","customer operations","implementation manager","deployment manager",
                                    "engagement manager","technical account manager"],
                          exclude: ["customer support specialist","support engineer","marketing"] }
  design:       # keep Shane's existing definitions as-is
  engineering:  # keep Shane's existing definitions as-is
levels: # keep the original level detection (intern → vp)
```

**Matching notes:**
- In GovCon, **"growth" usually means BD and capture** (e.g. "VP of Growth" at a defense contractor). It belongs in GTM or Growth here, but it needs tests.
- Defense companies use their own names for customer roles ("Mission Success", "Deployment Strategist", "Field Operations"). Collect real titles in Phase 2 and add them.
- Add an optional `exclude_departments` field per role. A department of "Marketing" or "Engineering" is a strong signal for dropping false positives on broad words like "growth" and "operations".

### Location (`config/locations.yaml`)

```yaml
metros:
  dmv:
    label: "DC Metro"
    match: [
      # DC
      "washington, dc", "washington dc", "washington, d.c.", "district of columbia",
      # Northern Virginia
      "arlington", "alexandria", "reston", "herndon", "mclean", "tysons", "vienna, va", "falls church", "fairfax",
      "chantilly", "ashburn", "sterling, va", "springfield, va", "dulles", "manassas", "leesburg", "northern virginia",
      # Maryland suburbs
      "bethesda", "rockville", "gaithersburg", "silver spring", "college park", "greenbelt", "laurel, md",
      "columbia, md", "fort meade", "ft. meade", "annapolis junction", "hanover, md", "lanham", "germantown, md"
    ]
```

Each job gets a `location_type`:
- `dmv_onsite`: in the DMV, on-site.
- `dmv_hybrid`: in the DMV, hybrid. This counts as DMV.
- `remote_us`: remote, US-eligible.
- Anything else is **dropped at scrape time**. This is controlled by a setting in `settings.yaml` in case that ever changes.

Edge cases to test:
- Multi-location postings ("Reston, VA; Austin, TX") are kept if any location is in the DMV.
- "Washington" alone is ambiguous with Washington state. **Don't pick a rule yet.** Log every bare "Washington" location (with company and title) to `data/meta.json` under `ambiguous_locations` and keep those jobs for now with `location_type: unknown`. Review the counts at the end of Phase 2, then decide and add tests.
- "Remote - Canada" is dropped.

### Tags (`config/tags.yaml`)

Tags are keyword-matched on title, department/team and description. Each one is a badge and a filter on the site.

```yaml
clearance:      ["clearance", "ts/sci", "top secret", "secret clearance", "polygraph", "public trust"]
public_sector:  ["public sector", "federal", "government", "national security", "defense", "dod", "civilian agencies",
                 "intelligence community", "state and local", "sled", "azure government", "govcloud"]
```

Companies can also carry a company-level tag. For example, every job at a pure defense tech company gets `public_sector` automatically, through its industry.

### Site

- Keep Shane's layout and URL-param filters, and add:
  - **Category** (umbrella) and **Role**
  - **Industry**
  - **Level**
  - **Location type**: DMV on-site, DMV hybrid, Remote
  - **Clearance** and **Public sector** toggles
- Sort defense tech and gov tech companies first by default. Users can re-sort by newest.
- Every filter state is a shareable URL, e.g. `?umbrella=gtm&public_sector=1&loc=dmv`.

### Visual design (replaces Shane's terminal look)

**Approved mockup:** [DMV Job Board Mockup](https://claude.ai/artifact/V2TUieLtetzvZaESMgifx7). This is the source of truth for layout, colors and components. Match it in Phase 1b.

The mockup keeps the **"Unaffiliated" community-project banner** at the very top: a thin bar with an "Unaffiliated" pill and the line *"A personal, community-run project. Not affiliated with, endorsed by, or operated by any company listed here. Listings link to each company's official job board."* The footer credits crsh-ovr/jobs (MIT). Both are required.

**Original inspiration:** [NexusNode social posts on Dribbble](https://dribbble.com/shots/27474450-NexusNode-Local-AI-Orchestration-Social-Media-Posts). The look is dark glass panels over glowing wireframe waves, with a teal-to-violet palette.

That reference is marketing art, and this is a data-heavy listing page. **Use the expressive parts (waves, glow, glass) in the header, the hero and the empty states. Keep the job list calm and readable.**

**Tokens** (starting values; tune for contrast):

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0E0F13` | Page background (near-black charcoal) |
| `--surface` | `rgba(255,255,255,0.05)` + `backdrop-filter: blur(16px)` | Glass cards and panels |
| `--border` | `rgba(255,255,255,0.10)` | 1px panel borders |
| `--text` | `#F2F4F7` | Primary text |
| `--muted` | `#9AA3AE` | Company, location, meta |
| `--teal` | `#4FE3D1` | Primary accent: links, active filters, primary buttons |
| `--cyan` | `#38BDF8` | Secondary accent |
| `--violet` | `#A78BFA` | Tags, secondary pills |
| `--magenta` | `#E879F9` | Sparing highlight (e.g. "New") |
| `--success` | `#34D399` | Status-style badges (e.g. "Public sector") |
| Gradient | teal → cyan → violet → magenta | Wave art, the logo mark, focus glows |

**Type:**
- A bold geometric sans for headings (e.g. Inter, Manrope or Plus Jakarta Sans, from Google Fonts). Big, tight, white, with an occasional accent-colored word, like "COMMAND **HUB**".
- Small uppercase labels with letter-spacing for section and filter labels ("HARDWARE METRICS" style).
- Tabular numerals for counts and dates.

**Components:**
- **Header/hero:** board name plus live stats ("1,284 roles · 212 companies · updated 6h ago") on a glass panel. Behind it, an animated wireframe wave mesh in the gradient (SVG or canvas, lightweight). Respect `prefers-reduced-motion` and fall back to a static image.
- **Filter bar:** glass panel with pill chips. Outlined pills when off, filled teal pills when on (like the "NEW NODE / RUN WORKFLOW / DEPLOY" buttons). The search field also gets a glass treatment.
- **Job cards:** glass cards with rounded corners (~14px), a 1px border and a subtle glow on hover.
  - Title in white semibold, with company · location · Hybrid/Remote in muted text.
  - Tag pills: Public sector (green, status style), Clearance (violet), New (magenta).
  - Offer a **compact list view** toggle as well, since scanning hundreds of rows matters more than visuals.
- **Stats strip (optional):** small gauge or sparkline tiles ("New this week", "Top hiring companies") styled like the reference's metric panels.
- **Empty and loading states:** a wave mesh with a short message.

**Rules:**
- Dark mode only for now.
- Body text must meet WCAG AA contrast on the glass surfaces. Test it, since blur over glowing art can wash out text.
- Keep it fast: no frameworks, CSS variables in `styles.css`, the wave as a small SVG or canvas, and no large images.
- Make it work at phone width.

---

## Phases

Each phase is one PR that ships with tests. Don't start a phase until the previous one is green.

### Phase 0: Fork and baseline
- Fork `crsh-ovr/jobs` into a **private** repo. Keep the LICENSE and add a credit line to the README.
- Remove Shane-specific branding, the "field guide" links and the Horizon3 featured tier.
- Run the scraper locally and view the site with `python -m http.server`. Make sure the Actions run green.
- **Done when:** the scraper runs in Actions and the site works locally, with Shane's full company list.

### Phase 1: Categories, location and tags
- Restructure `roles.yaml` into the categories above.
- Add `locations.yaml`, `tags.yaml` and `scraper/tagging.py`, and change the US-only filter to the DMV-or-remote filter.
- Add the new site filters.
- Tests:
  - Title cases for every role, including negatives: "Product Marketing Manager", "Growth Marketing Manager" (drop), "Customer Support Specialist", "Sales Engineer" (architecture, not sales), "Content Strategy Lead", "VP of Growth" (keep).
  - Location cases: "Reston, VA", "Hybrid - McLean", "Fort Meade, MD", "Remote (US)", "Remote - Canada" (drop), "Austin, TX" (drop), a multi-location posting, and "Washington" alone.
  - Tag cases for clearance and public sector.
- **Done when:** the board shows only DMV and remote roles across all categories, and every filter works.

### Phase 1b: Visual redesign
- Rebuild `site/index.html` and `site/styles.css` to the "Visual design" spec above. Keep `app.js` filtering and URL-param logic, and change only its rendering.
- Build it as tokens first (CSS variables), then components: header/hero, filter bar, job card, list view and empty state.
- Check it at desktop and phone widths, and check contrast on every text style.
- **Done when:** the redesigned site works with real data, passes an AA contrast check and looks right on a phone. This must be done before the site goes public at the end of Phase 2.

### Phase 2: Expand the company list (by hand)
- **Keep all of Shane's existing companies.** Everything here is additive.
- Extend the industry vocabulary: `deftech`, `govtech`, `gov-it`, `space`, `ai`, `cybersecurity`, `bigtech`, `saas`. Re-tag existing entries where it fits.
- Write `scripts/verify_company.py <ats> <slug>`, which prints the job count, sample titles and how many jobs survive the category and location filters.
- Add new companies, verifying **every** entry against its live board. Starting candidates are below; confirm the ATS for each, since some will be Workday or custom:
  - **Defense tech**: Anduril, Shield AI, Palantir, Scale AI, Saronic, Epirus, Hadrian, Skydio, Govini, Vannevar Labs, Rebellion Defense, Second Front, Rise8, Defense Unicorns, Applied Intuition, Castelion, Chaos Industries, Primer, Ask Sage, Istari
  - **Commercial companies with federal/public-sector teams**: Databricks, Snowflake, CrowdStrike, Okta, Zscaler, Palo Alto Networks, ServiceNow, Salesforce, Cloudflare, Elastic, MongoDB, Datadog, GitLab
  - **Big tech** (Phase 5): Microsoft, Google, AWS/Amazon, Oracle, IBM
- Collect real GTM and customer titles from defense companies, and feed them back into `roles.yaml` with tests.
- Review `ambiguous_locations` in `meta.json` and decide the bare "Washington" rule (treat it as DC, check the description for a state, or drop it). Add tests for the chosen rule.
- **Go public**:
  - Check the repo history for anything that shouldn't be public.
  - Make the repo public and turn on GitHub Pages.
  - Confirm the scheduled scrape redeploys the live site.
- **Done when:** at least 40 verified companies are added, every category has DMV or remote jobs, the Washington rule is decided, and the site is live on GitHub Pages.

### Phase 3: Payload size
- Move `description_html` into `data/descriptions/<id>.json`, loaded on demand, and keep a short plain-text snippet inline.
- The original is already about 4.7 MB at roughly 500 jobs, and big tech and the seeder will multiply that.
- **Done when:** `jobs.json` stays under about 1.5 MB at 2,000 jobs.

### Phase 4: Seeder (automated company discovery)
This is the main lever for being comprehensive. The goal is to find every company with a relevant, live DMV or remote job, not just the ones someone thought to add.

- `config/seed_sources.yaml` lists the sources, in three tiers.
  - **Tier 1: curated lists** (high signal, small volume)
    - `vc_portfolio`: defense-focused VCs first (a16z American Dynamism, 8VC, Founders Fund, Lux, General Catalyst, Shield Capital, Razor's Edge, Harpoon, Decisive Point, Red Cell Partners, J2 Ventures, In-Q-Tel), then generalists (Sequoia, Y Combinator).
    - `job_board_companies`: the company lists behind other curated boards, such as the ones the original site links to.
    - `static_list`: hand-pasted names or URLs, e.g. conference exhibitor lists (AUSA, Modern Day Marine, AFCEA).
  - **Tier 2: government data** (finds companies that actually win federal work)
    - `usaspending`: the USAspending.gov API, which is public and documented. Pull recent DoD and civilian contract recipients, filtered by NAICS codes for software, IT services and R&D, above a minimum dollar amount.
    - `sbir`: SBIR/STTR awardees from SBIR.gov. This is a strong source for early-stage defense tech.
  - **Tier 3: ATS enumeration** (most comprehensive; run monthly at most)
    - List every public board slug on Greenhouse, Lever and Ashby. Candidate methods:
      - Query the Common Crawl index for `boards.greenhouse.io`, `job-boards.greenhouse.io`, `jobs.lever.co` and `jobs.ashbyhq.com`.
      - Run web-search queries scoped to those domains.
    - Fetch each board once, and keep only companies with a job that survives the category and location filters.
    - This is tens of thousands of boards. Run it as a separate, resumable, heavily rate-limited job, and re-check only new slugs afterwards. Watch Actions minutes on a private repo; this tier may need to run locally.
- Pipeline in `scraper/seeder/`:
  1. **Discover** company names, domains or slugs.
     - Many portfolio boards are hosted on Getro or Consider. Investigate how each exposes data.
     - Document each source's status in `docs/seed_sources.md`, and skip any that aren't viable or whose terms forbid it.
  2. **Dedupe** against `companies.yaml`, `candidates.yaml` and `rejected.yaml`.
  3. **Probe** likely slugs (`anduril`, `andurilindustries`, `anduril-industries`, ...) against Greenhouse, Lever and Ashby. Cache the results and rate-limit.
  4. **Score**: keep companies with at least one job that survives the category and location filters. Record the matching titles as evidence, and rank by match count and defense or public-sector signals.
  5. **Write** `candidates.yaml` with name, ats, identifier, source, sample titles and a suggested industry. Relevant companies on unsupported ATSs go to `needs_adapter.yaml`.
- Add a weekly GitHub Action that opens a PR with the new candidates. To approve, move an entry into `companies.yaml`; to decline, move it into `rejected.yaml`. Nothing is auto-promoted.
- **Done when:** the weekly PR proposes relevant companies with evidence, and reviewing it takes under 10 minutes.

### Phase 5: Big-tech adapters (Microsoft, Google, Amazon first)
These companies run their own careers sites, so each needs a custom adapter. Let `needs_adapter.yaml` from Phase 4 confirm the priority order.

- **Investigate first, then build.** For each company:
  - Find the JSON endpoint the careers search page calls, using the browser's network tab.
  - Record the URL, parameters and response shape in `docs/adapters/<company>.md`.
  - Check robots.txt and terms of use. If a site has no usable endpoint or forbids automated access, skip it and link to its search page instead.
- **Query narrowly, server-side.**
  - Search by location: DC, Virginia, Maryland and remote US.
  - Then apply category matching and tagging locally.
  - Keep **all** in-scope roles in the DMV (not just public-sector teams), and let the `public_sector` tag do the filtering.
- Put the adapters in `scraper/adapters/bigtech/` with a shared search-then-paginate base, a page cap per run and a slower politeness delay.
- These endpoints are undocumented and **will break without warning**.
  - Put a recorded fixture and test in for each adapter.
  - Make failures visible in `meta.json`.
  - Rely on the retain-on-failure logic so a broken adapter doesn't wipe that company's listings.
- **Done when:** Microsoft, Google and Amazon DMV roles appear, with public-sector teams tagged, and the adapters survive a week of daily runs.

### Phase 6: Workday adapter
- Covers defense primes, government IT integrators and many enterprise software companies.
- Workday career sites call `POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`. The identifier becomes `tenant/wdN/site`.
- Paginate with `limit`/`offset`, and narrow the results server-side with the location facets.
- Fetch job details only for jobs that already match a category, and only when tags need the description.
- Run Workday in a separate, slower pass, with a recorded fixture and test.
- **Done when:** three or more Workday employers scrape reliably for a week.

### Phase 7: Polish (optional)
- "New this week" view, and starred jobs in localStorage.
- An RSS feed or weekly email digest for a saved filter URL.
- A health page from `meta.json` showing which adapters and boards are failing.

---

## Repo and hosting

**Decision: private through Phase 2, public at the end of Phase 2.**

- **Private while iterating.** Half-built scrapers and noisy data aren't public, and you can experiment freely. The catches:
  - **GitHub Pages doesn't publish from a private repo on a free account.** It needs a paid plan, so view the site locally (`python -m http.server`) during development.
  - **GitHub Actions minutes are limited on private repos** (public repos get unlimited minutes on standard runners). The daily scrape fits comfortably, but the Tier 3 enumeration in Phase 4 may not. Run that tier locally if needed.
- **Go public once Phases 0–2 are solid** and the board is ready for daily use. Public gets free Pages hosting and unlimited Actions minutes. With no per-user profiles, nothing in the repo is personal.
- **If you want it hosted but private**, a paid GitHub plan works, and so does deploying the `site/` folder to a free static host that supports private repos (e.g. Cloudflare Pages or Netlify). Note that the site itself would still be public unless you add access control.
- Check current GitHub plan details before deciding, since limits change.

## Guardrails
- Be polite to the ATS APIs:
  - Identify the bot in the User-Agent.
  - Keep the original delays and retries, with stricter limits for Workday and big tech.
  - Cache seeder probes.
- Respect each site's robots.txt and terms. If a site forbids automated access, leave it out.
- Keep the original safety rails: per-company failure isolation, retaining prior jobs when a fetch fails, the shrink guard, and the `safeUrl` sanitizer on job links.

## Open questions
1. "Washington" with no state: decide at the end of Phase 2, based on the logged data.

## How to use this plan with Claude Code
- Put this file in the repo root as `PLAN.md`, and add a `CLAUDE.md` that says: *"Follow PLAN.md. Work one phase at a time on a branch, with tests. Run `ruff check .` and `pytest` before committing. Ask before changing the data model beyond what the plan describes. For any adapter or seed source that hits an undocumented endpoint, investigate and document it in docs/ before writing code."*
- First prompt: *"Read PLAN.md and the existing code, then do Phase 0."*

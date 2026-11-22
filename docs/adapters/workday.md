# Workday adapter: endpoint notes

Investigated 2026-11-22 against Leidos, Booz Allen, GDIT, Northrop Grumman, CrowdStrike,
Salesforce, CACI and Palo Alto Networks. Workday doesn't document this API. It is the JSON
API each employer's public career site calls from the browser, so it can change without
notice. The adapter is `scraper/adapters/workday.py` and its tests use recorded responses.

## Identifying a board

A career site lives at `https://{tenant}.{wdN}.myworkdayjobs.com/{site}`, for example
`https://leidos.wd5.myworkdayjobs.com/External`. The `companies.yaml` identifier is
`{tenant}/{wdN}/{site}`, e.g. `leidos/wd5/External`. Find it by following the "search jobs"
link on the employer's careers page. The `wdN` data-center number varies (wd1, wd5, wd12, ...)
and the site name is case-sensitive.

## Endpoints

Base: `https://{tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}`

**Search:** `POST {base}/jobs` with JSON
`{"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}`.

- `limit` is capped at 20. A larger value returns HTTP 400.
- `total` is only reliable on the first page (later pages return `total: 0`).
- `total` tops out at 2,000 on some tenants (Leidos, Booz Allen show exactly 2000 with no
  filter). Keep each query under that by narrowing with facets (below).
- Each posting has `title`, `externalPath` (e.g. `/job/Reston-VA/Title_R-00123`),
  `locationsText` (one location, or "N Locations" for multi-location jobs), `postedOn`
  (relative text: "Posted Today", "Posted 3 Days Ago", "Posted 30+ Days Ago") and
  `bulletFields` (usually the requisition ID). No description and no remote flag.
- The first page also returns `facets`. Location values sit under a `locations` facet
  parameter, sometimes nested in a `locationMainGroup` group. Each value has an `id`,
  `descriptor` and `count`. Pass `{"locations": [id, ...]}` as `appliedFacets` to filter
  server-side; a posting matches if any of its locations is selected.

**Detail:** `GET {base}{externalPath}` returns `jobPostingInfo` with `jobDescription` (HTML),
`location`, `additionalLocations` (list, multi-location jobs only), `startDate` (the posting
date, `YYYY-MM-DD`), `jobReqId`, `externalUrl` and on some tenants `remoteType`.

## Location names differ by tenant

| Tenant | Examples |
|---|---|
| Leidos | `Reston, VA`, `0411 Vienna VA`, `6314 Remote/Teleworker US`, `Washington DC Home Office` |
| Booz Allen | `McLean, VA`, `Washington, D.C.` |
| GDIT | `USA VA Reston - 12310 Sunrise Valley Dr (VAC074)`, `Any Location / Remote` |
| Northrop Grumman | `United States-Virginia-McLean`, `United States-Remote`, site codes like `ALHU12` |
| CrowdStrike | `USA - Arlington, VA`, `USA - Remote, VA`, `Germany - Remote` |
| Salesforce | `Virginia - Herndon`, `Virginia - Remote`, `Maryland - Washington DC Metro - Remote` |

The adapter rewrites each one to "City, ST" style (`normalize_location`) and then uses the
board's own classifier (`scraper/location.py`) to decide which facet values are in the DMV or
US remote. Those values become the server-side filter, and the same rewrite is applied to the
locations stored on each job.

## How the adapter fetches

1. Check robots.txt. Skip (fail the board) if it disallows `/{site}/` or the API path.
2. First search page, to read the facets.
3. Search again filtered to in-area location values, 20 per page. If a filter reports 2,000
   or more, split the location values into halves and query each, de-duplicating by
   `externalPath`.
4. Title matching runs on the list results (scraper/main.py). Only matched jobs get a detail
   request, for the full location list and the description that clearance tagging needs.
   Details are cached in `.cache/workday/` (restored between runs with actions/cache), so a
   job's detail is fetched once and refreshed after 14 days.

A tenant with no location facet is paged without a filter, capped at 100 pages.

## robots.txt and terms

Each tenant has its own robots.txt. Every one checked disallows `/refreshFacet/`, which we
never call, and allows or disallows the career-site path per employer:

| Employer | Board | Allowed? |
|---|---|---|
| Leidos | `leidos/wd5/External` | Yes |
| Booz Allen | `bah/wd1/BAH_Jobs` | Yes |
| GDIT | `gdit/wd5/External_Career_Site` | Yes |
| Northrop Grumman | `ngc/wd1/Northrop_Grumman_External_Site` | Yes |
| CrowdStrike | `crowdstrike/wd5/crowdstrikecareers` | Yes |
| Salesforce | `salesforce/wd12/External_Career_Site` | Yes |
| CACI | `caci/wd1/External` | **No**: `Disallow: /External/` |
| Palo Alto Networks | `paloaltonetworks/wd5/panwexternalcareers` | **No**: `Disallow: /panwexternalcareers/` |

The disallowed ones stay in `config/needs_adapter.yaml` with the reason. The adapter
re-checks robots.txt on every run, so a later change fails that board and the board health
check alerts.

Not found on Workday (2026-11-22): SAIC, ServiceNow. ManTech uses Avature, Peraton iCIMS
and Parsons Phenom; those need other adapters.

## Politeness

Same User-Agent, retries and per-request delay as the other adapters (`config/settings.yaml`).
A first run for the six boards above makes roughly 300 search requests and one detail request
per category-matched job; later runs make detail requests only for new jobs.

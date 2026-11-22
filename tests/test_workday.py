"""Workday adapter: location rewriting, facet filtering, paging, detail enrichment, cache."""

import copy
import json
from datetime import date

import pytest

from scraper.adapters.registry import KNOWN_ATS
from scraper.adapters.workday import (
    RESULT_CAP,
    RobotsDisallowed,
    WorkdayAdapter,
    in_area_location_facets,
    normalize_location,
    parse_identifier,
    posted_from_relative,
)
from scraper.config_loader import ConfigError, load_companies, load_locations, load_roles, load_tags
from scraper.main import filter_jobs
from scraper.models import Company

TODAY = date(2026, 11, 22)
API = "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/External"
ROBOTS_OK = "User-agent: *\nAllow: /External/\nDisallow: /refreshFacet/\n"


class FakeSession:
    headers = {"User-Agent": "brians-job-bot/1.0"}


class FakeClient:
    """Answers search POSTs from `pages` (keyed by facet ids) and detail GETs from `details`."""

    def __init__(self, page, *, robots=ROBOTS_OK, details=None, totals=None):
        self.page = page
        self.robots = robots
        self.details = details or {}
        self.totals = totals or {}  # tuple(sorted(location ids)) -> total to report
        self.session = FakeSession()
        self.posts: list[dict] = []
        self.gets: list[str] = []

    def get_text(self, url):
        assert url.endswith("/robots.txt")
        return self.robots

    def post_json(self, url, payload):
        assert url == f"{API}/jobs"
        self.posts.append(payload)
        ids = tuple(sorted(payload["appliedFacets"].get("locations", [])))
        body = copy.deepcopy(self.page)
        if ids in self.totals:
            body["total"] = self.totals[ids]
        if payload["offset"]:
            body["total"] = 0  # like Workday: total only on the first page
            body["jobPostings"] = []
        return body

    def get_json(self, url):
        self.gets.append(url)
        return self.details[url[len(API):]]


def _company():
    return Company(name="Acme", ats="workday", identifier="acme/wd5/External",
                   industry=["deftech"])


def _adapter(client, tmp_path):
    return WorkdayAdapter(client, location_rules=load_locations(), cache_dir=tmp_path,
                          today=TODAY)


@pytest.mark.parametrize("raw, expected", [
    ("0411 Vienna VA", "Vienna, VA"),
    ("Reston, VA", "Reston, VA"),
    ("Washington DC Home Office", "Washington, DC (remote)"),
    ("USA VA Reston - 12310 Sunrise Valley Dr (VAC074)", "Reston, VA"),
    ("USA DC Home Office (DCHOME)", "DC (remote)"),
    ("United States-Virginia-McLean", "McLean, Virginia"),
    ("United States-Maryland-Unknown City", "Maryland"),
    ("United States-Remote", "Remote, US"),
    ("USA - Remote", "Remote, US"),
    ("USA - Arlington, VA", "Arlington, VA"),
    ("Virginia - Herndon", "Herndon, Virginia"),
    ("Germany - Remote", "Germany - Remote"),
    ("Ontario - Remote", "Remote, Ontario, Canada"),
    ("6314 Remote/Teleworker US", "Remote/Teleworker US"),
    (None, None),
])
def test_normalize_location(raw, expected):
    assert normalize_location(raw) == expected


def test_canadian_province_remote_is_not_us():
    from scraper.location import classify_location_type
    loc = normalize_location("Ontario - Remote")
    assert classify_location_type(loc, False, load_locations(), None, "") is None


def test_posted_from_relative():
    assert posted_from_relative("Posted Today", TODAY) == "2026-11-22"
    assert posted_from_relative("Posted Yesterday", TODAY) == "2026-11-21"
    assert posted_from_relative("Posted 3 Days Ago", TODAY) == "2026-11-19"
    assert posted_from_relative("Posted 30+ Days Ago", TODAY) is None


def test_parse_identifier():
    assert parse_identifier("leidos/wd5/External") == ("leidos", "wd5", "External")
    with pytest.raises(ValueError):
        parse_identifier("leidos")


def test_in_area_facets_pick_dmv_and_us_remote(load_fixture):
    param, ids = in_area_location_facets(load_fixture("workday_jobs_page.json")["facets"],
                                         load_locations())
    assert param == "locations"
    # Norfolk (not DMV), UK remote and Columbus are left out; Vienna's site number is handled.
    assert set(ids) == {"loc-reston", "loc-vienna", "loc-remote"}


def test_fetch_filters_server_side_and_normalizes(load_fixture, tmp_path):
    client = FakeClient(load_fixture("workday_jobs_page.json"))
    adapter = _adapter(client, tmp_path)
    jobs = adapter.normalize(adapter.fetch(_company()), _company())
    # First call reads facets; the second is filtered to in-area locations.
    assert client.posts[0]["appliedFacets"] == {}
    assert set(client.posts[1]["appliedFacets"]["locations"]) == {
        "loc-reston", "loc-vienna", "loc-remote"}
    capture = next(j for j in jobs if j.title == "Capture Manager")
    assert capture.id == "workday:acme/wd5/External:Capture-Manager_R-001"
    assert capture.url == "https://acme.wd5.myworkdayjobs.com/External/job/Reston-VA/Capture-Manager_R-001"
    assert capture.location == "Reston, VA"
    assert capture.posted_at == "2026-11-20"
    assert capture.description_available is False
    multi = next(j for j in jobs if j.title == "Senior Program Manager")
    assert multi.location is None  # "3 Locations": filled in by enrich
    payroll = next(j for j in jobs if j.title == "Payroll Specialist")
    assert payroll.location == "Vienna, VA"


def test_query_split_when_result_cap_hit(load_fixture, tmp_path):
    page = load_fixture("workday_jobs_page.json")
    all_ids = ("loc-remote", "loc-reston", "loc-vienna")
    client = FakeClient(page, totals={all_ids: RESULT_CAP})
    adapter = _adapter(client, tmp_path)
    raw = adapter.fetch(_company())
    filtered = [p["appliedFacets"]["locations"] for p in client.posts if p["appliedFacets"]]
    assert len(filtered) == 3  # the full set hit the cap, then each half
    assert len(raw) == 3  # the same postings from both halves are de-duplicated


def test_robots_disallow_fails_the_board(load_fixture, tmp_path):
    client = FakeClient(load_fixture("workday_jobs_page.json"),
                        robots="User-agent: *\nDisallow: /External/\n")
    with pytest.raises(RobotsDisallowed):
        _adapter(client, tmp_path).fetch(_company())
    assert client.posts == []


def test_enrich_adds_locations_description_and_caches(load_fixture, tmp_path):
    path = "/job/Remote/Senior-Program-Manager_R-002"
    client = FakeClient(load_fixture("workday_jobs_page.json"),
                        details={path: load_fixture("workday_detail.json")})
    adapter = _adapter(client, tmp_path)
    jobs = adapter.normalize(adapter.fetch(_company()), _company())
    job = adapter.enrich(next(j for j in jobs if j.title == "Senior Program Manager"))
    assert job.location == "Columbus, OH; Remote/Teleworker US; Norfolk, VA"
    assert job.remote is True and job.workplace_type == "remote"
    assert "TS/SCI" in job.description_html
    assert job.posted_at == "2026-11-22"
    adapter.finish()

    # Next run: the detail comes from the cache, not the network.
    client2 = FakeClient(load_fixture("workday_jobs_page.json"))
    adapter2 = _adapter(client2, tmp_path)
    jobs2 = adapter2.normalize(adapter2.fetch(_company()), _company())
    again = adapter2.enrich(next(j for j in jobs2 if j.title == "Senior Program Manager"))
    assert client2.gets == []
    assert again.location == job.location


def test_cache_drops_jobs_no_longer_listed(load_fixture, tmp_path):
    path = "/job/Remote/Senior-Program-Manager_R-002"
    client = FakeClient(load_fixture("workday_jobs_page.json"),
                        details={path: load_fixture("workday_detail.json")})
    adapter = _adapter(client, tmp_path)
    adapter.fetch(_company())
    adapter._cache["/job/Gone/Old_R-999"] = {"fetched": "2026-11-20", "info": {}}
    adapter.finish()
    saved = json.loads((tmp_path / "acme_External.json").read_text())
    assert "/job/Gone/Old_R-999" not in saved


def test_pipeline_enriches_only_matched_and_tags_from_description(load_fixture, tmp_path):
    path = "/job/Remote/Senior-Program-Manager_R-002"
    client = FakeClient(load_fixture("workday_jobs_page.json"),
                        details={path: load_fixture("workday_detail.json")})
    adapter = _adapter(client, tmp_path)
    raw = adapter.run(_company())
    umbrellas, levels = load_roles()

    def broken_enrich(job):
        if job.title == "Capture Manager":
            raise RuntimeError("detail 500")
        return WorkdayAdapter.enrich(adapter, job)

    adapter.enrich = broken_enrich
    kept, n_matched = filter_jobs(raw, umbrellas, levels, load_locations(), load_tags(),
                                  drop_out_of_area=True, adapter=adapter)
    titles = {j.title for j in kept}
    # Payroll doesn't match a category, so no detail call; Capture's detail failed: dropped.
    assert titles == {"Senior Program Manager"}
    assert n_matched == 1  # counted after enrich; the failed one is logged, not "out of area"
    assert client.gets == [f"{API}{path}"]
    spm = kept[0]
    assert spm.location_type == "remote_us"
    assert "clearance" in spm.tags


def test_config_rejects_bad_workday_identifier(tmp_path):
    bad = tmp_path / "companies.yaml"
    bad.write_text(
        "companies:\n  - name: X\n    ats: workday\n    identifier: leidos\n"
        "    industry: [deftech]\n"
    )
    with pytest.raises(ConfigError, match="tenant/wdN/site"):
        load_companies(path=bad, valid_ats=KNOWN_ATS)

"""Daily run without Workday, and the Workday-only local run (scripts/scrape_workday.py)."""

import dataclasses
import json

import pytest

import scraper.main as main_mod
from scraper.config_loader import load_settings
from scraper.models import Company, Job
from scraper.writer import merge_and_write

GH = Company(name="Acme", ats="greenhouse", identifier="acme", industry=["saas"])
WD = Company(name="Leidos", ats="workday", identifier="leidos/wd5/External", industry=["deftech"])


def _job(company, n, title=None):
    title = title or f"Senior Program Manager {n}"  # distinct, or dedup merges them
    return Job(id=f"{company.ats}:{company.identifier}:{n}", title=title, company=company.name,
               industries=list(company.industry), url=f"https://e/{n}",
               source_ats=company.ats, location="Reston, VA")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """main.run against tmp data files, two companies and a fake scraper."""
    settings = dataclasses.replace(load_settings(), jobs_path="jobs.json", meta_path="meta.json")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    monkeypatch.setattr(main_mod, "load_settings", lambda: settings)
    monkeypatch.setattr(main_mod, "load_companies", lambda valid_ats=None: [GH, WD])
    calls = []
    jobs = {"greenhouse": [_job(GH, 1)], "workday": [_job(WD, 1), _job(WD, 2)]}

    def fake_scrape(company, client):
        calls.append(company.ats)
        status = {"company": company.name, "ats": company.ats, "identifier": company.identifier,
                  "ok": True, "count": len(jobs[company.ats]), "error": None}
        return list(jobs[company.ats]), status, None

    monkeypatch.setattr(main_mod, "scrape_company", fake_scrape)
    return tmp_path, calls, jobs


def _read(path, name):
    return json.loads((path / name).read_text())


def test_settings_mark_workday_local_only():
    assert "workday" in load_settings().local_only_ats


def test_daily_run_skips_workday_and_keeps_its_jobs(env):
    path, calls, _ = env
    assert main_mod.run(only_ats={"workday"}) == 0  # the weekly local run
    assert calls == ["workday"]
    calls.clear()

    assert main_mod.run() == 0  # daily: everything except Workday
    assert calls == ["greenhouse"]
    ids = {j["id"] for j in _read(path, "jobs.json")["jobs"]}
    assert ids == {"greenhouse:acme:1", "workday:leidos/wd5/External:1",
                   "workday:leidos/wd5/External:2"}
    meta = _read(path, "meta.json")
    wd = next(a for a in meta["adapters"] if a["ats"] == "workday")
    assert wd["carried"] is True and wd["count"] == 2  # status from the weekly run
    assert "workday" in meta["last_run_by_ats"]
    assert meta["local_only_ats"] == ["workday"]


def test_workday_run_keeps_other_boards_and_isnt_shrink_blocked(env):
    path, calls, jobs = env
    jobs["greenhouse"] = [_job(GH, n) for n in range(20)]
    assert main_mod.run() == 0  # daily: 20 Greenhouse jobs
    gh_run = _read(path, "meta.json")["last_run_by_ats"]["greenhouse"]
    calls.clear()

    assert main_mod.run(only_ats={"workday"}) == 0  # 2 fresh jobs vs 20 prior: not a shrink
    assert calls == ["workday"]
    data = _read(path, "jobs.json")["jobs"]
    assert sum(j["source_ats"] == "greenhouse" for j in data) == 20
    meta = _read(path, "meta.json")
    assert meta["last_run_by_ats"]["greenhouse"] == gh_run  # untouched
    assert meta["shrink_blocked"] is False


def test_never_run_workday_board_is_not_a_health_alert(env):
    path, _, _ = env
    assert main_mod.run() == 0
    meta = _read(path, "meta.json")
    wd = next(a for a in meta["adapters"] if a["ats"] == "workday")
    assert wd["error"] == "not run yet"
    assert meta["board_health"] == {"empty": [], "failing": []}


def test_shrink_guard_compares_only_boards_that_ran(tmp_path):
    jobs_path, meta_path = tmp_path / "jobs.json", tmp_path / "meta.json"
    seed = [_job(GH, n) for n in range(10)] + [_job(WD, n) for n in range(90)]
    merge_and_write(seed, {}, jobs_path=jobs_path, meta_path=meta_path, today="2026-11-22")
    # Greenhouse ran and still has 10; Workday was carried. Not a shrink.
    ok = merge_and_write(seed[:10], {}, jobs_path=jobs_path, meta_path=meta_path,
                         today="2026-11-23", retain_prefixes={"workday:leidos/wd5/External:"})
    assert ok["shrink_blocked"] is False
    # Greenhouse collapses to 1 of 10 while Workday is carried: blocked.
    bad = merge_and_write(seed[:1], {}, jobs_path=jobs_path, meta_path=meta_path,
                          today="2026-11-24", retain_prefixes={"workday:leidos/wd5/External:"})
    assert bad["shrink_blocked"] is True

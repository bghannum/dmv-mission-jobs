"""Board health: empty and failing boards, carried across runs, alerting only on new ones."""

import json

from scraper import health
from scraper.health import alerts, board_health


def _status(company, count=0, ok=True, error=None, ats="lever", identifier=None):
    return {
        "company": company, "ats": ats, "identifier": identifier or company.lower(),
        "ok": ok, "count": count, "error": error,
    }


def test_board_that_had_jobs_and_went_empty_alerts():
    prior = {"adapters": [_status("Shield", count=40)]}
    h = board_health([_status("Shield")], prior, "2026-11-22")
    assert h["empty"] == [{
        "company": "Shield", "ats": "lever", "identifier": "shield",
        "since": "2026-11-22", "new": True, "had_jobs": True,
    }]
    assert len(alerts(h)) == 1
    assert "verify_company.py --find" in alerts(h)[0]


def test_board_never_had_jobs_listed_but_no_alert():
    prior = {"adapters": [_status("Tiny", count=0)]}
    h = board_health([_status("Tiny")], prior, "2026-11-22")
    assert h["empty"][0]["had_jobs"] is False
    assert alerts(h) == []


def test_since_and_had_jobs_carry_forward_and_alert_only_once():
    day1 = {"adapters": [_status("Shield", count=40)]}
    h1 = board_health([_status("Shield")], day1, "2026-11-22")
    day2 = {"adapters": [_status("Shield")], "board_health": h1}
    h2 = board_health([_status("Shield")], day2, "2026-11-23")
    assert h2["empty"][0]["since"] == "2026-11-22"
    assert h2["empty"][0]["had_jobs"] is True
    assert h2["empty"][0]["new"] is False
    assert alerts(h2) == []


def test_board_recovers_and_drops_off_the_list():
    h1 = board_health([_status("Shield")], {"adapters": [_status("Shield", 5)]}, "2026-11-22")
    h2 = board_health([_status("Shield", count=7)], {"board_health": h1}, "2026-11-23")
    assert h2 == {"empty": [], "failing": []}


def test_failing_board_alerts_once():
    err = "HTTPError: 404"
    h1 = board_health([_status("Cedar", ok=False, error=err)], {}, "2026-11-22")
    assert h1["failing"][0]["since"] == "2026-11-22"
    assert len(alerts(h1)) == 1
    h2 = board_health([_status("Cedar", ok=False, error=err)], {"board_health": h1}, "2026-11-23")
    assert h2["failing"][0]["since"] == "2026-11-22"
    assert alerts(h2) == []


def test_prior_meta_without_identifier_falls_back_to_company_name():
    old = {"company": "Shield", "ats": "lever", "ok": True, "count": 40, "error": None}
    h = board_health([_status("Shield")], {"adapters": [old]}, "2026-11-22")
    assert h["empty"][0]["had_jobs"] is True


def test_disabled_adapter_ignored():
    h = board_health([_status("G", ats="getro", error="disabled")], {}, "2026-11-22")
    assert h == {"empty": [], "failing": []}


def test_cli_exit_code_and_summary(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    meta = tmp_path / "meta.json"
    bh = board_health([_status("Shield")], {"adapters": [_status("Shield", 40)]}, "2026-11-22")
    meta.write_text(json.dumps({"board_health": bh}))
    assert health.main([str(meta)]) == 1
    assert "::error title=Board health::Shield" in capsys.readouterr().out
    assert "Went silent" in summary.read_text()

    quiet = tmp_path / "quiet.json"
    quiet.write_text(json.dumps({"board_health": {"empty": [], "failing": []}}))
    assert health.main([str(quiet)]) == 0

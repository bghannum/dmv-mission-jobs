"""Validate the live config — this is the guardrail for community 'add a company' PRs."""

import pytest

from scraper.adapters.registry import KNOWN_ATS
from scraper.config_loader import (
    ConfigError,
    load_companies,
    load_roles,
    load_settings,
)
from scraper.models import INDUSTRY_VOCAB


def test_live_companies_valid():
    companies = load_companies(valid_ats=KNOWN_ATS)
    assert companies, "companies.yaml must list at least one company"
    for c in companies:
        assert c.ats in KNOWN_ATS
        assert c.identifier
        assert set(c.industry) <= INDUSTRY_VOCAB


def test_live_roles_and_settings_load():
    umbrellas, levels = load_roles()
    assert umbrellas
    assert "order" in levels and "detection" in levels
    settings = load_settings()
    assert settings.user_agent
    assert 0 < settings.max_shrink_fraction <= 1


def test_unknown_ats_rejected(tmp_path):
    bad = tmp_path / "companies.yaml"
    bad.write_text(
        "companies:\n  - name: X\n    ats: workday\n    identifier: x\n    industry: [grc]\n"
    )
    with pytest.raises(ConfigError):
        load_companies(path=bad, valid_ats=KNOWN_ATS)


def test_unknown_industry_rejected(tmp_path):
    bad = tmp_path / "companies.yaml"
    bad.write_text(
        "companies:\n  - name: X\n    ats: ashby\n    identifier: x\n    industry: [crypto]\n"
    )
    with pytest.raises(ConfigError):
        load_companies(path=bad, valid_ats=KNOWN_ATS)


def test_invalid_priority_rejected(tmp_path):
    bad = tmp_path / "companies.yaml"
    bad.write_text(
        "companies:\n  - name: X\n    ats: ashby\n    identifier: x\n"
        "    industry: [grc]\n    priority: 9\n"
    )
    with pytest.raises(ConfigError):
        load_companies(path=bad, valid_ats=KNOWN_ATS)


def test_priority_defaults_to_three(tmp_path):
    ok = tmp_path / "companies.yaml"
    ok.write_text(
        "companies:\n  - name: X\n    ats: ashby\n    identifier: x\n    industry: [grc]\n"
    )
    assert load_companies(path=ok, valid_ats=KNOWN_ATS)[0].priority == 3

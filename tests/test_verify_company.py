"""scripts/verify_company.py helpers and the shared scrape filter it reuses."""

import importlib.util
from pathlib import Path

import yaml

from scraper.config_loader import load_locations, load_roles, load_tags
from scraper.main import filter_jobs
from scraper.models import Company, Job

_SPEC = importlib.util.spec_from_file_location(
    "verify_company", Path(__file__).parent.parent / "scripts" / "verify_company.py"
)
vc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vc)


def _job(title, location, remote=False, industries=("saas",)):
    return Job(id=title, title=title, company="Acme", industries=list(industries),
               url="https://example.com", source_ats="greenhouse", location=location,
               remote=remote)


def _filter(jobs, ambiguous=None):
    umbrellas, levels = load_roles()
    return filter_jobs(jobs, umbrellas, levels, load_locations(), load_tags(),
                       drop_out_of_area=True, ambiguous=ambiguous)


def test_filter_jobs_matches_role_then_location():
    jobs = [
        _job("Senior Product Manager", "Arlington, VA"),
        _job("Solutions Architect", "Remote - US", remote=True),
        _job("Account Executive", "London, UK"),       # role matches, out of area
        _job("Office Coordinator", "Washington, DC"),  # not a target role
    ]
    kept, n_matched = _filter(jobs)
    assert n_matched == 3
    assert [(j.title, j.location_type) for j in kept] == [
        ("Senior Product Manager", "dmv_onsite"),
        ("Solutions Architect", "remote_us"),
    ]


def test_filter_jobs_records_bare_washington():
    ambiguous = []
    kept, _ = _filter([_job("Product Manager", "Washington")], ambiguous)
    assert [j.location_type for j in kept] == ["unknown"]
    assert ambiguous == [{"company": "Acme", "title": "Product Manager",
                          "location": "Washington"}]


def test_already_listed_by_name_or_board():
    cos = [Company(name="Scale AI", ats="greenhouse", identifier="scaleai", industry=["ai"])]
    assert vc.already_listed(cos, "scale ai", "lever", "x") == "Scale AI"
    assert vc.already_listed(cos, "Other", "greenhouse", "ScaleAI") == "Scale AI"
    assert vc.already_listed(cos, "Other", "ashby", "scaleai") is None


def test_summarize_counts():
    kept, n = _filter([_job("Product Manager", "Reston, VA"), _job("Sales Engineer", "Remote")])
    s = vc.summarize([None] * 5, kept, n)
    assert (s["fetched"], s["role_matched"], s["kept"]) == (5, 2, 2)
    assert sum(s["by_location"].values()) == 2


def test_yaml_entry_is_valid_companies_yaml():
    text = vc.yaml_entry('Acme "Labs"', "ashby", "Acme-Labs", ["saas", "ai"], "https://acme.io")
    entry = yaml.safe_load("companies:\n" + text)["companies"][0]
    assert entry == {"name": 'Acme "Labs"', "ats": "ashby", "identifier": "Acme-Labs",
                     "industry": ["saas", "ai"], "homepage": "https://acme.io"}

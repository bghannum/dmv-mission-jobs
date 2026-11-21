"""Clearance and public-sector tagging (config/tags.yaml)."""

import pytest

from scraper.config_loader import load_tags
from scraper.models import Job
from scraper.tagging import apply_tags, html_to_text, tags_for

RULES = load_tags()

EEO = (
    "We are an equal opportunity employer. All qualified applicants will receive "
    "consideration without regard to any status protected by federal, state and local "
    "laws. Please bring a valid government-issued ID to your interview."
)


@pytest.mark.parametrize(
    "title,department,description",
    [
        ("Solutions Engineer, TS/SCI", None, ""),
        ("Account Executive", None, "Candidates must hold an active Top Secret clearance."),
        ("Program Manager", None, "Ability to obtain a security clearance is required."),
        ("Program Manager", None, "Must be able to pass a Public Trust investigation."),
        ("Systems Engineer (Polygraph)", None, ""),
    ],
)
def test_clearance(title, department, description):
    assert "clearance" in tags_for(
        RULES, title=title, department=department, description=description.lower()
    )


@pytest.mark.parametrize(
    "title,department,description",
    [
        ("Account Executive, Federal", None, ""),
        ("Solutions Architect, Public Sector", None, ""),
        ("Account Executive", "Public Sector Sales", ""),
        ("Account Executive, SLED", None, ""),
        ("Customer Success Manager, DoD", None, ""),
        ("Account Executive", None, "you will sell to federal civilian agencies and the dod."),
        ("Product Manager", None,
         "serve the intelligence community and the department of defense."),
        ("Product Manager", None, "build tools for the u.s. government and federal agencies."),
        ("USG Growth Lead", None, ""),
    ],
)
def test_public_sector(title, department, description):
    assert "public_sector" in tags_for(
        RULES, title=title, department=department, description=description
    )


@pytest.mark.parametrize(
    "title,department,description",
    [
        ("Product Manager", "Product", EEO.lower()),          # EEO boilerplate
        ("Cyber Defense Analyst", None, ""),                    # cyber "defense", not DoD
        ("Product Manager, Threat Defense", None, ""),
        ("Account Executive", None, "learn our defense-in-depth platform."),
        ("Product Manager", "Product", "plan the product roadmap."),
        ("Customs Clearance Specialist", None, ""),             # not a security clearance
        # One-off company blurb in every posting: needs 2+ description hits.
        ("Senior ML Engineer", "Engineering",
         "we're trusted by half of the fortune 500 and government agencies around the world."),
        # E-Verify boilerplate
        ("Analytics Engineer", None,
         "we participate in e-verify and will provide the federal government with your form "
         "i-9 information. we also partner with the federal government on nothing else."),
    ],
)
def test_no_false_public_sector(title, department, description):
    assert "public_sector" not in tags_for(
        RULES, title=title, department=department, description=description
    )


def test_customs_clearance_does_tag_clearance_keyword():
    # Documented limitation: bare "clearance" in a title still tags. Rare in board roles.
    assert "clearance" in tags_for(RULES, title="Customs Clearance Specialist")


def test_eeo_boilerplate_does_not_tag_clearance():
    assert tags_for(RULES, title="Product Manager", description=EEO.lower()) == []


def test_deftech_industry_tags_public_sector():
    assert tags_for(RULES, title="Product Manager", industries=["deftech"]) == ["public_sector"]
    assert tags_for(RULES, title="Product Manager", industries=["cybersecurity"]) == []


def test_html_to_text_handles_escaped_html():
    assert html_to_text("&lt;p&gt;Active &amp;amp; TS/SCI&lt;/p&gt;") == "active & ts/sci"
    assert html_to_text(None) == ""


def test_apply_tags_uses_description_html():
    job = Job(
        id="x:1", title="Program Manager", company="Acme", industries=["cybersecurity"],
        url="https://e/1", source_ats="greenhouse",
        description_html="<p>Requires an active <b>TS/SCI</b> clearance.</p>",
    )
    assert apply_tags(job, RULES).tags == ["clearance"]

"""Truth table for the DMV-or-remote location model (PLAN.md, "Location")."""

import pytest

from scraper.config_loader import load_locations
from scraper.location import (
    DMV_HYBRID,
    DMV_ONSITE,
    REMOTE_US,
    UNKNOWN,
    classify_location_type,
)

RULES = load_locations()


@pytest.mark.parametrize(
    "location,remote,expected",
    [
        # DMV on-site
        ("Reston, VA", False, DMV_ONSITE),
        ("Fort Meade, MD", False, DMV_ONSITE),
        ("Washington, DC", False, DMV_ONSITE),
        ("Washington, D.C.", False, DMV_ONSITE),
        ("Washington D.C.", False, DMV_ONSITE),
        ("Washington, District of Columbia, United States", False, DMV_ONSITE),
        ("Arlington, Virginia", False, DMV_ONSITE),
        ("Laurel, Maryland", False, DMV_ONSITE),
        ("Annapolis Junction, MD", False, DMV_ONSITE),
        # DMV hybrid counts as DMV
        ("Hybrid - McLean", False, DMV_HYBRID),
        ("Herndon, VA (Hybrid)", False, DMV_HYBRID),
        # Multi-location postings are kept if ANY location is in the DMV
        ("Reston, VA; Austin, TX", False, DMV_ONSITE),
        ("Austin, TX / Bethesda, MD", False, DMV_ONSITE),
        # DMV + remote -> the role is open to US remote
        ("Remote or Washington, DC", False, REMOTE_US),
        ("Reston, VA", True, REMOTE_US),
        # US remote, including a bare "Remote" with no country
        ("Remote (US)", False, REMOTE_US),
        ("Remote - United States", False, REMOTE_US),
        ("Remote", False, REMOTE_US),
        ("", True, REMOTE_US),
        # Remote scope (2026-11-22): generic US remote or remote in VA/MD/DC only
        ("United States", True, REMOTE_US),
        ("Remote, VA", False, REMOTE_US),
        ("Remote, Maryland", False, REMOTE_US),
        ("Remote - Washington D.C.", False, REMOTE_US),
        ("Remote, AZ; Remote, NV; Remote, VA", False, REMOTE_US),
        ("Boston or Remote", False, REMOTE_US),
        ("Charlotte, Denver, New York, Atlanta, Remote", False, REMOTE_US),
        ("SF, NY, SEA, Remote-US", False, REMOTE_US),
        ("Remote U.S. or Pittsburgh, PA", False, REMOTE_US),
        ("New York City (Preferred) / Open to Remote", False, REMOTE_US),
        ("Remote, VA", False, REMOTE_US),
        ("Virginia, USA, Remote", False, REMOTE_US),
        ("San Francisco, CA, US; Remote, US", False, REMOTE_US),
        ("San Francisco, CA, Portland, OR, or Remote within Canada or United States", False,
         REMOTE_US),
        ("District of Columbia, USA, Remote; Virginia, USA, Remote", False, REMOTE_US),
        ("Austin, TX", True, None),
        ("Texas, United States", True, None),
        ("Remote, Arizona; Remote, Nevada", False, None),
        ("Remote - California", False, None),
        ("Remote, CA", False, None),
        ("Texas, US (Remote)", False, None),
        ("Remote, Colorado, United States, AMER", False, None),
        ("Remote (Houston, TX)", False, None),
        ("US-TX-Remote", False, None),
        ("Remote, United Kingdom", False, None),
        ("California, USA, Remote", False, None),
        ("Remote, West Virginia", False, None),
        ("Remote - UK", False, None),
        ("Remote, Ontario, Canada", False, None),
        # A DMV office plus remote elsewhere is on-site for a DMV reader
        ("Herndon, VA; Remote, CA", False, DMV_ONSITE),
        ("Herndon, VA; Remote, US", False, REMOTE_US),
        # Bare "Washington" is ambiguous: kept as unknown and logged
        ("Washington", False, UNKNOWN),
        ("Washington, United States", False, UNKNOWN),
        ("Remote - Washington", False, UNKNOWN),
        # Dropped
        ("Remote - Canada", False, None),
        ("Remote, EMEA", False, None),
        ("Austin, TX", False, None),
        ("San Francisco, CA", False, None),
        ("Seattle, Washington", False, None),
        ("Washington State", False, None),
        # "City, Washington" and Washington among other states are the state, not DC
        ("Tacoma, Washington, United States", False, None),
        ("Kent, Washington", False, None),
        ("Remote - California; Remote - Oregon; Remote - Washington", False, None),
        ("Nevada; Remote - California; Remote - Washington", False, None),
        ("Arlington, TX", False, None),
        ("London, UK", False, None),
        ("", False, None),
        (None, False, None),
    ],
)
def test_location_type(location, remote, expected):
    assert classify_location_type(location, remote, RULES) == expected


def test_state_abbreviations_expand_to_full_names():
    assert "columbia, maryland" in RULES.dmv_match
    assert "vienna, virginia" in RULES.dmv_match


def test_ats_hybrid_workplace_marks_dmv_hybrid():
    assert classify_location_type("Reston, VA", False, RULES, "hybrid") == DMV_HYBRID
    assert classify_location_type("Reston, VA", False, RULES, "onsite") == DMV_ONSITE
    # Hybrid outside the DMV is still out of area.
    assert classify_location_type("Hybrid - San Francisco, CA", False, RULES, "hybrid") is None


@pytest.mark.parametrize(
    "title,location,expected",
    [
        # A Washington State place in the title settles a bare "Washington"
        ("Enterprise Account Executive - Pacific Northwest", "Washington, United States", None),
        ("Enterprise Account Executive - Seattle", "Washington, United States", None),
        ("Account Executive, PNW", "Washington", None),
        ("Solutions Engineer (Tacoma)", "Washington", None),
        # ...and if the role is remote, it's US remote (within the state)
        ("Strategic Account Executive - Pacific Northwest", "Remote - Washington", None),
        # No hint: stays uncertain
        ("Solutions Architect - Games", "Washington", UNKNOWN),
        ("Senior SRE, Managed Gateways", "Washington, United States", UNKNOWN),
        # Hints only matter for a bare "Washington"; a DC location stays DMV
        ("Account Executive, Pacific Northwest and Mid-Atlantic", "Washington, DC", DMV_ONSITE),
        # Whole words only: "pnw" inside another word doesn't count
        ("Snwpnwx Engineer", "Washington", UNKNOWN),
    ],
)
def test_title_settles_bare_washington(title, location, expected):
    assert classify_location_type(location, False, RULES, title=title) == expected

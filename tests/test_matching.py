"""Truth table for role-umbrella matching and level detection."""

import pytest

from scraper.config_loader import load_roles
from scraper.matching import detect_level, match_roles

UMBRELLAS, LEVELS = load_roles()


@pytest.mark.parametrize(
    "title,umbrella,role",
    [
        ("Senior Frontend Engineer", "engineering", "frontend"),
        ("Staff Full Stack Engineer", "engineering", "full_stack"),
        ("Principal DevEx Engineer", "engineering", "devops"),
        ("AI Engineer, Agentic Systems", "engineering", "agentic"),
        ("Staff Product Manager", "product", "product_manager"),
        ("Technical Program Manager", "program", "technical_program_manager"),
        ("Senior Product Analyst", "product", "product_analytics"),
        ("Analytics Engineer", "product", "product_analytics"),
        ("Senior Product Designer", "design", "product_designer"),
        ("Senior Technical Writer", "engineering", "tech_writer"),
        ("Documentation Engineer", "engineering", "tech_writer"),
        # Phase 1 categories
        ("Senior Product Owner", "product", "product_manager"),
        ("Senior TPM, Platform", "program", "technical_program_manager"),
        ("Program Manager, Space Systems", "program", "program_manager"),
        ("Solutions Architect, Public Sector", "architecture", "solutions_architect"),
        ("Sales Engineer", "architecture", "solutions_architect"),
        ("Forward Deployed Engineer", "architecture", "solutions_architect"),
        ("Cloud Architect", "architecture", "enterprise_architect"),
        ("Federal Account Executive, DoD", "gtm", "sales"),
        ("Enterprise Account Manager", "gtm", "sales"),
        ("Capture Manager", "gtm", "business_development"),
        ("Director, Business Development", "gtm", "business_development"),
        ("Strategic Partnerships Lead", "gtm", "partnerships"),
        ("VP of Growth", "growth", "growth"),
        ("Revenue Operations Manager", "growth", "growth"),
        ("Strategy & Operations Lead", "growth", "strategy_ops"),
        ("Chief of Staff", "growth", "strategy_ops"),
        ("Customer Success Manager, Government", "customer", "customer_success"),
        ("Mission Success Manager", "customer", "customer_success"),
        ("Technical Account Manager", "customer", "customer_success"),
    ],
)
def test_matches_expected_role(title, umbrella, role):
    umbs, roles = match_roles(title, UMBRELLAS)
    assert umbrella in umbs
    assert role in roles


@pytest.mark.parametrize(
    "title",
    [
        "Product Marketing Manager",  # excluded from product_manager
        "Account Executive",
        "Office Manager",
        "Customer Success Manager",
        "Executive Assistant",
        "Security Analyst",           # excluded from product_analytics
        "SOC Analyst",                # excluded from product_analytics
        "Grant Writer",               # excluded from tech_writer
    ],
)
def test_non_target_roles_are_dropped(title):
    _, roles = match_roles(title, UMBRELLAS)
    # "Office Manager"/"Customer Success Manager" contain "manager" but match no target role
    # because manager is a LEVEL keyword, not a role keyword. Security/SOC analysts must not
    # fall into product_analytics; grant writers must not fall into tech_writer.
    assert "product_manager" not in roles
    assert "product_analytics" not in roles
    assert "tech_writer" not in roles


@pytest.mark.parametrize(
    "title,level",
    [
        ("Staff Full Stack Engineer", "staff"),
        ("Senior Frontend Engineer", "senior"),
        ("Principal DevEx Engineer", "principal"),
        ("Director of Product", "director"),
        ("VP of Engineering", "vp"),
        ("Software Engineer Intern", "intern"),
        ("Full Stack Engineer", "mid"),
    ],
)
def test_level_detection(title, level):
    assert detect_level(title, LEVELS) == level


@pytest.mark.parametrize(
    "title",
    [
        "Product Marketing Manager",
        "Growth Marketing Manager",
        "Customer Support Specialist",
        "Content Strategy Lead",
        "Brand Strategy Director",
        "Technical Recruiter",          # recruiting is not a board category
        "Office Manager",
        "Executive Assistant",
    ],
)
def test_out_of_scope_titles_match_nothing(title):
    assert match_roles(title, UMBRELLAS) == ([], [])


def test_sales_engineer_is_architecture_not_sales():
    umbs, roles = match_roles("Senior Sales Engineer", UMBRELLAS)
    assert "architecture" in umbs
    assert "gtm" not in umbs and "sales" not in roles


def test_technical_account_manager_is_customer_not_sales():
    _, roles = match_roles("Technical Account Manager", UMBRELLAS)
    assert roles == ["customer_success"]


def test_technical_program_manager_is_not_also_program_manager():
    _, roles = match_roles("Technical Program Manager", UMBRELLAS)
    assert roles == ["technical_program_manager"]


def test_exclude_departments_drops_growth_in_marketing_or_engineering():
    assert match_roles("Growth Lead", UMBRELLAS, department="Growth Marketing") == ([], [])
    assert match_roles("Growth Lead", UMBRELLAS, department="Engineering") == ([], [])
    assert match_roles("Growth Lead", UMBRELLAS, department="Business Development")[1] == [
        "growth"
    ]
    assert match_roles("Growth Engineer", UMBRELLAS) == ([], [])

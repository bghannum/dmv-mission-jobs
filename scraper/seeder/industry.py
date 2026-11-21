"""Suggest `industry` values for a discovered company from its one-paragraph description.

Deliberately conservative: these are starting values for human review in the PR, and
`deftech` matters most because it tags every job at the company `public_sector`.
"""

from __future__ import annotations

import re

# a16z sector page -> board industry.
SECTOR_INDUSTRY = {
    "ai": "ai",
    "american-dynamism": "american-dynamism",
    "bio-health": "healthtech",
    "consumer": "consumer",
    "enterprise": "saas",
    "fintech": "fintech",
    "infra": "saas",
    "speedrun": "games",
}

# Defense phrases. Bare "defense" isn't trusted: cybersecurity copy says "threat defense"
# and a bank lending to "AI, defense, manufacturing" companies isn't a defense company.
DEFENSE_PHRASES = ("national security", "department of defense", "warfighter", "warfighters",
                   "military", "armed forces", "munitions", "counter-drone", "hypersonic", "dod",
                   "naval", "warfare", "defense technology", "defense tech", "defense company",
                   "defense organizations", "defense contractors", "aerospace and defense",
                   "defense industrial base", "defense and intelligence")

# Extra detail on top of the sector. Phrases match as whole words/phrases.
RULES: list[tuple[str, tuple[str, ...]]] = [
    ("space", ("satellite", "satellites", "spacecraft", "orbital", "in orbit", "launch vehicle",
               "rocket", "rockets", "aerospace", "space station", "space-based", "lunar")),
    ("govtech", ("government agencies", "governments", "public sector", "municipal",
                 "public safety", "state and local", "govtech", "law enforcement",
                 "first responders", "911")),
    ("cybersecurity", ("cybersecurity", "cyber security", "threat detection",
                       "security operations", "identity security", "application security",
                       "cloud security", "zero trust", "vulnerabilities")),
    ("crypto", ("crypto", "cryptocurrency", "blockchain", "web3", "bitcoin", "ethereum",
                "stablecoin", "stablecoins", "defi", "onchain", "on-chain", "nfts")),
    ("fintech", ("payments", "banking", "fintech", "lending", "insurance", "financial services",
                 "credit card", "payroll", "brokerage", "neobank", "mortgage")),
    ("healthtech", ("healthcare", "clinical", "patients", "biotech", "therapeutics", "pharma",
                    "genomics", "hospitals")),
    ("games", ("video game", "video games", "gaming", "esports", "game studio")),
    ("ai", ("artificial intelligence", "machine learning", "llm", "llms",
            "large language model", "large language models", "generative ai",
            "foundation model", "foundation models", "ai agents", "agentic")),
]
FALLBACK = "saas"


def _has(text: str, phrase: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None


def suggest_industries(name: str, overview: str, sectors=()) -> list[str]:
    """a16z sectors first, then keyword detail. Always returns at least one industry."""
    text = re.sub(r"\s+", " ", f"{name} {overview}".lower())
    found: list[str] = []

    def add(ind: str) -> None:
        if ind not in found:
            found.append(ind)

    # A company that calls itself "... Defense" is one, even with no description.
    if any(_has(text, p) for p in DEFENSE_PHRASES) or _has(name.lower(), "defense"):
        add("deftech")
    for sector in sectors:
        if sector in SECTOR_INDUSTRY:
            add(SECTOR_INDUSTRY[sector])
    for ind, phrases in RULES:
        if any(_has(text, p) for p in phrases):
            add(ind)
    if not found or found == ["ai"]:
        add(FALLBACK)
    return found

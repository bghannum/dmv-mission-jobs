"""Classify free-text job locations.

Two layers:

- `classify` / `is_us`: US vs non-US vs unknown (from the original project). Still used to
  decide whether a remote role is US-eligible.
- `classify_location_type`: the board's DMV-or-remote model (PLAN.md, "Location").

The original US-vs-non-US notes follow.

Location strings vary a lot across ATSes ("US, Remote", "San Francisco, CA",
"London, UK", "Bengaluru, India", "Remote - EMEA", "Remote"). The goal is to keep a role
if it is hiring in the US (even when it also hires elsewhere) and drop clearly non-US
roles. US signals are checked FIRST so a multi-region role like "San Francisco, CA / London"
is kept.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 50 states + DC + Puerto Rico. Matched only as uppercase codes after a comma ("City, CA")
# to avoid false positives from words like "in"/"or"/"ok" or country codes.
_STATE_ABBREV = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR",
}

_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
    "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
    "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york", "north carolina",
    "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island",
    "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia", "puerto rico",
}

# Explicit US phrases (substring match on the lowercased string).
_US_PHRASES = (
    "united states", "u.s.a", "u.s.", "us-remote", "us remote", "remote - us",
    "remote-us", "remote, us", "remote (us", "remote us", "anywhere in the us",
    "anywhere in the u.s", "nationwide", "remote - united states", "remote, united states",
    "remote (united states", "washington, d.c", "washington dc",
)

# Clear non-US signals (country names / regions / major non-US hub cities). Substring match.
_NON_US = (
    # regions
    "emea", "apac", "latam", "europe", "european union", "middle east", "asia pacific",
    # countries
    "united kingdom", "england", "scotland", "wales", "northern ireland", "ireland",
    "canada", "mexico", "brazil", "brasil", "argentina", "chile", "colombia", "peru",
    "uruguay", "costa rica", "germany", "france", "spain", "portugal", "italy",
    "netherlands", "belgium", "switzerland", "austria", "sweden", "norway", "denmark",
    "finland", "poland", "czech", "slovakia", "romania", "bulgaria", "hungary", "greece",
    "ukraine", "serbia", "croatia", "lithuania", "latvia", "estonia", "iceland", "turkey",
    "israel", "united arab emirates", "saudi arabia", "qatar", "egypt", "south africa",
    "nigeria", "kenya", "morocco", "india", "pakistan", "bangladesh", "sri lanka",
    "china", "hong kong", "taiwan", "japan", "south korea", "singapore", "malaysia",
    "indonesia", "philippines", "vietnam", "thailand", "australia", "new zealand",
    # hub cities
    "london", "dublin", "manchester", "edinburgh", "berlin", "munich", "hamburg",
    "frankfurt", "paris", "lyon", "madrid", "barcelona", "lisbon", "porto", "amsterdam",
    "rotterdam", "brussels", "zurich", "geneva", "vienna", "stockholm", "oslo",
    "copenhagen", "helsinki", "warsaw", "krakow", "prague", "bucharest", "sofia",
    "budapest", "athens", "vilnius", "tallinn", "riga", "belgrade", "tel aviv", "dubai",
    "abu dhabi", "cairo", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai",
    "new delhi", "gurgaon", "gurugram", "noida", "chennai", "kolkata", "ahmedabad",
    "karachi", "lahore", "dhaka", "colombo", "beijing", "shanghai", "shenzhen",
    "tokyo", "osaka", "seoul", "taipei", "kuala lumpur", "jakarta", "manila",
    "ho chi minh", "bangkok", "sydney", "melbourne", "brisbane", "auckland",
    "toronto", "vancouver", "montreal", "ottawa", "calgary", "waterloo", "mexico city",
    "sao paulo", "são paulo", "buenos aires", "bogota", "bogotá", "santiago", "lima",
)

# "City, ST" — uppercase 2-letter code after a comma.
_CITY_STATE_RE = re.compile(r",\s*([A-Z]{2})(?=\b|\s|/|;|$)")
# Standalone US / USA token.
_US_TOKEN_RE = re.compile(r"\b(us|usa)\b")


def _has_us_signal(text: str, low: str) -> bool:
    if any(p in low for p in _US_PHRASES):
        return True
    if any(name in low for name in _STATE_NAMES):
        return True
    if _US_TOKEN_RE.search(low):
        return True
    if any(code in _STATE_ABBREV for code in _CITY_STATE_RE.findall(text)):
        return True
    return False


def classify(location: str | None) -> bool | None:
    """Return True (US), False (non-US), or None (unknown/ambiguous)."""
    text = (location or "").strip()
    if not text:
        return None
    low = text.lower()
    if _has_us_signal(text, low):
        return True
    if any(tok in low for tok in _NON_US):
        return False
    return None


def is_us(location: str | None, *, include_unknown: bool = True) -> bool:
    """Whether a role should be kept under a US-only filter.

    US signals win over non-US (a role hiring in the US stays even if also elsewhere).
    Ambiguous/blank locations fall back to `include_unknown` (most curated companies that
    post a bare "Remote" are US-based).
    """
    verdict = classify(location)
    if verdict is None:
        return include_unknown
    return verdict


# --- DMV-or-remote model -------------------------------------------------------------------

DMV_ONSITE = "dmv_onsite"
DMV_HYBRID = "dmv_hybrid"
REMOTE_US = "remote_us"
UNKNOWN = "unknown"  # bare "Washington": DC or Washington state? Logged for review.
OTHER = "other"  # out of area; only kept when drop_out_of_area is off

# "Washington" NOT followed by a DC / state qualifier, e.g. "Washington" or
# "Washington, United States". "Washington, DC" forms are matched as DMV before this runs.
_BARE_WASHINGTON_RE = re.compile(
    r"\bwashington\b(?!\s*,?\s*(?:d\.?\s?c\b|district|wa\b|state\b))"
)
_WASHINGTON_STATE_HINTS = ("washington state", "seattle", "bellevue", "redmond", "kirkland")


@dataclass(frozen=True)
class LocationRules:
    dmv_match: tuple[str, ...]
    dmv_exclude: tuple[str, ...]
    remote_keywords: tuple[str, ...]
    hybrid_keywords: tuple[str, ...]


def is_dmv(low: str, rules: LocationRules) -> bool:
    for phrase in rules.dmv_exclude:
        low = low.replace(phrase, " ")
    return any(m in low for m in rules.dmv_match)


def is_bare_washington(low: str) -> bool:
    if any(h in low for h in _WASHINGTON_STATE_HINTS):
        return False
    return bool(_BARE_WASHINGTON_RE.search(low))


def classify_location_type(
    location: str | None,
    remote: bool,
    rules: LocationRules,
    workplace_type: str | None = None,
) -> str | None:
    """Assign a location_type, or None when the role is out of area.

    Order matters:
    1. Any DMV location (multi-location postings count if ANY location is in the DMV):
       hybrid (ATS workplace_type or text) -> dmv_hybrid; else remote -> remote_us;
       else dmv_onsite.
    2. A bare "Washington" -> unknown (kept and logged; the rule is decided in Phase 2).
    3. Remote and US-eligible -> remote_us. A bare "Remote" with no country counts as US.
       Remote with only non-US signals ("Remote - Canada") -> None.
    4. Anything else (other US cities, non-US, blank) -> None.
    """
    text = (location or "").strip()
    low = re.sub(r"\s+", " ", text.lower())
    is_remote = remote or any(k in low for k in rules.remote_keywords)
    if low and is_dmv(low, rules):
        if workplace_type == "hybrid" or any(k in low for k in rules.hybrid_keywords):
            return DMV_HYBRID
        return REMOTE_US if is_remote else DMV_ONSITE
    if low and is_bare_washington(low):
        return UNKNOWN
    if is_remote:
        return REMOTE_US if classify(text) is not False else None
    return None

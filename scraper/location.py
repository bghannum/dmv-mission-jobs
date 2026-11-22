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
# Places in a job TITLE that settle a bare "Washington" location as Washington State.
_WA_TITLE_HINTS = ("washington state", "seattle", "bellevue", "redmond", "kirkland", "tacoma",
                   "spokane", "everett", "olympia", "pacific northwest", "pnw")


def title_says_washington_state(title: str | None) -> bool:
    low = (title or "").lower()
    return any(re.search(r"(?<![a-z])" + re.escape(h) + r"(?![a-z])", low)
               for h in _WA_TITLE_HINTS)


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


_OTHER_STATES = tuple(
    sorted(_STATE_NAMES - {"washington", "district of columbia"}, key=len, reverse=True)
)


def is_bare_washington(low: str) -> bool:
    """A "Washington" that could be DC or the state. Not ambiguous when:
    - a WA city or "Washington State" is named;
    - it follows a city ("Tacoma, Washington"), which makes it the state;
    - other US states are listed alongside it ("Remote - California; Remote - Washington").
    """
    if any(h in low for h in _WASHINGTON_STATE_HINTS):
        return False
    if re.search(r"[a-z.]\s*,\s*washington\b(?!\s*,?\s*(?:d\.?\s?c\b|district))", low):
        return False
    if any(re.search(r"\b" + re.escape(st) + r"\b", low) for st in _OTHER_STATES):
        return False
    return bool(_BARE_WASHINGTON_RE.search(low))


# --- Remote scope: generic US remote, or remote in VA/MD/DC (decided 2026-11-22) ----------

_DMV_STATES = {"VA", "MD", "DC"}
# Longest names first so "west virginia" is consumed before "virginia".
_STATE_NAME_ORDER = sorted(_STATE_NAMES, key=len, reverse=True)
_DC_RE = re.compile(r"\bwashington,?\s*d\.?\s?c\b\.?|\bdistrict of columbia\b")
_ABBREV_TOKEN_RE = re.compile(r"(?<![A-Za-z])([A-Z]{2})(?![A-Za-z])")
_UK_RE = re.compile(r"\buk\b")
# Parts of a location string: "A; B", "A | B", and "Boston or Remote".
_PART_SPLIT_RE = re.compile(r"[;|]|\s+or\s+(?=remote)", re.IGNORECASE)


def _named_states(part: str) -> set[str]:
    """US states named in one location part: "DC", "VA", "CA", ... ("Washington" alone = WA)."""
    low = part.lower()
    found: set[str] = set()
    if _DC_RE.search(low):
        found.add("DC")
        low = _DC_RE.sub(" ", low)
    for name in _STATE_NAME_ORDER:
        pattern = r"\b" + re.escape(name) + r"\b"
        if re.search(pattern, low):
            found.add("DMV" if name in ("virginia", "maryland") else name)
            low = re.sub(pattern, " ", low)
    found |= {code for code in _ABBREV_TOKEN_RE.findall(part) if code in _STATE_ABBREV}
    return found


_COUNTRY = r"(?:usa|us|u\.s\.?|united states)"
# "California, USA, Remote", "Texas, US (Remote)", "Remote, Colorado, United States, AMER"
_STATE_COUNTRY_REMOTE_RE = re.compile(
    r"^([a-z .]+?),\s*" + _COUNTRY + r"\s*[,(]?\s*remote\)?$"
)
_REMOTE_STATE_COUNTRY_RE = re.compile(r"^remote,\s*([a-z .]+?),\s*" + _COUNTRY + r"\b")
_TOKEN_SPLIT_RE = re.compile(r"[,/]|\s+or\s+")
_GENERIC_WORDS_RE = re.compile(
    r"\b(?:usa|us|u\.s\.?|united states|in the|within the|open to|only|nationwide|anywhere"
    r"|east coast|based|position)\b"
)


def _generic_remote_token(tokens: list[str], i: int, rules: LocationRules) -> bool:
    """tokens[i] says remote and nothing narrower ("Remote", "US-Remote", "Remote in the US"),
    and isn't followed by a state ("Remote, CA")."""
    low = tokens[i].lower()
    if not any(k in low for k in rules.remote_keywords):
        return False
    for k in rules.remote_keywords:
        low = low.replace(k, " ")
    if re.sub(r"[\s\-().&]", "", _GENERIC_WORDS_RE.sub(" ", low)):
        return False
    nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
    return not _named_states(nxt)


def _remote_part_ok(part: str, rules: LocationRules) -> bool:
    """A remote location part we accept: in the DMV, generic US, or naming VA/MD/DC."""
    low = re.sub(r"\s+", " ", part.lower()).strip()
    if not low:
        return True
    if is_dmv(low, rules):
        return True
    m = _STATE_COUNTRY_REMOTE_RE.match(low) or _REMOTE_STATE_COUNTRY_RE.match(low)
    if m and m.group(1).strip() in _STATE_NAMES:
        return bool(_named_states(m.group(1)) & (_DMV_STATES | {"DMV"}))
    # A list with a generic remote item: "Charlotte, Denver, New York, Remote", "SF, NY, Remote-US"
    non_us = classify(part) is False or bool(_UK_RE.search(low))
    tokens = [t.strip() for t in _TOKEN_SPLIT_RE.split(part)]
    if not non_us and any(_generic_remote_token(tokens, i, rules) for i in range(len(tokens))):
        return True
    states = _named_states(part)
    if states:
        return bool(states & (_DMV_STATES | {"DMV"}))
    if _UK_RE.search(low):
        return False
    return classify(part) is not False


def remote_eligible(text: str, remote_flag: bool, rules: LocationRules) -> bool:
    """Whether a remote role is open to someone in the DMV.

    Generic US remote ("Remote", "Remote - US", "United States") and remote in VA, MD or DC
    count. Remote limited to other states ("Remote, AZ; Remote, NV", "Remote - California")
    or other countries doesn't. The parts that mention remote decide; when the ATS flags the
    role remote, its plain location parts ("United States", "New York, NY") are judged too.
    """
    parts = [p.strip() for p in _PART_SPLIT_RE.split(text or "") if p and p.strip()]
    if not parts:
        return True  # remote with no location: generic
    remote_parts = [p for p in parts if any(k in p.lower() for k in rules.remote_keywords)]
    candidates = remote_parts + ([p for p in parts if p not in remote_parts] if remote_flag else [])
    return any(_remote_part_ok(p, rules) for p in candidates)


def classify_location_type(
    location: str | None,
    remote: bool,
    rules: LocationRules,
    workplace_type: str | None = None,
    title: str | None = None,
) -> str | None:
    """Assign a location_type, or None when the role is out of area.

    Order matters:
    1. Any DMV location (multi-location postings count if ANY location is in the DMV):
       hybrid (ATS workplace_type or text) -> dmv_hybrid; else remote -> remote_us;
       else dmv_onsite.
    2. A bare "Washington" -> unknown (kept, labelled "Location uncertain", logged), unless
       the job title names a Washington State place ("Seattle", "Pacific Northwest"); then
       it is the state and falls through to the remote check below.
    3. Remote and open to the DMV -> remote_us: generic US remote (a bare "Remote" counts)
       or remote in VA/MD/DC. Remote limited to other states ("Remote, AZ") or other
       countries ("Remote - Canada", "Remote - UK") -> None. See remote_eligible.
    4. Anything else (other US cities, non-US, blank) -> None.
    """
    text = (location or "").strip()
    low = re.sub(r"\s+", " ", text.lower())
    is_remote = remote or any(k in low for k in rules.remote_keywords)
    flagged = remote or workplace_type == "remote"
    if low and is_dmv(low, rules):
        if workplace_type == "hybrid" or any(k in low for k in rules.hybrid_keywords):
            return DMV_HYBRID
        # "Herndon, VA; Remote, CA" is on-site in the DMV, not remote for a DMV reader.
        return REMOTE_US if is_remote and remote_eligible(text, flagged, rules) else DMV_ONSITE
    if low and is_bare_washington(low) and not title_says_washington_state(title):
        return UNKNOWN
    if is_remote:
        return REMOTE_US if remote_eligible(text, flagged, rules) else None
    return None

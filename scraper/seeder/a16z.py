"""a16z portfolio source (docs/seed_sources.md).

Reads the company list that a16z.com/portfolio/ embeds as JSON objects in its HTML. This is
a16z's own public site (robots.txt allows all; the terms of use don't restrict automated
access). The a16z *jobs* board (portfoliojobs.a16z.com) is NOT used: it runs on Consider,
whose terms forbid scrapers without written permission.
"""

from __future__ import annotations

import json
import re

PORTFOLIO_URL = "https://a16z.com/portfolio/"
# a16z's own sector pages; each embeds the same company objects for its sector.
SECTOR_PAGES = {
    "ai": "https://a16z.com/ai/",
    "american-dynamism": "https://a16z.com/american-dynamism/",
    "bio-health": "https://a16z.com/bio-health/",
    "consumer": "https://a16z.com/consumer/",
    "enterprise": "https://a16z.com/enterprise/",
    "fintech": "https://a16z.com/fintech/",
    "infra": "https://a16z.com/infra/",
    "speedrun": "https://a16z.com/speedrun/",  # games accelerator
}
_OBJ_START = re.compile(r'\{"id":"\d+","logo_width"')


def parse_portfolio(html: str) -> list[dict]:
    """Return [{"id", "name", "website", "socials", "acquired", "overview"}] from the page."""
    dec = json.JSONDecoder()
    found: dict[str, dict] = {}
    for m in _OBJ_START.finditer(html):
        try:
            obj, _ = dec.raw_decode(html, m.start())
        except ValueError:
            continue
        if not isinstance(obj, dict) or not obj.get("title"):
            continue
        socials = [s.get("url") for s in obj.get("socials") or [] if isinstance(s, dict)]
        found[str(obj["id"])] = {
            "id": str(obj["id"]),
            "name": re.sub(r"\s+", " ", obj["title"]).strip(),
            "website": (obj.get("web") or "").strip() or None,
            "socials": [u for u in socials if u],
            "acquired": bool((obj.get("acquirer") or "").strip()),
            "overview": obj.get("overview") or "",
        }
    return list(found.values())


def parse_sector_ids(html: str) -> set[str]:
    """Company ids embedded on one sector page."""
    return {m.group(1) for m in re.finditer(r'\{"id":"(\d+)","logo_width"', html)}

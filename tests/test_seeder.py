"""Seeder pieces: a16z page parsing, slug candidates, board verification, industries."""

import json

from scraper.seeder.a16z import parse_portfolio, parse_sector_ids
from scraper.seeder.industry import suggest_industries
from scraper.seeder.probe import Prober, name_similar, slug_candidates, verify


def _obj(cid, title, web="", acquirer="", socials=(), overview=""):
    return json.dumps({
        "id": cid, "logo_width": "", "title": title, "web": web, "acquirer": acquirer,
        "socials": [{"url": u} for u in socials], "overview": overview,
    }, separators=(",", ":"))  # compact, as a16z.com embeds it


PAGE = (
    "<html><script>var x = [" + _obj("1", "Anduril", "https://www.anduril.com",
                                     socials=["https://www.facebook.com/andurilindustries/",
                                              "https://www.linkedin.com/company/anduril"])
    + "," + _obj("2", "OldCo", "https://old.co", acquirer="BigCo")
    + "," + _obj("1", "Anduril", "https://www.anduril.com") + "];</script></html>"
)


def test_parse_portfolio_dedupes_and_flags_acquired():
    cos = {c["name"]: c for c in parse_portfolio(PAGE)}
    assert set(cos) == {"Anduril", "OldCo"}
    assert cos["OldCo"]["acquired"] is True
    assert cos["Anduril"]["website"] == "https://www.anduril.com"


def test_parse_sector_ids():
    assert parse_sector_ids(PAGE) == {"1", "2"}


def test_slug_candidates_domain_then_socials_then_name():
    slugs = slug_candidates("Anduril", "https://www.anduril.com",
                            ["https://www.facebook.com/andurilindustries/",
                             "https://www.linkedin.com/company/anduril-industries",
                             "https://twitter.com/intent/follow"])
    assert slugs[0] == "anduril"
    assert "andurilindustries" in slugs and "anduril-industries" in slugs
    assert "intent" not in slugs and "follow" not in slugs


def test_slug_candidates_name_forms():
    slugs = slug_candidates("Shield AI")
    assert {"shieldai", "shield-ai", "shield"} <= set(slugs)


def test_name_similar():
    assert name_similar("Anduril", "Anduril Industries")
    assert not name_similar("Nova", "Apex Fintech")


def test_verify():
    gh = {"ats": "greenhouse", "board_name": "Anduril Industries"}
    assert verify(gh, "Anduril", None)
    assert not verify({"ats": "greenhouse", "board_name": "Apex Fintech"}, "Apex Space", None)
    ashby = {"ats": "ashby", "sample": "at ramp we build the finance platform"}
    assert verify(ashby, "Ramp", "https://ramp.com")
    assert not verify({"ats": "ashby", "sample": "join acme corp today"}, "Ramp", None)
    assert not verify({"ats": "lever", "sample": ""}, "Ramp", None)  # empty board


class _Resp:
    def __init__(self, status, data=None):
        self.status_code, self._data = status, data
        self.ok = 200 <= status < 300

    def json(self):
        return self._data


class _Session:
    """Fake ATS APIs: `anduril` is an empty Greenhouse board, `andurilindustries` the real one."""

    def __init__(self):
        self.headers, self.calls = {}, []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if url.endswith("/boards/anduril/jobs"):
            return _Resp(200, {"jobs": []})
        if url.endswith("/boards/anduril"):
            return _Resp(200, {"name": "Anduril"})
        if url.endswith("/boards/andurilindustries/jobs"):
            return _Resp(200, {"jobs": [{}] * 3})
        if url.endswith("/boards/andurilindustries"):
            return _Resp(200, {"name": "Anduril Industries"})
        return _Resp(404)


def test_find_board_prefers_the_real_board_and_caches(tmp_path):
    session = _Session()
    p = Prober(user_agent="t", cache_path=tmp_path / "c.json", delay=0, session=session,
               sleep=lambda s: None)
    hit = p.find_board("Anduril", ["anduril", "andurilindustries"])
    assert (hit["ats"], hit["slug"], hit["jobs"], hit["verified"]) == (
        "greenhouse", "andurilindustries", 3, True)
    n = len(session.calls)
    p.find_board("Anduril", ["anduril", "andurilindustries"])
    assert len(session.calls) == n  # second run served from cache
    p.save()
    assert json.loads((tmp_path / "c.json").read_text())


def test_industries_from_sectors_and_keywords():
    assert suggest_industries("Affirm", "pay over time", ["fintech"]) == ["fintech"]
    ind = suggest_industries("Anduril", "defense technology for the warfighter",
                             ["american-dynamism"])
    assert ind[:2] == ["deftech", "american-dynamism"]
    assert "deftech" in suggest_industries(
        "Saronic", "autonomous surface vessels for the future of naval warfare",
        ["american-dynamism"])
    # Bare "defense" isn't enough: cyber copy and banks that lend to defense companies
    assert "deftech" not in suggest_industries("SecCo", "threat defense platform",
                                               ["enterprise"])
    assert "deftech" not in suggest_industries(
        "Erebor Bank", "lending for companies in artificial intelligence, defense, "
        "manufacturing", ["american-dynamism"])
    assert "deftech" in suggest_industries("Chariot Defense", "", ["american-dynamism"])
    assert "space" in suggest_industries("Apex", "satellite buses", ["american-dynamism"])
    assert suggest_industries("Mystery", "", []) == ["saas"]

#!/usr/bin/env python3
"""NBADraft.net pre-draft scouting grades collector (standalone; no `infra` package).

Every profile used is a Wayback Machine capture taken strictly BEFORE the player's draft-night cutoff
(22:00 UTC on the first night of his draft), because NBADraft.net keeps editing profiles for years after
the draft and the live site is Cloudflare-gated (never touched here).

Stages (all resumable, cached under this directory):
  1. index     CDX listing of every 200-OK capture of every profile URL   -> cdx_index.csv
  2. download  latest pre-draft capture per player                        -> raw/<draft_year>/<slug>.html(+.json)
                                                                             status.jsonl (checkpoint per player)
  3. build     parse the cache into the deliverables                      -> features.csv, comps.csv,
                                                                             status.csv, provenance.csv, unmatched.csv

  python3 collect_nbadraftnet.py index      # (re)build the capture index
  python3 collect_nbadraftnet.py download   # fill the cache (long; run under nohup)
  python3 collect_nbadraftnet.py build      # offline: cache -> csvs
  python3 collect_nbadraftnet.py all        # index + download + build
  python3 collect_nbadraftnet.py download --retry   # also re-try previously failed players

Wayback etiquette: one shared token bucket at ~1 request/s across all threads, <=2 CDX queries in flight,
<=2 capture downloads in flight, exponential backoff on 429/503/5xx, descriptive User-Agent, no live-site
requests at all.
"""

import argparse
import json
import os
import re
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from lxml import html

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
INDEX_CSV = HERE / "cdx_index.csv"
STATUS_JSONL = HERE / "status.jsonl"

IDENTITY = Path("/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv")

# Draft-night cutoffs from novel/COLLECTOR_RULES.md (a capture is pre-draft only if ts < DAY 22:00 UTC).
# 2026 is not in the rules file; 20260623 (Colin's builders) is used and is conservative for that class.
DRAFT_NIGHT = {
    2000: "20000628", 2001: "20010627", 2002: "20020626", 2003: "20030626", 2004: "20040624", 2005: "20050628",
    2006: "20060628", 2007: "20070628", 2008: "20080626", 2009: "20090625", 2010: "20100624", 2011: "20110623",
    2012: "20120628", 2013: "20130627", 2014: "20140626", 2015: "20150625", 2016: "20160623", 2017: "20170622",
    2018: "20180621", 2019: "20190620", 2020: "20201118", 2021: "20210729", 2022: "20220623", 2023: "20230622",
    2024: "20240626", 2025: "20250625", 2026: "20260623",
}
CUTOFF_HHMM = "2200"
YEARS = sorted(DRAFT_NIGHT)

WAYBACK = "https://web.archive.org"
UA = "Mozilla/5.0 (compatible; nba-redraft-research/1.0; pre-draft scouting archive; non-commercial research)"

# --------------------------------------------------------------------------- polite HTTP

_RATE_LOCK = threading.Lock()
_NEXT_AT = [0.0]
MIN_INTERVAL = 1.05  # seconds between ANY two web.archive.org requests (~1 req/s)


def _throttle():
    with _RATE_LOCK:
        now = time.monotonic()
        wait = _NEXT_AT[0] - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _NEXT_AT[0] = now + MIN_INTERVAL


_S = requests.Session()
_S.headers["User-Agent"] = UA


def _get(url, params=None, tries=5, timeout=180):
    """One throttled GET with exponential backoff on 429/503/5xx and transport errors. None on 404 / give-up."""
    for i in range(tries):
        _throttle()
        try:
            r = _S.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
            if r.status_code in (429, 503, 502, 500, 504, 403):
                time.sleep(min(300, 10 * 2 ** i))
                continue
            return None
        except requests.RequestException:
            time.sleep(min(300, 10 * 2 ** i))
    return None


_TS_LINE = re.compile(r"^\d{14} ")


def _cdx(params, tries=6):
    """Rows of a CDX query (fl=timestamp,original,statuscode). The API sometimes answers with an HTML
    'Temporarily Offline' page at status 200, so anything that is not a capture listing is retried."""
    for i in range(tries):
        r = _get(f"{WAYBACK}/cdx/search/cdx", {"fl": "timestamp,original,statuscode", **params}, tries=3)
        if r is not None:
            text = r.text.strip()
            if not text:
                return []
            lines = text.splitlines()
            if all(_TS_LINE.match(ln) for ln in lines):
                return [ln.split(" ", 2) for ln in lines]
        time.sleep(min(300, 15 * (i + 1)))
    return None


def _decode(content):
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")  # the 2008 ASP pages


def _offline(text):
    return "Internet Archive" in text[:400] and "Temporarily Offline" in text[:400]  # served with status 200


def _download(ts, original):
    """Raw capture (id_ flag); zstd/brotli-stored captures fall back to the rewritten page."""
    for i in range(4):
        r = _get(f"{WAYBACK}/web/{ts}id_/{original}", tries=3)
        if r is None:
            return None
        if r.headers.get("content-encoding", "").lower() in ("zstd", "br") or r.content[:4] == b"\x28\xb5\x2f\xfd":
            r = _get(f"{WAYBACK}/web/{ts}/{original}", tries=3)
            if r is None:
                return None
        text = _decode(r.content)
        if not _offline(text):
            return text
        time.sleep(min(300, 15 * (i + 1)))
    return None


# --------------------------------------------------------------------------- capture index

_PLAYERS_PATH = re.compile(r"^https?://(?:www\.)?nbadraft\.net(?::80)?/players/([a-z0-9][a-z0-9\-]*)/?$")
_ASP_PATH = re.compile(r"^https?://(?:www\.)?nbadraft\.net(?::80)?/admincp/profiles/([a-z0-9\-]+)\.html?$")
# the original Sports Phenoms site: /profiles/<slug>.htm (2000-2008) and /profiles/<slug>.asp (2003-2008),
# plus a /profiles/2000/<slug>.htm archive of the 2000 class (only captured in 2001, i.e. post-draft)
_OLD_PATH = re.compile(r"^https?://(?:www\.)?nbadraft\.net(?::80)?/profiles/(?:\d{4}/)?([a-z0-9][a-z0-9\-]*)\.(?:asp|html?)$")


def _index_rows(rows):
    out = []
    for ts, url, status in rows:
        if status != "200":
            continue
        m = _PLAYERS_PATH.match(url)
        if m:
            out.append({"ts": ts, "url": url, "slug": m.group(1), "layout": "players"})
            continue
        low = url.lower()
        m = _ASP_PATH.match(low)
        if m:
            out.append({"ts": ts, "url": url, "slug": m.group(1), "layout": "asp"})
            continue
        m = _OLD_PATH.match(low)
        if m:
            out.append({"ts": ts, "url": url, "slug": m.group(1), "layout": "old"})
    return out


def build_index(force=False):
    """Every 200-OK capture of every NBADraft.net profile URL. The /players/* listing is queried one calendar
    year at a time (the API's own paging returns inconsistent page boundaries between calls)."""
    if INDEX_CSV.exists() and not force:
        return pd.read_csv(INDEX_CSV, dtype=str)
    rows = []
    for y in range(2006, 2028):
        page = _cdx({"url": "nbadraft.net/players/*", "from": str(y), "to": str(y), "limit": 100000})
        if page is None:
            raise RuntimeError(f"CDX listing for {y} failed")
        rows += _index_rows(page)
        print(f"cdx players {y}: {len(rows)} profile captures so far", flush=True)
    asp = _cdx({"url": "nbadraft.net/admincp/profiles/*", "to": "20091231", "limit": 100000})
    if asp is None:
        raise RuntimeError("CDX admincp listing failed")
    rows += _index_rows(asp)
    print(f"cdx admincp: {len(rows)} profile captures total", flush=True)
    old = _cdx({"url": "nbadraft.net/profiles/*", "to": "20091231", "limit": 200000})
    if old is None:
        raise RuntimeError("CDX /profiles listing failed")
    rows += _index_rows(old)
    print(f"cdx /profiles: {len(rows)} profile captures total", flush=True)
    df = pd.DataFrame(rows).drop_duplicates(["ts", "url"]).sort_values(["slug", "ts"])
    HERE.mkdir(parents=True, exist_ok=True)
    df.to_csv(INDEX_CSV, index=False)
    return df


# --------------------------------------------------------------------------- names

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_TRANSLIT = str.maketrans({"ı": "i", "İ": "I", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ß": "ss",
                           "ø": "o", "Ø": "O", "æ": "ae", "Æ": "Ae"})


def norm_name(s):
    """lowercase ascii letters only; accents stripped, punctuation dropped, trailing Jr/Sr/II/III/IV/V removed."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    toks = re.split(r"[\s]+", s.lower().replace(".", " ").replace(",", " ").replace("'", "").replace("-", " "))
    while toks and re.sub(r"[^a-z]", "", toks[-1]) in _SUFFIXES and len(toks) > 1:
        toks.pop()
    return re.sub(r"[^a-z]", "", "".join(toks))


def alt_name(s):
    return norm_name(str(s).translate(_TRANSLIT))


# slug-derived name (norm_name) <-> draft-table name, where normalisation alone does not resolve it.
# Ported from Colin's builders and extended; the pair is treated symmetrically (either side may be ours).
ALIAS_PAIRS = [
    ("aleksandarpavlovic", "sashapavlovic"), ("eneskanter", "enesfreedom"),
    ("guillermohernangomez", "willyhernangomez"), ("timotheluwawu", "timotheluwawucabarrot"),
    ("hansenyang", "yanghansen"), ("bjboston", "brandonboston"), ("giannisadetokunbo", "giannisantetokounmpo"),
    ("giannisadetokoubo", "giannisantetokounmpo"), ("billwalker", "henrywalker"), ("bjmullens", "byronmullens"),
    ("jeffpendergraph", "jeffayres"), ("patrickbeverly", "patrickbeverley"), ("sergiigladyr", "sergiygladyr"),
    ("patrickmills", "pattymills"), ("moeharkless", "mauriceharkless"), ("jefferytaylor", "jefftaylor"),
    ("ricardoledo", "rickyledo"), ("waltertavares", "edytavares"), ("roydevynmarble", "devynmarble"),
    ("juanvaulet", "juanpablovaulet"), ("josephyoung", "joeyoung"), ("satnamsinghbhamara", "satnamsingh"),
    ("danieldiez", "danidiez"), ("juanhernangomez", "juanchohernangomez"), ("kahlilfelder", "kayfelder"),
    ("wesleyiwundu", "wesiwundu"), ("aleksandarvezenkov", "sashavezenkov"), ("mohamedbamba", "mobamba"),
    ("sviatoslavmykhailiuk", "svimykhailiuk"), ("raymondspalding", "rayspalding"), ("cameronreddish", "camreddish"),
    ("nicolasclaxton", "nicclaxton"), ("marcoslouzadasilva", "didilouzada"), ("nahshonhyland", "boneshyland"),
    ("cameronthomas", "camthomas"), ("alexandresarr", "alexsarr"), ("ronaldholland", "ronholland"),
    ("carltoncarrington", "bubcarrington"), ("lrmbahamoute", "lucmbahamoute"),
]
ALIASES = {}
for _a, _b in ALIAS_PAIRS:
    ALIASES.setdefault(_a, set()).add(_b)
    ALIASES.setdefault(_b, set()).add(_a)


def name_keys(name):
    """All normalised spellings a name may take (used on both the roster side and the slug side)."""
    ks = {norm_name(name), alt_name(name)}
    for k in list(ks):
        ks |= ALIASES.get(k, set())
    return {k for k in ks if k}


def slug_key(slug):
    return norm_name(slug.replace("-", " "))


# --------------------------------------------------------------------------- roster


def roster():
    d = pd.read_csv(IDENTITY)
    d = d[d.draft_year.isin(YEARS)].copy()
    d["key"] = d.player_name.map(norm_name)
    return d.reset_index(drop=True)


def candidates(pool, index):
    """pid -> candidate slugs, from every indexed slug whose name normalises to one of the player's keys.
    Slugs whose key matches players from more than one pid are only offered to a pid whose draft cycle the
    capture timestamps are compatible with (see fetch_profile / unmatched.csv)."""
    by_key = {}
    for slug in set(index.slug):
        by_key.setdefault(slug_key(slug), []).append(slug)
    out = {}
    for pid, name in zip(pool.pid, pool.player_name):
        cands = []
        for k in name_keys(name):
            for s in by_key.get(k, []):
                if s not in cands:
                    cands.append(s)
        out[pid] = cands
    return out


# --------------------------------------------------------------------------- parsers
# Three layouts, all carrying the same 1-10 grid, an Overall grade, an NBA comparison and Strengths /
# Weaknesses paragraphs. On the two older layouts the grid labels are an image chosen by position
# (attribute_banner_<POS>.gif / parameters.gif), so the column order is positional.

GUARD_GRID = ["athleticism", "size", "defense", "strength", "quickness", "leadership", "jumpshot", "nbaready",
              "ballhandling", "potential", "passing", "intangibles"]
BIG_GRID = ["athleticism", "size", "defense", "strength", "quickness", "leadership", "jumpshot", "nbaready",
            "rebounding", "potential", "postskills", "intangibles"]
LABELS = {"athleticism": "athleticism", "size": "size", "defense": "defense", "strength": "strength",
          "quickness": "quickness", "leadership": "leadership", "jump shot": "jumpshot", "nba ready": "nbaready",
          "ball handling": "ballhandling", "rebounding": "rebounding", "potential": "potential",
          "post skills": "postskills", "passing": "passing", "intangibles": "intangibles"}
GRID_COLS = ["athleticism", "size", "defense", "strength", "quickness", "leadership", "jumpshot", "nbaready",
             "potential", "intangibles", "ballhandling", "passing", "rebounding", "postskills"]
BIG_POS = ("center", "power forward", "small forward/power forward", "forward/center")


def _clean(s):
    return " ".join(s.split())


def _num(s):
    m = re.search(r"\d+(?:\.\d+)?", s or "")
    return float(m.group(0)) if m else np.nan


def _height_in(s):
    m = re.search(r"(\d)\s*[-'’′]\s*(\d{1,2}(?:\.\d+)?)", s or "")
    return int(m.group(1)) * 12 + float(m.group(2)) if m else np.nan


def _grid_group(text, position):
    """Which unlabelled grid an ASP / Drupal page shows: the position banner image, else the position text."""
    m = re.search(r"attribute_banner_([A-Z]+)\.gif", text)
    if m:
        return BIG_GRID if m.group(1) in ("C", "PF", "SFPF", "PFC") else GUARD_GRID
    m = re.search(r"parameters(\d?)\.gif", text)
    if m:
        return GUARD_GRID if m.group(1) == "1" else BIG_GRID
    if position:
        return BIG_GRID if position.lower().strip() in BIG_POS else GUARD_GRID
    return None


_TEXT_END = (r"(?:Strengths?:|Weakness(?:es)?:|NBA Comparison:|Notes?:|Outlook:|Overall:|High School:|College:|Related|"
             r"YouTube|Youtube|[A-Z][a-z]+(?: [A-Z]\.)? [A-Z][A-Za-z']+(?: III| Jr\.?)?\s*[-–—]?\s*"
             r"\d{1,2}/\d{1,2}/\d{2,4}|$)")  # next section / author signature
_STRENGTHS = re.compile(r"Strengths?:\s*(.*?)\s*(?=" + _TEXT_END + ")", re.S)
_WEAKNESSES = re.compile(r"Weakness(?:es)?:\s*(.*?)\s*(?=" + _TEXT_END + ")", re.S)
_COMPARISON = re.compile(r"NBA Comparison:\s*(.{1,80}?)\s*(?=" + _TEXT_END + ")", re.S)


def _flat(el):
    return _clean(" ".join(el.itertext()))


def parse_profile(text):
    """{name, position, grid: {col: score}, overall, compares_to, strengths, weaknesses} for any of the three layouts."""
    doc = html.fromstring(text)
    for bad in doc.xpath("//script|//style"):
        bad.drop_tree()
    out = {"grid": {}, "overall": np.nan, "position": "", "name": "", "layout": ""}
    body = None
    if doc.xpath('//div[@id="p_details" or @id="nbap_p_details"]'):  # 2008 ASP layout (two id variants)
        out["layout"] = "asp"
        out["name"] = _clean(" ".join(doc.xpath('//div[@id="name" or @id="nbap_name"]//text()')))
        for li in doc.xpath('//div[@id="detail_list"]//li'):
            title = _clean(" ".join(li.xpath('.//div[@class="item_title"]//text()'))).lower()
            val = _clean(" ".join(li.xpath('.//div[@class="item_content"]//text()')))
            if title.startswith("nba pos"):
                out["position"] = val
        scores = []
        for block in doc.xpath('//div[@id="p_details" or @id="nbap_p_details"]/div[contains(@class,"block")]'):
            t = _clean(block.text_content())
            if "Overall" in t:
                out["overall"] = _num(t.replace("Overall", ""))
            else:
                scores.append(_num(t))
        group = _grid_group(text, out["position"])
        if group and len(scores) == len(group):
            out["grid"] = dict(zip(group, scores))
        body = doc.xpath('//div[@id="content_bottom"]')
    elif doc.xpath('//div[@id="nba_player_attrib_blocks"] | //div[@id="nba_player_stats"]'):  # Drupal layout
        out["layout"] = "drupal"
        out["name"] = re.sub(r"^\s*\d+\s*-\s*", "", _clean(" ".join(doc.xpath('//h2[@class="number"]//text()'))))
        for li in doc.xpath('//div[@id="nba_player_stats_middle"]//li'):
            label = _clean(" ".join(li.xpath('./span[@class="label"]//text()'))).lower()
            val = _clean(li.text_content().replace(_clean(" ".join(li.xpath('./span[@class="label"]//text()'))), "", 1))
            if label.startswith("nba pos"):
                out["position"] = val
        scores = [_num(_clean(p.text_content())) for p in doc.xpath('//p[@class="nba_player_attrib_score"]')]
        tot = doc.xpath('//div[contains(@class,"attrib_total")]//p[@class="whitebox"]')
        if tot:
            out["overall"] = _num(_clean(tot[0].text_content()))
        group = _grid_group(text, out["position"])
        if group and len(scores) == len(group):
            out["grid"] = dict(zip(group, scores))
        body = doc.xpath('//div[@id="nbap_content_bottom"]')
    elif (re.search(r"NBA\s*Draft\.?net\s*-{1,2}", _clean(" ".join(doc.xpath("//title//text()"))), re.I)
          or doc.xpath('//img[contains(@src,"profiles.gif")]')):
        # original Sports Phenoms layout (2000-2008): bio table + NBA Comparison / Strengths / Weaknesses
        # paragraph. No 1-10 grid exists on these pages, so only the text features are available.
        out["layout"] = "old"
        m = re.search(r"NBA Position:\s*(.*?)\s*(?=College:|Class:|Ht:|Wt:|High School:|Hometown:|NBA Comparison:|$)",
                      _flat(doc))
        out["position"] = m.group(1) if m else ""
        body = doc.xpath("//body")
    else:  # WordPress layout (2019-11 onward)
        out["layout"] = "wordpress"
        h1 = doc.xpath('//h1[contains(@class,"player-name")]')
        if h1:
            for sp in h1[0].xpath('.//span[contains(@class,"player-number")]'):
                sp.drop_tree()
            out["name"] = _clean(h1[0].text_content())
        out["position"] = _clean(" ".join(doc.xpath('//span[contains(@class,"player-position")]//text()')))
        for row in doc.xpath('//div[contains(@class,"player-attributes")]//div[contains(@class,"div-table-row")]'):
            label = _clean(" ".join(row.xpath('.//div[contains(@class,"attribute-name")]//text()'))).lower()
            val = _num(_clean(" ".join(row.xpath('.//div[contains(@class,"attribute-value")]//text()'))))
            if label in LABELS and not np.isnan(val):
                out["grid"][LABELS[label]] = val
        tot = doc.xpath('//div[contains(@class,"attribute-overall")]//span[contains(@class,"value")]')
        if tot:
            out["overall"] = _num(_clean(tot[0].text_content()))
        body = doc.xpath('//h3[contains(., "NBA Comparison")]/.. | //p[strong[contains(., "Strength")]]/..')
    if not out["name"]:
        title = _clean(" ".join(doc.xpath("//title//text()")))
        title = re.sub(r"(?i)^\s*nba\s*draft\.?net\s*[-–—|]{1,2}\s*", "", title)
        title = re.sub(r"(?i)\s*profile\s*$", "", title)
        out["name"] = re.sub(r"(?i)\s*[|\-]\s*nbadraft\.net\s*$|nbadraft\.net\s*[-|]\s*", "", title).strip()
    flat = _flat(body[0]) if body else _flat(doc)
    m = _COMPARISON.search(flat)
    out["compares_to"] = m.group(1).strip(" .") if m and m.group(1).strip(" .").upper() not in ("N/A", "NA", "TBD", "?") else ""
    m = _STRENGTHS.search(flat)
    out["strengths"] = m.group(1) if m else ""
    m = _WEAKNESSES.search(flat)
    out["weaknesses"] = m.group(1) if m else ""
    return out


# --------------------------------------------------------------------------- keyword dictionaries
# Rule-based only: each feature is the NUMBER OF REGEX HITS of a fixed dictionary over a fixed scope.
# "both" = Strengths + Weaknesses paragraphs; "weaknesses" = the Weaknesses paragraph only (a "great motor"
# in Strengths is not a concern). Case-insensitive, overlapping alternatives counted once per match.

KEYWORDS = {
    "injury": (r"injur|surger|\bknee|\bankle|stress fracture|\btorn\b|\btear\b|concussion|achilles|meniscus|\bacl\b|"
               r"back (?:injur|issue|problem|surger|spasm)|bad back|foot (?:injur|issue|problem|surger)|"
               r"out for the season|missed (?:the|most of the|the entire) season", "both"),
    "upside": (r"upside|ceiling|\braw\b|\bproject\b|long[- ]term", "both"),
    "motor": (r"\bmotor\b|\beffort\b|\blazy\b|\bcoast(?:s|ed|ing)?\b|takes? plays off|\bpassive\b", "weaknesses"),
    "character": (r"character|matur|attitude|off[- ]?(?:the[- ])?court|disciplin|red flag|coachab|\bego\b|selfish|"
                  r"work ethic", "weaknesses"),
    "shooting_concern": (r"mechanic|inconsistent|poor shoot|free[- ]throw|\bft\b|streaky|shooting (?:form|stroke)|"
                         r"jump ?shot|jumper|three[- ]point|3[- ]?p(?:t|oint)|perimeter shot|shooting range", "weaknesses"),
    "nba_ready": (r"polished|nba[- ]ready|ready (?:to contribute|now|made)|day one|plug[- ]and[- ]play|"
                  r"contribute (?:immediately|right away)|immediate(?:ly)? (?:impact|contribut)", "both"),
}


def _words(s):
    return len(re.findall(r"[A-Za-z][A-Za-z'’]*", s))


def _grade(v):
    try:
        return v if v > 0 else np.nan  # the site shows 0 for a prospect it has not graded yet
    except TypeError:
        return np.nan


def features(p, snapshot, year):
    f = {"sc_" + c: _grade(p["grid"].get(c, np.nan)) for c in GRID_COLS}
    f["sc_overall"] = _grade(p["overall"])
    il = [f["sc_intangibles"], f["sc_leadership"]]
    il = [v for v in il if pd.notna(v)]
    f["sc_intang_lead"] = float(np.mean(il)) if len(il) == 2 else np.nan
    s, w = p["strengths"], p["weaknesses"]
    for col, (pat, scope) in KEYWORDS.items():
        scope_text = (s + " " + w) if scope == "both" else w
        f["sc_kw_" + col] = len(re.findall(pat, scope_text, re.I)) if (s or w) else np.nan
    f["sc_words_strengths"] = _words(s) if s else np.nan
    f["sc_words_weaknesses"] = _words(w) if w else np.nan
    f["sc_capture_days_before_draft"] = (pd.Timestamp(DRAFT_NIGHT[year]) - pd.Timestamp(snapshot[:8])).days
    f["sc_has_profile"] = 1
    return f


FEATURE_COLS = (["pid"] + ["sc_" + c for c in ["athleticism", "size", "defense", "strength", "quickness", "leadership",
                                               "jumpshot", "nbaready", "potential", "intangibles", "ballhandling",
                                               "passing", "rebounding", "postskills", "overall", "intang_lead"]]
                + ["sc_kw_" + k for k in ["injury", "upside", "motor", "character", "shooting_concern", "nba_ready"]]
                + ["sc_words_strengths", "sc_words_weaknesses", "sc_capture_days_before_draft", "sc_has_profile"])


# --------------------------------------------------------------------------- fetch

MAX_TRIES = 5  # captures tried per candidate slug (a capture can be truncated, a redirect stub or a wrong-person page)
NAME_MIN = 0.85


def _name_ok(page_name, name):
    n = norm_name(page_name)
    if not n:
        return False
    keys = name_keys(name)
    if n in keys or alt_name(page_name) in keys:
        return True
    return max(SequenceMatcher(None, n, k).ratio() for k in keys) >= NAME_MIN


def _usable(p):
    return bool(p["grid"]) or bool(p["strengths"]) or bool(p["weaknesses"])


def fetch_profile(pid, name, year, slugs, caps_by_slug):
    """Download + cache the latest pre-draft capture of the first candidate slug whose page is this player."""
    cutoff = DRAFT_NIGHT[year] + CUTOFF_HHMM
    ydir = RAW / str(year)
    base = {"pid": pid, "draft_year": year, "n_candidate_slugs": len(slugs)}
    if not slugs:
        return dict(base, status="no_profile", n_captures=0, n_rejected_postdraft=0)
    n_caps = n_rej = 0
    pre = {}
    for s in slugs:
        caps = caps_by_slug.get(s, [])
        n_caps += len(caps)
        n_rej += sum(1 for ts, _ in caps if ts >= cutoff)
        p = sorted([c for c in caps if c[0] < cutoff], reverse=True)
        if p:
            pre[s] = p
    if not pre:
        return dict(base, status="no_capture_before_draft", n_captures=n_caps, n_rejected_postdraft=n_rej)
    reason = "download_failed"
    # freshest pre-draft capture first: a 2009 draftee's Drupal page beats his 2008 ASP page
    for slug in sorted(pre, key=lambda s: pre[s][0][0], reverse=True):
        for ts, url in pre[slug][:MAX_TRIES]:
            text = _download(ts, url)
            if text is None or len(text) < 2000:
                continue
            try:
                p = parse_profile(text)
            except Exception:
                reason = "parse_failed"
                continue
            if not p["name"]:
                # mid-2007 the /profiles/<slug>.asp pages became JS redirect stubs to the admincp page: they keep a
                # stale copy of the text but no heading, so the player cannot be verified -- try an older capture
                reason = "unverified_name"
                continue
            if not _name_ok(p["name"], name):
                reason = "name_mismatch"
                break  # the slug is another player; try the next slug
            if not _usable(p):
                reason = "no_content"
                continue
            ydir.mkdir(parents=True, exist_ok=True)
            (ydir / (slug + ".html")).write_text(text)
            meta = dict(base, status="ok", slug=slug, url=url, capture_ts=ts, layout=p["layout"],
                        n_captures=n_caps, n_rejected_postdraft=n_rej, page_name=p["name"])
            (ydir / (slug + ".json")).write_text(json.dumps(meta))
            return meta
    return dict(base, status=reason, n_captures=n_caps, n_rejected_postdraft=n_rej, slug=";".join(slugs[:5]))


# --------------------------------------------------------------------------- checkpointed crawl

_WRITE_LOCK = threading.Lock()


def _load_status():
    done = {}
    if STATUS_JSONL.exists():
        for line in STATUS_JSONL.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            done[rec["pid"]] = rec
    return done


def _checkpoint(rec):
    with _WRITE_LOCK:
        with STATUS_JSONL.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            os.fsync(fh.fileno())


def download_all(retry=False, workers=2, years=None):
    index = build_index()
    caps_by_slug = {}
    for slug, ts, url in zip(index.slug, index.ts, index.url):
        caps_by_slug.setdefault(slug, []).append((ts, url))
    pool = roster()
    if years:
        pool = pool[pool.draft_year.isin(years)]
    done = _load_status()
    cands = candidates(pool, index)

    # ambiguity guard (rule 5): a slug whose name matches more than one pid is only used for a pid whose
    # draft cycle it plausibly belongs to; unresolvable cases are logged and skipped.
    slug_owners = {}
    for pid, slugs in cands.items():
        for s in slugs:
            slug_owners.setdefault(s, []).append(pid)
    years_by_pid = dict(zip(pool.pid, pool.draft_year))
    unmatched = []
    for s, pids in slug_owners.items():
        if len(pids) < 2:
            continue
        caps = sorted(ts for ts, _ in caps_by_slug.get(s, []))
        keep = []
        for pid in pids:
            y = years_by_pid[pid]
            lo, hi = "%d0901" % (y - 3), DRAFT_NIGHT[y] + CUTOFF_HHMM
            if any(lo <= ts < hi for ts in caps):
                keep.append(pid)
        # a slug still claimed by two players (same normalised name, overlapping draft cycles) is not guessed at
        drop = pids if len(keep) > 1 else [p for p in pids if p not in keep]
        for pid in drop:
            cands[pid] = [x for x in cands[pid] if x != s]
            unmatched.append({"pid": pid, "draft_year": years_by_pid[pid], "slug": s, "n_pids_sharing": len(pids),
                              "reason": "ambiguous_shared_slug" if len(keep) > 1 else "shared_slug_no_capture_in_window"})
    if unmatched:
        pd.DataFrame(unmatched).to_csv(HERE / "unmatched.csv", index=False)

    todo = [pid for pid in pool.pid if pid not in done or (retry and done[pid].get("status") != "ok")]
    names = dict(zip(pool.pid, pool.player_name))
    print(f"{len(pool)} players, {len(done)} already recorded, {len(todo)} to fetch", flush=True)
    t0 = time.time()
    n = [0]

    def work(pid):
        rec = fetch_profile(pid, names[pid], int(years_by_pid[pid]), cands.get(pid, []), caps_by_slug)
        _checkpoint(rec)
        with _WRITE_LOCK:
            n[0] += 1
            if n[0] % 25 == 0:
                print(f"  {n[0]}/{len(todo)} in {time.time() - t0:.0f}s  (last: {pid} {rec['status']})", flush=True)
        return rec

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))
    print(f"download pass finished: {len(todo)} players in {time.time() - t0:.0f}s", flush=True)


# --------------------------------------------------------------------------- build


def build():
    pool = roster()
    done = _load_status()
    rows, comps, prov, status_rows = [], [], [], []
    for pid, name, year in zip(pool.pid, pool.player_name, pool.draft_year):
        rec = done.get(pid)
        if rec is None:
            status_rows.append({"pid": pid, "draft_year": year, "status": "not_attempted", "slug": "",
                                "capture_ts": "", "n_captures": "", "n_rejected_postdraft": "", "layout": ""})
            rows.append({"pid": pid, "sc_has_profile": 0})
            continue
        status_rows.append({"pid": pid, "draft_year": year, "status": rec["status"], "slug": rec.get("slug", ""),
                            "capture_ts": rec.get("capture_ts", ""), "n_captures": rec.get("n_captures", ""),
                            "n_rejected_postdraft": rec.get("n_rejected_postdraft", ""), "layout": rec.get("layout", "")})
        if rec["status"] != "ok":
            rows.append({"pid": pid, "sc_has_profile": 0})
            continue
        hp = RAW / str(year) / (rec["slug"] + ".html")
        if not hp.exists():
            rows.append({"pid": pid, "sc_has_profile": 0})
            continue
        assert rec["capture_ts"] < DRAFT_NIGHT[year] + CUTOFF_HHMM, (pid, year, rec["capture_ts"])  # pre-draft guard
        p = parse_profile(hp.read_text())
        f = features(p, rec["capture_ts"], int(year))
        rows.append(dict(f, pid=pid))
        if p["compares_to"]:
            comps.append({"pid": pid, "comp_name": p["compares_to"], "capture_ts": rec["capture_ts"]})
        prov.append({"pid": pid, "draft_year": year, "source": "nbadraftnet", "url": rec["url"],
                     "capture_ts": rec["capture_ts"], "layout": rec.get("layout", ""),
                     "days_before_draft": f["sc_capture_days_before_draft"],
                     "fields_parsed": int(sum(pd.notna(v) for k, v in f.items()))})
    out = pd.DataFrame(rows).reindex(columns=FEATURE_COLS)
    out["sc_has_profile"] = out.sc_has_profile.fillna(0).astype(int)
    out.to_csv(HERE / "features.csv", index=False)
    pd.DataFrame(status_rows).to_csv(HERE / "status.csv", index=False)
    pd.DataFrame(prov).to_csv(HERE / "provenance.csv", index=False)
    pd.DataFrame(comps, columns=["pid", "comp_name", "capture_ts"]).to_csv(HERE / "comps.csv", index=False)
    return out


BANDS = [("2000-07", 2000, 2007), ("2008-18", 2008, 2018), ("2019-25", 2019, 2025), ("2026", 2026, 2026)]


def write_coverage(out):
    """Regenerate the coverage section of README.md (between the <!-- COVERAGE --> marker and the next '## ')."""
    pool = roster()
    st = pd.read_csv(HERE / "status.csv")
    m = pool.merge(out, on="pid", how="left")
    lines = ["", "Built %s from %d captures indexed over %d profile slugs." % (
        pd.Timestamp.today().date(), len(pd.read_csv(INDEX_CSV, dtype=str)), pd.read_csv(INDEX_CSV, dtype=str).slug.nunique()), "",
        "| draft-year band | players | with pre-draft profile | with 1-10 grid | with Strengths/Weaknesses | median days before draft |",
        "|---|---|---|---|---|---|"]
    for lab, a, b in BANDS:
        g = m[(m.draft_year >= a) & (m.draft_year <= b)]
        if not len(g):
            continue
        days = g.sc_capture_days_before_draft.dropna()
        lines.append("| %s | %d | %d (%.0f%%) | %d (%.0f%%) | %d (%.0f%%) | %s |" % (
            lab, len(g), g.sc_has_profile.sum(), 100 * g.sc_has_profile.mean(),
            g.sc_athleticism.notna().sum(), 100 * g.sc_athleticism.notna().mean(),
            g.sc_words_strengths.notna().sum(), 100 * g.sc_words_strengths.notna().mean(),
            ("%.0f" % days.median()) if len(days) else "-"))
    g = m
    days = g.sc_capture_days_before_draft.dropna()
    lines += ["| **all 2000-2026** | %d | %d (%.0f%%) | %d (%.0f%%) | %d (%.0f%%) | %s |" % (
        len(g), g.sc_has_profile.sum(), 100 * g.sc_has_profile.mean(), g.sc_athleticism.notna().sum(),
        100 * g.sc_athleticism.notna().mean(), g.sc_words_strengths.notna().sum(),
        100 * g.sc_words_strengths.notna().mean(), ("%.0f" % days.median()) if len(days) else "-"), ""]
    lines += ["Per-year detail is in `status.csv`. Why the misses (all pids):", "", "```"]
    lines += st.status.value_counts().to_string().splitlines()
    lines += ["```", "",
              "Post-draft captures seen and rejected for these players: %d." % int(
                  pd.to_numeric(st.n_rejected_postdraft, errors="coerce").fillna(0).sum()),
              "NBA comparisons captured in `comps.csv`: %d." % len(pd.read_csv(HERE / "comps.csv")), ""]
    txt = (HERE / "README.md").read_text()
    head, _, rest = txt.partition("<!-- COVERAGE -->")
    tail = rest[rest.index("\n## "):] if "\n## " in rest else ""
    (HERE / "README.md").write_text(head + "<!-- COVERAGE -->\n" + "\n".join(lines) + tail)


def report(out):
    pool = roster()
    st = pd.read_csv(HERE / "status.csv")
    m = pool.merge(out, on="pid", how="left")
    print("\nrows in features.csv:", len(out))
    print("\nyear  players  profile  grid  text   median_days_before  reject_postdraft")
    for y, g in m.groupby("draft_year"):
        s = st[st.draft_year == y]
        days = g.sc_capture_days_before_draft.dropna()
        print(f"{y}  {len(g):7d}  {int(g.sc_has_profile.sum()):7d}  {int(g.sc_athleticism.notna().sum()):4d}  "
              f"{int(g.sc_words_strengths.notna().sum()):4d}   {days.median() if len(days) else float('nan'):18.0f}  "
              f"{int(pd.to_numeric(s.n_rejected_postdraft, errors='coerce').fillna(0).sum()):16d}")
    bands = [("2000-07", 2000, 2007), ("2008-18", 2008, 2018), ("2019-25", 2019, 2025), ("2026", 2026, 2026)]
    print("\nband      players  with_profile  coverage  with_grid  with_text")
    for lab, a, b in bands:
        g = m[(m.draft_year >= a) & (m.draft_year <= b)]
        if not len(g):
            continue
        print(f"{lab:9s} {len(g):7d}  {int(g.sc_has_profile.sum()):12d}  {g.sc_has_profile.mean():7.1%}  "
              f"{int(g.sc_athleticism.notna().sum()):9d}  {int(g.sc_words_strengths.notna().sum()):9d}")
    print("\nstatus counts:\n" + st.status.value_counts().to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["index", "download", "build", "all"])
    ap.add_argument("--retry", action="store_true")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--years", type=str, default="")
    a = ap.parse_args()
    yrs = [int(y) for y in a.years.split(",")] if a.years else None
    if a.stage in ("index", "all"):
        idx = build_index()
        print(f"index: {len(idx)} captures, {idx.slug.nunique()} slugs", flush=True)
    if a.stage in ("download", "all"):
        download_all(retry=a.retry, workers=a.workers, years=yrs)
    if a.stage in ("build", "all"):
        res = build()
        report(res)
        write_coverage(res)

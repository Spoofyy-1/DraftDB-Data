"""Layout parsers. Every parser is pure regex / table-structure -- no judgement,
no LLM scoring, and scouting prose is never retained (only rank, name, position,
school, class, age, height, weight, movement arrow).

Each parser returns a list of dicts:
  rank (int), name (str), pos, school, klass, age (float|None),
  height_in (float|None), weight (float|None), change (int|None), tier (str|None)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bb_common import html_unescape, strip_tags  # noqa: E402

# --------------------------------------------------------------------------
NOISE = re.compile(
    r"^(watch video|read more|full profile|nba draft|mock draft|top 100|scouting|"
    r"more rankings|advertisement|home|news|video|rankings|profile)$", re.I)


def _clean(s):
    s = html_unescape(s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _ht_in(s):
    """'6-10', "6'10\"", "6' 10\"" -> inches."""
    if not s:
        return None
    s = html_unescape(s).replace("’", "'").replace("”", '"').replace("″", '"')
    m = re.search(r"(\d)\s*[-'’]\s*(\d{1,2})", s)
    if m:
        return int(m.group(1)) * 12 + int(m.group(2))
    return None


def _num(s):
    if s is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(s))
    return float(m.group(0)) if m else None


def plausible_name(n):
    n = _clean(n)
    if not n or len(n) < 4 or len(n) > 40:
        return False
    if NOISE.match(n):
        return False
    if not re.match(r"^[A-Za-z][A-Za-z'\.\-À-ɏ]*(?: [A-Za-z'\.\-À-ɏ]+){1,3}$", n):
        return False
    if not re.search(r"[a-z]", n):
        # ALL-CAPS is a column header ("DRAFT RANGE", "COMMENTS"), not a name
        return False
    return True


# ===================================================== nbadraft.net big board
ND_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
ND_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)


def parse_nd_board(html):
    """Both eras: <table class="nba_ranking bigboard"> (2008-2018) and
    <table class="big-board-table ..."> (2019+). Columns:
    rank | change | player | height | weight | pos | school/team | class
    """
    out = []
    # isolate the big-board table
    tbl = None
    for m in re.finditer(r"<table[^>]*class=\"([^\"]*)\"[^>]*>(.*?)</table>", html, re.S | re.I):
        cls = m.group(1).lower()
        if "bigboard" in cls or "big-board" in cls or "nba_ranking" in cls:
            tbl = m.group(2)
            break
    if tbl is None:
        # fall back: any table whose header row has Change + School/Team
        for m in re.finditer(r"<table[^>]*>(.*?)</table>", html, re.S | re.I):
            body = m.group(1)
            head = body[:600].lower()
            if "change" in head and ("school/team" in head or "school" in head):
                tbl = body
                break
    if tbl is None:
        return out

    for rm in ND_ROW.finditer(tbl):
        row = rm.group(1)
        cells = ND_CELL.findall(row)
        if len(cells) < 7:
            continue
        rank_txt = _clean(strip_tags(cells[0]))
        m = re.match(r"^(\d{1,3})\.?$", rank_txt)
        if not m:
            continue
        rank = int(m.group(1))
        change_txt = _clean(strip_tags(cells[1]))
        cm = re.search(r"([+-]\s*\d+)", change_txt)
        if cm:
            change = int(cm.group(1).replace(" ", ""))
        elif re.search(r"arrow_no_change", cells[1]):
            change = 0
        elif cells[1].strip() in ("", "&nbsp;"):
            change = 0
        else:
            change = None
        name = _clean(strip_tags(cells[2]))
        if not plausible_name(name):
            continue
        out.append({
            "rank": rank, "name": name, "change": change,
            "height_in": _ht_in(_clean(strip_tags(cells[3]))),
            "weight": _num(_clean(strip_tags(cells[4]))),
            "pos": _clean(strip_tags(cells[5]))[:12],
            "school": _clean(strip_tags(cells[6]))[:60],
            "klass": _clean(strip_tags(cells[7]))[:12] if len(cells) > 7 else "",
            "age": None, "tier": None,
        })
    # keep the first occurrence of each rank, ranks must be 1..150
    seen, ded = set(), []
    for r in out:
        if r["rank"] in seen or not (1 <= r["rank"] <= 150):
            continue
        seen.add(r["rank"])
        ded.append(r)
    return ded


# ================================================ nbadraft.net mock (editorial)
# NBA franchises (incl. historical names) -- used only to reject team cells so
# they are never mistaken for a player name.
TEAM_WORDS = set("""
atlanta hawks boston celtics brooklyn nets charlotte hornets bobcats chicago bulls
cleveland cavaliers cavs dallas mavericks denver nuggets detroit pistons
golden state warriors houston rockets indiana pacers la clippers los angeles
lakers memphis grizzlies miami heat milwaukee bucks minnesota timberwolves
new orleans pelicans hornets new jersey new york knicks oklahoma city thunder
orlando magic philadelphia sixers phoenix suns portland trail blazers
sacramento kings san antonio spurs seattle sonics supersonics toronto raptors
utah jazz vancouver washington wizards nets clippers okc phi ny nj gs sa
""".split())

# 2004-2008 cell shape: "Dwight Howard 6-10 240 PF GA HSSr."
NDM_PLAYER = re.compile(
    r"^([A-Z][A-Za-z'\.\-\u00C0-\u024F]+(?:\s+[A-Za-z'\.\-\u00C0-\u024F]+){1,3})"
    r"\s+(\d)\s*-\s*(\d{1,2})\s+(\d{2,3})\b")


# 2000-2003 cell shape: "Kenyon Martin Cincinnati Sr. PF 6-9 230"
# (name, then school, then class, position, height, weight).  The name group is
# lazy so it takes the shortest run of capitalised tokens that still leaves a
# school/class/pos/ht/wt tail.
NDM_PLAYER2 = re.compile(
    r"^([A-Z][A-Za-z'\.\-\u00C0-\u024F]+(?:\s+[A-Za-z'\.\-\u00C0-\u024F]+){1,2}?)"
    r"\s+.{0,40}?\b(?:Fr|So|Jr|Sr|HSSr|HSJr|Intl|Int)\.?\s+"
    r"(?:PG|SG|SF|PF|C|G|F)(?:/(?:PG|SG|SF|PF|C|G|F))?\s+"
    r"(\d)\s*-\s*(\d{1,2})\s+(\d{2,3})\b")


def _is_team(text):
    t = _clean(text).lower().strip("*. ")
    if not t:
        return True
    toks = re.sub(r"[^a-z ]", " ", t).split()
    return bool(toks) and all(w in TEAM_WORDS for w in toks)


def parse_nd_mock(html):
    """nbadraft.net editorial mock drafts, three layout eras:

    (a) 2001-2008 two-column tables: one <tr> holds BOTH pick N (round 1) and
        pick N+30 (round 2); cells run  N. | logo | <b>Team</b> |
        "First Last 6-10 240 PF School Class".
    (b) 2009-2018 one pick per <tr>: N | logo | <a href=/players/..>Name</a> |
        height | weight | pos | school | class.
    (c) 2019+ WordPress tables, same one-pick-per-row shape.

    A cell is a rank when its whole text is "N" / "N."; a cell is a player when
    it holds a /players/ link, or its text starts with a name followed by a
    height and weight, or (last resort) it is a plain 2-4 token name that is
    not an NBA franchise.
    """
    out = []
    for rm in ND_ROW.finditer(html):
        cells = ND_CELL.findall(rm.group(1))
        if len(cells) < 3:
            continue
        cur = None
        for c in cells:
            t = _clean(strip_tags(c))
            m = re.match(r"^(\d{1,3})\.?$", t)
            if m:
                cur = int(m.group(1))
                continue
            if cur is None or not (1 <= cur <= 90):
                continue
            name = None
            height = None
            lm = re.search(r"/players/[^\"'>]*[\"']?[^>]*>(.*?)</a>", c, re.S | re.I)
            if lm:
                cand = _clean(strip_tags(lm.group(1)))
                if plausible_name(cand):
                    name = cand
            if name is None:
                pm = NDM_PLAYER.match(t)
                if pm and plausible_name(pm.group(1)):
                    name = _clean(pm.group(1))
                    height = int(pm.group(2)) * 12 + int(pm.group(3))
            if name is None:
                pm = NDM_PLAYER2.match(t)
                if pm and plausible_name(pm.group(1)) and not _is_team(pm.group(1)):
                    name = _clean(pm.group(1))
                    height = int(pm.group(2)) * 12 + int(pm.group(3))
            if name is None and plausible_name(t) and not _is_team(t) \
                    and not re.search(r"<b>", c, re.I):
                name = t
            if name:
                out.append({"rank": cur, "name": name, "change": None,
                            "height_in": height, "weight": None, "pos": "",
                            "school": "", "klass": "", "age": None, "tier": None})
                cur = None
    seen, ded = set(), []
    for r in out:
        if r["rank"] in seen:
            continue
        seen.add(r["rank"])
        ded.append(r)
    return sorted(ded, key=lambda x: x["rank"])


# ============================================ nbadraft.net crowd consensus page
def parse_nd_crowd(html):
    """/nba-mock-drafts/consensus/ -- a table of aggregated user mocks:
    Rank/Pick | Player | ... (layouts vary; same <tr> extraction as the mock)."""
    rows = parse_nd_mock(html)
    if rows:
        return rows
    out = []
    txt = strip_tags(html)
    for m in re.finditer(r"(?m)^\s*(\d{1,3})[\.\)]\s+([A-Z][A-Za-z'\.\-]+(?: [A-Za-z'\.\-]+){1,3})\s*$", txt):
        n = _clean(m.group(2))
        if plausible_name(n):
            out.append({"rank": int(m.group(1)), "name": n, "change": None,
                        "height_in": None, "weight": None, "pos": "", "school": "",
                        "klass": "", "age": None, "tier": None})
    return out


# ================================================== DraftExpress (all layouts)
# href may be quoted (2010+) or unquoted (the 2008-2009 layout)
DX_PROFILE = re.compile(
    r"href=[\"']?[^\"'> ]*?/profile/([A-Za-z0-9\-\.'%_]+?)-(\d+)/?[\"']?[^>]*>"
    r"(?:\s*<b>)?(.*?)(?:</b>\s*)?</a>",
    re.S | re.I)
DX_RANK_TOKENS = re.compile(
    r"(?:<font size=[\"']?[45][\"']?[^>]*>\s*(\d{1,3})\.?\s*</font>"   # mock / 2015+ board
    r"|<td[^>]*>\s*(\d{1,3})\s*</td>"                                  # 2008-2014 bluecells
    r"|<div class=[\"']?numero[\"']?[^>]*>\s*<font[^>]*>\s*(\d{1,3})\.?\s*</font>)",
    re.S | re.I)


def _dx_rank_before(html, start, floor):
    """Nearest rank token in html[floor:start]."""
    best = None
    for m in DX_RANK_TOKENS.finditer(html, floor, start):
        g = m.group(1) or m.group(2) or m.group(3)
        if g is not None:
            best = int(g)
    return best


DX_META = re.compile(
    r"(?:<br\s*/?>\s*)?([A-Z]{1,2}(?:/[A-Z]{1,2})?)?\s*\(?\s*"
    r"(?:<a[^>]*/clubhouse/[^\"']*\"[^>]*>(.*?)</a>)?", re.S)


def parse_dx(html, is_mock=False):
    """One parser for the DX Top-100 board and the DX mock draft (both list
    /profile/ links preceded by a rank/pick token)."""
    out = []
    prev_end = 0
    for pm in DX_PROFILE.finditer(html):
        name = _clean(strip_tags(pm.group(3)))
        if not plausible_name(name):
            prev_end = pm.end()
            continue
        rank = _dx_rank_before(html, pm.start(), prev_end)
        prev_end = pm.end()
        if rank is None:
            continue
        tail = html[pm.end():pm.end() + 700]
        # position: first token after the </a>
        pos = ""
        m = re.match(r"\s*(?:</font>)?\s*(?:&nbsp;|\s)*([A-Z]{1,2}(?:/[A-Z]{1,2})?)\b", tail)
        if m:
            pos = m.group(1)
        school = ""
        sm = re.search(r"/clubhouse/[^\"'> ]*[\"']?[^>]*>(.*?)</a>", tail, re.S | re.I)
        if sm:
            school = _clean(strip_tags(sm.group(1)))[:60]
        ttxt = _clean(strip_tags(tail))
        am = re.search(r"(\d{1,2}(?:\.\d)?)\s*years?\s*old", ttxt, re.I)
        age = float(am.group(1)) if am else None
        km = re.search(r"\b(Freshman|Sophomore|Junior|Senior|Fifth Year|International|Intl)\b",
                       ttxt, re.I)
        klass = km.group(1) if km else ""
        hm = re.search(r"(\d)\s*['’]\s*(\d{1,2})", ttxt)
        height = int(hm.group(1)) * 12 + int(hm.group(2)) if hm else None
        wm = re.search(r"(\d{2,3})\s*lbs", ttxt, re.I)
        weight = float(wm.group(1)) if wm else None
        out.append({"rank": rank, "name": name, "change": None, "height_in": height,
                    "weight": weight, "pos": pos, "school": school, "klass": klass,
                    "age": age, "tier": None, "dx_id": pm.group(2)})
    hi = 90 if is_mock else 160
    seen, ded = set(), []
    for r in out:
        if r["rank"] in seen or not (1 <= r["rank"] <= hi):
            continue
        seen.add(r["rank"])
        ded.append(r)
    return ded


# two stamp formats appear across the site's life:
#   "This Ranking was last updated on Mon May 19th at 04:41:19 PM"   (2012-2016)
#   "Last updated : June 14, 2017 at 04:40 pm"                        (2017)
DX_LASTUPD = re.compile(
    r"last updated\s*(?:on|:)?\s*(?:\w{3,9},?\s+)?([A-Za-z]{3,9})\.?\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?", re.I)
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def dx_last_updated(html, capture_ts):
    """'This Ranking was last updated on Mon May 19th at 04:41:19 PM' -> date str.
    The year is usually absent, so it is taken from the capture timestamp (and
    rolled back a year if that would place the update after the capture)."""
    txt = strip_tags(html)
    m = DX_LASTUPD.search(txt)
    if not m:
        return None
    mon = MONTHS.get(m.group(1)[:3].lower())
    if not mon:
        return None
    day = int(m.group(2))
    yr = int(m.group(3)) if m.group(3) else int(capture_ts[:4])
    cap_md = (int(capture_ts[4:6]), int(capture_ts[6:8]))
    if not m.group(3) and (mon, day) > cap_md:
        yr -= 1
    try:
        return "%04d-%02d-%02d" % (yr, mon, day)
    except Exception:
        return None


# ============================================================ The Stepien
STEP_CARD = re.compile(r"<div class=\"rank-(tier|card)\"[^>]*>(.*?)(?=<div class=\"rank-(?:tier|card)\"|</div>\s*</div>\s*</div>)",
                       re.S | re.I)


def parse_stepien(html):
    """Two layouts:
    (a) composite '20xx Draft Rankings' pages: <div class="rank-tier"><span>Tier N</span>
        and <div class="rank-card"><h3>N. Name</h3><span class="rank-team">School</span>
    (b) individual analyst posts: plain '10. Michael Porter Jr.' lines with
        optional '<h*>Tier N</h*>' headers.
    """
    out = []
    tier = None
    # layout (a): split on the card/tier boundaries so the final card is kept
    marks = [(m.start(), m.group(1)) for m in
             re.finditer(r"<div class=\"rank-(tier|card)\"", html, re.I)]
    for i, (pos, kind) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else min(len(html), pos + 6000)
        blk = html[pos:end]
        if kind.lower() == "tier":
            tm = re.search(r"<span[^>]*>(.*?)</span>", blk, re.S | re.I)
            if tm:
                tier = _clean(strip_tags(tm.group(1)))[:20]
            continue
        hm = re.search(r"<h[1-6][^>]*>\s*(?:(\d{1,3})\.)?\s*(.*?)</h[1-6]>",
                       blk, re.S | re.I)
        if not hm:
            continue
        name = _clean(strip_tags(hm.group(2)))
        if not plausible_name(name):
            continue
        # the 2020 board dropped explicit numbering ("order within tiers is
        # fluid"); rank is then the card's ordinal position on the page, which
        # is exactly the order the site presents the board in
        rank = int(hm.group(1)) if hm.group(1) else (len(out) + 1)
        sm = re.search(r"class=\"rank-team\"[^>]*>(.*?)</span>", blk, re.S | re.I)
        out.append({"rank": rank, "name": name, "change": None,
                    "height_in": None, "weight": None, "pos": "",
                    "school": _clean(strip_tags(sm.group(1)))[:60] if sm else "",
                    "klass": "", "age": None, "tier": tier})
    if out:
        return _dedupe_rank(out)

    # layout (b): headings / paragraphs "N. Name"
    body = html
    em = re.search(r"class=\"[^\"]*entry-content[^\"]*\"[^>]*>(.*)", html, re.S | re.I)
    if em:
        body = em.group(1)
    tier = None
    for m in re.finditer(r"<(h[1-6]|p|li|strong|div)[^>]*>(.*?)</\1>", body, re.S | re.I):
        seg = _clean(strip_tags(m.group(2)))
        tm = re.match(r"^(Tier\s*[0-9IVX]+[a-z]?)\b", seg, re.I)
        if tm and len(seg) < 60:
            tier = tm.group(1)
            continue
        rm = re.match(r"^(\d{1,3})[\.\)]\s+([A-Za-z][A-Za-z'\.\-À-ɏ]*"
                      r"(?: [A-Za-z'\.\-À-ɏ]+){1,3})\b", seg)
        if not rm:
            continue
        name = _clean(rm.group(2))
        if not plausible_name(name):
            continue
        out.append({"rank": int(rm.group(1)), "name": name, "change": None,
                    "height_in": None, "weight": None, "pos": "", "school": "",
                    "klass": "", "age": None, "tier": tier})
    return _dedupe_rank(out)


def _dedupe_rank(rows):
    seen, ded = set(), []
    for r in sorted(rows, key=lambda x: x["rank"]):
        if r["rank"] in seen or not (1 <= r["rank"] <= 200):
            continue
        seen.add(r["rank"])
        ded.append(r)
    return ded


# ------------------------------------------------ Stepien analyst-grid layout
def parse_stepien_indiv(html):
    """The '/<year>-individual-rankings/' pages are a tablepress grid:

        | Composite | Mike Gribanov | Cole Zwicker | ... |
        | 1. Zion Williamson | 1.01 | 1.01 | ... |

    Column 1 carries the composite entry (an <h3>N. Name</h3>, or a
    <div class="rank-tier"> header) and every other column carries that
    analyst's ranking in "Tier.OverallRank" form ("3.06" = tier 3, 6th
    overall), or a bare integer, or "NR".

    Returns [] when the page is not this layout.
    """
    m = re.search(r"<table[^>]*class=\"[^\"]*(?:tablepress|rankings-table)[^\"]*\"[^>]*>(.*?)</table>",
                  html, re.S | re.I)
    if not m:
        return []
    tbl = m.group(1)
    hm = re.search(r"<thead.*?</thead>", tbl, re.S | re.I)
    analysts = []
    if hm:
        for c in re.findall(r"<th[^>]*>(.*?)</th>", hm.group(0), re.S | re.I):
            analysts.append(_clean(strip_tags(c)))
    if len(analysts) < 2:
        return []
    out = []
    tier = None
    for rm in re.finditer(r"<tr[^>]*>(.*?)</tr>", tbl, re.S | re.I):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", rm.group(1), re.S | re.I)
        if len(cells) < 2:
            continue
        c0 = cells[0]
        tm = re.search(r"rank-tier\"[^>]*>\s*<span>(.*?)</span>", c0, re.S | re.I)
        if tm:
            tier = _clean(strip_tags(tm.group(1)))[:20]
            continue
        nm = re.search(r"<h[1-6][^>]*>\s*(\d{1,3})\.\s*(.*?)</h[1-6]>", c0, re.S | re.I)
        if not nm:
            t0 = _clean(strip_tags(c0))
            nm2 = re.match(r"^(\d{1,3})[\.\)]\s+(.+)$", t0)
            if not nm2:
                continue
            rank, name = int(nm2.group(1)), _clean(nm2.group(2))
        else:
            rank, name = int(nm.group(1)), _clean(strip_tags(nm.group(2)))
        if not plausible_name(name):
            continue
        ar = {}
        for i, c in enumerate(cells[1:], start=1):
            if i >= len(analysts):
                break
            t = _clean(strip_tags(c))
            if not t or t.upper().startswith("NR"):
                continue
            mm = re.match(r"^(\d{1,2})\.(\d{1,3})$", t)
            if mm:
                ar[analysts[i]] = int(mm.group(2))
            elif re.match(r"^\d{1,3}$", t):
                ar[analysts[i]] = int(t)
        out.append({"rank": rank, "name": name, "change": None, "height_in": None,
                    "weight": None, "pos": "", "school": "", "klass": "",
                    "age": None, "tier": tier, "analyst_ranks": ar})
    return out

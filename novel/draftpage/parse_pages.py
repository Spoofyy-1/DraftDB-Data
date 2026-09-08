#!/usr/bin/env python3
"""Rule-based extraction of pre-draft "draft page" features from the last
Wikipedia revision of "YYYY NBA draft" BEFORE draft night.

Reads raw/YYYY.json (written by fetch_pages.py), writes features.csv,
unmatched.csv, provenance.csv, counts.csv.  Regex + dictionaries only.
"""
import csv, json, os, re, sys, unicodedata
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
IDENTITY = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"
AGEFILE = "/Users/kennakao/nba/datarebuild/age_verified_wiki.csv"

DRAFT_DATE = {2000: "2000-06-28", 2001: "2001-06-27", 2002: "2002-06-26", 2003: "2003-06-26",
              2004: "2004-06-24", 2005: "2005-06-28", 2006: "2006-06-28", 2007: "2007-06-28",
              2008: "2008-06-26", 2009: "2009-06-25", 2010: "2010-06-24", 2011: "2011-06-23",
              2012: "2012-06-28", 2013: "2013-06-27", 2014: "2014-06-26", 2015: "2015-06-25",
              2016: "2016-06-23", 2017: "2017-06-22", 2018: "2018-06-21", 2019: "2019-06-20",
              2020: "2020-11-18", 2021: "2021-07-29", 2022: "2022-06-23", 2023: "2023-06-22",
              2024: "2024-06-26", 2025: "2025-06-25",
              # 2026 is not in COLLECTOR_RULES.md; date taken from this project's own
              # wiki_raw/attn_*.json cache (draft_date), which matches the rules table
              # exactly for every year 2000-2025.
              2026: "2026-06-24"}

# ------------------------------------------------------------------ wikitext --
RE_COMMENT = re.compile(r"<!--.*?-->", re.S)
RE_COMMENT_OPEN = re.compile(r"<!--.*\Z", re.S)          # unterminated comment
RE_REF_PAIR = re.compile(r"<ref[^>]*>.*?</ref\s*>", re.S | re.I)
RE_REF_SELF = re.compile(r"<ref[^>]*/\s*>", re.S | re.I)
RE_TAG = re.compile(r"<[^>]{1,300}>")
RE_HEAD = re.compile(r"^(={2,6})\s*(.*?)\s*\1\s*$", re.M)
RE_LINK = re.compile(r"\[\[([^\]\[|]{1,150})(?:\|([^\]\[]{0,150}))?\]\]")
RE_DISAMB = re.compile(r"\s*\([^)]*\)\s*$")


def strip_comments(s):
    s = RE_COMMENT.sub(" ", s)
    return RE_COMMENT_OPEN.sub(" ", s)


def strip_refs(s):
    s = RE_REF_PAIR.sub(" ", s)
    return RE_REF_SELF.sub(" ", s)


RE_SORTNAME = re.compile(r"\{\{\s*sortname\s*\|([^{}|]*)\|([^{}|]*)((?:\|[^{}|]*)*)\}\}", re.I)


def expand_sortname(s):
    """{{sortname|First|Last}} / {{sortname|First|Last|dab=basketball}} -> 'First Last'
    (2015 uses this template inside its early-entrant tables)."""
    return RE_SORTNAME.sub(lambda m: (m.group(1).strip() + " " + m.group(2).strip()).strip(), s)


def strip_templates(s, rounds=10):
    inner = re.compile(r"\{\{[^{}]*\}\}")
    for _ in range(rounds):
        s, n = inner.subn(" ", s)
        if not n:
            break
    return s


def prose(s):
    """Refs/templates/tags removed, wikilinks kept."""
    s = strip_refs(s)
    s = strip_templates(s)
    s = RE_TAG.sub(" ", s)
    s = s.replace("'''", "").replace("''", "")
    s = re.sub(r"\[(?:https?|//)\S+?(?:\s+([^\]]*))?\]", r"\1", s)
    return re.sub(r"[ \t]+", " ", s)


def unlink(s):
    s = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ sections --
def section_tree(wt):
    """[(level, path_tuple, body)] -- body is raw wikitext (comments stripped)."""
    out = []
    ms = list(RE_HEAD.finditer(wt))
    out.append((0, ("",), wt[:ms[0].start() if ms else len(wt)]))
    stack = []
    for i, m in enumerate(ms):
        lvl = len(m.group(1))
        head = m.group(2).strip()
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        stack.append((lvl, head))
        end = ms[i + 1].start() if i + 1 < len(ms) else len(wt)
        out.append((lvl, tuple(h for _, h in stack), wt[m.end():end]))
    return out


# -------------------------------------------------------------------- names ---
SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?\s*$")
PARTICLES = {"de", "van", "von", "der", "den", "da", "di", "dos", "del", "la", "le",
             "el", "bin", "al", "mc", "st", "dell", "ter", "op"}
NON_PERSON = re.compile(
    r"\b(university|universities|college|colleges|school|academy|league|association|conference|"
    r"team|teams|club|olympic|olympics|games|championship|championships|tournament|cup|finals|"
    r"basketball|football|baseball|soccer|hockey|nba|wnba|nfl|mlb|nhl|ncaa|fiba|euroleague|"
    r"draft|award|trophy|state|county|city|national|american|united|company|magazine|news|"
    r"television|network|institute|program|series|season|region|province|republic|liga|"
    r"island|islands|army|navy|force|church|center|centre|arena|stadium|hall|fame|players)\b",
    re.I)


def norm_name(s):
    s = RE_DISAMB.sub("", s or "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("’", "'").replace("ʼ", "'").lower()
    s = re.sub(r"[.'`]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    for _ in range(2):
        s2 = SUFFIX.sub("", s).strip()
        if s2 == s:
            break
        s = s2
    toks = s.split()
    # merge runs of single letters:  "r j barrett" -> "rj barrett"
    merged, buf = [], ""
    for t in toks:
        if len(t) == 1:
            buf += t
        else:
            if buf:
                merged.append(buf); buf = ""
            merged.append(t)
    if buf:
        merged.append(buf)
    return " ".join(merged)


def looks_like_person(name):
    """Documented shape test: 2-5 tokens, each capitalised (or a known particle),
    no digits, no institution keyword."""
    n = RE_DISAMB.sub("", (name or "").strip())
    if not n or any(ch.isdigit() for ch in n):
        return False
    if NON_PERSON.search(n):
        return False
    toks = [t for t in re.split(r"\s+", n) if t]
    if not (2 <= len(toks) <= 5):
        return False
    for t in toks:
        if t.lower().strip(".") in PARTICLES:
            continue
        c = t.lstrip("(\"'‘“")
        if not c or not c[0].isupper():
            return False
    return True


# ------------------------------------------------------------- list entries ---
RE_FLAG_PREFIX = re.compile(r"^(?:\s*(?:\{\{[^{}]*\}\}|/|–|-|,)\s*)+")


def entry_name(item):
    """Leading player name from one list item / table cell.

    Rules: expand {{sortname}}, strip refs + HTML tags, strip leading flag
    templates and separators (including a comma, as in '{{flag|Spain}}, [[X]]');
    if the remainder starts with a wikilink, use (display, target) of that link;
    otherwise take the text up to the first comma / en-dash / hyphen / paren.
    Returns (display_name, link_target or None) or (None, None).
    """
    s = expand_sortname(item)
    s = strip_refs(s)
    s = RE_TAG.sub(" ", s)
    s = re.sub(r"^[*#:;|]+", "", s).strip()
    s = RE_FLAG_PREFIX.sub("", s).strip()
    m = RE_LINK.match(s)
    if m:
        tgt = m.group(1).strip()
        disp = (m.group(2) or tgt).strip()
        return disp, tgt
    s = strip_templates(s)
    s = re.sub(r"\[(?:https?|//)\S+?(?:\s+([^\]]*))?\]", r"\1", s)
    s = s.replace("'''", "").replace("''", "").strip()
    s = re.split(r"\s*[,–—]|\s+-\s+|\s*\(", s)[0].strip()
    s = re.sub(r"\s+", " ", s)
    return (s, None) if s else (None, None)


def bullet_items(body):
    """Top-level '*' list items (continuation lines joined; '**' notes skipped)."""
    items, cur = [], None
    for line in body.split("\n"):
        st = line.strip()
        if st.startswith("**") or st.startswith("*:"):
            continue
        if st.startswith("*"):
            if cur is not None:
                items.append(cur)
            cur = st
        elif cur is not None:
            if st == "" or st.startswith(("{|", "|}", "|-", "{{", "==")):
                items.append(cur); cur = None
            else:
                cur += " " + st
    if cur is not None:
        items.append(cur)
    return items


def split_cells(line):
    """Split a table line into cells, honouring [[..]] / {{..}} nesting, and drop
    per-cell style attributes ('style="x"| value' -> 'value')."""
    body = line[1:] if line[:1] in "|!" else line
    sep = "!!" if line.startswith("!") else "||"
    cells, depth_sq, depth_cu, cur, i = [], 0, 0, "", 0
    while i < len(body):
        if body.startswith("[[", i):
            depth_sq += 1; cur += "[["; i += 2; continue
        if body.startswith("]]", i):
            depth_sq -= 1; cur += "]]"; i += 2; continue
        if body.startswith("{{", i):
            depth_cu += 1; cur += "{{"; i += 2; continue
        if body.startswith("}}", i):
            depth_cu -= 1; cur += "}}"; i += 2; continue
        if depth_sq <= 0 and depth_cu <= 0 and body.startswith(sep, i):
            cells.append(cur); cur = ""; i += 2; continue
        cur += body[i]; i += 1
    cells.append(cur)
    out = []
    for c in cells:
        # attribute prefix: a single '|' at nesting depth 0 in the first ~90 chars
        d_sq = d_cu = 0
        cut = -1
        for j, ch in enumerate(c):
            if c.startswith("[[", j): d_sq += 1
            elif c.startswith("]]", j): d_sq -= 1
            elif c.startswith("{{", j): d_cu += 1
            elif c.startswith("}}", j): d_cu -= 1
            elif ch == "|" and d_sq <= 0 and d_cu <= 0:
                cut = j; break
        if cut >= 0 and re.search(r"=", c[:cut]):
            c = c[cut + 1:]
        out.append(c.strip())
    return out


def tables(body):
    """Yield raw wikitext of each top-level {| ... |} table in body."""
    out, depth, start = [], 0, None
    for m in re.finditer(r"^\s*(\{\||\|\})", body, re.M):
        if m.group(1) == "{|":
            if depth == 0:
                start = m.start()
            depth += 1
        else:
            depth -= 1
            if depth == 0 and start is not None:
                out.append(body[start:m.end()]); start = None
    return out


def table_caption(tbl):
    m = re.search(r"^\s*\|\+\s*(.*)$", tbl, re.M)
    return unlink(strip_templates(strip_refs(m.group(1)))) if m else ""


def table_rows(tbl):
    """[(is_header, has_colspan, [cells])].

    A row counts as a HEADER row only when every cell came from a '!' line, so
    'plainrowheaders' tables (whose first cell is `!scope="row"|Player`) are
    still treated as data rows.  Rows using colspan cannot be column-aligned and
    are flagged so callers can skip them.
    """
    rows, cur, bang, span = [], None, [], False
    for line in tbl.split("\n"):
        st = line.strip()
        if st.startswith("{|"):
            continue
        if st.startswith("|}"):
            break
        if st.startswith("|+"):
            continue
        if st.startswith("|-"):
            if cur is not None:
                rows.append((bool(bang) and all(bang), span, cur))
            cur, bang, span = [], [], False
            continue
        if st[:1] in ("!", "|"):
            if cur is None:
                cur, bang, span = [], [], False
            cells = split_cells(st)
            cur.extend(cells)
            bang.extend([st.startswith("!")] * len(cells))
            if re.search(r"colspan", st, re.I):
                span = True
        elif cur:
            cur[-1] = cur[-1] + " " + st
    if cur is not None:
        rows.append((bool(bang) and all(bang), span, cur))
    return rows


def table_first_cell_names(body):
    """[(name, target, raw_cell, table_caption)] for every data row's first cell."""
    out = []
    for tbl in tables(body):
        cap = table_caption(tbl)
        for is_hdr, _span, cells in table_rows(tbl):
            if is_hdr or not cells:
                continue
            disp, tgt = entry_name(cells[0])
            if disp:
                out.append((disp, tgt, cells[0], cap))
    return out


# ------------------------------------------------- draft-results assertion ----
PLACEHOLDER = re.compile(r"^(?:[-–—]|&[mn]dash;|n/?a|tbd|\?+)$", re.I)


def blank(cell):
    """True when a results-table player cell holds no name: empty, &nbsp;, or a
    dash / 'N/A' / 'TBD' placeholder (2007 uses '-' for every unfilled cell)."""
    c = strip_comments(cell or "")
    c = strip_refs(c)
    c = c.replace("&nbsp;", " ").replace(" ", " ")
    c = RE_TAG.sub(" ", c)
    c = strip_templates(c)
    c = c.replace("'''", "").replace("''", "").strip()
    return (not c) or bool(PLACEHOLDER.match(c))


def selection_table_check(wt):
    """Every draft-results table must have EMPTY player cells (pre-draft proof).
    Returns (n_tables, n_rows, [offending strings]).  Rows using colspan (e.g.
    the 'Forfeited pick' rows of 2022) are skipped: their columns cannot be
    aligned to the header, so the player column is undefined for them."""
    n_tab = n_row = 0
    bad = []
    for tbl in tables(wt):
        rows = table_rows(tbl)
        hdr = None
        for is_hdr, _span, cells in rows:
            if is_hdr and cells:
                hdr = cells
                break
        if not hdr:
            continue
        pidx = None
        for i, c in enumerate(hdr):
            t = unlink(strip_templates(strip_refs(c))).strip()
            if re.match(r"^player\b", t, re.I):
                pidx = i
                break
        if pidx is None:
            continue
        data = [c for h, sp, c in rows if not h and not sp and len(c) > pidx]
        picks = [c for c in data if re.match(r"^\s*(\[\[[^\]]*\|)?\s*\d{1,2}\s*\]?\]?\s*$",
                                             strip_templates(c[0]).strip())]
        if len(picks) < 10:            # not a pick-by-pick results table
            continue
        n_tab += 1
        for cells in data:
            n_row += 1
            if not blank(cells[pidx]):
                bad.append(re.sub(r"\s+", " ", cells[pidx])[:120])
    return n_tab, n_row, bad


# ------------------------------------------------------------------- dates ----
MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}
RE_DATE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", re.I)
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
           "eight": 8, "nine": 9, "ten": 10}
RE_REL = re.compile(r"\b(?:(the following day|the next day|a day later)|"
                    r"(one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\s+days\s+later|"
                    r"(the following week|a week later))\b", re.I)


def first_date(text, year):
    """First explicit date in `text` that is <=120 days before, and before, draft night."""
    dd = DRAFT_DATE[year]
    draft = date(int(dd[:4]), int(dd[5:7]), int(dd[8:10]))
    for m in RE_DATE.finditer(text):
        yy = int(m.group(3)) if m.group(3) else year
        if yy != year:
            continue
        try:
            d = date(yy, MONTHS[m.group(1).lower()], int(m.group(2)))
        except ValueError:
            continue
        if draft - timedelta(days=120) <= d < draft:
            return d
    return None


def relative_date(text, prev):
    if prev is None:
        return None
    m = RE_REL.search(text)
    if not m:
        return None
    if m.group(1):
        return prev + timedelta(days=1)
    if m.group(2):
        g = m.group(2).lower()
        return prev + timedelta(days=WORDNUM.get(g, int(g) if g.isdigit() else 0))
    return prev + timedelta(days=7)


# -------------------------------------------------------------- green room ----
RE_LATER = re.compile(r"not on the original list|added later|later invited|"
                      r"later addition|added to the list", re.I)
RE_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")


def split_sentences(text):
    """Sentence split that never cuts inside a [[wikilink]] (needed for names
    with initials such as [[R.J. Hunter]])."""
    spans = [(m.start(), m.end()) for m in re.finditer(r"\[\[[^\]]*\]\]", text)]
    out, start = [], 0
    for m in RE_SENT.finditer(text):
        if any(a < m.start() < b for a, b in spans):
            continue
        out.append(text[start:m.start()]); start = m.end()
    out.append(text[start:])
    return [x.strip() for x in out if x.strip()]
RE_INVITE_CUE = re.compile(r"\binvit", re.I)


def merge_runs(body):
    """[(preamble_text, [items])] -- runs of '*' lines, merged across pure
    layout templates ({{col-2}}, {{div col}}, {{col-begin}} ...)."""
    lines = body.split("\n")
    pre = []
    idx = 0
    blocks = []                                     # (pre_lines, item_lines)
    while idx < len(lines):
        st = lines[idx].strip()
        if st.startswith("*") and not st.startswith("**"):
            items = []
            while idx < len(lines):
                st = lines[idx].strip()
                if st.startswith("**") or st.startswith("*:"):
                    idx += 1; continue
                if st.startswith("*"):
                    items.append(st); idx += 1; continue
                # look ahead across pure-layout / blank lines
                j, gap = idx, []
                while j < len(lines):
                    g = lines[j].strip()
                    if g == "" or re.fullmatch(r"(\{\{[^{}]*\}\}\s*)+", g):
                        gap.append(g); j += 1; continue
                    break
                if j < len(lines) and lines[j].strip().startswith("*") and \
                        not lines[j].strip().startswith("**"):
                    idx = j; continue
                break
            blocks.append((pre, items)); pre = []
        else:
            pre.append(lines[idx]); idx += 1
    return blocks


def parse_green_room(wt, year):
    """[(name, target, wave, announce_date, raw)] plus (list_found, n_waves)."""
    tree = section_tree(wt)
    blocks = []
    for lvl, path, body in tree:
        own = path[-1].lower()
        if re.search(r"invit", own) and re.search(r"attend", own):
            blocks.append(body)
    if not blocks:                                   # fallback: green-room prose
        for lvl, path, body in tree:
            m = re.search(r"green room", body, re.I)
            if m and RE_INVITE_CUE.search(body[m.start():]):
                blocks.append(body[m.start():])
    if not blocks:
        return [], 0
    body = "\n".join(blocks)
    out = []
    runs = merge_runs(body)
    runs = [(p, it) for p, it in runs if it]
    if runs:
        prev = None
        for wave, (pre_lines, items) in enumerate(runs, 1):
            pre = prose("\n".join(pre_lines))
            d = first_date(pre, year) or relative_date(pre, prev)
            prev = d or prev
            for it in items:
                disp, tgt = entry_name(it)
                if not disp:
                    continue
                later = bool(RE_LATER.search(it))
                w = wave if len(runs) > 1 else (2 if later else 1)
                if len(runs) == 1 and not RE_LATER.search(body):
                    w = ""                            # page draws no wave distinction
                dd = "" if (len(runs) == 1 and later) else (d or "")
                out.append((disp, tgt, w, dd, it))
        return out, len(runs)
    # no bullet list: prose sentences that announce invitees (>=3 person links)
    txt = prose(body)
    d = first_date(txt, year)
    for sent in split_sentences(txt):
        if not RE_INVITE_CUE.search(sent):
            continue
        lk = [((m.group(2) or m.group(1)).strip(), m.group(1).strip())
              for m in RE_LINK.finditer(sent)]
        lk = [(dp, tg) for dp, tg in lk if looks_like_person(dp)]
        if len(lk) < 3:
            continue
        for dp, tg in lk:
            out.append((dp, tg, "", d or "", sent[:200]))
    return out, (1 if out else 0)


# ---------------------------------------------------------------- entrants ----
def classify(path):
    joined = " > ".join(path).lower()
    own = path[-1].lower()
    withdrawn = bool(re.search(r"withdraw|withdrew", joined)) and \
        not re.search(r"previous draft", joined)
    tags = set()
    if re.search(r"early entrant|early entry|underclassmen declaring|"
                 r"international players declaring", joined):
        tags.add("early")
        if re.search(r"international", joined):
            tags.add("intl")
    if re.search(r"automatic(?:ally)? eligib", joined):
        tags.add("auto")
    if re.search(r"projected draftees|speculated|other lottery picks", own):
        tags.add("projected")
    if withdrawn:
        tags.add("withdrawn")
    return tags


def parse_lists(wt, year):
    """{tag: [(name, target, raw)]} for early / intl / auto / projected / withdrawn.

    A section's heading path sets the base tag; a table's caption refines it
    (2015 has no 'International players' sub-heading -- the split is carried by
    the table captions 'College underclassmen' / 'International players')."""
    got = {"early": [], "intl": [], "auto": [], "projected": [], "withdrawn": []}

    def add(tags, entries):
        if not entries:
            return
        if "withdrawn" in tags:
            got["withdrawn"].extend(entries)
            return
        for t in ("early", "intl", "auto", "projected"):
            if t in tags:
                got[t].extend(entries)

    for lvl, path, body in section_tree(wt):
        tags = classify(path)
        if not tags:
            continue
        bullets = []
        for it in bullet_items(body):
            disp, tgt = entry_name(it)
            if disp and looks_like_person(disp):
                bullets.append((disp, tgt, it))
        add(tags, bullets)
        for tbl in tables(body):
            cap = table_caption(tbl)
            ttags = set(tags)
            if cap:
                if re.search(r"international", cap, re.I):
                    ttags.add("intl")
                elif re.search(r"college|underclassmen|senior", cap, re.I):
                    ttags.discard("intl")
            entries = []
            for is_hdr, _span, cells in table_rows(tbl):
                if is_hdr or not cells:
                    continue
                disp, tgt = entry_name(cells[0])
                if disp and looks_like_person(disp):
                    entries.append((disp, tgt, cells[0]))
            add(ttags, entries)
    return got


# ------------------------------------------------------------------ matching --
def load_identity():
    by_year = {}
    for r in csv.DictReader(open(IDENTITY)):
        y = int(r["draft_year"])
        by_year.setdefault(y, []).append(
            {"pid": r["pid"], "name": r["player_name"], "norm": norm_name(r["player_name"])})
    return by_year


def load_birthyears():
    out = {}
    if os.path.exists(AGEFILE):
        for r in csv.DictReader(open(AGEFILE)):
            if r.get("birth_date"):
                out[r["pid"]] = int(r["birth_date"][:4])
    return out


BIRTH = load_birthyears()
RE_BORN = re.compile(r"\bborn\s+(19\d\d|20\d\d)\b", re.I)


def match(name, target, year, roster, raw="", allow_surname_tier=False):
    """Match a page name to a drafted player of the SAME draft year.

    Four documented tiers, tried in order on the link display text and then on
    the link target; each tier must yield exactly ONE candidate inside that
    draft year or the entry is logged as ambiguous instead of guessed:
      1 exact      normalised strings equal
      2 prefix     one token list is a leading sub-sequence of the other
                   ('Timothe Luwawu' ~ 'Timothe Luwawu-Cabarrot')
      3 firstpfx   same surname and one given name is a prefix of the other
                   ('Alexandre Sarr' ~ 'Alex Sarr')
      4 surname    same surname (>=5 chars), used only for the short green-room
                   list, where a nickname can replace the given name
                   ('Edrice Adebayo' ~ 'Bam Adebayo')
    A 'born YYYY' annotation on the page must agree with the verified birth year
    (age_verified_wiki.csv) when both are available.
    Returns (pid, tier) or (None, reason)."""
    cands, tier = [], None
    for key in [k for k in (name, target) if k]:
        n = norm_name(key)
        if not n:
            continue
        nt = n.split()
        hit = [p for p in roster if p["norm"] == n]
        if hit:
            cands, tier = hit, "exact"; break
        hit = []
        for p in roster:
            pt = p["norm"].split()
            k = min(len(nt), len(pt))
            if k >= 2 and nt[:k] == pt[:k]:
                hit.append(p)
        if hit:
            cands, tier = hit, "prefix"; break
        hit = []
        for p in roster:
            pt = p["norm"].split()
            if len(nt) >= 2 and len(pt) >= 2 and nt[-1] == pt[-1] and len(nt[-1]) >= 3 and \
                    (nt[0].startswith(pt[0]) or pt[0].startswith(nt[0])):
                hit.append(p)
        if hit:
            cands, tier = hit, "firstpfx"; break
        if allow_surname_tier and nt and len(nt[-1]) >= 5:
            hit = [p for p in roster if p["norm"].split() and p["norm"].split()[-1] == nt[-1]]
            if hit:
                cands, tier = hit, "surname"; break
    if not cands:
        return None, "no_match"
    if len(cands) > 1:
        return None, "ambiguous(%d)" % len(cands)
    pid = cands[0]["pid"]
    m = RE_BORN.search(raw or "")
    if m and pid in BIRTH and int(m.group(1)) != BIRTH[pid]:
        return None, "birthyear_conflict"
    return pid, tier


DEFS = [
    ("dp_page_year_covered",
     "1 if a pre-draft revision of the 'YYYY NBA draft' article exists for the "
     "player's draft year (0 for 2000-2004, whose articles were written after the fact)."),
    ("dp_green_room",
     "1 if the NBA invited the player to the draft green room, per the page's "
     "'Invited attendees' list; 0 for other players of a year that has such a list; "
     "empty for years with no list (2005-2010, 2020-2023)."),
    ("dp_green_room_days_before_draft",
     "Days from the announcement of that player's invite wave to draft night; empty "
     "when the page does not date the wave, and for non-invitees."),
    ("dp_green_room_wave",
     "1 = named in the initial invite announcement, 2/3 = later addition; empty when "
     "the page draws no wave distinction, and for non-invitees."),
    ("dp_early_entrant",
     "1 if listed as an early entrant (college underclassman/senior, international or "
     "'other' declarant) still in the draft at the cutoff; 0 for other players of a year "
     "with such a list; empty for years without one (2005, 2006, 2009)."),
    ("dp_intl_early_entrant",
     "1 if the early-entrant listing was the international one; 0/empty as above."),
    ("dp_auto_eligible",
     "1 if named in the page's 'automatically eligible entrants' player table -- the "
     "unusual cases only (pro contract abroad, G League, no college); 0 means 'not "
     "listed', NOT 'not automatically eligible'."),
    ("dp_wiki_projected",
     "1 if named in the editor-written 'projected draftees' / 'speculated picks' list "
     "(2005 and 2006 only); a Wikipedia mock-draft consensus, not an NBA signal."),
]


# ---------------------------------------------------------------------- main --
def main():
    roster_by_year = load_identity()
    years = sorted(DRAFT_DATE)
    feats = {}                       # pid -> dict
    unmatched, prov, counts, tiers = [], [], [], []
    aborted = []

    for y in years:
        path = os.path.join(RAW, "%d.json" % y)
        rec = json.load(open(path)) if os.path.exists(path) else {"status": "missing_cache"}
        roster = roster_by_year.get(y, [])
        for p in roster:
            feats.setdefault(p["pid"], {"pid": p["pid"], "year": y})
        url = ("https://en.wikipedia.org/w/index.php?oldid=%s" % rec["revid"]) \
            if rec.get("revid") else ""
        if rec.get("status") != "ok":
            for p in roster:
                feats[p["pid"]]["dp_page_year_covered"] = 0
            prov.append({"year": y, "status": rec.get("status"), "rev_ts": "", "revid": "",
                         "url": "", "cutoff": DRAFT_DATE[y] + "T22:00:00Z",
                         "sel_tables": "", "sel_rows": "", "player_cells_empty": "",
                         "green_room": 0, "early": 0, "intl": 0, "auto": 0, "projected": 0})
            counts.append({"year": y, "status": rec.get("status"), "green_room": "",
                           "gr_matched": "", "gr_waves": "", "gr_days_before": "",
                           "early": "", "early_matched": "", "intl": "", "intl_matched": "",
                           "auto": "", "auto_matched": "", "projected": "",
                           "projected_matched": "", "withdrawn": "", "withdrawn_matched": ""})
            continue

        wt = strip_comments(rec["wikitext"])

        # ---- dating assertion: draft-results player cells must be EMPTY --------
        n_tab, n_row, bad = selection_table_check(wt)
        if bad:
            aborted.append((y, len(bad), bad[:5]))
            for p in roster:
                feats[p["pid"]]["dp_page_year_covered"] = 0
            prov.append({"year": y, "status": "ABORT_player_cells_not_empty",
                         "rev_ts": rec["rev_ts"], "revid": rec["revid"], "url": url,
                         "cutoff": rec["cutoff"], "sel_tables": n_tab, "sel_rows": n_row,
                         "player_cells_empty": 0, "green_room": 0, "early": 0, "intl": 0,
                         "auto": 0, "projected": 0})
            continue

        for p in roster:
            feats[p["pid"]]["dp_page_year_covered"] = 1

        gr, n_waves = parse_green_room(wt, y)
        lists = parse_lists(wt, y)

        # pass 1 -- resolve every list; pass 2 -- reuse each year's own
        # (page name -> pid) mapping so a name that resolved on one list also
        # resolves on the others (e.g. 'Edrice Adebayo' is matched on the short
        # green-room list and that mapping then applies to the entrant lists).
        alias, alias_bad = {}, set()
        pending = []

        def resolve(entries, tag):
            pids, n_ok = {}, 0
            for e in entries:
                disp, tgt, raw = e[0], e[1], e[-1]
                pid, why = match(disp, tgt, y, roster, raw,
                                 allow_surname_tier=(tag == "green_room"))
                if pid:
                    pids[pid] = e; n_ok += 1
                    tiers.append({"year": y, "list": tag, "pid": pid, "tier": why,
                                  "name_on_page": disp})
                    for k in (norm_name(disp), norm_name(tgt or "")):
                        if not k:
                            continue
                        if alias.get(k, pid) != pid:
                            alias_bad.add(k)
                        alias[k] = pid
                else:
                    pending.append((pids, tag, e, why))
            return pids, n_ok

        def resolve_aliases():
            n = {}
            for pids, tag, e, why in pending:
                disp, tgt = e[0], e[1]
                pid = None
                for k in (norm_name(disp), norm_name(tgt or "")):
                    if k and k not in alias_bad and k in alias:
                        pid = alias[k]; break
                if pid and pid not in pids:
                    pids[pid] = e
                    n[tag] = n.get(tag, 0) + 1
                    tiers.append({"year": y, "list": tag, "pid": pid, "tier": "alias",
                                  "name_on_page": disp})
                elif not pid:
                    unmatched.append({"year": y, "list": tag, "name_on_page": disp,
                                      "link_target": tgt or "", "reason": why})
            return n

        gr_pids, gr_ok = resolve(gr, "green_room")
        early_pids, early_ok = resolve(lists["early"], "early_entrant")
        intl_pids, intl_ok = resolve(lists["intl"], "intl_early_entrant")
        auto_pids, auto_ok = resolve(lists["auto"], "auto_eligible")
        proj_pids, proj_ok = resolve(lists["projected"], "projected")
        wd_pids, wd_ok = resolve(lists["withdrawn"], "withdrawn")
        extra = resolve_aliases()
        gr_ok += extra.get("green_room", 0)
        early_ok += extra.get("early_entrant", 0)
        intl_ok += extra.get("intl_early_entrant", 0)
        auto_ok += extra.get("auto_eligible", 0)
        proj_ok += extra.get("projected", 0)
        wd_ok += extra.get("withdrawn", 0)

        dd = DRAFT_DATE[y]
        draft = date(int(dd[:4]), int(dd[5:7]), int(dd[8:10]))
        days_seen = set()

        for p in roster:
            f = feats[p["pid"]]
            if gr:
                f["dp_green_room"] = 1 if p["pid"] in gr_pids else 0
                if p["pid"] in gr_pids:
                    _, _, w, adate, _ = gr_pids[p["pid"]]
                    if w != "":
                        f["dp_green_room_wave"] = w
                    if adate:
                        f["dp_green_room_days_before_draft"] = (draft - adate).days
                        days_seen.add((draft - adate).days)
            if lists["early"]:
                inwd = p["pid"] in wd_pids and p["pid"] not in early_pids \
                    and p["pid"] not in intl_pids
                f["dp_early_entrant"] = 1 if (p["pid"] in early_pids or
                                              p["pid"] in intl_pids) else 0
                if inwd:
                    f["dp_early_entrant"] = 0
            if lists["intl"]:
                f["dp_intl_early_entrant"] = 1 if p["pid"] in intl_pids else 0
            if lists["auto"]:
                f["dp_auto_eligible"] = 1 if p["pid"] in auto_pids else 0
            if lists["projected"]:
                f["dp_wiki_projected"] = 1 if p["pid"] in proj_pids else 0

        prov.append({"year": y, "status": "ok", "rev_ts": rec["rev_ts"], "revid": rec["revid"],
                     "url": url, "cutoff": rec["cutoff"], "sel_tables": n_tab,
                     "sel_rows": n_row, "player_cells_empty": 1,
                     "green_room": len(gr), "early": len(lists["early"]),
                     "intl": len(lists["intl"]), "auto": len(lists["auto"]),
                     "projected": len(lists["projected"])})
        counts.append({"year": y, "status": "ok", "green_room": len(gr), "gr_matched": gr_ok,
                       "gr_waves": n_waves,
                       "gr_days_before": ";".join(str(x) for x in sorted(days_seen, reverse=True)),
                       "early": len(lists["early"]), "early_matched": early_ok,
                       "intl": len(lists["intl"]), "intl_matched": intl_ok,
                       "auto": len(lists["auto"]), "auto_matched": auto_ok,
                       "projected": len(lists["projected"]), "projected_matched": proj_ok,
                       "withdrawn": len(lists["withdrawn"]), "withdrawn_matched": wd_ok})

    # ------------------------------------------------------------------ write --
    cols = ["pid", "dp_page_year_covered", "dp_green_room",
            "dp_green_room_days_before_draft", "dp_green_room_wave", "dp_early_entrant",
            "dp_intl_early_entrant", "dp_auto_eligible", "dp_wiki_projected"]
    rows = [feats[k] for k in sorted(feats)]
    with open(os.path.join(HERE, "features.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    with open(os.path.join(HERE, "match_tiers.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["year", "list", "pid", "tier", "name_on_page"])
        w.writeheader(); w.writerows(tiers)
    with open(os.path.join(HERE, "unmatched.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["year", "list", "name_on_page", "link_target",
                                           "reason"])
        w.writeheader(); w.writerows(unmatched)
    with open(os.path.join(HERE, "provenance.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(prov[0].keys()))
        w.writeheader(); w.writerows(prov)
    with open(os.path.join(HERE, "counts_by_year.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(counts[0].keys()))
        w.writeheader(); w.writerows(counts)

    # ----------------------------------------------------------------- report --
    print("rows in features.csv: %d" % len(rows))
    if aborted:
        print("ABORTED YEARS (player cells not empty): %s" % aborted)
    print("\nper-year counts (items on page / matched to identity):")
    print("%-5s %-6s %10s %10s %6s %-14s %10s %10s %8s %9s" %
          ("year", "status", "greenroom", "gr_match", "blocks", "gr_days_before",
           "early", "early_mat", "intl", "intl_mat"))
    for c in counts:
        print("%-5s %-6s %10s %10s %6s %-14s %10s %10s %8s %9s" %
              (c["year"], c["status"][:6], c["green_room"], c["gr_matched"], c["gr_waves"],
               c["gr_days_before"], c["early"], c["early_matched"], c["intl"],
               c["intl_matched"]))
    nz = {c: sum(1 for r in rows if str(r.get(c, "")) not in ("", "0")) for c in cols[1:]}
    tot = {c: sum(1 for r in rows if str(r.get(c, "")) != "") for c in cols[1:]}
    print("\nfeature   non-missing / positive")
    for c in cols[1:]:
        print("  %-34s %5d / %4d" % (c, tot[c], nz[c]))
    import collections as _c
    print("\nmatch tiers: %s" % dict(_c.Counter(t["tier"] for t in tiers)))
    print("unmatched rows: %d  (see unmatched.csv)" % len(unmatched))

    year_of = {r["pid"]: r["year"] for r in rows}
    bands = [("2000-07", 2000, 2007), ("2008-18", 2008, 2018), ("2019-26", 2019, 2026)]
    print("\ncoverage by draft-year band (rows with a non-missing value):")
    print("  %-9s %6s  %s" % ("band", "pids", "  ".join("%-24s" % c for c in cols[1:])))
    for nm, lo, hi in bands:
        sel = [r for r in rows if lo <= year_of[r["pid"]] <= hi]
        cells = []
        for c in cols[1:]:
            k = sum(1 for r in sel if str(r.get(c, "")) != "")
            cells.append("%-24s" % ("%d (%.0f%%)" % (k, 100.0 * k / max(1, len(sel)))))
        print("  %-9s %6d  %s" % (nm, len(sel), "  ".join(cells)))

    print("\nfeature definitions:")
    for c, d in DEFS:
        print("  %-33s %s" % (c, d))


if __name__ == "__main__":
    main()

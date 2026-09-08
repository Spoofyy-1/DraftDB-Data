#!/usr/bin/env python3
"""Rule-based biographical features from cached Wikipedia wikitext.

Sources
  current article  : /Users/kennakao/nba/datarebuild/wiki_raw/current/<pid>.json  (fetched 2026-09-08)
                     -> TIME-INVARIANT facts only (relatives, HS sports, pathway, birthplace, handedness)
  pre-draft revision: raw/predraft/<pid>.json (fetched by fetch_predraft.py)
                     -> TIME-VARYING facts only (injuries), last revision strictly before draft night

No LLM judgement anywhere: regex + dictionaries (dicts.py), all documented in README.md.
Outputs: features.csv, provenance.csv, ambiguous_names.csv, unmatched.csv, coverage.txt
"""
import csv, json, os, re, sys, datetime as dt
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wtutil as W
import dicts as D

BASE = "/Users/kennakao/nba/datarebuild"
NAMES = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"
CUR = os.path.join(BASE, "wiki_raw/current")
PRE = os.path.join(HERE, "raw/predraft")
sys.path.insert(0, HERE)
from fetch_predraft import CUTOFF  # single source of truth for draft-night dates

RE_KIN = [(re.compile(p, re.I), c, f) for p, c, f in D.KIN_PATTERNS]
RE_KIN_ANY = re.compile(D.KIN_ANY, re.I)
RE_PRO = re.compile("|".join(D.PRO_SPORT_TOKENS))
RE_HS_SEC = re.compile(D.HS_SECTION, re.I)
RE_COLL_SEC = re.compile(D.COLLEGE_SECTION, re.I)
RE_HS_VERB = re.compile(D.HS_VERBS, re.I)
RE_SPORT = {s: re.compile("|".join(v), re.I) for s, v in D.HS_SPORTS.items()}
RE_AMFB = re.compile(r"\bgridiron\b|\bquarterback\b|\bwide receiver\b|\btight end\b|\blinebacker\b|"
                     r"\bdefensive (?:end|back|lineman)\b|\brunning back\b|\bcornerback\b|"
                     r"\bAmerican football\b|\bfree safety\b", re.I)
RE_PREP = re.compile(D.PREP_RX)          # case-sensitive: "<Name> Prep" needs the capitals
RE_PREP_I = re.compile(D.PREP_RX.rsplit("|", 1)[0], re.I)   # the wording-based part
RE_JUCO = re.compile(D.JUCO_RX, re.I)
RE_TRANSFER = re.compile(D.TRANSFER_RX, re.I)
RE_RECLASS = re.compile(r"reclassif", re.I)
RE_CLASSOF = re.compile(r"class of (?:the )?((?:19|20)\d\d)", re.I)
RE_GRAD = re.compile(r"graduat(?:ed|ing|es|ion)[^.]{0,60}?\b((?:19|20)\d\d)\b|"
                     r"\b((?:19|20)\d\d)\s+graduate\b", re.I)
RE_SENIOR = re.compile(r"senior (?:year|season)[^.]{0,40}?\b(?:19|20)\d\d[–\-—](\d{2})\b", re.I)
RE_LEFT = re.compile(D.HANDED_LEFT, re.I)
RE_RIGHT = re.compile(D.HANDED_RIGHT, re.I)
RE_SEV = {3: [re.compile(p, re.I) for p in D.SEV3],
          2: [re.compile(p, re.I) for p in D.SEV2],
          1: [re.compile(p, re.I) for p in D.SEV1]}
RE_SURG = re.compile(D.SURGERY_RX, re.I)
RE_NEG = [re.compile(p, re.I) for p in D.NEGATION]
RE_INJ_EXCL = re.compile(D.INJ_EXCLUDE, re.I)
# relations by marriage / naming / another person's relatives -> not blood kin of the prospect
RE_NOT_BLOOD = re.compile(r"\bin[- ]law\b|\bgod(?:father|mother|son|daughter)\b|\bnamed (?:after|for)\b|"
                          r"\bin hono(?:u)?r of\b|\bnamesake\b|\bmarri(?:ed|es|age)\b|\bwife\b|"
                          r"\bhusband\b|\bgirlfriend\b|\bfianc", re.I)
RE_NONSPORT_OCC = re.compile(D.NON_SPORT_OCCUPATION, re.I)
RE_OTHER_SUBJ = re.compile(r"\b[A-Z][a-z]{2,}'s\s+(?:teammate|teammates|coach|friend|agent|trainer|"
                           r"wife|husband|girlfriend|mother|father|brother|sister|son|daughter)\b")


# ------------------------------------------------------------------ inputs ---
def load_roster():
    rows = {}
    with open(NAMES) as fh:
        for r in csv.DictReader(fh):
            rows[r["pid"]] = {"draft_year": int(r["draft_year"]),
                              "name": r["player_name"],
                              "nba_id": int(float(r["nba_id"])) if r.get("nba_id") else None}
    return rows


def load_nba_index():
    d = json.load(open(os.path.join(BASE, "nba_all_players.json")))
    rs = d["resultSets"][0]
    h = {k: i for i, k in enumerate(rs["headers"])}
    idx = defaultdict(list)
    for row in rs["rowSet"]:
        nm = row[h["DISPLAY_FIRST_LAST"]]
        if not nm:
            continue
        try:
            fy = int(row[h["FROM_YEAR"]]); ty = int(row[h["TO_YEAR"]])
        except (TypeError, ValueError):
            continue
        idx[W.norm_name(nm)].append((row[h["PERSON_ID"]], fy, ty))
    return idx


def load_birthdates():
    bd = {}
    with open(os.path.join(BASE, "age_verified_wiki.csv")) as fh:
        for r in csv.DictReader(fh):
            try:
                bd[r["pid"]] = (dt.date.fromisoformat(r["birth_date"]), 1)
            except Exception:
                pass
    return bd


RE_LEAD_BORN = re.compile(r"\bborn\s+(?:[A-Z][a-z]+\.?\s+\d{1,2},?\s+)?((?:19|20)\d\d)\b")
RE_BDATE_TPL = re.compile(r"\{\{\s*[Bb]irth[ _]date(?:[ _]and[ _]age)?[^}]*?\|\s*(?:df=\w+\s*\|\s*)?"
                          r"((?:19|20)\d\d)\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})")


def infobox_birthdate(wt):
    m = RE_BDATE_TPL.search(wt)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


# -------------------------------------------------------------- relatives ---
def kin_hits(sentence):
    out = []
    for rx, cls, form in RE_KIN:
        for m in rx.finditer(sentence):
            out.append((m.start(), m.end(), cls, form))
    return sorted(out)


def relatives_from_text(text_links, draft_year, nba_idx, self_nba_id):
    """Match linked relatives; see README section 1 for windows and exclusions."""
    nba_rels, pro_names, ambiguous = {}, set(), 0
    for sent in W.sentences(text_links):
        kins = [k for k in kin_hits(sent) if k[2] != D.OTHER]   # "father of X" -> X is a descendant
        if not kins:
            continue
        if RE_NOT_BLOOD.search(sent) or RE_OTHER_SUBJ.search(sent):
            continue
        is_pro_sent = bool(RE_PRO.search(W.unlink(sent)))
        for (ls, le, tgt, disp) in W.links(sent):
            best, strict, cls = None, False, None
            for (ks, ke, kc, kf) in kins:
                if ke <= ls:                                     # link AFTER the kinship phrase
                    gap = sent[ke:ls]
                    lim = 100 if kf == "of" else 45
                    if ls - ke > lim or "." in gap or ";" in gap:
                        continue
                    if RE_NONSPORT_OCC.search(gap):
                        continue                             # "son of state senator Al Jackson"
                    if best is None or ls - ke < best:
                        best, cls = ls - ke, kc
                        strict = (ls - ke <= 45 and "," not in gap and " and " not in gap)
                elif kf == "poss" and ks >= le and ks - le <= 30:   # "[[Name]], his father"
                    if not re.fullmatch(r"[\s,]{0,3}", sent[le:ks]):
                        continue
                    if best is None or ks - le < best:
                        best, cls, strict = ks - le, kc, True
            if best is None:
                continue
            if not (W.person_like(tgt) or W.person_like(disp)):
                continue
            if re.search(r"\bthe\s*$", sent[:ls], re.I):
                continue                     # "with the [[Charlotte Hornets]]" is not a person
            for key in {W.norm_name(tgt), W.norm_name(disp)}:      # NBA all-time list match
                if len(key.split()) < 2 or key not in nba_idx:
                    continue
                cands = [c for c in nba_idx[key] if c[1] < draft_year and c[0] != self_nba_id]
                if not cands:
                    continue
                if len(cands) > 1:
                    ambiguous += 1
                cands.sort(key=lambda c: (min(c[2], draft_year - 1) - c[1] + 1), reverse=True)
                pid_, fy, ty = cands[0]
                seasons = max(0, min(ty, draft_year - 1) - fy + 1)
                prev = nba_rels.get(pid_)
                if prev is None or seasons > prev[0]:
                    nba_rels[pid_] = (seasons, cls)
                break
            if strict and is_pro_sent:                              # pro in any sport
                key = W.norm_name(tgt)
                nba_hit = nba_idx.get(key) or nba_idx.get(W.norm_name(disp))
                if nba_hit and all(c[1] >= draft_year for c in nba_hit):
                    continue        # NBA career started only after the draft -> not pre-draft news
                pro_names.add(key)
    return nba_rels, len(pro_names), ambiguous


# ------------------------------------------------------------- HS sports ---
RE_PRONOUN = re.compile(r"\b(?:he|his|him|himself)\b", re.I)


def hs_sports(wt, born_usa, name_tokens):
    """Returns None if there is no HS/early-life section, else the set of non-basketball
    sports the PLAYER is stated to have played (see README section 2)."""
    bodies = [b for h, b in W.sections(wt) if h and RE_HS_SEC.search(h)]
    if not bodies:
        return None
    found = set()
    for body in bodies:
        txt = W.plain(body)
        for sent in W.sentences(txt):
            if RE_KIN_ANY.search(sent):
                continue
            snorm = set(W.norm_name(sent).split())
            if not (snorm & name_tokens) and not RE_PRONOUN.search(sent):
                continue                      # sentence is about somebody else
            verbs = [m.end() for m in RE_HS_VERB.finditer(sent)]
            if not verbs:
                continue
            hits = []
            for sport, rx in RE_SPORT.items():
                for m in rx.finditer(sent):
                    hits.append((m.start(), m.group(0), sport))
            hits.sort()
            accepted = []
            for pos, tok, sport in hits:
                ok = any(0 <= pos - v <= 100 for v in verbs)
                if not ok:
                    ok = any(0 <= pos - p2 <= 60 for p2, _, _ in accepted)
                if not ok:
                    continue
                accepted.append((pos, tok, sport))
                if sport == "football" and "association" in sent[max(0, pos - 14):pos].lower():
                    sport = "soccer"                     # "association football" == soccer
                elif sport == "football" and not RE_AMFB.search(tok):
                    # bare "football": American football only for US/Canada-born players
                    if born_usa == 0:
                        sport = "soccer"
                found.add(sport)
    return found


# --------------------------------------------------------------- pathway ---
RE_COLLEGE_LINK = re.compile(r"\[\[([^\]\[|]+)(?:\|[^\]\[]*)?\]\]")


def n_colleges(wt):
    f = W.infobox_field(wt, "college")
    if not f:
        return None
    f = re.sub(r"<!--.*?-->", " ", f, flags=re.S)
    tg = []
    for m in RE_COLLEGE_LINK.finditer(f):
        t = W.norm_name(re.sub(r"\s+men'?s basketball.*$", "", m.group(1), flags=re.I))
        if t and t not in tg:
            tg.append(t)
    if tg:
        return len(tg)
    plain = W.plain(f)
    if not plain:
        return None
    parts = [p for p in re.split(r"\s*(?:\*|;|<br\s*/?>)\s*", plain) if p.strip()]
    return max(1, len(parts))


def class_year_candidates(wt, hs_bodies):
    """Candidate HS graduating years in priority order [(year, src), ...].
    src 1 = "class of YYYY"; 2 = "graduated in YYYY" / senior-season text;
    src 3 = infobox college start year (PROXY - no cohort offset computed for it)."""
    out = []
    hs_txt = W.plain(" \n".join(hs_bodies)) if hs_bodies else ""
    lead = W.plain(W.sections(wt)[0][1])
    for txt in (hs_txt, lead):
        m = RE_CLASSOF.search(txt)
        if m:
            out.append((int(m.group(1)), 1))
            break
    if hs_txt:
        m = RE_GRAD.search(hs_txt)
        if m:
            out.append((int(m.group(1) or m.group(2)), 2))
        else:
            m = RE_SENIOR.search(hs_txt)
            if m:
                yy = int(m.group(1))
                out.append((2000 + yy if yy < 50 else 1900 + yy, 2))
    col = W.infobox_field(wt, "college")
    if col:
        ys = re.findall(r"\(((?:19|20)\d\d)[–\-—]", col)
        if ys:
            out.append((min(int(y) for y in ys), 3))
    return out


def cohort_offset(birth_date, cy):
    """Days between the birthdate and the cohort's nominal birth-year centre
    (1 January of class_year-18; a Sept 1 school cut-off puts a normal cohort in -122..+242)."""
    return (birth_date - dt.date(cy - 18, 1, 1)).days


def reclassified_sentences(txt):
    """Sentences that say the PLAYER reclassified (kinship sentences excluded: a brother's
    reclassification is not the prospect's)."""
    return [s for s in W.sentences(txt) if RE_RECLASS.search(s) and not RE_KIN_ANY.search(s)]


def reclass_direction(sents, txt):
    """+1 = moved to an EARLIER graduating class, -1 = later, None = undetermined."""
    for sent in sents:
        m2 = re.search(r"from (?:the )?[^.]{0,25}?class of ((?:19|20)\d\d)[^.]{0,50}?"
                       r"to (?:the )?[^.]{0,25}?class of ((?:19|20)\d\d)", sent, re.I)
        if m2:
            a, b = int(m2.group(1)), int(m2.group(2))
            if a != b:
                return 1 if b < a else -1
        m = re.search(r"reclassif\w*[^.]{0,80}?class of ((?:19|20)\d\d)", sent, re.I)
        if not m:
            continue
        new = int(m.group(1))
        others = [int(y) for y in RE_CLASSOF.findall(txt) if int(y) != new]
        if others:
            orig = max(others) if max(others) != new else min(others)
            if orig != new:
                return 1 if new < orig else -1
    return None


# ------------------------------------------------------------ birthplace ---
RE_PAREN = re.compile(r"\s*\([^)]*\)")


def birthplace(wt):
    f = W.infobox_field(wt, "birth_place")
    if not f:
        return None, None
    txt = W.plain(f)
    txt = RE_PAREN.sub("", txt)
    parts = [p.strip(" .‎)").strip() for p in txt.split(",")]
    parts = [p for p in parts if p]
    if not parts:
        return None, None
    keys = [re.sub(r"[^a-z ]", " ", p.lower()).strip() for p in parts]
    keys = [re.sub(r"\s+", " ", k) for k in keys]
    cid = sid = None
    for i in range(len(keys) - 1, -1, -1):
        k = keys[i]
        if k in D.COUNTRY_ID:
            cid = D.COUNTRY_ID[k]
            break
        for alias, v in D.COUNTRY_ID.items():          # suffix match ("SR Bosnia ... SFR Yugoslavia")
            if k.endswith(" " + alias):
                cid = v
                break
        if cid:
            break
    if cid is None:
        for k in reversed(keys):                       # bare US state as last element
            if k in D.STATE_ID:
                cid = 840
                break
    if cid == 840:
        for k in reversed(keys):
            if k in D.STATE_ID:
                sid = D.STATE_ID[k]
                break
    return cid, sid


# --------------------------------------------------------------- injuries ---
RE_MD_Y = re.compile(r"\b(" + "|".join(D.MONTHS) + r")\.?\s+(\d{1,2}),?\s+((?:19|20)\d\d)\b", re.I)
RE_D_M_Y = re.compile(r"\b(\d{1,2})\s+(" + "|".join(D.MONTHS) + r")\.?\s+((?:19|20)\d\d)\b", re.I)
RE_M_Y = re.compile(r"\b(" + "|".join(D.MONTHS) + r")\.?\s+((?:19|20)\d\d)\b", re.I)
RE_SEASON = re.compile(r"\b((?:19|20)\d\d)[–\-—](\d{2}|\d{4})\b")
RE_YEAR = re.compile(r"\b((?:19|20)\d\d)\b")


def sentence_dates(sent):
    """Earliest-plausible date for every date/season expression in the sentence."""
    out = []
    for m in RE_MD_Y.finditer(sent):
        try:
            out.append(dt.date(int(m.group(3)), D.MONTHS[m.group(1).lower()], int(m.group(2))))
        except ValueError:
            pass
    for m in RE_D_M_Y.finditer(sent):
        try:
            out.append(dt.date(int(m.group(3)), D.MONTHS[m.group(2).lower()], int(m.group(1))))
        except ValueError:
            pass
    for m in RE_M_Y.finditer(sent):
        out.append(dt.date(int(m.group(2)), D.MONTHS[m.group(1).lower()], 1))
    for m in RE_SEASON.finditer(sent):
        out.append(dt.date(int(m.group(1)), 10, 1))     # season starts in the autumn
    for m in RE_YEAR.finditer(sent):
        out.append(dt.date(int(m.group(1)), 1, 1))      # bare year -> earliest day
    return out


# another person named as the SUBJECT of the injury clause ("... Zed Key was declared out ...")
RE_FULLNAME = re.compile(r"\b([A-Z][a-z]{1,15} [A-Z][a-z'\u2019]{1,15})\s+"
                         r"(?:was|is|were|had|has|suffered|underwent|tore|broke|missed|would|"
                         r"will|went|got|sustained|required|exited|injured|being|returned)\b")


def negated(sent, pos):
    win = sent[max(0, pos - 90):pos]
    return any(rx.search(win) for rx in RE_NEG)


def other_person_before(sent, pos, name_tokens):
    """True if a person-like full name that is not the prospect's sits just before the hit
    ("... after starting center Zed Key was declared out for the season")."""
    for m in RE_FULLNAME.finditer(sent[max(0, pos - 70):pos]):
        nm = m.group(1)
        if not W.person_like(nm):
            continue
        if not (set(W.norm_name(nm).split()) & name_tokens):
            return True
    return False


def injuries(wt, cutoff_date, draft_year, name_tokens=frozenset()):
    """Typed, dated injury flags from a PRE-DRAFT revision.
    A sentence counts only if it carries a date/season that precedes the draft cutoff, or
    inherits one from the nearest preceding dated sentence in the same section (see README)."""
    sev = {1: 0, 2: 0, 3: 0}
    n_surg = 0
    latest = None
    for head, body in W.sections(wt):
        ctx = None
        hd = [d for d in sentence_dates(head) if d < cutoff_date and d.year >= draft_year - 12]
        if hd:
            ctx = max(hd)
        for sent in W.sentences(W.plain(body)):
            dates = [d for d in sentence_dates(sent)
                     if d < cutoff_date and d.year >= draft_year - 12]
            if dates:
                ctx = max(dates)
            anchor = max(dates) if dates else ctx
            if anchor is None:
                continue                                 # undated -> never counted
            if RE_INJ_EXCL.search(sent):
                continue
            hit_any = False
            for lvl, rxs in RE_SEV.items():
                for rx in rxs:
                    m = rx.search(sent)
                    if (m and not negated(sent, m.start())
                            and not other_person_before(sent, m.start(), name_tokens)):
                        sev[lvl] += 1
                        hit_any = True
                        break
            for m in RE_SURG.finditer(sent):
                if not negated(sent, m.start()) and not other_person_before(sent, m.start(), name_tokens):
                    n_surg += 1
                    hit_any = True
            if hit_any and (latest is None or anchor > latest):
                latest = anchor
    recency = None
    if latest is not None:
        season_end = latest.year if latest.month <= 6 else latest.year + 1
        recency = max(0, draft_year - season_end)
    return sev, n_surg, recency


# ------------------------------------------------------------------ main ---
FIELDS = ["pid", "wk_has_article", "wk_article_identity_ok", "wk_has_predraft_rev",
          "wk_nba_relative", "wk_nba_relative_seasons_pre_draft", "wk_n_relatives_pro_any_sport",
          "wk_relative_is_parent", "wk_relative_is_sibling",
          "wk_hs_multisport", "wk_hs_football", "wk_hs_track", "wk_n_hs_sports",
          "wk_prep_year", "wk_reclassified", "wk_reclass_direction", "wk_juco",
          "wk_n_colleges", "wk_transferred", "wk_hs_transferred", "wk_hs_class_year", "wk_hs_class_year_src",
          "wk_cohort_offset_days", "wk_reclass_up_flag", "wk_reclass_down_flag",
          "wk_years_hs_to_draft", "wk_birthdate_src",
          "wk_birth_country_id", "wk_born_outside_usa", "wk_birth_state_id",
          "wk_left_handed",
          "wk_inj_sev3", "wk_inj_sev2", "wk_inj_sev1", "wk_n_surgeries",
          "wk_inj_recency_seasons", "wk_inj_any"]


def article_birth_year(wt):
    """Birth year from the infobox birth-date template, else from 'born ... YYYY' in the lead."""
    b = infobox_birthdate(wt)
    if b:
        return b.year
    m = RE_LEAD_BORN.search(W.plain(W.sections(wt)[0][1]))
    return int(m.group(1)) if m else None


def main():
    roster = load_roster()
    nba_idx = load_nba_index()
    bdates = load_birthdates()
    rows, prov, ambig, unmatched = [], [], [], []
    for pid in sorted(roster):
        info = roster[pid]
        dy = info["draft_year"]
        cutoff = dt.date.fromisoformat(CUTOFF[dy])
        r = {k: "" for k in FIELDS}
        r["pid"] = pid
        cur_f = os.path.join(CUR, pid + ".json")
        pre_f = os.path.join(PRE, pid + ".json")
        r["wk_has_article"] = 1 if os.path.exists(cur_f) else 0
        pre_status, rev_ts, revid = "absent", "", ""

        wt = ""
        if r["wk_has_article"]:
            wt = json.load(open(cur_f))["wikitext"] or ""
        identity_ok = 1
        if r["wk_has_article"]:
            by = article_birth_year(wt)
            if by is not None and not (17 <= dy - by <= 32):
                identity_ok = 0                       # cached article is a different person
                unmatched.append({"pid": pid, "draft_year": dy, "article_birth_year": by,
                                  "reason": "implausible_age_at_draft"})
            r["wk_article_identity_ok"] = identity_ok

        if r["wk_has_article"] and identity_ok:
            body = W.clean_keep_links(wt)

            # --- 5. birthplace (needed early: disambiguates football/soccer) ---
            cid, sid = birthplace(wt)
            if cid is not None:
                r["wk_birth_country_id"] = cid
                r["wk_born_outside_usa"] = 0 if cid == 840 else 1
                if sid is not None:
                    r["wk_birth_state_id"] = sid
            born_usa = 1 if cid in (840, 124) else (0 if cid is not None else 1)

            # --- 1. relatives ---
            nba_rels, n_pro, namb = relatives_from_text(body, dy, nba_idx, info["nba_id"])
            r["wk_nba_relative"] = 1 if nba_rels else 0
            r["wk_nba_relative_seasons_pre_draft"] = max((s for s, _ in nba_rels.values()), default=0)
            r["wk_n_relatives_pro_any_sport"] = n_pro
            classes = {c for _, c in nba_rels.values()}
            r["wk_relative_is_parent"] = 1 if D.PARENT in classes else 0
            r["wk_relative_is_sibling"] = 1 if D.SIBLING in classes else 0
            if namb:
                ambig.append({"pid": pid, "n_ambiguous_name_matches": namb})

            # --- 2. high-school multisport ---
            ntok = {t for t in W.norm_name(info["name"]).split() if len(t) > 2}
            sports = hs_sports(wt, born_usa, ntok)
            if sports is None:
                pass                                    # no HS section -> missing
            else:
                r["wk_n_hs_sports"] = len(sports)
                r["wk_hs_multisport"] = 1 if sports else 0
                r["wk_hs_football"] = 1 if "football" in sports else 0
                r["wk_hs_track"] = 1 if "track" in sports else 0

            # --- 3. pathway ---
            secs = W.sections(wt)
            hs_bodies = [b for h, b in secs if h and RE_HS_SEC.search(h)]
            path_txt = W.plain(" \n".join(
                [b for h, b in secs if (h == "" or RE_HS_SEC.search(h) or RE_COLL_SEC.search(h))]))
            r["wk_prep_year"] = 1 if (RE_PREP.search(path_txt) or RE_PREP_I.search(path_txt)) else 0
            rc_sents = reclassified_sentences(path_txt)
            r["wk_reclassified"] = 1 if rc_sents else 0
            if rc_sents:
                d = reclass_direction(rc_sents, path_txt)
                if d is not None:
                    r["wk_reclass_direction"] = d
            r["wk_juco"] = 1 if RE_JUCO.search(path_txt) else 0
            nc = n_colleges(wt)
            if nc is not None:
                r["wk_n_colleges"] = nc
            col_txt = W.plain(" \n".join([b for h, b in secs if h and RE_COLL_SEC.search(h)]))
            tr = 1 if RE_TRANSFER.search(col_txt) else 0
            if nc is not None and nc >= 2:
                tr = 1                                    # >=2 colleges in the infobox
            r["wk_transferred"] = tr
            if hs_bodies:
                hs_txt = W.plain(" \n".join(hs_bodies))
                r["wk_hs_transferred"] = 1 if RE_TRANSFER.search(hs_txt) else 0

            bd = bdates.get(pid)
            if bd is None:
                ib = infobox_birthdate(wt)
                bd = (ib, 2) if ib else None
            cy = src = off = None
            for cand, csrc in class_year_candidates(wt, hs_bodies):
                if not (1 <= dy - cand <= 8):
                    continue                                # implausible: college class / other person
                if csrc in (1, 2) and bd is not None:
                    o = cohort_offset(bd[0], cand)
                    if abs(o) > 700:
                        continue                            # >~2 cohort years off: wrong "class of"
                    cy, src, off = cand, csrc, o
                    break
                cy, src = cand, csrc
                break
            if cy is not None:
                r["wk_hs_class_year"] = cy
                r["wk_hs_class_year_src"] = src
                r["wk_years_hs_to_draft"] = dy - cy
                if off is not None and src in (1, 2):
                    r["wk_birthdate_src"] = bd[1]
                    r["wk_cohort_offset_days"] = off
                    r["wk_reclass_up_flag"] = 1 if off < -120 else 0
                    r["wk_reclass_down_flag"] = 1 if off > 250 else 0

            # --- 6. handedness ---
            hand_txt = " ".join(s for s in W.sentences(W.plain(wt)) if not RE_KIN_ANY.search(s))
            if RE_LEFT.search(hand_txt):
                r["wk_left_handed"] = 1
            elif RE_RIGHT.search(hand_txt):
                r["wk_left_handed"] = 0

        # --- 4. injuries (PRE-DRAFT revision only) ---
        if os.path.exists(pre_f) and identity_ok:
            p = json.load(open(pre_f))
            pre_status = p.get("status") or "unknown"
            if pre_status == "ok" and p.get("wikitext"):
                rev_ts, revid = p.get("rev_ts", ""), p.get("revid", "")
                r["wk_has_predraft_rev"] = 1
                ntok2 = {t for t in W.norm_name(info["name"]).split() if len(t) > 2}
                sev, ns, rec = injuries(p["wikitext"], cutoff, dy, ntok2)
                r["wk_inj_sev3"] = 1 if sev[3] else 0
                r["wk_inj_sev2"] = 1 if sev[2] else 0
                r["wk_inj_sev1"] = 1 if sev[1] else 0
                r["wk_n_surgeries"] = ns
                r["wk_inj_any"] = 1 if (sev[1] or sev[2] or sev[3] or ns) else 0
                if rec is not None:
                    r["wk_inj_recency_seasons"] = rec
            else:
                r["wk_has_predraft_rev"] = 0
        else:
            r["wk_has_predraft_rev"] = ""               # not yet fetched -> missing

        rows.append(r)
        prov.append({"pid": pid, "draft_year": dy, "has_current_article": r["wk_has_article"],
                     "predraft_status": pre_status, "predraft_rev_ts": rev_ts, "predraft_revid": revid,
                     "current_fetch_date": "2026-09-08", "draft_cutoff": CUTOFF[dy] + "T22:00:00Z"})

    with open(os.path.join(HERE, "features.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(HERE, "provenance.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["pid", "draft_year", "has_current_article",
                                           "predraft_status", "predraft_rev_ts", "predraft_revid",
                                           "current_fetch_date", "draft_cutoff"])
        w.writeheader()
        w.writerows(prov)
    with open(os.path.join(HERE, "unmatched.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["pid", "draft_year", "article_birth_year", "reason"])
        w.writeheader()
        w.writerows(unmatched)
    with open(os.path.join(HERE, "ambiguous_names.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["pid", "n_ambiguous_name_matches"])
        w.writeheader()
        w.writerows(ambig)
    print(f"wrote {len(rows)} rows -> features.csv ({len(FIELDS)} cols)")
    return rows


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""NBA comparison prominence features  (collector: comps)

Stages
  resolve  nbadraftnet/comps.csv -> parsed comp names -> NBA PERSON_ID (rule-based, dated)
  fetch    playercareerstats per PERSON_ID (G League host), cached under raw/
  build    features.csv + provenance.csv + unmatched.csv

Usage: python3 build_comps.py [resolve|fetch|build|all]
"""
import csv, http.client, json, os, re, socket, sys, time, unicodedata
from collections import defaultdict

BASE      = os.path.dirname(os.path.abspath(__file__))
RAW       = os.path.join(BASE, "raw")
COMPS_CSV = "/Users/kennakao/nba/datarebuild/novel/nbadraftnet/comps.csv"
NAMES_CSV = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"
ALLPLAY   = "/Users/kennakao/nba/datarebuild/nba_all_players.json"

# =============================================================================
# 1. PARSING RULES   (rule 4: regex + dictionaries only)
# =============================================================================
DESCRIPTORS = {
    "a", "an", "the", "poor", "poors", "man", "mans", "man's", "rich", "richer",
    "budget", "discount", "lite", "light", "mini", "super", "young", "younger",
    "older", "old", "taller", "shorter", "bigger", "smaller", "thinner", "heavier",
    "stronger", "faster", "quicker", "slower", "athletic", "less", "more", "better",
    "worse", "version", "clone", "type", "like", "of", "his", "her", "brother",
    "cousin", "son", "father", "poorman", "sort", "kind", "similar", "to", "think",
    "maybe", "possibly", "somewhat", "slightly", "very", "with", "without", "and",
    "or", "but", "skinnier", "bulkier", "left", "right", "handed", "shooting",
}
SPLIT_RE  = re.compile(r"\s*(?:/|,|;|\||\bor\b|\band\b|&|\bvs\.?\b|\bmeets\b)\s*", re.I)
BYLINE_RE = re.compile(r"\s*[-–—]\s*\d{1,2}/\d{1,2}/\d{2,4}\s*$")   # "- 4/25/2008"
PAREN_RE  = re.compile(r"\([^)]*\)|\[[^\]]*\]")                              # "(with a jump shot)"
EDGE_RE   = re.compile(r"^[\s\.\-–:\"'`]+|[\s\.\-–:\"'`]+$")

def parse_comp(raw):
    """raw comparison string -> [(verbatim_piece, descriptor_stripped_piece), ...]"""
    s = raw.strip().strip('"').strip()
    s = BYLINE_RE.sub("", s)              # 1. trailing scout byline + date (contains slashes!)
    s = PAREN_RE.sub(" ", s)              # 2. parenthetical / bracketed qualifiers
    s = s.replace("’", "'").replace("‘", "'")
    out = []
    for piece in SPLIT_RE.split(s):       # 3. split on  /  ,  ;  |  &  "or"  "and"  "vs"
        p = re.sub(r"\s+", " ", EDGE_RE.sub("", piece)).strip()
        if not p:
            continue
        toks = p.split()
        st = list(toks)                   # 4. descriptor-stripped variant (used only as
        while st and (st[0].lower().strip(".'") in DESCRIPTORS or st[0][:1].islower()):
            st.pop(0)                     #    a fallback, so surnames such as Young or
        while st and st[-1].lower().strip(".'") in DESCRIPTORS:
            st.pop()                      #    Rich are never eaten from a real name)
        out.append((" ".join(toks), " ".join(st)))
    return out

# =============================================================================
# 2. NAME NORMALISATION + ROSTER INDEX
# =============================================================================
SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv)\b\.?$")

def norm(n):
    n = unicodedata.normalize("NFKD", n)
    n = "".join(c for c in n if not unicodedata.combining(c))     # Schröder -> Schroder
    n = n.lower().replace("’", "'")
    n = re.sub(r"[\.'`]", "", n)                                  # O'Bryant -> obryant
    n = re.sub(r"[^a-z0-9]+", " ", n)                             # hyphen -> space
    return re.sub(r"\s+", " ", n).strip()

def strip_suffix(n):
    return SUFFIX_RE.sub("", norm(n)).strip()

ALIASES = {   # nickname / listed-name changes no general rule can reach (all in README)
    "fat lever":              "Lafayette Lever",
    "jr rider":               "Isaiah Rider",
    "penny hardaway":         "Anfernee Hardaway",
    "nene hilario":           "Nene",
    "mo harkless":            "Maurice Harkless",
    "rip hamilton":           "Richard Hamilton",
    "ron artest":             "Metta World Peace",
    "saer sene":              "Mouhamed Sene",
    "joseph young":           "Joe Young",
    "clarence witherspoon":   "Clar. Weatherspoon",
    "luc richard mbah moute": "Luc Mbah a Moute",
    "kenyon martin jr":       "KJ Martin",
}

def dlev(a, b, cap):
    """Damerau-Levenshtein (optimal string alignment) with early exit above cap."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > cap:
            return cap + 1
        prev2, prev = prev, cur
    return prev[len(b)]

class Roster:
    """commonallplayers rowSet indexed for the matching tiers."""
    def __init__(self, path):
        rs = json.load(open(path))["resultSets"][0]
        h = {k: i for i, k in enumerate(rs["headers"])}
        self.exact, self.ns, self.sfx = defaultdict(list), defaultdict(list), defaultdict(list)
        self.mid, self.first, self.last = defaultdict(list), defaultdict(list), defaultdict(list)
        self.all = []
        for r in rs["rowSet"]:
            fy = int(r[h["FROM_YEAR"]]) if r[h["FROM_YEAR"]] else None
            ty = int(r[h["TO_YEAR"]]) if r[h["TO_YEAR"]] else None
            rec = dict(person_id=r[h["PERSON_ID"]], name=r[h["DISPLAY_FIRST_LAST"]],
                       from_year=fy, to_year=ty, n=norm(r[h["DISPLAY_FIRST_LAST"]]))
            self.all.append(rec)
            self.exact[rec["n"]].append(rec)
            self.ns[rec["n"].replace(" ", "")].append(rec)
            self.sfx[strip_suffix(rec["name"])].append(rec)
            t = rec["n"].split()
            if t:
                self.first[t[0]].append(rec)
                self.last[t[-1]].append(rec)
        for rec in self.all:                       # middle-name key: "Cliff T. Robinson"
            t = rec["n"].split()
            if len(t) >= 3:
                k = t[0] + " " + t[-1]
                if k not in self.exact:            # never shadow a real full name
                    self.mid[k].append(rec)

    def tier1(self, name):
        """identity tier: exact / alias / space-insensitive"""
        n = norm(name)
        if n in ALIASES:
            a = norm(ALIASES[n])
            if a in self.exact:
                return list(self.exact[a]), "alias"
        if n in self.exact:
            return list(self.exact[n]), "exact"
        k = n.replace(" ", "")
        if k in self.ns:
            return list(self.ns[k]), "nospace"     # "Carter Williams" == "Carter-Williams"
        return [], None

    def tier2(self, name):
        """generational-suffix tolerant (Jr / Sr / II / III / IV)"""
        s = strip_suffix(name)
        return (list(self.sfx[s]), "suffix") if s and s in self.sfx else ([], None)

    def tier3(self, name):
        """approximate: token drop, roster middle-name key, nickname prefix, typo"""
        n = norm(name)
        t = n.split()
        got, rules = {}, {}
        def add(recs, rule):
            for r in recs:
                got.setdefault(r["person_id"], r)
                rules.setdefault(r["person_id"], rule)
        if len(t) >= 3:                                        # drop one token
            for i in range(len(t)):
                v = " ".join(t[:i] + t[i + 1:])
                if v in self.exact:
                    add(self.exact[v], "tokendrop")
        if n in self.mid:                                      # roster middle name dropped
            add(self.mid[n], "midkey")
        if len(t) >= 2:                                        # Mo/Maurice, Lou/Louis, Nic/Nicolas
            for r in self.last.get(t[-1], []):
                rt = r["n"].split()
                if len(rt) == len(t) and rt[1:] == t[1:]:
                    a, b = t[0], rt[0]
                    if a != b and min(len(a), len(b)) >= 2 and (a.startswith(b) or b.startswith(a)):
                        add([r], "nickname_prefix")
        cap = 2 if len(n) >= 12 else 1                         # typo tolerance
        pool = {}
        if t:
            for r in self.first.get(t[0], []) + self.last.get(t[-1], []):
                pool[r["person_id"]] = r                       # same given OR family name
        best, bestd = [], cap + 1
        for r in pool.values():
            d = dlev(n, r["n"], cap)
            if d == 0 or d > cap:
                continue
            if d < bestd:
                best, bestd = [r], d
            elif d == bestd:
                best.append(r)
        if best:
            add(best, "editdist%d" % bestd)
        if not got:
            return [], None
        return list(got.values()), "+".join(sorted(set(rules.values())))

def pick(cands, ref_year):
    """date-aware disambiguation. ref_year = latest NBA season-start year already under
    way at the capture date. -> (record, rule) or (None, reason)."""
    if not cands:
        return None, "no_name_match"
    if len(cands) == 1:
        c = cands[0]
        if c["from_year"] is not None and c["from_year"] > ref_year:
            return None, "only_candidate_debuts_after_capture"
        return c, "unique"
    act = [c for c in cands if c["from_year"] is not None and c["to_year"] is not None
           and c["from_year"] <= ref_year <= c["to_year"]]
    if len(act) == 1:
        return act[0], "active_at_capture"
    if len(act) > 1:
        return None, "ambiguous_multiple_active_at_capture"
    ret = [c for c in cands if c["to_year"] is not None and c["to_year"] <= ref_year]
    if not ret:
        return None, "all_candidates_debut_after_capture"
    if len({c["n"] for c in ret}) == 1:
        # true homonyms: the string cannot distinguish them, the writer means the more
        # prominent one -> longest career, then most recent
        key = lambda c: (c["to_year"] - (c["from_year"] or c["to_year"]), c["to_year"])
        rule = "homonym_longest_career"
    else:
        # different spellings joined by an approximate rule: a contemporary player is a
        # likelier referent than a long-retired one -> most recent, then longest
        key = lambda c: (c["to_year"], c["to_year"] - (c["from_year"] or c["to_year"]))
        rule = "most_recent_retired_at_capture"
    ret.sort(key=key, reverse=True)
    if len(ret) > 1 and key(ret[0]) == key(ret[1]):
        return None, "ambiguous_retired_tie"
    return ret[0], rule

def resolve_name(piece, stripped, roster, ref_year):
    """-> (record|None, match_rule, pick_rule). Tiers run in order; a tier whose
    candidates are all date-implausible falls through, an AMBIGUOUS tier stops
    (rule 5: log, never guess). An explicit Jr/Sr/III in the source is honoured: it
    may only be dropped by the suffix tier for a candidate active at the capture date
    (father/son pairs); an alias/exact hit is unaffected."""
    has_sfx = bool(SUFFIX_RE.search(norm(piece)))
    fail = None
    passes = [(piece, "")] + ([(stripped, "+desc")] if stripped and stripped != piece else [])
    for nm, tag in passes:
        for tier in (roster.tier1, roster.tier2, roster.tier3):
            c, rule = tier(nm)
            if not c:
                continue
            rec, why = pick(c, ref_year)
            if why.startswith("ambiguous"):
                return None, rule + tag, why
            if rec is not None:
                if (rule == "suffix" and has_sfx and not SUFFIX_RE.search(rec["n"])
                        and why != "active_at_capture"):
                    fail = fail or "explicit_suffix_only_matches_elder"
                    continue
                return rec, rule + tag, why
            fail = fail or why
        toks = nm.split()
        if len(toks) > 3:                                  # greedy longest resolvable prefix
            for k in range(len(toks) - 1, 1, -1):
                for tier in (roster.tier1, roster.tier2, roster.tier3):
                    c, rule = tier(" ".join(toks[:k]))
                    if not c:
                        continue
                    rec, why = pick(c, ref_year)
                    if rec is not None and not why.startswith("ambiguous"):
                        return rec, rule + "+prefix" + tag, why
    return None, "none", fail or "no_name_match"

# =============================================================================
# 3. FETCH  (G League host only - stats.nba.com hangs from this network)
# =============================================================================
# this network resolves the host to IPv6 first and the v6 connect stalls ~20 s before
# falling back; pinning getaddrinfo to IPv4 keeps every request under a second
_GAI = socket.getaddrinfo
socket.getaddrinfo = lambda h, p, f=0, t=0, pr=0, fl=0: _GAI(h, p, socket.AF_INET, t, pr, fl)

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Referer": "https://www.nba.com/", "Origin": "https://www.nba.com",
    "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
    "x-nba-stats-origin": "stats", "x-nba-stats-token": "true",
    "Connection": "keep-alive", "Accept-Encoding": "identity",
}

HOST = "stats.gleague.nba.com"
PATH = "/stats/playercareerstats?PlayerID=%d&PerMode=Totals&LeagueID=00"
_CONN = []                       # one keep-alive connection per process: a fresh TLS
                                 # handshake per request is what the host throttles

def _conn(new=False):
    if new and _CONN:
        try:
            _CONN.pop().close()
        except Exception:
            pass
    if not _CONN:
        _CONN.append(http.client.HTTPSConnection(HOST, timeout=10))
    return _CONN[0]

def fetch_one(person_id, tries=5):
    path = os.path.join(RAW, "%d.json" % person_id)
    if os.path.exists(path) and os.path.getsize(path) > 200:
        return "cached"
    delay = 1.0
    for a in range(tries):
        try:
            c = _conn(new=(a > 0))
            c.request("GET", PATH % person_id, headers=HEADERS)
            r = c.getresponse()
            body = r.read()
            if r.status != 200:
                raise IOError("HTTP %d" % r.status)
            j = json.loads(body)
            if not any(rs["name"] == "SeasonTotalsRegularSeason"
                       for rs in j.get("resultSets", [])):
                # the endpoint answers 200 with "{}" for a handful of fringe players;
                # record it so re-runs never ask again
                open(os.path.join(RAW, "%d.empty" % person_id), "wb").write(body)
                return "empty"
            tmp = path + ".tmp"
            open(tmp, "wb").write(body)
            os.replace(tmp, path)
            return "ok"
        except Exception as e:
            print("    retry %d id=%d %s %s" % (a, person_id, type(e).__name__, e), flush=True)
            if a == tries - 1:
                return "fail:%s" % type(e).__name__
            time.sleep(delay)
            delay *= 2
    return "fail"

# =============================================================================
# 4. SEASON MATH  (rule 2: date every record)
# =============================================================================
def season_start(season_id):
    m = re.match(r"^(\d{4})-\d{2}$", season_id or "")
    return int(m.group(1)) if m else None

def career_to_date(person_id, draft_year):
    """NBA regular-season rows whose season ENDS before draft night: season S/(S+1)
    qualifies iff S + 1 <= draft_year  (i.e. S <= draft_year - 1)."""
    path = os.path.join(RAW, "%d.json" % person_id)
    if not os.path.exists(path):
        return None
    rs = [x for x in json.load(open(path))["resultSets"]
          if x["name"] == "SeasonTotalsRegularSeason"][0]
    h = {k: i for i, k in enumerate(rs["headers"])}
    F = lambda r, k: (r[h[k]] if r[h[k]] is not None else 0)
    tot = dict(seasons=0, gp=0, mn=0.0, pts=0.0, reb=0.0, ast=0.0, stl=0.0, blk=0.0,
               fg3m=0.0, fg3a=0.0, ftm=0.0, fta=0.0, mn_stk=0.0, peak_mpg=None,
               peak_ppg=None, active_final=0)
    for r in rs["rowSet"]:
        if r[h["LEAGUE_ID"]] not in (None, "00"):
            continue                                    # NBA only (drops ABA rows)
        s = season_start(r[h["SEASON_ID"]])
        if s is None or s > draft_year - 1:
            continue
        gp, mn = F(r, "GP"), F(r, "MIN")
        tot["seasons"] += 1
        tot["gp"] += gp
        tot["mn"] += mn
        for a, b in (("pts","PTS"),("reb","REB"),("ast","AST"),("stl","STL"),("blk","BLK"),
                     ("fg3m","FG3M"),("fg3a","FG3A"),("ftm","FTM"),("fta","FTA")):
            tot[a] += F(r, b)
        if r[h["STL"]] is not None and r[h["BLK"]] is not None:
            tot["mn_stk"] += mn        # steals/blocks were not recorded before 1973-74:
                                       # those minutes must not dilute cp_stk36
        if gp:
            tot["peak_mpg"] = max(tot["peak_mpg"] or 0.0, mn / gp)
            tot["peak_ppg"] = max(tot["peak_ppg"] or 0.0, F(r, "PTS") / gp)
        if s == draft_year - 1 and gp > 0:
            tot["active_final"] = 1                     # played the season ending in Y
    return tot

# =============================================================================
def load_ids():
    return {r["pid"]: r for r in csv.DictReader(open(NAMES_CSV))}

def load_parse_resolve():
    roster = Roster(ALLPLAY)
    ids = load_ids()
    out = []
    for row in csv.DictReader(open(COMPS_CSV)):
        pid, raw, ts = row["pid"], row["comp_name"], row["capture_ts"]
        meta = ids.get(pid)
        if not meta:
            continue
        cy, cm = int(ts[:4]), int(ts[4:6])
        ref_year = cy if cm >= 10 else cy - 1           # latest season already under way
        res, seen = [], set()
        for piece, stripped in parse_comp(raw):
            rec, mrule, prule = resolve_name(piece, stripped, roster, ref_year)
            if rec is not None:
                if rec["person_id"] in seen:            # same comp named twice
                    continue
                seen.add(rec["person_id"])
            res.append(dict(name=piece, rec=rec, match_rule=mrule, pick_rule=prule))
        out.append(dict(pid=pid, draft_year=int(float(meta["draft_year"])), raw=raw, ts=ts,
                        ref_year=ref_year, parsed=res, name=meta["player_name"]))
    return out

def cmd_resolve(verbose=True):
    rows = load_parse_resolve()
    n = sum(len(r["parsed"]) for r in rows)
    ok = sum(1 for r in rows for p in r["parsed"] if p["rec"])
    if verbose:
        print("prospect rows %d | parsed names %d | resolved %d (%.1f%%)"
              % (len(rows), n, ok, 100.0 * ok / n))
        bad = defaultdict(list)
        for r in rows:
            for p in r["parsed"]:
                if not p["rec"]:
                    bad[p["pick_rule"]].append((p["name"], r["raw"], r["draft_year"]))
        for k, v in sorted(bad.items(), key=lambda x: -len(x[1])):
            print("  UNRESOLVED %-40s %d" % (k, len(v)))
            for x in sorted(set(v)):
                print("       ", x)
    return rows

def cmd_fetch(shard=0, nshard=1):
    """`fetch [i/n]` splits the id list over n polite workers; each sleeps nshard*1.1 s
    between its own requests, so the aggregate rate stays at about 1 request/s."""
    rows = load_parse_resolve()
    want = sorted({p["rec"]["person_id"] for r in rows for p in r["parsed"] if p["rec"]})
    want = [x for i, x in enumerate(want) if i % nshard == shard]
    print("unique comp players to fetch: %d" % len(want), flush=True)
    n_ok = n_c = n_f = 0
    for i, pid in enumerate(want, 1):
        st = fetch_one(pid)
        if st in ("cached", "empty"):
            n_c += 1
        elif st == "ok":
            n_ok += 1
            time.sleep(1.1 * nshard)                    # rule 3: >= 1 s between requests
        else:
            n_f += 1
            print("  FAIL %d %s" % (pid, st), flush=True)
        if i % 50 == 0:
            print("  %d/%d ok=%d cached=%d fail=%d" % (i, len(want), n_ok, n_c, n_f), flush=True)
    print("fetch done shard %d/%d ok=%d cached=%d fail=%d" % (shard, nshard, n_ok, n_c, n_f), flush=True)

FEATS = ["cp_n_comps","cp_resolved","cp_n_resolved","cp_seasons_to_date","cp_min_to_date",
         "cp_pts36_to_date","cp_reb36","cp_ast36","cp_stk36","cp_fg3_pct_to_date",
         "cp_ft_pct_to_date","cp_peak_mpg_to_date","cp_peak_pts_pg_to_date",
         "cp_active_at_draft","cp_years_since_comp_debut","cp_comp_is_hall_tier",
         "cp_max_pts36_to_date","cp_max_peak_pts_pg_to_date"]

def cmd_build():
    rows = load_parse_resolve()
    ids = load_ids()
    feat, prov, unm, spot = {}, [], [], []
    for r in rows:
        comps = []
        for p in r["parsed"]:
            if not p["rec"]:
                unm.append(dict(pid=r["pid"], draft_year=r["draft_year"], raw_comp=r["raw"],
                                parsed_name=p["name"], match_rule=p["match_rule"],
                                reason=p["pick_rule"]))
                continue
            c = career_to_date(p["rec"]["person_id"], r["draft_year"])
            if c is None:
                empty = os.path.exists(os.path.join(RAW, "%d.empty" % p["rec"]["person_id"]))
                unm.append(dict(pid=r["pid"], draft_year=r["draft_year"], raw_comp=r["raw"],
                                parsed_name=p["name"], match_rule=p["match_rule"],
                                reason="career_endpoint_empty" if empty else "no_career_json"))
                continue
            comps.append((p, c))
            prov.append(dict(pid=r["pid"], draft_year=r["draft_year"], capture_ts=r["ts"],
                             raw_comp=r["raw"], parsed_name=p["name"],
                             comp_person_id=p["rec"]["person_id"],
                             comp_display_name=p["rec"]["name"],
                             comp_from_year=p["rec"]["from_year"],
                             comp_to_year=p["rec"]["to_year"],
                             match_rule=p["match_rule"], pick_rule=p["pick_rule"],
                             seasons_to_date=c["seasons"], gp_to_date=c["gp"],
                             min_to_date=round(c["mn"], 1), pts_to_date=round(c["pts"], 1)))
        f = {k: "" for k in FEATS}
        f["cp_n_comps"]    = len(r["parsed"])
        f["cp_n_resolved"] = len(comps)
        f["cp_resolved"]   = 1 if comps else 0
        if comps:
            k = len(comps)
            S = lambda x: sum(c[x] for _, c in comps)
            f["cp_seasons_to_date"] = round(S("seasons") / k, 4)
            f["cp_min_to_date"]     = round(S("mn") / k, 1)
            mn = S("mn")
            if mn > 0:
                f["cp_pts36_to_date"] = round(36.0 * S("pts") / mn, 4)
                f["cp_reb36"]         = round(36.0 * S("reb") / mn, 4)
                f["cp_ast36"]         = round(36.0 * S("ast") / mn, 4)
            if S("mn_stk") > 0:
                f["cp_stk36"]         = round(36.0 * (S("stl") + S("blk")) / S("mn_stk"), 4)
            if S("fg3a") > 0:
                f["cp_fg3_pct_to_date"] = round(S("fg3m") / S("fg3a"), 4)
            if S("fta") > 0:
                f["cp_ft_pct_to_date"]  = round(S("ftm") / S("fta"), 4)
            pm = [c["peak_mpg"] for _, c in comps if c["peak_mpg"] is not None]
            pp = [c["peak_ppg"] for _, c in comps if c["peak_ppg"] is not None]
            if pm:
                f["cp_peak_mpg_to_date"] = round(sum(pm) / len(pm), 4)
            if pp:
                f["cp_peak_pts_pg_to_date"]     = round(sum(pp) / len(pp), 4)
                f["cp_max_peak_pts_pg_to_date"] = round(max(pp), 4)
            f["cp_active_at_draft"] = max(c["active_final"] for _, c in comps)
            fy = [r["draft_year"] - p["rec"]["from_year"] for p, _ in comps
                  if p["rec"]["from_year"] is not None]
            if fy:
                f["cp_years_since_comp_debut"] = round(sum(fy) / len(fy), 4)
            f["cp_comp_is_hall_tier"] = max(
                1 if (c["gp"] >= 500 and c["pts"] / c["gp"] >= 20.0) else 0 for _, c in comps)
            per = [36.0 * c["pts"] / c["mn"] for _, c in comps if c["mn"] > 0]
            if per:
                f["cp_max_pts36_to_date"] = round(max(per), 4)
        feat[r["pid"]] = f
        # NOTE: prospect names are never written to disk (they live only in the identity
        # file); report.py joins them in memory for the printed spot check
        spot.append([r["pid"], r["draft_year"], r["raw"],
                     " + ".join(p["rec"]["name"] for p, _ in comps), f["cp_pts36_to_date"]])

    with open(os.path.join(BASE, "features.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pid"] + FEATS)
        for pid in ids:                                  # one row per drafted player
            f = feat.get(pid)
            w.writerow([pid] + ([f[c] for c in FEATS] if f else [""] * len(FEATS)))
    for fn, data, cols in (
        ("provenance.csv", prov, ["pid","draft_year","capture_ts","raw_comp","parsed_name",
            "comp_person_id","comp_display_name","comp_from_year","comp_to_year",
            "match_rule","pick_rule","seasons_to_date","gp_to_date","min_to_date","pts_to_date"]),
        ("unmatched.csv", unm, ["pid","draft_year","raw_comp","parsed_name","match_rule","reason"])):
        with open(os.path.join(BASE, fn), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for d in data:
                w.writerow(d)
    json.dump(spot, open(os.path.join(BASE, "spotcheck.json"), "w"))
    print("features rows=%d  with-comp=%d  resolved=%d  comp-links=%d  unmatched=%d"
          % (len(ids), len(feat), sum(1 for f in feat.values() if f["cp_resolved"] == 1),
             len(prov), len(unm)))

if __name__ == "__main__":
    os.makedirs(RAW, exist_ok=True)
    c = sys.argv[1] if len(sys.argv) > 1 else "all"
    if c == "resolve":
        cmd_resolve()
    elif c == "fetch":
        sh = sys.argv[2].split("/") if len(sys.argv) > 2 else ["0", "1"]
        cmd_fetch(int(sh[0]), int(sh[1]))
    elif c == "build":
        cmd_build()
    else:
        cmd_resolve(verbose=False)
        cmd_fetch()
        cmd_build()

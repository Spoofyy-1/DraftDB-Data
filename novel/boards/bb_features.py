"""Stage 3: parse the cached captures and build features.csv / provenance.csv.

Runs entirely offline against raw/ .
"""
import csv
import gzip
import json
import os
import re
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bb_parse as P  # noqa: E402
from bb_common import (BASE, DRAFT_CUTOFF, RAW, board_year_for_ts, cache_path,  # noqa: E402
                       days_before_draft, log, norm_name, strip_tags, ts_dt,
                       url_ok)

IDENT = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"
PLAN = os.path.join(RAW, "fetch_plan.csv")
PARSED = os.path.join(RAW, "parsed.jsonl.gz")

YEARS = list(range(2001, 2026))
ABSENT = 101          # rank encoding for "not on the final nbadraft.net board"
MIN_BOARD = 40        # a board capture must have this many entries to count
MIN_MOCK = 20         # a mock capture must have this many picks to count


# ------------------------------------------------------------------ identity
def load_identity():
    rows = []
    with open(IDENT) as f:
        for r in csv.DictReader(f):
            try:
                y = int(r["draft_year"])
            except Exception:
                continue
            rows.append({"pid": r["pid"], "year": y, "name": r["player_name"],
                         "pick": r["actual_pick"], "norm": norm_name(r["player_name"])})
    return rows


def build_matcher(ident):
    full = defaultdict(list)      # (year, norm) -> pids
    initial = defaultdict(list)   # (year, 'j smith') -> pids
    last = defaultdict(list)      # (year, 'smith') -> [(first, pid)]
    for r in ident:
        y, n = r["year"], r["norm"]
        if not n:
            continue
        full[(y, n)].append(r["pid"])
        parts = n.split()
        if len(parts) >= 2:
            initial[(y, parts[0][0] + " " + parts[-1])].append(r["pid"])
            last[(y, parts[-1])].append((parts[0], r["pid"]))
    return full, initial, last


class Matcher(object):
    def __init__(self, ident):
        self.full, self.initial, self.last = build_matcher(ident)
        self.unmatched = []
        self.cache = {}

    def match(self, name, year, source, log=True):
        key = (year, norm_name(name))
        if key in self.cache:
            return self.cache[key]
        n = key[1]
        pid = None
        rule = ""
        if not n:
            pid = None
        elif len(self.full.get(key, [])) == 1:
            pid, rule = self.full[key][0], "exact"
        elif len(self.full.get(key, [])) > 1:
            rule = "ambiguous_exact"
        else:
            parts = n.split()
            if len(parts) >= 2:
                k2 = (year, parts[0][0] + " " + parts[-1])
                cand = self.initial.get(k2, [])
                if len(cand) == 1:
                    pid, rule = cand[0], "initial_last"
                elif len(cand) > 1:
                    rule = "ambiguous_initial"
                else:
                    cand3 = self.last.get((year, parts[-1]), [])
                    same = [p for fn, p in cand3 if fn[:1] == parts[0][:1]]
                    if len(cand3) == 1 and len(same) == 1:
                        pid, rule = same[0], "last_only"
                    elif cand3:
                        rule = "ambiguous_last"
        self.cache[key] = pid
        if pid is None and log:
            self.unmatched.append((source, year, name, rule or "no_candidate"))
        return pid


# ------------------------------------------------------------------- parsing
def parse_all():
    """Parse every cached capture in the plan -> raw/parsed.jsonl.gz"""
    plan = list(csv.DictReader(open(PLAN)))
    out = gzip.open(PARSED, "wt")
    n_ok = n_miss = n_empty = n_skip = 0
    for i, r in enumerate(plan):
        src, y, ts, orig = r["source"], int(r["year"]), r["ts"], r["original"]
        if not url_ok(src, orig):
            n_skip += 1
            continue
        p = cache_path(src, ts, orig)
        if not os.path.exists(p):
            n_miss += 1
            continue
        try:
            with gzip.open(p, "rb") as f:
                html = f.read().decode("utf-8", "replace")
        except Exception:
            n_miss += 1
            continue
        if src == "nd_board":
            rows = P.parse_nd_board(html)
        elif src == "nd_mock":
            rows = P.parse_nd_mock(html)
        elif src == "nd_crowd":
            rows = P.parse_nd_crowd(html)
        elif src in ("dx_board", "dx_mock", "dx_mockx"):
            rows = P.parse_dx(html, is_mock=src.startswith("dx_mock"))
        elif src == "stepien":
            rows = P.parse_stepien_indiv(html)
            layout = "grid" if rows else None
            if not rows:
                rows = P.parse_stepien(html)
                layout = ("composite" if re.search(r"draft-rankings", orig)
                          else "post")
        else:
            rows = []
        if not rows:
            n_empty += 1
            continue
        rec = {"source": src, "year_cal": y, "ts": ts, "url": orig,
               "mode": r["mode"], "dbd": float(r["days_before_draft"]),
               "n": len(rows), "rows": rows}
        if src == "dx_board":
            rec["last_updated"] = P.dx_last_updated(html, ts)
            rec["page"] = dx_page_of(orig)
        if src == "stepien":
            rec["layout"] = layout
            # a dated Stepien post carries its publication date in the path;
            # that, not the capture time, is when the board was knowable
            pm = re.search(r"thestepien\.com/(20\d\d)/(\d\d)/(\d\d)/", orig)
            if pm:
                rec["pub_ts"] = "%s%s%s120000" % pm.groups()
        out.write(json.dumps(rec) + "\n")
        n_ok += 1
        if (i + 1) % 500 == 0:
            log("  parsed %d/%d (ok %d, empty %d, missing %d)" %
                (i + 1, len(plan), n_ok, n_empty, n_miss))
    out.close()
    log("parse: ok=%d empty=%d off-shape-url=%d missing=%d"
        % (n_ok, n_empty, n_skip, n_miss))


def dx_page_of(url):
    m = re.search(r"Top-100-Prospects/(\d)", url)
    return int(m.group(1)) if m else 1


def load_parsed():
    recs = []
    with gzip.open(PARSED, "rt") as f:
        for line in f:
            recs.append(json.loads(line))
    return recs


# ------------------------------------------------ class-year sanity for boards
MIN_AGREE = 0.20   # a board must share >=20% of its top 30 with a draft class
# A post-draft mock capture is refused when too many of its picks land exactly
# on the real draft slot: that is a results page, not a mock.  Measured over
# 464 strictly pre-draft mock captures the exact-agreement rate never exceeded
# 0.27 (median 0.09), while nbadraft.net's /mocks/2008_nba_draft.html scores
# 1.00.  0.35 sits clear of every genuine mock observed.
MAX_RESULT_AGREE = 0.35


def results_agreement(rows, year, matcher, pick_by_pid):
    """Fraction of a mock's picks that exactly equal the real draft slot.
    Returns None when too few entries could be matched to judge."""
    hits = tot = 0
    for row in rows:
        pid = matcher.match(row["name"], year, "leak_check", log=False)
        if not pid:
            continue
        ap = pick_by_pid.get(pid)
        if ap is None:
            continue
        tot += 1
        if int(ap) == row["rank"]:
            hits += 1
    return (hits / tot) if tot >= 10 else None


def class_year_check(rows, cal_year, ident_by_year):
    """Fraction of the top-30 names that are drafted players of year y, for
    y in {cal-1, cal, cal+1}.  Returns (chosen_year_or_None, fracs).

    The calendar rule wins unless another candidate beats it by >= 0.10 (a
    board captured before the site reset, or a site that resets early).  A
    board that agrees with no candidate class at all (< MIN_AGREE) is dropped:
    that is how stale copies served long after a site stopped updating are
    kept out."""
    top = [norm_name(r["name"]) for r in sorted(rows, key=lambda x: x["rank"])[:30]]
    top = [t for t in top if t]
    fracs = {}
    for y in (cal_year - 1, cal_year, cal_year + 1):
        s = ident_by_year.get(y, set())
        fracs[y] = (sum(1 for t in top if t in s) / len(top)) if top else 0.0
    best = max(fracs, key=lambda k: fracs[k])
    chosen = best if fracs[best] - fracs[cal_year] >= 0.10 else cal_year
    if fracs[best] < MIN_AGREE:
        return None, fracs
    return chosen, fracs


def sig(rows):
    """Signature of a published board/mock state: the FULL (rank, name) list.

    (An earlier version hashed only the top 25, which collapsed a complete
    100-man board into an earlier state that shared its top 25 and left a
    single 25-entry page standing as the "final" board.)"""
    return tuple((r["rank"], norm_name(r["name"]))
                 for r in sorted(rows, key=lambda x: x["rank"]))


def dedupe_states(recs):
    """Keep the EARLIEST capture of each distinct published board/mock state."""
    seen = {}
    out = []
    for r in sorted(recs, key=lambda x: x["ts"]):
        s = sig(r["rows"])
        if s in seen:
            continue
        seen[s] = r["ts"]
        out.append(r)
    return out


MAX_STALE = 120.0   # a horizon capture may not be older than horizon+120 days


def at_or_before(series, horizon_days, max_stale=MAX_STALE):
    """Nearest capture at or before a horizon: the latest capture whose
    days-before-draft is >= horizon, provided it is not more than `max_stale`
    days older than the horizon itself (so a preseason board never stands in
    for a "30 days before the draft" reading)."""
    cand = [r for r in series if horizon_days <= r["dbd"] <= horizon_days + max_stale]
    return cand[-1] if cand else None


def tier_num(t):
    if not t:
        return None
    m = re.search(r"(\d+)", t)
    if m:
        return float(m.group(1))
    m = re.search(r"\b(I{1,3}|IV|V|VI{0,3}|IX|X)\b", t.upper())
    if m:
        rn = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
              "VIII": 8, "IX": 9, "X": 10}
        return float(rn.get(m.group(1), 0)) or None
    return None


STEP_ANALYST = re.compile(
    r"thestepien\.com/\d{4}/\d{2}/\d{2}/([a-z]+(?:-[a-z]+)?)(?:s)?-", re.I)


def stepien_analyst(url):
    m = re.search(r"/\d{4}/\d{2}/\d{2}/([a-z0-9\-]+)/?$", url.lower())
    if not m:
        return None
    slug = m.group(1)
    for a in ("jackson-hoy", "mike-gribanov", "ross-homan", "spencer-pearlman",
              "ricky-scricca", "tyler-metcalf", "matt-powers", "cole-zwicker"):
        if slug.startswith(a):
            return a
    m2 = re.match(r"^([a-z]+-[a-z]+?)s?-(?:final|updated|midseason|preseason|"
                  r"pre|first|20\d\d|top|big)", slug)
    if m2:
        return m2.group(1)
    return None


# ================================================================== features
def main():
    if "--parse" in sys.argv or not os.path.exists(PARSED):
        parse_all()
    recs = load_parsed()
    log("loaded %d parsed captures" % len(recs))

    ident = load_identity()
    ident_by_year = defaultdict(set)
    for r in ident:
        ident_by_year[r["year"]].add(r["norm"])
    M = Matcher(ident)
    pick_by_pid = {r["pid"]: (float(r["pick"]) if r["pick"] else None) for r in ident}

    # ---- group captures by (source, class year), fixing the class year -----
    groups = defaultdict(list)
    yearlog = []
    for r in recs:
        y = r["year_cal"]
        checkable = (r["source"] == "nd_board" and r["n"] >= MIN_BOARD) or \
                    (r["source"] in ("nd_mock", "nd_crowd", "dx_mock", "dx_mockx")
                     and r["n"] >= MIN_MOCK)
        if checkable:
            y2, fracs = class_year_check(r["rows"], y, ident_by_year)
            if y2 is None:
                yearlog.append((r["source"], r["ts"], y, "DROPPED",
                                round(fracs[y], 2), round(max(fracs.values()), 2)))
                continue
            if y2 != y:
                yearlog.append((r["source"], r["ts"], y, y2,
                                round(fracs[y], 2), round(fracs[y2], 2)))
                y = y2
                r["dbd"] = days_before_draft(r["ts"], y) if y in DRAFT_CUTOFF else r["dbd"]
        r["year"] = y
        if y not in DRAFT_CUTOFF or not (2001 <= y <= 2025):
            continue
        if r.get("pub_ts"):          # Stepien dated post: date it by publication
            r["dbd"] = days_before_draft(r["pub_ts"], y)
        # Post-draft ("frozen") captures are allowed for the big boards, which
        # freeze until late August, and for mocks whose URL names the class --
        # but a mock page may have been silently replaced by the real results,
        # so each frozen mock must pass the exact-agreement guard first.
        if r["dbd"] < 0:
            if r["source"] == "nd_board":
                pass
            elif r["source"] in ("nd_mock", "dx_mock", "dx_mockx", "nd_crowd"):
                agree = results_agreement(r["rows"], y, M, pick_by_pid)
                if agree is None or agree >= MAX_RESULT_AGREE:
                    yearlog.append((r["source"], r["ts"], y, "RESULTS_LEAK",
                                    "" if agree is None else round(agree, 2), ""))
                    continue
            else:
                continue
        groups[(r["source"], y)].append(r)

    # ---- dx board -----------------------------------------------------
    # The 2015-2017 board is paginated 25 per page, so pages must be stitched
    # back together BEFORE the class year is judged.  Pages of the same
    # published board share the on-page "last updated" stamp; where the site
    # printed no stamp (2008-2011) the board was a single page and the capture
    # day is used instead.
    dx_pages = defaultdict(list)
    for r in recs:
        if r["source"] != "dx_board":
            continue
        key = r.get("last_updated") or ("day:" + r["ts"][:8])
        dx_pages[key].append(r)

    dx_boards = defaultdict(dict)   # year -> state_ts -> merged board
    for key, pages in dx_pages.items():
        merged = {}
        for it in sorted(pages, key=lambda x: x["ts"]):
            for row in it["rows"]:
                merged.setdefault(row["rank"], row)
        if len(merged) < 20 or min(merged) > 5:
            continue                       # a page-2-only capture is no board
        ts = min(p["ts"] for p in pages)
        cal_ts = (key.replace("-", "") + "120000") if not key.startswith("day:") else ts
        cal_y, _ = board_year_for_ts(cal_ts)
        rows = list(merged.values())
        y, fracs = class_year_check(rows, cal_y, ident_by_year)
        if y is None:
            yearlog.append(("dx_board", ts, cal_y, "DROPPED",
                            round(fracs[cal_y], 2), round(max(fracs.values()), 2)))
            continue
        if y != cal_y:
            yearlog.append(("dx_board", ts, cal_y, y,
                            round(fracs[cal_y], 2), round(fracs[y], 2)))
        if y not in DRAFT_CUTOFF or not (2001 <= y <= 2025):
            continue
        # acceptance: the published board (last-updated stamp when present,
        # else the capture) must pre-date draft night
        dbd = days_before_draft(cal_ts, y)
        if dbd < 0:
            continue
        dx_boards[y][ts] = {"ts": ts, "dbd": dbd, "rows": rows,
                            "last_updated": None if key.startswith("day:") else key,
                            "url": pages[0]["url"], "n": len(merged),
                            "source": "dx_board"}

    feats = defaultdict(dict)
    prov = []

    # =================================================== nbadraft.net board
    for y in YEARS:
        rs = [r for r in groups.get(("nd_board", y), []) if r["n"] >= MIN_BOARD]
        if not rs:
            continue
        rs = dedupe_states(rs)
        rs.sort(key=lambda x: x["ts"])
        # prefer a genuinely pre-draft capture for the "final" board; a frozen
        # post-draft capture is only the fallback for classes where the archive
        # missed the pre-draft window entirely
        pre_rs = [r for r in rs if r["dbd"] >= 0]
        cand = pre_rs or rs
        full = [r for r in cand if r["n"] >= 50]
        final = (full or cand)[-1]
        # rank lookup per capture
        ranked = []
        for r in rs:
            d = {}
            for row in r["rows"]:
                pid = M.match(row["name"], y, "nd_board")
                if pid:
                    d[pid] = row
            ranked.append((r, d))
        final_map = next(d for r, d in ranked if r is final)
        r30 = at_or_before([r for r, _ in ranked], 30.0)
        r60 = at_or_before([r for r, _ in ranked], 60.0)
        m30 = dict(next((d for r, d in ranked if r is r30), {}))
        m60 = dict(next((d for r, d in ranked if r is r60), {}))
        # The ABSENT (=101) encoding is applied only to players the identity
        # file records as actually drafted in class y; undrafted identity rows
        # get a rank only when they really appear on the board.
        for p in [x for x in ident if x["year"] == y]:
            pid = p["pid"]
            drafted = bool(p["pick"])
            row = final_map.get(pid)
            if row:
                feats[pid]["bb_nd_board_rank_final"] = row["rank"]
                feats[pid]["bb_nd_unranked_board"] = 0
                prov.append([pid, "nd_board_final", final["ts"], final["url"]])
            elif drafted:
                feats[pid]["bb_nd_board_rank_final"] = ABSENT
                feats[pid]["bb_nd_unranked_board"] = 1
            if r30 is not None:
                rr = m30.get(pid)
                if rr:
                    feats[pid]["bb_nd_board_rank_30d"] = rr["rank"]
                elif drafted:
                    feats[pid]["bb_nd_board_rank_30d"] = ABSENT
            if r60 is not None:
                rr = m60.get(pid)
                if rr:
                    feats[pid]["bb_nd_board_rank_60d"] = rr["rank"]
                elif drafted:
                    feats[pid]["bb_nd_board_rank_60d"] = ABSENT
        # cumulative change over the last 60 days + first-seen
        chg = defaultdict(float)
        chg_n = defaultdict(int)
        first_seen = {}
        for r, d in ranked:
            if r["dbd"] < 0:            # frozen post-draft capture
                continue
            for pid, row in d.items():
                if pid not in first_seen:
                    first_seen[pid] = r["dbd"]
                if r["dbd"] <= 60.0 and row.get("change") is not None:
                    chg[pid] += row["change"]
                    chg_n[pid] += 1
        for pid, v in chg.items():
            if chg_n[pid] >= 1:
                feats[pid]["bb_nd_board_change_60d"] = v
        for pid, v in first_seen.items():
            feats[pid]["bb_nd_board_first_seen_days"] = round(v, 1)

    # ============================================ nbadraft.net editorial mock
    for y in YEARS:
        rs = [r for r in groups.get(("nd_mock", y), []) if r["n"] >= MIN_MOCK]
        if not rs:
            continue
        rs.sort(key=lambda x: x["ts"])
        final = rs[-1]
        for row in final["rows"]:
            pid = M.match(row["name"], y, "nd_mock")
            if pid:
                feats[pid]["bb_nd_mock_rank_final"] = row["rank"]
                prov.append([pid, "nd_mock_final", final["ts"], final["url"]])

    # ============================================= nbadraft.net crowd consensus
    for y in YEARS:
        rs = [r for r in groups.get(("nd_crowd", y), []) if r["n"] >= MIN_MOCK]
        if not rs:
            continue
        rs.sort(key=lambda x: x["ts"])
        final = rs[-1]
        for row in final["rows"]:
            pid = M.match(row["name"], y, "nd_crowd")
            if pid:
                feats[pid]["bb_nd_crowd_mock_rank_final"] = row["rank"]
                prov.append([pid, "nd_crowd_final", final["ts"], final["url"]])

    # ==================================================== DraftExpress board
    for y in YEARS:
        caps = sorted(dx_boards.get(y, {}).values(), key=lambda x: x["ts"])
        if not caps:
            continue
        ded = dedupe_states(caps)
        ded.sort(key=lambda x: x["ts"])
        # the final board must be a full board, not a stray single page
        full = [c for c in ded if c["n"] >= 50]
        final = (full or ded)[-1]
        c30 = at_or_before(ded, 30.0)
        fm = {}
        for row in final["rows"]:
            pid = M.match(row["name"], y, "dx_board")
            if pid:
                fm[pid] = row
                feats[pid]["bb_dx_board_rank_final"] = row["rank"]
                if row.get("age"):
                    feats[pid]["bb_dx_age_listed"] = row["age"]
                prov.append([pid, "dx_board_final", final["ts"], final["url"]])
        if c30 is not None:
            for row in c30["rows"]:
                pid = M.match(row["name"], y, "dx_board")
                if pid:
                    feats[pid]["bb_dx_board_rank_30d"] = row["rank"]
        for pid in fm:
            a = feats[pid].get("bb_dx_board_rank_30d")
            b = feats[pid].get("bb_dx_board_rank_final")
            if a is not None and b is not None:
                feats[pid]["bb_dx_board_momentum_30d"] = a - b

    # ===================================================== DraftExpress mock
    for y in YEARS:
        rs = [r for r in groups.get(("dx_mock", y), []) if r["n"] >= MIN_MOCK]
        rx = [r for r in groups.get(("dx_mockx", y), []) if r["n"] >= MIN_MOCK]
        allr = rs + rx
        if not allr:
            continue
        allr = dedupe_states(allr)
        allr.sort(key=lambda x: x["ts"])
        picks = defaultdict(list)
        firsts = {}
        for r in allr:
            if r["dbd"] < 0:
                # a frozen post-draft capture may stand in for the FINAL mock
                # (below) but never contributes to a time-series feature
                continue
            for row in r["rows"]:
                pid = M.match(row["name"], y, "dx_mock")
                if not pid:
                    continue
                picks[pid].append(row["rank"])
                if pid not in firsts:
                    firsts[pid] = r["dbd"]
        # the final one-round/two-round mock (prefer the standard mock page)
        fin = [r for r in allr if r["source"] == "dx_mock"] or allr
        final = fin[-1]
        for row in final["rows"]:
            pid = M.match(row["name"], y, "dx_mock")
            if pid:
                feats[pid]["bb_dx_mock_pick_final"] = row["rank"]
                prov.append([pid, "dx_mock_final", final["ts"], final["url"]])
        for pid, ps in picks.items():
            if len(ps) >= 2:
                feats[pid]["bb_dx_mock_volatility"] = round(statistics.stdev(ps), 3)
        for pid, d in firsts.items():
            feats[pid]["bb_dx_first_mock_lead_days"] = round(d, 1)

    # ============================================================ The Stepien
    for y in YEARS:
        rs = groups.get(("stepien", y), [])
        if not rs:
            continue
        # The Stepien's boards are short by design (the 2020 composite is a
        # 12-man tiered board), so the minimum here is lower than for a
        # 60-pick mock or a 100-man board.
        grid = sorted([r for r in rs if r.get("layout") == "grid" and r["n"] >= 10],
                      key=lambda x: x["ts"])
        comp = sorted([r for r in rs if r.get("layout") == "composite" and r["n"] >= 10],
                      key=lambda x: x["ts"])
        posts = [r for r in rs if r.get("layout") == "post" and r["n"] >= 15]

        # ---- composite rank + tier (the '<year>-draft-rankings' page; the
        # analyst grid's first column carries the same composite ordering)
        series = comp or grid
        if series:
            final = series[-1]
            for row in final["rows"]:
                pid = M.match(row["name"], y, "stepien")
                if not pid:
                    continue
                feats[pid]["bb_stepien_consensus_rank"] = row["rank"]
                t = tier_num(row.get("tier"))
                if t:
                    feats[pid]["bb_stepien_tier"] = t
                prov.append([pid, "stepien_composite_final", final["ts"], final["url"]])
            pre = [c for c in series if c["dbd"] >= 150]
            if pre:
                pm = {}
                for row in pre[0]["rows"]:
                    pid = M.match(row["name"], y, "stepien")
                    if pid:
                        pm[pid] = row["rank"]
                for row in final["rows"]:
                    pid = M.match(row["name"], y, "stepien")
                    if pid and pid in pm:
                        feats[pid]["bb_stepien_preseason_to_final_delta"] = \
                            pm[pid] - row["rank"]

        # ---- dispersion: spread of the SAME player's rank across analysts
        done_disp = False
        if grid:
            g = grid[-1]
            for row in g["rows"]:
                ar = row.get("analyst_ranks") or {}
                if len(ar) < 2:
                    continue
                pid = M.match(row["name"], y, "stepien_grid")
                if pid:
                    feats[pid]["bb_stepien_dispersion"] = \
                        round(statistics.stdev(list(ar.values())), 3)
                    done_disp = True
        if not done_disp and posts:
            by_analyst = defaultdict(list)
            for r in posts:
                a = stepien_analyst(r["url"])
                if a is None:
                    continue      # unattributed lists (e.g. "sleepers") are not
                by_analyst[a].append(r)   # one analyst's board
            boards = []
            for a, items in by_analyst.items():
                items.sort(key=lambda x: x["ts"])
                boards.append(items[-1])
            if len(boards) >= 2:
                ranks = defaultdict(list)
                for b_ in boards:
                    for row in b_["rows"]:
                        pid = M.match(row["name"], y, "stepien_indiv")
                        if pid:
                            ranks[pid].append(row["rank"])
                for pid, rr in ranks.items():
                    if len(rr) >= 2:
                        feats[pid]["bb_stepien_dispersion"] = \
                            round(statistics.stdev(rr), 3)

    # ================================================================= derived
    for pid, d in feats.items():
        ndm, ndb = d.get("bb_nd_mock_rank_final"), d.get("bb_nd_board_rank_final")
        if ndm is not None and ndb is not None:
            d["bb_nd_fit_gap"] = ndm - ndb
        dxm, dxb = d.get("bb_dx_mock_pick_final"), d.get("bb_dx_board_rank_final")
        if dxm is not None and dxb is not None:
            d["bb_dx_fit_gap"] = dxm - dxb
        gaps = [d[k] for k in ("bb_nd_fit_gap", "bb_dx_fit_gap") if d.get(k) is not None]
        if gaps:
            d["bb_fit_gap_mean"] = round(sum(gaps) / len(gaps), 3)
        n = 0
        if d.get("bb_nd_board_rank_final") is not None and \
                d.get("bb_nd_unranked_board") == 0:
            n += 1
        if d.get("bb_dx_board_rank_final") is not None:
            n += 1
        if d.get("bb_stepien_consensus_rank") is not None:
            n += 1
        d["bb_n_board_sources"] = n

    # =================================================================== write
    cols = ["bb_nd_board_rank_final", "bb_nd_board_rank_30d", "bb_nd_board_rank_60d",
            "bb_nd_board_change_60d", "bb_nd_board_first_seen_days",
            "bb_nd_mock_rank_final", "bb_nd_crowd_mock_rank_final", "bb_nd_fit_gap",
            "bb_nd_unranked_board",
            "bb_dx_board_rank_final", "bb_dx_board_rank_30d", "bb_dx_mock_pick_final",
            "bb_dx_fit_gap", "bb_dx_mock_volatility", "bb_dx_board_momentum_30d",
            "bb_dx_first_mock_lead_days", "bb_dx_age_listed",
            "bb_stepien_consensus_rank", "bb_stepien_dispersion", "bb_stepien_tier",
            "bb_stepien_preseason_to_final_delta",
            "bb_fit_gap_mean", "bb_n_board_sources"]
    out = os.path.join(BASE, "features.csv")
    n_rows = 0
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pid"] + cols)
        for p in ident:
            pid = p["pid"]
            if not (2001 <= p["year"] <= 2025):
                continue
            d = feats.get(pid)
            if not d:
                continue
            vals = [d.get(c, "") for c in cols]
            # keep the row only if at least one real observation landed on it
            # (bb_n_board_sources is always written, so it does not count)
            if all(d.get(c) is None for c in cols if c != "bb_n_board_sources"):
                continue
            w.writerow([pid] + ["" if v is None else v for v in vals])
            n_rows += 1
    log("features.csv rows: %d" % n_rows)

    with open(os.path.join(BASE, "provenance.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pid", "source", "capture_ts", "capture_url"])
        seen = set()
        for r in prov:
            k = (r[0], r[1])
            if k in seen:
                continue
            seen.add(k)
            w.writerow(r)
    log("provenance.csv rows: %d" % len(seen))

    with open(os.path.join(RAW, "capture_usage.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "class_year", "ts", "n_entries", "days_before_draft"])
        for (src, y), rs in sorted(groups.items()):
            for r in sorted(rs, key=lambda x: x["ts"]):
                w.writerow([src, y, r["ts"], r["n"], "%.2f" % r["dbd"]])
        for y, d in sorted(dx_boards.items()):
            for ts, b in sorted(d.items()):
                w.writerow(["dx_board", y, ts, b["n"], "%.2f" % b["dbd"]])

    log("class-year reassignments/drops: %d" % len(yearlog))
    with open(os.path.join(RAW, "year_reassignments.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "ts", "calendar_year", "content_year", "frac_cal",
                    "frac_new"])
        w.writerows(sorted(yearlog, key=lambda r: (r[0], r[1])))

    with open(os.path.join(BASE, "unmatched.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "draft_year", "listed_name", "reason", "n_occurrences"])
        cnt = defaultdict(int)
        for s, y, nm, why in M.unmatched:
            cnt[(s, y, nm, why)] += 1
        for (s, y, nm, why), c in sorted(cnt.items(), key=lambda kv: -kv[1]):
            w.writerow([s, y, nm, why, c])
    log("unmatched distinct: %d" % len(cnt))
    return feats, cols


def nd_version(u):
    m = re.search(r"nba-mock-draft-(\d+)", u or "")
    return int(m.group(1)) if m else 0


if __name__ == "__main__":
    main()

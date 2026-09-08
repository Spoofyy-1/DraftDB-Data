"""Stage 2: pick the captures we actually need and download them (raw `id_`).

Selection is per (source, draft-class year) and checkpointed in
raw/fetch_done.txt, so the job is resumable: re-running skips whatever is
already cached under raw/<source>/.
"""
import csv
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bb_common import (DRAFT_CUTOFF, RAW, board_year_for_ts, capture_missing,  # noqa: E402
                       days_before_draft, get_capture, log, ts_dt)

INDEX = os.path.join(RAW, "index.csv")
PLAN = os.path.join(RAW, "fetch_plan.csv")
DONE = os.path.join(RAW, "fetch_done.txt")

YEARS = list(range(2001, 2026))

# how many captures to keep per (source, year)
CAPS = {
    "nd_board": 400,   # every pre-draft board capture (momentum series)
    "dx_board": 400,
    "dx_mock": 40,     # evenly spaced, for volatility
    "dx_mockx": 8,
    "nd_mock": 20,
    "nd_crowd": 10,
    "stepien": 60,
}


def urlkey(u):
    u = re.sub(r"^https?://", "", u.lower())
    u = re.sub(r"^www\.", "", u)
    u = re.sub(r":80(/|$)", r"\1", u)
    u = u.rstrip("/")
    return u


def url_year(u):
    """Draft class year encoded in the URL path, if any."""
    m = re.search(r"(?<!\d)(20[0-2]\d)(?!\d)", u)
    if m and 2001 <= int(m.group(1)) <= 2026:
        return int(m.group(1))
    m = re.search(r"/mock(20\d\d)\.htm", u)
    if m:
        return int(m.group(1))
    return None


def nd_mock_version(u):
    m = re.search(r"nba-mock-draft-(\d+)", u)
    if m:
        return int(m.group(1))
    m = re.search(r"extended-nba-mock-draft-(\d+)", u)
    if m:
        return int(m.group(1))
    return 0


def spread(items, k):
    """Keep k items evenly spaced through the list, always keeping the last."""
    if len(items) <= k:
        return items
    idx = sorted(set([round(i * (len(items) - 1) / (k - 1)) for i in range(k)]))
    idx = sorted(set(idx + [len(items) - 1]))
    return [items[i] for i in idx]


def build_plan():
    rows = []
    with open(INDEX) as f:
        for r in csv.DictReader(f):
            rows.append(r)
    # dedupe on (source, ts, urlkey)
    seen = set()
    ded = []
    for r in rows:
        k = (r["source"], r["ts"], urlkey(r["original"]))
        if k in seen:
            continue
        seen.add(k)
        ded.append(r)
    log("index rows %d -> unique %d" % (len(rows), len(ded)))

    buckets = defaultdict(list)   # (source, year) -> [(ts, original, url)]
    for r in ded:
        src, ts, orig = r["source"], r["ts"], r["original"]
        if len(ts) != 14 or ts < "20000101000000":
            continue
        uk = urlkey(orig)
        if src == "dx_mock" and "mock-draft-extended" in uk:
            src = "dx_mockx"
        # nbadraft.net crowd-aggregate pages live under both /nba-mock-drafts/
        # and the older /nba_mock_drafts/ (underscore) paths
        if src in ("nd_mock", "nd_crowd"):
            if "consensus" in uk:
                src = "nd_crowd"
            else:
                src = "nd_mock"
        if src == "nd_mock" and re.search(r"/(forum|comment|node|tag|user|search)/", uk):
            continue
        if src == "nd_crowd" and ("forum" in uk or "?" in uk):
            continue
        uy = url_year(uk)
        if src in ("nd_board", "dx_board", "nd_crowd"):
            y, mode = board_year_for_ts(ts)
        elif src == "stepien":
            # publication date is in the path: /YYYY/MM/DD/slug
            m = re.search(r"thestepien\.com/(20\d\d)/(\d\d)/(\d\d)/", uk)
            if m:
                pub = "%s%s%s000000" % (m.group(1), m.group(2), m.group(3))
                y, mode = board_year_for_ts(pub)
            elif uy:
                y, mode = uy, "url"
            else:
                y, mode = board_year_for_ts(ts)
        else:  # mocks
            if uy:
                y, mode = uy, "url"
            else:
                y, mode = board_year_for_ts(ts)
        if y not in DRAFT_CUTOFF:
            continue
        # acceptance: pre-draft, or the frozen post-draft board (<= Aug 15 of Y)
        d = ts_dt(ts)
        if d >= DRAFT_CUTOFF[y]:
            if src in ("nd_board", "dx_board") and d.year == y and d.month < 8 or \
               (src in ("nd_board", "dx_board") and d.year == y and d.month == 8 and d.day < 15):
                mode = "frozen"
            elif src in ("nd_mock", "dx_mock", "dx_mockx", "nd_crowd", "stepien") and \
                    uy == y and (d - DRAFT_CUTOFF[y]).days <= 40:
                mode = "frozen"
            else:
                continue
        buckets[(src, y)].append((ts, orig, uk, mode))

    plan = []
    for (src, y), items in sorted(buckets.items()):
        items.sort()
        cap = CAPS.get(src, 30)
        if src == "nd_mock":
            # the editorial mock only needs its LAST pre-draft edition, so take
            # (a) the 12 captures closest to draft night and (b) up to 3 from
            # each of the highest-numbered revision URLs, which is where the
            # final edition lives in the 2017+ /YYYY-nba-mock-draft-N/ era.
            pre = [it for it in items if it[3] != "frozen"]
            post = [it for it in items if it[3] == "frozen"]
            keep = pre[-12:] + post[-2:]
            per_url = defaultdict(list)
            for it in pre:
                per_url[it[2]].append(it)
            ranked = sorted(per_url.items(),
                            key=lambda kv: (nd_mock_version(kv[0]),
                                            max(x[0] for x in kv[1])), reverse=True)
            for uk, its in ranked[:4]:
                keep.extend(its[-3:])
            items = sorted(set(keep))[:cap]
        elif src in ("dx_mock", "dx_mockx"):
            items = spread(items, cap)
        elif src == "nd_crowd":
            items = items[-cap:]
        else:
            items = items[:cap] if len(items) > cap else items
        for ts, orig, uk, mode in items:
            plan.append([src, y, ts, orig, mode,
                         "%.2f" % days_before_draft(ts, y)])
    plan.sort(key=lambda r: (r[0], r[1], r[2]))
    with open(PLAN, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "year", "ts", "original", "mode", "days_before_draft"])
        w.writerows(plan)
    log("plan: %d captures" % len(plan))
    cnt = defaultdict(int)
    for r in plan:
        cnt[r[0]] += 1
    for k in sorted(cnt):
        log("   %-9s %5d" % (k, cnt[k]))
    return plan


def main():
    if not os.path.exists(PLAN) or "--replan" in sys.argv:
        plan = build_plan()
    else:
        with open(PLAN) as f:
            plan = [[r["source"], int(r["year"]), r["ts"], r["original"], r["mode"],
                     r["days_before_draft"]] for r in csv.DictReader(f)]
        log("loaded plan: %d captures" % len(plan))
    if "--plan-only" in sys.argv:
        return

    done = set()
    if os.path.exists(DONE):
        with open(DONE) as f:
            done = set(x.strip() for x in f if x.strip())

    n_new = 0
    for i, (src, y, ts, orig, mode, dbd) in enumerate(plan):
        key = "%s|%s|%s" % (src, ts, urlkey(orig))
        if key in done:
            continue
        if capture_missing(src, ts, orig):
            with open(DONE, "a") as f:
                f.write(key + "\n")
            continue
        txt = get_capture(src, ts, orig)
        with open(DONE, "a") as f:
            f.write(key + "\n")
        n_new += 1
        if n_new % 50 == 0:
            log("  fetched %d (%d/%d plan) last=%s %s" % (n_new, i + 1, len(plan), src, ts))
    log("fetch complete: %d new captures" % n_new)


if __name__ == "__main__":
    main()

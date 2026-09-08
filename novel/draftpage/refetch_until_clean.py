#!/usr/bin/env python3
"""Walk back one revision at a time until the draft-results player cells are empty.

The premise of this collector is that the last revision before the draft-night
cutoff is clean by construction.  For one year (2017) an editor pre-filled a
player cell 71 minutes BEFORE the draft started, so the assertion fires.  Rather
than dropping the year, this script steps to the immediately preceding revision
(still strictly pre-draft) until the assertion passes, or gives up after
MAX_STEPS.  Every rejected revision is kept under raw/rejected/ for audit.

Usage:  python3 refetch_until_clean.py [year ...]      (default: all cached years)
"""
import json, os, sys, time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_pages as F                                            # noqa: E402
import parse_pages as P                                            # noqa: E402

RAW = os.path.join(HERE, "raw")
REJ = os.path.join(RAW, "rejected")
MAX_STEPS = 40


def check(rec):
    wt = P.strip_comments(rec["wikitext"])
    return P.selection_table_check(wt)


def main():
    years = [int(a) for a in sys.argv[1:]] or sorted(F.CUTOFF)
    os.makedirs(REJ, exist_ok=True)
    for y in years:
        path = os.path.join(RAW, "%d.json" % y)
        if not os.path.exists(path):
            continue
        rec = json.load(open(path))
        if rec.get("status") != "ok":
            continue
        steps = 0
        while True:
            n_tab, n_row, bad = check(rec)
            if not bad:
                if steps:
                    print("%d CLEAN after %d step(s): rev_ts=%s revid=%s (%d tables/%d rows)"
                          % (y, steps, rec["rev_ts"], rec["revid"], n_tab, n_row), flush=True)
                    rec["walkback_steps"] = steps
                    json.dump(rec, open(path, "w"))
                break
            if steps >= MAX_STEPS:
                print("%d GIVE UP after %d steps (still %d filled cells)"
                      % (y, steps, len(bad)), flush=True)
                rec["status"] = "abort_player_cells_not_empty"
                json.dump(rec, open(path, "w"))
                break
            print("%d rev_ts=%s revid=%s -> %d filled player cell(s) %s; stepping back"
                  % (y, rec["rev_ts"], rec["revid"], len(bad), bad[:2]), flush=True)
            json.dump(rec, open(os.path.join(REJ, "%d_%s.json"
                                             % (y, rec["rev_ts"].replace(":", ""))), "w"))
            # rvstart is inclusive, so ask for the last revision one second earlier
            prev = (datetime.strptime(rec["rev_ts"], "%Y-%m-%dT%H:%M:%SZ")
                    - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            d = F.fetch(rec["title"], prev)
            pages = d.get("query", {}).get("pages", [])
            got = None
            if pages and pages[0].get("revisions"):
                rv = pages[0]["revisions"][0]
                if rv["timestamp"] < rec["rev_ts"]:
                    got = rv
            if got is None:
                print("%d no older revision available" % y, flush=True)
                rec["status"] = "abort_player_cells_not_empty"
                json.dump(rec, open(path, "w"))
                break
            rec = dict(rec, rev_ts=got["timestamp"], revid=got.get("revid"),
                       wikitext=got.get("slots", {}).get("main", {}).get("content"))
            steps += 1
            time.sleep(1.2)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()

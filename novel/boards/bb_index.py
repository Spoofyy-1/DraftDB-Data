"""Stage 1: build the snapshot index for every board / mock URL we need.

Writes raw/index.csv with columns: source,kind,url,ts,original
Sources: nd_board, nd_mock, nd_crowd, dx_board, dx_mock, stepien
Uses the timemap endpoint per URL (cheap, 1 request) and a handful of CDX
prefix/domain listings to discover URL variants. Checkpointed: URLs already in
raw/index_done.txt are skipped on resume.
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bb_common import RAW, cdx, log, timemap  # noqa: E402

INDEX = os.path.join(RAW, "index.csv")
DONE = os.path.join(RAW, "index_done.txt")

YEARS = list(range(2001, 2026))

# ---------------------------------------------------------------- URL targets
def nd_board_urls():
    return [("nd_board", "board", "https://www.nbadraft.net/ranking/bigboard/"),
            ("nd_board", "board", "http://www.nbadraft.net/ranking/bigboard"),
            ("nd_board", "board", "http://www.nbadraft.net/rankings/top-100/"),
            ("nd_board", "board", "http://www.nbadraft.net/nbadraft-top-100/"),
            ("nd_board", "board", "http://www.nbadraft.net/top100.htm"),
            ("nd_board", "board", "http://www.nbadraft.net/ranking/top100/")]


def nd_mock_urls():
    """Only the crowd-consensus page needs a per-URL timemap; the editorial mock
    URLs are discovered wholesale by the nbadraft.net CDX domain job below."""
    return [("nd_crowd", "crowd", "https://www.nbadraft.net/nba-mock-drafts/consensus/"),
            ("nd_crowd", "crowd", "http://www.nbadraft.net/nba-mock-drafts/consensus")]


def dx_board_urls():
    out = [("dx_board", "board", "http://www.draftexpress.com/rankings/Top-100-Prospects/"),
           ("dx_board", "board", "http://www.draftexpress.com/rankings/Top-100-Prospects/printable/"),
           ("dx_board", "board", "http://www.draftexpress.com/rankings/Top-100-Prospects/printable")]
    for p in (2, 3, 4, 5):
        out.append(("dx_board", "board", "http://www.draftexpress.com/rankings/Top-100-Prospects/%d/" % p))
        out.append(("dx_board", "board", "http://www.draftexpress.com/rankings/Top-100-Prospects/%d" % p))
    return out


def dx_mock_urls():
    out = []
    for y in range(2005, 2019):
        out.append(("dx_mock", "mock", "http://www.draftexpress.com/nba-mock-draft/%d/" % y))
        out.append(("dx_mock", "mock", "http://www.draftexpress.com/nba-mock-draft-extended/%d/" % y))
        out.append(("dx_mock", "mock", "http://www.draftexpress.com/nba-mock-draft-extended/%d" % y))
    out.append(("dx_mock", "mock", "http://www.draftexpress.com/nba-mock-draft/"))
    return out


# --------------------------------------------------------------- CDX crawls
CDX_JOBS = [
    # (source, kind, url, matchType, server-side filter, client-side regex)
    ("nd_mock", "mock", "nbadraft.net", "domain", "original:.*[Mm]ock.*", r"mock"),
    ("dx_mock", "mock", "draftexpress.com", "domain", "original:.*nba-mock-draft.*",
     r"nba-mock-draft"),
    ("dx_board", "board", "draftexpress.com/rankings", "prefix", None,
     r"[Tt]op-?100|Top-100-Prospects"),
    ("stepien", "board", "thestepien.com", "domain", None,
     r"big-?board|draft-rankings|draft-board|draft-guide|top-\d+|rankings"),
]


def load_done():
    if not os.path.exists(DONE):
        return set()
    with open(DONE) as f:
        return set(x.strip() for x in f if x.strip())


def mark_done(key):
    with open(DONE, "a") as f:
        f.write(key + "\n")


def append_rows(rows):
    new = not os.path.exists(INDEX)
    with open(INDEX, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["source", "kind", "url", "ts", "original"])
        w.writerows(rows)


def main():
    os.makedirs(RAW, exist_ok=True)
    done = load_done()

    # --- phase 1: CDX bulk discovery (at most one listing in flight here) ---
    for src, kind, url, mt, sfilt, cfilt in CDX_JOBS:
        key = "CDX2|%s|%s" % (url, sfilt or "")
        if key in done:
            continue
        log("CDX %s %s (%s) filter=%s" % (src, url, mt, sfilt))
        extra = {"filter": "statuscode:200"}
        if sfilt:
            extra["filter2"] = sfilt   # placeholder, replaced below
        rows = cdx_multi(url, mt, sfilt)
        log("  raw rows: %d" % len(rows))
        rx = re.compile(cfilt) if cfilt else None
        keep = []
        for r in rows:
            o = r.get("original", "")
            mime = r.get("mimetype", "")
            if mime and "html" not in mime and mime != "warc/revisit":
                continue
            if rx and not rx.search(o):
                continue
            if re.search(r"\.(jpg|jpeg|png|gif|css|js|pdf|xml|ico|swf)(\?|$)", o, re.I):
                continue
            keep.append([src, kind, o, r["timestamp"], o])
        if keep:
            append_rows(keep)
        mark_done(key)
        log("  kept: %d" % len(keep))

    # --- phase 2: per-URL timemaps for the board pages -----------------------
    targets = nd_board_urls() + dx_board_urls() + nd_mock_urls() + dx_mock_urls()
    log("timemap targets: %d" % len(targets))
    for i, (src, kind, url) in enumerate(targets):
        key = "TM|" + url
        if key in done:
            continue
        snaps = timemap(url)
        if snaps:
            append_rows([[src, kind, url, ts, orig] for ts, orig in snaps])
            log("  %-9s %-70s %4d snaps" % (src, url[-70:], len(snaps)))
        mark_done(key)

    log("index complete")


def cdx_multi(url, mt, sfilt):
    """CDX listing with an optional server-side `filter` expression."""
    import json
    import urllib.parse
    from bb_common import fetch
    q = {"url": url, "output": "json",
         "fl": "timestamp,original,statuscode,mimetype", "collapse": "digest",
         "matchType": mt}
    parts = urllib.parse.urlencode(q) + "&filter=statuscode:200"
    if sfilt:
        parts += "&filter=" + urllib.parse.quote(sfilt, safe="")
    u = "http://web.archive.org/cdx/search/cdx?" + parts
    st, data = fetch(u, timeout=600)
    if st != 200 or not data:
        log("  CDX failed status=%s" % st)
        return []
    try:
        rows = json.loads(data.decode("utf-8", "replace"))
    except Exception as e:
        log("  CDX parse error %s" % e)
        return []
    if not rows:
        return []
    hdr = rows[0]
    return [dict(zip(hdr, r)) for r in rows[1:]]


if __name__ == "__main__":
    main()

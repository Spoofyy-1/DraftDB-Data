"""Supplementary discovery for The Stepien (the domain-wide CDX pass missed the
2021 class and several dated analyst posts)."""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bb_common import RAW, log, timemap  # noqa: E402
from bb_index import append_rows, cdx_multi, load_done, mark_done  # noqa: E402

TM = []
for y in range(2017, 2024):
    TM += ["https://www.thestepien.com/%d-draft-rankings/" % y,
           "https://www.thestepien.com/%d-individual-rankings/" % y,
           "https://www.thestepien.com/%d-big-board/" % y]
TM += ["https://www.thestepien.com/individual-rankings/",
       "https://www.thestepien.com/draft-rankings/",
       "https://www.thestepien.com/big-board/"]

CDX = [("thestepien.com/%d" % y, "prefix",
        r"big-?board|rankings|draft-board|top-\d+") for y in range(2017, 2024)]


def main():
    done = load_done()
    for url in TM:
        key = "TM|" + url
        if key in done:
            continue
        snaps = timemap(url)
        if snaps:
            append_rows([["stepien", "board", url, ts, o] for ts, o in snaps])
            log("  stepien %-70s %4d" % (url[-70:], len(snaps)))
        mark_done(key)
    for url, mt, cfilt in CDX:
        key = "CDXS|" + url
        if key in done:
            continue
        rows = cdx_multi(url, mt, None)
        rx = re.compile(cfilt)
        keep = []
        for r in rows:
            o = r.get("original", "")
            if not rx.search(o):
                continue
            if re.search(r"\.(jpg|jpeg|png|gif|css|js|pdf|xml|ico)(\?|$)", o, re.I):
                continue
            if "?" in o and "replytocom" in o:
                continue
            keep.append(["stepien", "board", o, r["timestamp"], o])
        if keep:
            append_rows(keep)
        mark_done(key)
        log("  CDX %s -> %d kept (of %d)" % (url, len(keep), len(rows)))


if __name__ == "__main__":
    main()

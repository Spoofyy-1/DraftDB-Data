#!/usr/bin/env python3
"""Fetch the last Wikipedia revision strictly BEFORE each player's draft-night cutoff.

Cache: raw/predraft/<pid>.json  -> {pid, title, cutoff, status, rev_ts, revid, wikitext}
status: ok | no_predraft_rev (article created after cutoff) | missing_page | error:<msg>
Polite: 1 request per >=1.1 s, descriptive User-Agent, resumable (skips existing cache files).
"""
import json, os, sys, time, csv, glob, urllib.request, urllib.parse, urllib.error

BASE = "/Users/kennakao/nba/datarebuild"
OUT = os.path.join(BASE, "novel/wikitext/raw/predraft")
UA = "DraftDB-research/1.0 (NBA draft research; contact mike@alphax.inc) python-urllib/3"
API = "https://en.wikipedia.org/w/api.php"

# Draft-night cutoffs from COLLECTOR_RULES.md (22:00 UTC on the draft date)
CUTOFF = {2000: "2000-06-28", 2001: "2001-06-27", 2002: "2002-06-26", 2003: "2003-06-26",
          2004: "2004-06-24", 2005: "2005-06-28", 2006: "2006-06-28", 2007: "2007-06-28",
          2008: "2008-06-26", 2009: "2009-06-25", 2010: "2010-06-24", 2011: "2011-06-23",
          2012: "2012-06-28", 2013: "2013-06-27", 2014: "2014-06-26", 2015: "2015-06-25",
          2016: "2016-06-23", 2017: "2017-06-22", 2018: "2018-06-21", 2019: "2019-06-20",
          2020: "2020-11-18", 2021: "2021-07-29", 2022: "2022-06-23", 2023: "2023-06-22",
          2024: "2024-06-26", 2025: "2025-06-25",
          # 2026 is not in COLLECTOR_RULES.md; date taken from the project's own
          # wiki_raw/attn_*.json cache (draft_date field), which matches the rules
          # table exactly for every year 2000-2025.
          2026: "2026-06-24"}


def load_targets():
    dy = {}
    with open("/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv") as fh:
        for r in csv.DictReader(fh):
            dy[r["pid"]] = int(r["draft_year"])
    out = []
    for f in sorted(glob.glob(os.path.join(BASE, "wiki_raw/current/*.json"))):
        pid = os.path.basename(f)[:-5]
        if pid not in dy:
            continue
        d = json.load(open(f))
        title = d.get("title")
        if not title:
            continue
        out.append((pid, title, CUTOFF[dy[pid]] + "T22:00:00Z"))
    return out


def fetch(title, cutoff):
    p = {"action": "query", "prop": "revisions", "titles": title,
         "rvprop": "timestamp|content|ids", "rvslots": "main", "rvlimit": "1",
         "rvdir": "older", "rvstart": cutoff, "format": "json", "formatversion": "2",
         "redirects": "1"}
    url = API + "?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())


def main():
    os.makedirs(OUT, exist_ok=True)
    targets = load_targets()
    todo = [t for t in targets if not os.path.exists(os.path.join(OUT, t[0] + ".json"))]
    print(f"targets={len(targets)} todo={len(todo)}", flush=True)
    for i, (pid, title, cutoff) in enumerate(todo, 1):
        rec = {"pid": pid, "title": title, "cutoff": cutoff, "status": None,
               "rev_ts": None, "revid": None, "wikitext": None}
        delay = 5
        for attempt in range(4):
            try:
                d = fetch(title, cutoff)
                pages = d.get("query", {}).get("pages", [])
                if not pages or pages[0].get("missing"):
                    rec["status"] = "missing_page"
                elif not pages[0].get("revisions"):
                    rec["status"] = "no_predraft_rev"
                else:
                    rv = pages[0]["revisions"][0]
                    ts = rv["timestamp"]
                    if ts >= cutoff:
                        rec["status"] = "no_predraft_rev"
                    else:
                        rec.update(status="ok", rev_ts=ts, revid=rv.get("revid"),
                                   wikitext=rv.get("slots", {}).get("main", {}).get("content"))
                        if rec["wikitext"] is None:
                            rec["status"] = "no_content"
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 503) and attempt < 3:
                    time.sleep(delay); delay *= 2; continue
                rec["status"] = f"error:HTTP{e.code}"; break
            except Exception as e:  # noqa: BLE001
                if attempt < 3:
                    time.sleep(delay); delay *= 2; continue
                rec["status"] = "error:" + type(e).__name__; break
        with open(os.path.join(OUT, pid + ".json"), "w") as fh:
            json.dump(rec, fh)
        if i % 50 == 0:
            print(f"{i}/{len(todo)} last={pid} {rec['status']}", flush=True)
        time.sleep(1.1)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()

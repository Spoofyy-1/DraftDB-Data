#!/usr/bin/env python3
"""
Nike Hoop Summit World Select participation from English Wikipedia.

Source: https://en.wikipedia.org/wiki/Nike_Hoop_Summit , section
"Alumni selected in the NBA draft" -- a wikitable whose columns are
  Name | Position | Draft Year | Round | Pick | Drafted by | NHS Year(s) | NHS Team
NHS Team is literally "USA" or "World".

Dating: the fact recorded is participation in the Hoop Summit game, which is
played in April of the NHS year, i.e. always before that year's draft night
(earliest cutoff in the project is 2019-06-20; the 2020 game was cancelled).
A row is used only when min(NHS year) <= draft_year.  The Wikipedia revision
id/timestamp of the captured page is stored for provenance.

Rule-based extraction only: wiki-table split on "|-" and "||", link text taken
from [[Target|Display]] / [[Target]].

Output: raw/parsed/hoop_summit.json   (list of rows, cached wikitext alongside)
Usage:  python3 hoop_summit.py
"""
import json
import os
import re

from fibalib import PARSED, RAW, log, norm_name

import requests

UA = ("DraftDB-Research/1.0 (non-commercial NBA draft research; "
      "contact mike@alphax.inc)")
API = "https://en.wikipedia.org/w/api.php"
TITLE = "Nike Hoop Summit"
CACHE = os.path.join(RAW, "wikipedia", "nike_hoop_summit.json")


def fetch_wikitext():
    if os.path.exists(CACHE):
        with open(CACHE) as fh:
            return json.load(fh)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    r = requests.get(API, params={
        "action": "query", "prop": "revisions",
        "rvprop": "content|timestamp|ids", "rvslots": "main",
        "format": "json", "formatversion": "2", "titles": TITLE},
        headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    page = r.json()["query"]["pages"][0]
    rev = page["revisions"][0]
    rec = {"title": TITLE, "revid": rev["revid"], "rev_ts": rev["timestamp"],
           "url": "https://en.wikipedia.org/wiki/Nike_Hoop_Summit",
           "wikitext": rev["slots"]["main"]["content"]}
    with open(CACHE, "w") as fh:
        json.dump(rec, fh)
    return rec


_LINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]|]+)\]\]")


def clean_cell(c):
    c = c.strip()
    c = re.sub(r'^\s*(?:style|scope)="[^"]*"\s*\|', "", c).strip()
    c = _LINK.sub(r"\1", c)
    c = re.sub(r"<[^>]+>", "", c)
    c = c.replace("{{", "").replace("}}", "")
    return c.strip().strip("|").strip()


def parse(wikitext):
    i = wikitext.find("==Alumni selected in the NBA draft==")
    if i < 0:
        return []
    j = wikitext.find("\n==See also==", i)
    sec = wikitext[i:j if j > 0 else len(wikitext)]
    tables = re.findall(r"\{\|(?:.|\n)*?\n\|\}", sec)
    if not tables:
        return []
    rows = []
    for raw_row in tables[-1].split("\n|-"):
        cells = [clean_cell(c) for c in raw_row.strip().split("||")]
        if len(cells) < 8:
            continue
        name = cells[0]
        dy = re.search(r"(\d{4})", cells[2])
        if not name or not dy:
            continue
        years = [int(y) for y in re.findall(r"(\d{4})", cells[6])]
        team = cells[7].split("\n")[0].strip()
        if team not in ("USA", "World"):
            continue
        rows.append({"name_norm": norm_name(name), "draft_year": int(dy.group(1)),
                     "nhs_years": sorted(years), "nhs_team": team})
    return rows


def main():
    rec = fetch_wikitext()
    rows = parse(rec["wikitext"])
    out = {"source_url": rec["url"], "revid": rec["revid"],
           "rev_ts": rec["rev_ts"], "rows": rows}
    os.makedirs(PARSED, exist_ok=True)
    with open(os.path.join(PARSED, "hoop_summit.json"), "w") as fh:
        json.dump(out, fh)
    world = [r for r in rows if r["nhs_team"] == "World"]
    log("hoop summit: %d alumni rows (%d World) rev %s (%s)" % (
        len(rows), len(world), rec["revid"], rec["rev_ts"]))
    if rows:
        log("  draft years %d-%d" % (min(r["draft_year"] for r in rows),
                                     max(r["draft_year"] for r in rows)))


if __name__ == "__main__":
    main()

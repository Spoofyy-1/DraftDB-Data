"""NCAA tournament fields + seeds from Wikipedia bracket templates (rule-based regex on wikitext).

Parsing: each {{NTeamBracket ...}} chunk yields RD1-team<idx> entries. If the chunk carries explicit
RD1-seed<idx> parameters they are used; otherwise (the 2008-2010 style 16TeamBracket) the seed is the
template's fixed first-round ordering [1,16,8,9,5,12,4,13,6,11,3,14,7,10,2,15].

Dating: we first take the last revision at or before 22:00 UTC on 20 June of the tournament year (the
earliest draft night that could use that season). Where that revision does not exist or does not yet
contain a machine-readable bracket (the 2003-2007 articles used ASCII-art brackets), we fall back to
the current revision and flag it in work/seeds_provenance.csv. A team's tournament seed is public on
Selection Sunday, i.e. three months before the earliest draft that uses it, so the later revision
carries no post-draft information; only the transcription is later.
Outputs: raw/wiki/<year>_<mode>.json (cache), work/seeds.csv, work/seeds_provenance.csv
"""
import json, os, re, sys, time, urllib.parse, urllib.request, csv

D = "/Users/kennakao/nba/datarebuild/novel/gamelogs"
os.makedirs(f"{D}/raw/wiki", exist_ok=True)
API = "https://en.wikipedia.org/w/api.php"
UA = "DraftDB-research/1.0 (mike@alphax.inc)"
POS = [1, 16, 8, 9, 5, 12, 4, 13, 6, 11, 3, 14, 7, 10, 2, 15]

def get(params):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for a in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r: return json.load(r)
        except Exception as e:
            print("  retry", a, e, flush=True); time.sleep(3 * (a + 1))
    return None

def fetch(year, mode):
    fp = f"{D}/raw/wiki/{year}_{mode}.json"
    if os.path.exists(fp): return json.load(open(fp))
    title = f"{year} NCAA Division I men's basketball tournament"
    base = dict(action="query", prop="revisions", titles=title, rvprop="content|timestamp|ids",
                rvslots="main", rvlimit=1, format="json", formatversion=2, redirects=1)
    if mode == "pre_draft":
        d = get(dict(base, rvdir="older", rvstart=f"{year}-06-20T22:00:00Z"))
    else:
        d = get(dict(base))
    time.sleep(1.5)
    pg = (d or {}).get("query", {}).get("pages", [{}])[0]
    if not pg.get("revisions"): return None
    r = pg["revisions"][0]
    out = dict(year=year, mode=mode, timestamp=r["timestamp"], revid=r.get("revid"),
               title=pg.get("title"), text=r["slots"]["main"]["content"])
    json.dump(out, open(fp, "w")); return out

LINK = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]\|]*)\]\]")
def clean(raw):
    m = re.search(r"\[\[(?:[^\|\]]*\|)?([^\]]*)\]\]", raw)
    nm = m.group(1) if m else raw.split("|")[0]
    nm = re.sub(r"<[^>]*>", " ", nm)
    nm = re.sub(r"\s*\(.*?\)\s*$", "", nm).replace("'''", "").replace("''", "").strip()
    nm = re.sub(r"^\d{4}\s*[-–—]\s*\d{2,4}\s+", "", nm)
    nm = re.sub(r"\s+(men'?s basketball team|men'?s basketball|basketball team|basketball)$", "", nm, flags=re.I)
    nm = re.sub(r"\}\}.*$", "", nm)
    return nm.strip(" *|")

def parse(text):
    seeds = {}
    chunks = re.split(r"(?=\{\{\s*\d+TeamBracket)", text)
    for ch in chunks:
        if not re.match(r"\{\{\s*\d+TeamBracket", ch): continue
        ch = ch[:20000]
        tms = dict((m.group(1), m.group(2)) for m in
                   re.finditer(r"RD1-team(\d+)\s*=\s*([^\n]+)", ch))
        sds = {}
        for m in re.finditer(r"RD1-seed(\d+)\s*=\s*'*(\d{1,2})[ab]?'*", ch):
            sds[m.group(1)] = int(m.group(2))
        for idx, raw in tms.items():
            nm = clean(raw)
            if not nm or len(nm) > 60: continue
            if idx in sds: sd = sds[idx]
            elif len(tms) >= 16 and idx.isdigit() and 1 <= int(idx) <= 16: sd = POS[int(idx) - 1]
            else: continue
            if 1 <= sd <= 16: seeds.setdefault(nm, sd)
    return seeds

rows, prov = [], []
for year in range(2003, 2026):
    if year == 2020:
        prov.append(dict(year=year, mode="cancelled", timestamp="", revid="", n_teams=0)); continue
    best = None
    for mode in ("pre_draft", "current"):
        d = fetch(year, mode)
        if not d: continue
        sd = parse(d["text"])
        if best is None or len(sd) > len(best[1]): best = (d, sd)
        if len(sd) >= 63: break
    if not best:
        prov.append(dict(year=year, mode="missing", timestamp="", revid="", n_teams=0))
        print(year, "MISSING", flush=True); continue
    d, sd = best
    for nm, s in sorted(sd.items()): rows.append(dict(year=year, team_wiki=nm, seed=s))
    prov.append(dict(year=year, mode=d["mode"], timestamp=d["timestamp"], revid=d["revid"], n_teams=len(sd)))
    print(year, d["mode"], d["timestamp"], "teams", len(sd), flush=True)

with open(f"{D}/work/seeds.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["year", "team_wiki", "seed"]); w.writeheader(); w.writerows(rows)
with open(f"{D}/work/seeds_provenance.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["year", "mode", "timestamp", "revid", "n_teams"])
    w.writeheader(); w.writerows(prov)
print("seed rows", len(rows))

#!/usr/bin/env python3
"""Cache Bart Torvik's CONFERENCE-ONLY player-season export under raw/ (gzipped).

Endpoint:
  https://barttorvik.com/getadvstats.php?year=YYYY&conyes=1&csv=1  -> raw/advconf_YYYY.csv.gz

Same 67 unlabelled columns as the full-season export (`...?year=YYYY&csv=1`), restricted to
conference games.  The full-season files are NOT fetched here: they are already cached by the
sibling collector at ../torvik_context/raw/adv_YYYY.csv.gz and are reused as-is.

robots.txt (https://barttorvik.com/robots.txt, cached to raw/robots.txt) disallows db.php, box.php,
results.php, playerstat.php, teamcast.php, the *-time-machine.php pages and /*.json.
getadvstats.php is NOT disallowed.  The `User-agent: *` block sets `Crawl-Delay: 10`, honoured here:
one request every 10 s, exponential backoff on failure, descriptive User-Agent.  No login, paywall
or JS challenge is involved.  Budget: 19 season requests (2008-2026) + 1 robots.txt, once.

Years before 2008 are never requested: the endpoint silently serves the CURRENT season for them,
which would be a silent mislabelling.  Every cached file is asserted to carry the requested year in
column 31 by build.py.

Everything is stored gzipped (this Mac has <1 GB free).  Resumable and idempotent: a cached file
larger than 1000 bytes is never re-requested, so a re-run costs zero network traffic.
"""
import gzip
import hashlib
import io
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
UA = "DraftDB-research/1.0 (contact: mike@alphax.inc) non-commercial NBA draft research"
DELAY = 10.0                       # robots.txt Crawl-Delay
YEARS = list(range(2008, 2027))    # 2008 is Torvik's first season; <2008 silently returns "now"
PROV = os.path.join(HERE, "provenance.csv")


def get(url: str) -> bytes:
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
            with urllib.request.urlopen(req, timeout=180) as r:
                body = r.read()
            if len(body) < 500:
                raise IOError(f"short body {len(body)} B")
            return body
        except Exception as e:                       # exponential backoff on 429/503/timeouts
            wait = DELAY * (2 ** attempt)
            print(f"warn  attempt {attempt+1} for {url}: {e}; sleeping {wait:.0f}s", flush=True)
            time.sleep(wait)
    raise SystemExit(f"FAIL {url}")


def fetch_season(year: int) -> bool:
    """Returns True if the network was hit."""
    dest = os.path.join(RAW, f"advconf_{year}.csv.gz")
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        print(f"skip  advconf_{year}.csv.gz ({os.path.getsize(dest)} B)", flush=True)
        return False
    url = f"https://barttorvik.com/getadvstats.php?year={year}&conyes=1&csv=1"
    body = get(url)
    tmp = dest + ".part"
    with gzip.open(tmp, "wb", compresslevel=9) as f:      # gzip: <1 GB free on this disk
        f.write(body)
    os.replace(tmp, dest)
    rows = body.count(b"\n")
    meta = (f"raw/advconf_{year}.csv.gz,{url},{year},player_season_conference_only,"
            f"{len(body)},{os.path.getsize(dest)},{rows},{hashlib.sha256(body).hexdigest()},"
            f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())},"
            f"yes (only db/box/results/playerstat/teamcast/time-machine/*.json are disallowed),"
            f"{int(DELAY)},{UA}\n")
    new = not os.path.exists(PROV)
    with open(PROV, "a") as f:
        if new:
            f.write("file,url,season,kind,bytes_uncompressed,bytes_gz,rows,sha256_uncompressed,"
                    "fetched_utc,robots_allowed,crawl_delay_s,user_agent\n")
        f.write(meta)
    print(f"got   advconf_{year}.csv.gz  {len(body)} B raw -> {os.path.getsize(dest)} B gz, {rows} rows", flush=True)
    return True


def main() -> None:
    os.makedirs(RAW, exist_ok=True)
    years = [int(a) for a in sys.argv[1:]] or YEARS
    rob = os.path.join(RAW, "robots.txt")
    hit = False
    if not os.path.exists(rob):
        body = get("https://barttorvik.com/robots.txt")
        with open(rob, "wb") as f:
            f.write(body)
        print(f"got   robots.txt {len(body)} B", flush=True)
        hit = True
    for y in years:
        if hit:
            time.sleep(DELAY)
        hit = fetch_season(y)
    print("done", flush=True)


if __name__ == "__main__":
    main()

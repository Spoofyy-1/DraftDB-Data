#!/usr/bin/env python3
"""Cache Bart Torvik full-league CSV exports under raw/.

Endpoints (both allowed by https://barttorvik.com/robots.txt as of 2026-09-08;
robots sets `Crawl-Delay: 10` for User-agent: *, which we honour):
  https://barttorvik.com/getadvstats.php?year=YYYY&csv=1   -> raw/adv_YYYY.csv   (player-seasons)
  https://barttorvik.com/getgamestats.php?year=YYYY&csv=1  -> raw/games_YYYY.csv (team-games)

Disallowed and never called: db.php, box.php, results.php, playerstat.php,
teamcast.php, *-time-machine.php, *.json.

Resumable: files already on disk with >1000 bytes are skipped.
"""
import os, sys, time, urllib.request, urllib.error

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
UA = "DraftDB-research/1.0 non-commercial NBA draft research"
DELAY = 10.0          # robots.txt Crawl-Delay
YEARS = range(2008, 2027)


def fetch(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        print(f"skip  {os.path.basename(dest)} ({os.path.getsize(dest)} B)", flush=True)
        return False
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
            if len(body) < 1000:
                raise IOError(f"short body {len(body)} B")
            tmp = dest + ".part"
            with open(tmp, "wb") as f:
                f.write(body)
            os.replace(tmp, dest)
            print(f"got   {os.path.basename(dest)} {len(body)} B", flush=True)
            return True
        except Exception as e:                     # exponential backoff on 429/503/timeouts
            wait = DELAY * (2 ** attempt)
            print(f"warn  {os.path.basename(dest)} attempt {attempt+1}: {e}; sleeping {wait:.0f}s", flush=True)
            time.sleep(wait)
    print(f"FAIL  {os.path.basename(dest)}", flush=True)
    return False


def main():
    os.makedirs(RAW, exist_ok=True)
    jobs = []
    for y in YEARS:
        jobs.append((f"https://barttorvik.com/getadvstats.php?year={y}&csv=1", os.path.join(RAW, f"adv_{y}.csv")))
        jobs.append((f"https://barttorvik.com/getgamestats.php?year={y}&csv=1", os.path.join(RAW, f"games_{y}.csv")))
    for i, (url, dest) in enumerate(jobs):
        hit_net = fetch(url, dest)
        if hit_net and i != len(jobs) - 1:
            time.sleep(DELAY)
    print("done", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Pull every game box score from the open Euroleague API (api-live.euroleague.net)
for competitions E (Euroleague), U (EuroCup) and J (U18 Adidas Next Generation
Tournament).  Caches every response under raw/ so re-runs are offline and
resumable; checkpoints per season.

Polite: >=1.1s between requests, adaptive slow-down + long cooldown on 429,
descriptive User-Agent.  robots.txt at api-live.euroleague.net is empty.

Usage:  nohup python3 pull.py >> run.log 2>&1 &
Resume: just run the same command again; finished seasons and cached games
        are skipped.
"""
import gzip
import json
import os
import sys
import time
import random
from datetime import datetime

import requests

BASE = "https://api-live.euroleague.net/v2"
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
UA = ("DraftDB-research/1.0 (non-commercial NBA draft research; "
      "contact mike@alphax.inc)")
COMPS = ["E", "U", "J"]
SLEEP_MIN = 1.1      # floor: >= 1 s between requests (COLLECTOR_RULES rule 3)
SLEEP_MAX = 6.0
MAX_RETRY = 8
STATE = {"sleep": SLEEP_MIN, "ok_streak": 0}

NOT_FOUND = object()   # genuine 404, distinct from "failed, try again later"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "application/json"})

_last = [0.0]


def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def throttle():
    dt = time.time() - _last[0]
    if dt < STATE["sleep"]:
        time.sleep(STATE["sleep"] - dt)
    _last[0] = time.time()


def slow_down(why):
    """Adaptive back-pressure: a 429 permanently widens the gap between
    requests until a long clean streak earns it back."""
    old = STATE["sleep"]
    STATE["sleep"] = min(STATE["sleep"] + 0.4, SLEEP_MAX)
    STATE["ok_streak"] = 0
    if STATE["sleep"] != old:
        log(f"  rate: {old:.2f}s -> {STATE['sleep']:.2f}s between requests ({why})")


def speed_up():
    STATE["ok_streak"] += 1
    if STATE["ok_streak"] >= 400 and STATE["sleep"] > SLEEP_MIN:
        old = STATE["sleep"]
        STATE["sleep"] = max(STATE["sleep"] - 0.1, SLEEP_MIN)
        STATE["ok_streak"] = 0
        log(f"  rate: {old:.2f}s -> {STATE['sleep']:.2f}s between requests (clean streak)")


def get_json(url, params=None, allow_404=False):
    """GET with polite throttling and exponential backoff."""
    delay = 2.0
    for attempt in range(MAX_RETRY):
        throttle()
        try:
            r = SESSION.get(url, params=params, timeout=60)
        except requests.RequestException as e:
            log(f"  net error {e} -> sleep {delay:.0f}s")
            time.sleep(delay)
            delay = min(delay * 2, 120)
            continue
        if r.status_code == 200:
            try:
                out = r.json()
                speed_up()
                return out
            except ValueError:
                log(f"  bad json from {url} -> sleep {delay:.0f}s")
                time.sleep(delay)
                delay = min(delay * 2, 120)
                continue
        if r.status_code == 404:
            return NOT_FOUND if allow_404 else None
        if r.status_code == 429:
            slow_down("HTTP 429")
            wait = max(delay, 30) + random.uniform(0, 5)
            log(f"  HTTP 429 on {url} -> cooldown {wait:.0f}s")
            time.sleep(wait)
            delay = min(max(delay, 30) * 2, 300)
            continue
        if r.status_code in (500, 502, 503, 504):
            wait = delay + random.uniform(0, 1)
            log(f"  HTTP {r.status_code} on {url} -> backoff {wait:.0f}s")
            time.sleep(wait)
            delay = min(delay * 2, 120)
            continue
        log(f"  HTTP {r.status_code} on {url} -> giving up on this request")
        return None
    log(f"  exhausted retries on {url}")
    return None


def write_gz(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh)
    os.replace(tmp, path)


def read_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def seasons_for(comp):
    """Season list for a competition, cached."""
    path = os.path.join(RAW, "seasons", f"{comp}.json.gz")
    if os.path.exists(path):
        d = read_gz(path)
    else:
        d = get_json(f"{BASE}/competitions/{comp}/seasons", {"limit": 500})
        if d is None:
            return []
        write_gz(path, d)
    return d.get("data", [])


def games_for(comp, season_code):
    """Game list for one season, cached."""
    path = os.path.join(RAW, "games", comp, f"{season_code}.json.gz")
    if os.path.exists(path):
        d = read_gz(path)
    else:
        out, offset = [], 0
        total = None
        while True:
            d = get_json(f"{BASE}/competitions/{comp}/seasons/{season_code}/games",
                         {"limit": 500, "offset": offset}, allow_404=True)
            if d is None:
                break
            chunk = d.get("data", [])
            total = d.get("total", len(chunk))
            out.extend(chunk)
            offset += len(chunk)
            if not chunk or offset >= (total or 0):
                break
        d = {"total": total if total is not None else len(out), "data": out}
        write_gz(path, d)
    return d.get("data", [])


def pull_season(comp, season_code):
    done_marker = os.path.join(RAW, "done", f"{comp}_{season_code}.done")
    if os.path.exists(done_marker):
        return None
    games = games_for(comp, season_code)
    played = [g for g in games if g.get("played")]
    n_new = n_404 = n_fail = 0
    for g in played:
        gc = g.get("gameCode")
        if gc is None:
            continue
        path = os.path.join(RAW, "stats", comp, season_code, f"{gc}.json.gz")
        if os.path.exists(path):
            continue
        d = get_json(
            f"{BASE}/competitions/{comp}/seasons/{season_code}/games/{gc}/stats",
            allow_404=True)
        if d is NOT_FOUND:
            # genuine 404: cache the miss so a resume does not re-ask
            write_gz(path, {"_missing": True})
            n_404 += 1
            continue
        if d is None:
            # transient failure: leave uncached so a later run retries it
            n_fail += 1
            continue
        write_gz(path, d)
        n_new += 1
    if n_fail:
        log(f"  {comp} {season_code}: {n_fail} games failed transiently, "
            f"season NOT marked done (rerun to finish)")
        return len(games), len(played), n_new, n_404, n_fail
    os.makedirs(os.path.dirname(done_marker), exist_ok=True)
    with open(done_marker, "w") as fh:
        fh.write(json.dumps({"games": len(games), "played": len(played),
                             "fetched_now": n_new, "missing404": n_404,
                             "ts": datetime.now().isoformat()}))
    return len(games), len(played), n_new, n_404, 0


def count_mode(comps):
    """Cache all season game-listings and report the exact number of box
    scores the full pull will need."""
    grand_g = grand_p = grand_have = 0
    for comp in comps:
        ss = sorted(seasons_for(comp), key=lambda s: (s.get("year") or 0, s["code"]))
        cg = cp = ch = 0
        for s_ in ss:
            games = games_for(comp, s_["code"])
            played = [g for g in games if g.get("played")]
            have = len(os.listdir(os.path.join(RAW, "stats", comp, s_["code"])))\
                if os.path.isdir(os.path.join(RAW, "stats", comp, s_["code"])) else 0
            cg += len(games); cp += len(played); ch += have
        log(f"COUNT {comp}: seasons={len(ss)} games={cg} played={cp} cached={ch} "
            f"todo={cp - ch}")
        grand_g += cg; grand_p += cp; grand_have += ch
    log(f"COUNT TOTAL: games={grand_g} played={grand_p} cached={grand_have} "
        f"todo={grand_p - grand_have} "
        f"est_hours={(grand_p - grand_have) * SLEEP_MIN / 3600:.1f}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    only = args or COMPS
    if "--count" in sys.argv:
        count_mode(only)
        return
    log(f"=== pull start (competitions: {','.join(only)}) ===")
    plan = []
    for comp in only:
        ss = seasons_for(comp)
        # oldest first so partial runs cover the historically useful years
        ss = sorted(ss, key=lambda s: (s.get("year") or 0, s.get("code") or ""))
        log(f"competition {comp}: {len(ss)} seasons "
            f"({ss[0]['code'] if ss else '-'} .. {ss[-1]['code'] if ss else '-'})")
        for s in ss:
            plan.append((comp, s["code"]))
    log(f"total seasons to walk: {len(plan)}")

    t0 = time.time()
    for i, (comp, code) in enumerate(plan, 1):
        res = pull_season(comp, code)
        if res is None:
            log(f"[{i}/{len(plan)}] {comp} {code}: already done, skipped")
        else:
            g, p, n, m, f = res
            log(f"[{i}/{len(plan)}] {comp} {code}: games={g} played={p} "
                f"fetched={n} miss404={m} failed={f} "
                f"rate={STATE['sleep']:.2f}s elapsed={time.time()-t0:.0f}s")
    log("=== pull complete ===")


if __name__ == "__main__":
    main()

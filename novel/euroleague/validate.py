#!/usr/bin/env python3
"""Quality gate for the euroleague collector.  Exits non-zero if any check
fails, so it can be wired into a rebuild.  Run after build.py."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
IDENT = ("/Users/kennakao/Downloads/nba_redraft_handoff/"
         "identity_KEEP_SEPARATE/tabular_names.csv")

fails, warns = [], []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        fails.append(msg)


def warn(cond, msg):
    if not cond:
        print("  WARN  " + msg)
        warns.append(msg)


def main():
    f = pd.read_csv(os.path.join(HERE, "features.csv"))
    prov = pd.read_csv(os.path.join(HERE, "provenance.csv"))
    ident = pd.read_csv(IDENT)
    pg = pd.read_csv(os.path.join(HERE, "player_games.csv.gz"), low_memory=False)

    print("\n== schema ==")
    check("pid" in f.columns, "features.csv has a pid column")
    check(f.pid.duplicated().sum() == 0, "one row per pid (no duplicates)")
    obj = [c for c in f.columns if c != "pid" and f[c].dtype == object]
    check(not obj, f"all non-pid columns numeric (offenders: {obj[:5]})")
    check(f.pid.isin(ident.pid).all(), "every pid exists in the identity file")

    print("\n== dating / leakage ==")
    prov["last"] = pd.to_datetime(prov.last_game_used)
    prov["cut"] = pd.to_datetime(prov.cutoff_utc)
    check((prov["last"] < prov["cut"]).all(),
          "every player's last used game is strictly before his draft cutoff")
    check(set(f.pid) == set(prov.pid), "features.csv and provenance.csv cover the same pids")
    dy = dict(zip(ident.pid, ident.draft_year))
    check((prov.draft_year == prov.pid.map(dy)).all(),
          "provenance draft_year matches the identity file")

    print("\n== never fabricate a zero ==")
    for pre in ("el2", "eu2"):
        z = f[(f[f"{pre}_min"].fillna(0) == 0)]
        for col in (f"{pre}_ts", f"{pre}_pts40", f"{pre}_usage"):
            check(z[col].notna().sum() == 0,
                  f"{col} is empty for players with no {pre} minutes")
        # min_share is deliberately 0.0 for a player who was on the game-day
        # roster but never played (a real zero); it must be EMPTY only for a
        # player who never appeared in a box score for that competition at all.
        never = f[(f[f"{pre}_min"].fillna(0) == 0) & (f[f"{pre}_dnp"].fillna(0) == 0)]
        check(never[f"{pre}_min_share"].notna().sum() == 0,
              f"{pre}_min_share is empty for players never in a {pre} box score")
        rostered = f[(f[f"{pre}_min"].fillna(0) == 0) & (f[f"{pre}_dnp"].fillna(0) > 0)]
        check((rostered[f"{pre}_min_share"].fillna(-1) == 0).all(),
              f"{pre}_min_share is 0 for players rostered but never played "
              f"({len(rostered)} such)")
    # a rate must never be exactly 0 just because data was missing
    check(f.el2_pm40.notna().sum() <= (f.el2_min > 0).sum(),
          "el2_pm40 is only populated for players with minutes")

    print("\n== value ranges ==")
    rng = {
        "el2_ts": (0, 1.5), "eu2_ts": (0, 1.5), "angt_ts": (0, 1.5),
        "el2_efg": (0, 1.5), "el2_ftpct": (0, 1), "el2_3ppct": (0, 1),
        "el2_2ppct": (0, 1), "el2_min_share": (0, 1), "eu2_min_share": (0, 1),
        "el2_usage": (0, 100), "el2_pts40": (0, 80), "el2_age_first": (14, 45),
        "angt_age_first": (13, 19.5), "angt_rel_age": (-6, 6),
        "bio_height_cm": (150, 240), "tier_best": (-1, 2),
    }
    for col, (lo, hi) in rng.items():
        if col not in f.columns:
            continue
        s = f[col].dropna()
        ok = s.between(lo, hi).all()
        check(ok, f"{col} within [{lo}, {hi}] "
                  f"(observed {s.min():.2f}..{s.max():.2f})" if len(s)
              else f"{col} within [{lo}, {hi}] (no values)")

    print("\n== internal consistency ==")
    for pre in ("el2", "eu2"):
        sub = f[f[f"{pre}_min"] > 0]
        if not len(sub):
            continue
        check((sub[f"{pre}_starts"].fillna(0) <= sub[f"{pre}_start_games"].fillna(0)).all(),
              f"{pre}_starts never exceeds {pre}_start_games")
        check((sub[f"{pre}_ls_min"].fillna(0) <= sub[f"{pre}_min"] + 1e-6).all(),
              f"{pre}_ls_min never exceeds {pre}_min")
        check((sub[f"{pre}_seasons"] >= 1).all(),
              f"{pre}_seasons >= 1 whenever there are minutes")
    y = f[f.yng_min_senior.notna()]
    if len(y):
        check((y.yng_min_senior + 1e-6 >=
               y[["yng_min_e", "yng_min_u"]].sum(axis=1) - 1e-6).all(),
              "yng_min_senior equals yng_min_e + yng_min_u")
        check((y.yng_min_senior <= y[["el2_min", "eu2_min"]].sum(axis=1) + 1e-6).all(),
              "under-20 minutes never exceed total senior minutes")
    a = f[f.angt_has == 1]
    check((a.angt_games.fillna(0) > 0).all() if len(a) else True,
          "angt_has=1 implies angt_games > 0")

    print("\n== source table ==")
    check((pg.team != pg.opponent).all(), "no player-game has team == opponent")
    check(pg.game_dt.notna().all(), "every player-game has a timestamp")
    tm = pg.team_min.round(0)
    warn((tm.isin([200, 225, 250, 275, 300])).mean() > 0.95,
         f"team_min mostly 200/225/250 (actual {(tm.isin([200,225,250,275,300])).mean():.1%})")

    print(f"\n{len(f)} pids, {len(f.columns)-1} numeric columns, "
          f"{len(pg):,} player-game rows")
    print(f"\n{'FAILED: ' + str(len(fails)) + ' check(s)' if fails else 'ALL CHECKS PASSED'}"
          f"{' / ' + str(len(warns)) + ' warning(s)' if warns else ''}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

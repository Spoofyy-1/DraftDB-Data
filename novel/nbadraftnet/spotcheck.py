#!/usr/bin/env python3
"""Spot check: name, capture date, layout and Overall grade for a spread of players (names stay local)."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_nbadraftnet as M  # noqa: E402

HERE = Path(__file__).resolve().parent
pool = M.roster()
feat = pd.read_csv(HERE / "features.csv")
st = pd.read_csv(HERE / "status.csv")
comps = pd.read_csv(HERE / "comps.csv") if (HERE / "comps.csv").exists() else pd.DataFrame(columns=["pid", "comp_name"])
d = pool.merge(feat, on="pid").merge(st[["pid", "capture_ts", "layout", "status"]], on="pid") \
        .merge(comps[["pid", "comp_name"]], on="pid", how="left")

names = sys.argv[1:] or ["Kevin Durant", "Derrick Rose", "Stephen Curry", "Blake Griffin", "Anthony Davis",
                         "Giannis Antetokounmpo", "Karl-Anthony Towns", "Ben Simmons", "Luka Doncic",
                         "Zion Williamson", "Victor Wembanyama", "Cooper Flagg"]
print(f"{'player':24s} {'yr':>4s} {'capture':>10s} {'d-1':>5s} {'layout':10s} {'ovr':>5s} {'ath':>4s} {'int':>4s} {'lead':>4s} "
      f"{'I+L':>4s} {'quick':>5s} {'def':>4s}  comp")
for nm in names:
    r = d[d.player_name == nm]
    if r.empty:
        print(f"{nm:24s}  -- not in identity file / no row")
        continue
    r = r.sort_values("draft_year").iloc[-1]
    ts = str(r.capture_ts)
    cap = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 and ts != "nan" else "-"
    fmt = lambda v: ("-" if pd.isna(v) else f"{v:.0f}")  # noqa: E731
    print(f"{nm:24s} {int(r.draft_year):4d} {cap:>10s} {fmt(r.sc_capture_days_before_draft):>5s} {str(r.layout):10s} "
          f"{fmt(r.sc_overall):>5s} {fmt(r.sc_athleticism):>4s} {fmt(r.sc_intangibles):>4s} {fmt(r.sc_leadership):>4s} "
          f"{('-' if pd.isna(r.sc_intang_lead) else f'{r.sc_intang_lead:.1f}'):>4s} {fmt(r.sc_quickness):>5s} "
          f"{fmt(r.sc_defense):>4s}  {'' if pd.isna(r.comp_name) else r.comp_name}")

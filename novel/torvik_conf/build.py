#!/usr/bin/env python3
"""Conference-play versus full-season feature block for the NBA redraft model.

For every drafted prospect matched by the sibling collector ../torvik_context, this takes his FINAL
PRE-DRAFT Torvik season F and emits, for that season, the conference-only statistical line and the
delta (conference minus full season) for every rate and per-game stat of interest.

Sources, both the same endpoint with one parameter changed, both cached and gzipped under raw/:
  full season      https://barttorvik.com/getadvstats.php?year=YYYY&csv=1
                   -- reused from ../torvik_context/raw/adv_YYYY.csv.gz, never re-downloaded
  conference only  https://barttorvik.com/getadvstats.php?year=YYYY&conyes=1&csv=1
                   -- raw/advconf_YYYY.csv.gz, fetched by fetch_raw.py

The 67-column mapping and the pid -> Torvik-player matching are imported from ../torvik_context/build.py
so the pid mapping here is identical to that collector's by construction.

Leakage: season F ends in March (conference play ends before the conference tournaments), the draft
is in June, so every column is knowable on draft night.  Torvik's post-draft `pick` column is dropped
from both feeds at load and read nowhere.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
CTX = os.path.join(os.path.dirname(HERE), "torvik_context")
CTX_RAW = os.path.join(CTX, "raw")
IDENT = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"
SEASONS = list(range(2008, 2027))

def _sibling():
    """Import ../torvik_context/build.py (column mapping + pid matching) under its own name.

    Loaded by path, not by `import build`, because this file is also called build.py.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("torvik_context_build", os.path.join(CTX, "build.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


B = _sibling()


# ------------------------------------------------------------------ gz-transparent reads
@contextlib.contextmanager
def gz_transparent():
    """Let ../torvik_context/build.py read its own cache after it was gzipped.

    That collector's loaders ask for `adv_YYYY.csv`; the cache on this disk holds only
    `adv_YYYY.csv.gz` (<1 GB free).  Redirect `.csv` -> `.csv.gz` when, and only when, the plain
    file is absent, so its code is reused verbatim and nothing is decompressed to disk.
    """
    real_exists, real_read = os.path.exists, pd.read_csv

    def ex(p):
        return real_exists(p) or (isinstance(p, str) and p.endswith(".csv") and real_exists(p + ".gz"))

    def rd(p, *a, **k):
        if isinstance(p, str) and p.endswith(".csv") and not real_exists(p) and real_exists(p + ".gz"):
            p = p + ".gz"
        return real_read(p, *a, **k)

    os.path.exists, pd.read_csv = ex, rd
    try:
        yield
    finally:
        os.path.exists, pd.read_csv = real_exists, real_read


# ------------------------------------------------------------------ stats carried through
# (output suffix, column in the 67-column export).  `tpar` is derived below.
STATS = [
    ("usg",     "usg"),        # usage rate
    ("ortg",    "ORtg"),       # offensive rating
    ("adjoe",   "adjoe"),      # adjusted offensive rating
    ("drtg",    "drtg"),       # defensive rating
    ("adrtg",   "adrtg"),      # adjusted defensive rating
    ("bpm",     "bpm"),
    ("obpm",    "obpm"),
    ("dbpm",    "dbpm"),
    ("ts",      "TS_per"),
    ("efg",     "eFG"),
    ("ast_per", "AST_per"),
    ("tov_per", "TO_per"),
    ("orb_per", "ORB_per"),
    ("drb_per", "DRB_per"),
    ("stl_per", "stl_per"),
    ("blk_per", "blk_per"),
    ("ftr",     "ftr"),        # free-throw rate, FTA/FGA x100
    ("tp3_pct", "TP_per"),     # 3P%
    ("tpar",    "tpar"),       # 3PA rate = 3PA / FGA  (derived)
    ("tpa100",  "tpa_per100"), # 3PA per 100 team possessions
    ("porpag",  "porpag"),     # PORPAGATU
    ("minper",  "Min_per"),    # share of team minutes played
    ("pts_pg",  "pts"),
    ("reb_pg",  "treb"),
    ("ast_pg",  "ast"),
]
TEXT = {"player_name", "team", "conf", "yr", "ht", "hometown", "role", "birthdate"}


def derive(d: pd.DataFrame) -> pd.DataFrame:
    """Numeric coercion + the derived columns, applied identically to both feeds."""
    for c in d.columns:
        if c not in TEXT:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    fga = d.TPA + d.twoPA
    d["minutes"] = d.mpg * d.GP
    d["tpar"] = np.where(fga > 0, d.TPA / fga.replace(0, np.nan), np.nan)
    # a percentage on zero attempts is unknown, not zero (COLLECTOR_RULES rule 1)
    d.loc[d.TPA == 0, "TP_per"] = np.nan
    for c in ("eFG", "TS_per", "ftr", "ORtg"):
        d.loc[fga == 0, c] = np.nan
    return d


def load_conf() -> pd.DataFrame:
    """The conference-only export for every cached season, with the year assertion the brief asks for."""
    frames = []
    for y in SEASONS:
        p = os.path.join(RAW, f"advconf_{y}.csv.gz")
        if not os.path.exists(p):
            print(f"  MISSING {os.path.basename(p)} -- run fetch_raw.py", flush=True)
            continue
        d = pd.read_csv(p, header=None, names=B.ADV_COLS, low_memory=False)
        yr = pd.to_numeric(d.year, errors="coerce")
        # the endpoint silently serves the CURRENT season for year < 2008; assert we got what we asked for
        assert (yr == y).all(), f"advconf_{y}: year column holds {sorted(yr.dropna().unique())[:5]}"
        assert (d.hometown.astype(str) == "conf").all(), f"advconf_{y}: missing the conf-mode marker"
        frames.append(d)
    t = pd.concat(frames, ignore_index=True).drop(columns=B.DROP_LEAK)   # `pick` is post-draft leakage
    t = derive(t)
    t["year"] = t.year.astype(int)
    t["tpid"] = t.tpid.astype("Int64")
    assert not t.duplicated(["tpid", "year"]).any(), "conference feed is not unique per player-season"
    return t


# ------------------------------------------------------------------ verification of conyes=1
def verify_conyes(cf: pd.DataFrame, ff: pd.DataFrame) -> pd.DataFrame:
    """The brief's test: GP and minutes must drop, the year column must equal the requested year.

    Plus an independent cross-check the brief does not ask for: each team's maximum conference GP is
    compared with the number of games that team's rows in the SEPARATE getgamestats.php feed carry
    with gtype == 1 (conference regular season) and gtype in {1,2} (adding the conference tournament).
    """
    with gz_transparent():
        g = B.load_games()
    g1 = g[g.gtype == 1].groupby(["team", "year"]).size().rename("g_reg")
    g12 = g[g.gtype.isin([1, 2])].groupby(["team", "year"]).size().rename("g_regtourn")

    rows = []
    for y in sorted(cf.year.unique()):
        c, f = cf[cf.year == y], ff[ff.year == y]
        j = c.merge(f, on="tpid", suffixes=("_c", "_f"))
        tm = (c.groupby("team").GP.max().rename("gp_max").to_frame()
              .join(g1.xs(y, level="year"), how="inner").join(g12.xs(y, level="year")))
        rows.append(dict(
            year=y, rows_conf=len(c), rows_full=len(f), joined=len(j),
            year_col_ok=int((c.year == y).all()),
            gp_le=(j.GP_c <= j.GP_f).mean(), gp_lt=(j.GP_c < j.GP_f).mean(),
            min_le=(j.minutes_c <= j.minutes_f + 1e-6).mean(), min_lt=(j.minutes_c < j.minutes_f).mean(),
            gp_ratio=j.GP_c.sum() / j.GP_f.sum(), min_ratio=j.minutes_c.sum() / j.minutes_f.sum(),
            teams=len(tm), match_gtype1=(tm.gp_max == tm.g_reg).mean(),
            match_gtype12=(tm.gp_max == tm.g_regtourn).mean(),
        ))
    v = pd.DataFrame(rows)
    print("\n=== verification that conyes=1 really restricts the export to conference games ===")
    print(f"{'yr':>5} {'conf':>6} {'full':>6} {'yrOK':>5} {'GP<=':>7} {'GP<':>7} {'min<=':>7} {'min<':>7}"
          f" {'GPratio':>8} {'minRatio':>9} {'tm':>4} {'=gtype1':>8} {'=gtype1+2':>10}")
    for r in v.itertuples():
        print(f"{r.year:5d} {r.rows_conf:6d} {r.rows_full:6d} {r.year_col_ok:5d} {r.gp_le:7.3%} {r.gp_lt:7.3%}"
              f" {r.min_le:7.3%} {r.min_lt:7.3%} {r.gp_ratio:8.3f} {r.min_ratio:9.3f} {r.teams:4d}"
              f" {r.match_gtype1:8.1%} {r.match_gtype12:10.1%}")
    # Thresholds allow for season 2021: COVID wiped out most non-conference scheduling, so 8% of
    # players genuinely played the same number of games in both feeds (its GP ratio is 0.683 against
    # the 0.52-0.59 of every other season -- itself a confirmation that the parameter does what it says).
    assert v.year_col_ok.all(), "a cached conference file carries the wrong season"
    assert (v.gp_le > 0.995).all() and (v.gp_lt > 0.90).all(), "GP does not drop under conyes=1"
    assert (v.min_le > 0.98).all() and (v.min_lt > 0.94).all(), "minutes do not drop under conyes=1"
    assert (v.gp_ratio < 0.75).all(), "conference GP is not a strict subset of the season"
    assert (v.match_gtype1 > 0.98).all(), "conference GP disagrees with the game feed's gtype 1 count"
    assert (v.match_gtype1 - v.match_gtype12 > 0.5).all(), "conference tournament games look included"
    print("PASS: every season's year column equals the requested year; GP and minutes drop (aggregate\n"
          "      GP ratio 0.52-0.69, never above 0.75); and each team's max conference GP equals its\n"
          "      gtype==1 (conference regular season) game count in the independent getgamestats.php\n"
          "      feed, not its gtype in {1,2} count -- conference tournaments are NOT included.")
    return v


# ------------------------------------------------------------------ provenance
def write_provenance() -> None:
    """fetch_raw.py logs the conference pulls; add the reused full-season files.  Idempotent."""
    cols = ["file", "url", "season", "kind", "bytes_uncompressed", "bytes_gz", "rows",
            "sha256_uncompressed", "fetched_utc", "robots_allowed", "crawl_delay_s", "user_agent"]
    p = os.path.join(HERE, "provenance.csv")
    have = pd.read_csv(p) if os.path.exists(p) else pd.DataFrame(columns=cols)
    have = have[have.file.astype(str).str.startswith("raw/")]
    import datetime as dt
    import gzip
    add = []
    for y in SEASONS:
        f = os.path.join(CTX_RAW, f"adv_{y}.csv.gz")
        if not os.path.exists(f):
            continue
        body = gzip.open(f, "rb").read()
        add.append(dict(
            file=f"../torvik_context/raw/adv_{y}.csv.gz",
            url=f"https://barttorvik.com/getadvstats.php?year={y}&csv=1", season=y,
            kind="player_season_full_season (REUSED from ../torvik_context, not re-downloaded)",
            bytes_uncompressed=len(body), bytes_gz=os.path.getsize(f), rows=body.count(b"\n"),
            sha256_uncompressed=hashlib.sha256(body).hexdigest(),
            fetched_utc=dt.datetime.utcfromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            robots_allowed="yes (only db/box/results/playerstat/teamcast/time-machine/*.json are disallowed)",
            crawl_delay_s=10, user_agent="DraftDB-research/1.0 (contact: mike@alphax.inc) non-commercial NBA draft research"))
    out = pd.concat([have, pd.DataFrame(add, columns=cols)], ignore_index=True)
    out.drop_duplicates("file", keep="last").sort_values(["kind", "season"]).to_csv(p, index=False)
    print(f"\nprovenance.csv: {len(out)} cached files "
          f"({(~out.file.str.startswith('raw/')).sum()} reused full-season, "
          f"{out.file.str.startswith('raw/').sum()} conference-only)")


# ------------------------------------------------------------------ build
def main() -> None:
    with gz_transparent():
        ff = B.load_players()                        # full season, identical parse to torvik_context
        p = B.load_prospects()
        m, u, _ = B.match(p, ff)                     # identical pid -> (tpid, F) mapping
    ff = derive(ff)
    cf = load_conf()
    print(f"loaded  full-season {len(ff):,} player-seasons, conference-only {len(cf):,} "
          f"({cf.year.min()}-{cf.year.max()})")
    assert not ff.duplicated(["tpid", "year"]).any(), "full feed is not unique per player-season"
    print(f"matched {len(m):,} prospects (from ../torvik_context/build.py), unmatched {len(u):,}")
    assert (m.F <= m.draft_year).all(), "final season after the draft"

    keep = ["tpid", "year", "GP", "minutes"] + [c for _, c in STATS]
    F = m.merge(ff[keep].rename(columns={"year": "F"}), on=["tpid", "F"], how="left", validate="m:1")
    C = m[["pid", "tpid", "F"]].merge(cf[keep].rename(columns={"year": "F"}), on=["tpid", "F"],
                                      how="left", validate="m:1")
    assert (F.pid.values == C.pid.values).all()
    got = C.GP.notna() & (C.GP > 0)
    print(f"conference line found for {got.sum():,} of {len(m):,} matched prospects "
          f"({got.mean():.1%}); {(~got).sum()} have none")

    out = pd.DataFrame({"pid": m.pid.values, "tcf_season_final": m.F.values})
    out["tcf_conf_gp"] = C.GP.where(got).values
    out["tcf_conf_gp_share"] = (C.GP.where(got) / F.GP.replace(0, np.nan)).values
    for name, col in STATS:
        c = C[col].where(got)
        out[f"tcf_{name}"] = c.values
        out[f"tcf_d_{name}"] = (c - F[col]).values

    feats = [c for c in out.columns if c != "pid"]
    assert all(c.startswith("tcf_") for c in feats)
    out = out.replace([np.inf, -np.inf], np.nan).drop_duplicates("pid").reset_index(drop=True)
    for c in feats:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out.to_csv(os.path.join(HERE, "features.csv"), index=False, float_format="%.6g")

    v = verify_conyes(cf, ff)
    v.to_csv(os.path.join(HERE, "verify_conyes.csv"), index=False)
    write_provenance()

    # ---- coverage
    print(f"\nfeatures.csv: {len(out):,} rows x {len(feats)} tcf_ columns")
    ident = pd.read_csv(IDENT)
    dy = out[["pid"]].merge(m[["pid", "draft_year"]], on="pid")
    print(f"\n{'band':10s} {'drafted':>8s} {'rows':>7s} {'rate':>7s} {'w/ conf line':>13s} {'mean cell fill':>15s}")
    for nm, a, b in [("2000-07", 2000, 2007), ("2008-18", 2008, 2018), ("2019-25", 2019, 2025), ("2026", 2026, 2026)]:
        tot = int(((ident.draft_year >= a) & (ident.draft_year <= b)).sum())
        sel = out[out.pid.isin(dy[(dy.draft_year >= a) & (dy.draft_year <= b)].pid)]
        wc = int(sel.tcf_conf_gp.notna().sum())
        fill = sel[feats].notna().mean().mean() if len(sel) else float("nan")
        print(f"{nm:10s} {tot:8d} {len(sel):7d} {len(sel)/max(tot,1):7.1%} {wc:13d} {fill:15.1%}")

    print("\nper-draft-year (rows / prospects, with conference line):")
    for y in sorted(dy.draft_year.unique()):
        sel = out[out.pid.isin(dy[dy.draft_year == y].pid)]
        tot = int((ident.draft_year == y).sum())
        print(f"  {y}: {len(sel):4d}/{tot:4d}  conf line {sel.tcf_conf_gp.notna().sum():4d}", end="")
        print("" if y % 4 else "")
    print()
    print("\n10 lowest-coverage columns:")
    for k, val in out[feats].notna().mean().sort_values().head(10).items():
        print(f"  {k:24s} {val:6.1%}")

    # ---- distribution sanity: deltas should centre near zero and be wider for small samples
    print("\ndelta distributions (conference minus full season):")
    print(f"  {'column':22s} {'n':>5s} {'mean':>8s} {'sd':>7s} {'p10':>7s} {'p90':>7s}")
    for name, _ in STATS:
        s = out[f"tcf_d_{name}"].dropna()
        print(f"  tcf_d_{name:16s} {len(s):5d} {s.mean():8.3f} {s.std():7.3f} "
              f"{s.quantile(.10):7.2f} {s.quantile(.90):7.2f}")
    print(f"\nconference GP: median {out.tcf_conf_gp.median():.0f}, "
          f"share of season games median {out.tcf_conf_gp_share.median():.3f}")

    # ---- spot check, printed only (names never touch disk).  Rule: for each of the six draft years
    # 2019-2024, the matched prospect with the SMALLEST actual pick that has both deltas.
    nm = pd.read_csv(IDENT)[["pid", "player_name", "draft_year", "actual_pick"]]
    sc = out.merge(m[["pid", "draft_year", "actual_pick"]], on="pid").merge(nm[["pid", "player_name"]], on="pid")
    sc = sc[sc.tcf_d_usg.notna() & sc.tcf_d_bpm.notna() & sc.actual_pick.notna()]
    print("\n=== spot check: lowest matched pick of each draft year 2019-2024 ===")
    print(f"{'yr':>4} {'pk':>3} {'player':22s} {'season':>6} {'confGP':>6} {'usg':>6} {'d_usg':>7} {'bpm':>6} {'d_bpm':>7}")
    for y in range(2019, 2025):
        s = sc[sc.draft_year == y].nsmallest(1, "actual_pick")
        for r in s.itertuples():
            print(f"{y:4d} {int(r.actual_pick):3d} {r.player_name[:22]:22s} {int(r.tcf_season_final):6d} "
                  f"{r.tcf_conf_gp:6.0f} {r.tcf_usg:6.1f} {r.tcf_d_usg:+7.2f} {r.tcf_bpm:6.2f} {r.tcf_d_bpm:+7.2f}")


if __name__ == "__main__":
    main()

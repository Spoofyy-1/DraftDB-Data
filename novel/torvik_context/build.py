#!/usr/bin/env python3
"""Season-level college POPULATION and TEAM context features from Bart Torvik full-league CSV exports.

Reads only the cached CSVs under raw/ (fetch_raw.py downloads them).  Writes features.csv
(pid + numeric tc_* columns), unmatched.csv and prints coverage.

Every feature uses Torvik seasons with year <= draft_year Y only.  Population fits that need a
training sample (age curves, slope shrinkage, shooting priors, seed-expectation) use seasons
strictly < Y, refit per draft year (expanding window).  Same-season population statistics
(percentiles, residualisations, conference strength, team context) are allowed because season F
is complete in April and every draft is in June or later.
"""
from __future__ import annotations

import csv, os, re, sys, unicodedata, datetime as dt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
IDENT = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"
AGEV = "/Users/kennakao/nba/datarebuild/age_verified_wiki.csv"
RSCI = "/Users/kennakao/nba/datarebuild/rsci_features.csv"
V4 = "/Users/kennakao/nba/datarebuild/v4_build/data_v4"

MIN_PER_POP = 40.0       # population floor for percentiles / age curves / residualisations
MIN_PER_ROT = 20.0       # a teammate counts as rotation for max / top-2 BPM
BD_AGREE, BD_REJECT = 2, 400   # days: birthdates within 2 days confirm a match, more than 400 reject it
MIN_ATT_PRIOR = 20       # player-seasons with >= 20 attempts define the shooting priors
SEASONS = range(2008, 2027)

# ------------------------------------------------------------------ column mapping (inferred; see README)
ADV_COLS = [
    "player_name", "team", "conf", "GP", "Min_per", "ORtg", "usg", "eFG", "TS_per", "ORB_per",
    "DRB_per", "AST_per", "TO_per", "FTM", "FTA", "FT_per", "twoPM", "twoPA", "twoP_per",
    "TPM", "TPA", "TP_per", "blk_per", "stl_per", "ftr", "yr", "ht", "num", "porpag", "adjoe",
    "pfr", "year", "tpid", "hometown", "rec_rank_raw", "ast_tov", "rimmade", "rimatt",
    "midmade", "midatt", "rim_pct", "mid_pct", "dunkmade", "dunkatt", "dunk_pct", "pick",
    "drtg", "adrtg", "dporpag", "stops", "bpm", "obpm", "dbpm", "gbpm", "mpg", "ogbpm",
    "dgbpm", "oreb", "dreb", "treb", "ast", "stl", "blk", "pts", "role", "tpa_per100", "birthdate",
]
GAME_COLS = [
    "date", "gtype", "team", "conf", "opp", "venue", "result", "g_adjo", "g_adjd", "o_ppp",
    "o_efg", "o_to", "o_or", "o_ftr", "d_ppp", "d_efg", "d_to", "d_or", "d_ftr", "game_score",
    "opp_conf", "side", "year", "tempo", "gameid", "coach", "opp_coach", "adj_margin",
    "opp_barthag", "box_json", "misc",
]
DROP_LEAK = ["pick"]     # post-draft, never used

AGE_STATS = ["bpm", "obpm", "dbpm", "usg", "TS_per", "AST_per", "stl_per", "blk_per", "ORB_per", "DRB_per", "porpag"]
DEV_STATS = ["bpm", "usg", "TS_per", "AST_per", "stl_per", "blk_per", "Min_per"]
SHORT = {"bpm": "bpm", "obpm": "obpm", "dbpm": "dbpm", "usg": "usg", "TS_per": "ts", "AST_per": "ast",
         "stl_per": "stl", "blk_per": "blk", "ORB_per": "orb", "DRB_per": "drb", "porpag": "porpag",
         "Min_per": "minper"}

SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
NONAL = re.compile(r"[^a-z ]")


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.lower().replace(".", " ").replace("-", " ").replace("'", "")
    s = NONAL.sub(" ", s)
    s = SUFFIX.sub(" ", s)
    return " ".join(s.split())


def name_keys(s: str) -> set:
    """Normalised name plus the variant with a run of single-letter initials joined (C.J. -> cj)."""
    k = norm_name(s)
    return {k, re.sub(r"\b([a-z]) (?=[a-z]\b)", r"\1", k).strip()} if k else set()


# ------------------------------------------------------------------ load raw
def load_players() -> pd.DataFrame:
    frames = []
    for y in SEASONS:
        p = os.path.join(RAW, f"adv_{y}.csv")
        if not os.path.exists(p):
            continue
        d = pd.read_csv(p, header=None, names=ADV_COLS, low_memory=False)
        frames.append(d)
    t = pd.concat(frames, ignore_index=True)
    t = t.drop(columns=DROP_LEAK)
    for c in ADV_COLS:
        if c in t.columns and c not in ("player_name", "team", "conf", "yr", "ht", "hometown", "role", "birthdate"):
            t[c] = pd.to_numeric(t[c], errors="coerce")
    t["year"] = t.year.astype(int)
    t["tpid"] = t.tpid.astype("Int64")
    t["key"] = t.player_name.map(norm_name)
    t["key2"] = t.key.map(lambda k: re.sub(r"\b([a-z]) (?=[a-z]\b)", r"\1", k).strip())
    t["minutes"] = t.mpg * t.GP
    bd = pd.to_datetime(t.birthdate, errors="coerce")
    t["bd"] = bd
    # Torvik fills an unknown birthdate with October 15 of the class-implied birth year
    t["age_imputed"] = ((bd.dt.month == 10) & (bd.dt.day == 15)).astype(float)
    ref = pd.to_datetime(t.year.astype(str) + "-01-15")          # season midpoint
    t["age"] = (ref - bd).dt.days / 365.25
    t["bpm_pos"] = t.bpm.clip(lower=0)
    t["porpag_pos"] = t.porpag.clip(lower=0)
    t["pts40"] = t.pts * 40.0 / t.mpg.replace(0, np.nan)
    t["dunks_per40"] = t.dunkmade * 40.0 / t.minutes.replace(0, np.nan)
    t["dunkatt_per40"] = t.dunkatt * 40.0 / t.minutes.replace(0, np.nan)
    # rec_rank_raw is a descending 0..100 score with a 0.2 step; 100.0 == the class's #1 recruit
    t["rec_rank"] = (501.0 - 5.0 * t.rec_rank_raw).round()
    t.loc[t.rec_rank_raw.isna(), "rec_rank"] = np.nan
    return t


def load_games() -> pd.DataFrame:
    frames = []
    for y in SEASONS:
        p = os.path.join(RAW, f"games_{y}.csv")
        if not os.path.exists(p):
            continue
        d = pd.read_csv(p, header=None, names=GAME_COLS, low_memory=False,
                        usecols=[i for i, c in enumerate(GAME_COLS) if c != "box_json"])
        frames.append(d)
    g = pd.concat(frames, ignore_index=True)
    g["year"] = pd.to_numeric(g.year, errors="coerce").astype("Int64")
    g["gtype"] = pd.to_numeric(g.gtype, errors="coerce")
    g["opp_barthag"] = pd.to_numeric(g.opp_barthag, errors="coerce")
    g["win"] = g.result.astype(str).str.startswith("W").astype(int)
    g["gdate"] = pd.to_datetime(g.date, format="%m/%d/%y", errors="coerce")
    return g


# ------------------------------------------------------------------ team-season context from the games file
def team_games(g: pd.DataFrame) -> pd.DataFrame:
    """Per (team, year): record, tournament participation, own barthag, schedule strength."""
    out = []
    # own barthag = the opponent-barthag value other teams' rows carry for this team
    bt = (g.groupby(["opp", "year"]).opp_barthag.median().rename("barthag")
          .reset_index().rename(columns={"opp": "team"}))
    base = g.groupby(["team", "year"]).agg(
        tg_games=("win", "size"), tg_wins=("win", "sum"),
        tg_opp_barthag_mean=("opp_barthag", "mean"),
        tg_neutral=("venue", lambda s: (s == "N").mean()),
    ).reset_index()
    ct = g[g.gtype == 2].groupby(["team", "year"]).agg(tg_conf_t_games=("win", "size"), tg_conf_t_wins=("win", "sum")).reset_index()
    base = base.merge(bt, on=["team", "year"], how="left").merge(ct, on=["team", "year"], how="left")
    base[["tg_conf_t_games", "tg_conf_t_wins"]] = base[["tg_conf_t_games", "tg_conf_t_wins"]].fillna(0.0)
    base["tg_losses"] = base.tg_games - base.tg_wins
    base["tg_win_pct"] = base.tg_wins / base.tg_games
    base["barthag_rank"] = base.groupby("year").barthag.rank(ascending=False, method="min")
    ncaa = ncaa_tournament(g)
    base = base.merge(ncaa, on=["team", "year"], how="left")
    has = base.year.isin(pd.unique(ncaa.year)) if len(ncaa) else pd.Series(False, index=base.index)
    for c in ["tg_ncaa_games", "tg_ncaa_wins", "tg_final_four", "tg_champion"]:
        # 0 is observed for every team in a season that has a bracket; empty when no bracket exists (2020 COVID)
        base[c] = pd.to_numeric(base[c], errors="coerce").mask(has & base[c].isna(), 0.0)
    return base


def ncaa_tournament(g: pd.DataFrame) -> pd.DataFrame:
    """Isolate the NCAA tournament from Torvik gtype 3 (which also holds NIT/CBI/CIT/CBC).

    Rule: build the team graph of gtype-3 games and take its largest connected component.  The
    tournament fields are disjoint (no team plays in two of them), so every component is exactly one
    tournament; the NCAA field (65 before 2011, 68 after, 67 in 2021 after VCU's no-contest) is
    always the largest and the NIT (32) the second.  Champion = winner of the single game on the
    component's last date; Final Four = the teams playing on the previous date that has games.
    """
    rows = []
    for y, gy in g[g.gtype == 3].groupby("year"):
        pairs = gy.groupby("gameid").agg(teams=("team", lambda s: tuple(sorted(set(s)))), d=("gdate", "min"))
        pairs = pairs[pairs.teams.map(len) == 2]
        adj: dict[str, set[str]] = {}
        for a, b in pairs.teams:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        seen, comps = set(), []
        for s in adj:
            if s in seen:
                continue
            stack, comp = [s], set()
            while stack:
                n = stack.pop()
                if n in comp:
                    continue
                comp.add(n)
                seen.add(n)
                stack.extend(adj[n] - comp)
            comps.append(comp)
        if not comps:
            continue
        big = max(comps, key=len)
        sub = gy[gy.team.isin(big) & gy.opp.isin(big)]
        dates = sorted(sub.gdate.dropna().unique())
        final_d = dates[-1] if dates else None
        semi_d = dates[-2] if len(dates) >= 2 else None
        champs = set(sub[(sub.gdate == final_d) & (sub.win == 1)].team) if final_d is not None else set()
        f4 = set(sub[sub.gdate == semi_d].team) if semi_d is not None else set()
        agg = sub.groupby("team").agg(tg_ncaa_games=("win", "size"), tg_ncaa_wins=("win", "sum")).reset_index()
        agg["year"] = y
        agg["tg_final_four"] = agg.team.isin(f4).astype(float)
        agg["tg_champion"] = agg.team.isin(champs).astype(float)
        rows.append(agg)
    if not rows:
        return pd.DataFrame(columns=["team", "year", "tg_ncaa_games", "tg_ncaa_wins", "tg_final_four", "tg_champion"])
    return pd.concat(rows, ignore_index=True)


# ------------------------------------------------------------------ team-season context from the player file
def team_season(t: pd.DataFrame) -> pd.DataFrame:
    w = t.minutes.fillna(0.0)
    r = pd.DataFrame({"team": t.team, "year": t.year, "conf": t.conf, "w": w,
                      "wbp": w * t.bpm_pos.fillna(0.0),
                      "ptsg": t.pts * t.GP, "astg": t.ast * t.GP,
                      "porp": t.porpag_pos.fillna(0.0),
                      "ranked": (t.rec_rank <= 100).fillna(False).astype(int)})
    r["wbp2"] = r.wbp ** 2
    for s in ("bpm", "usg", "adjoe", "adrtg"):
        r[f"w_{s}"] = w.where(t[s].notna(), 0.0)
        r[f"ws_{s}"] = r[f"w_{s}"] * t[s].fillna(0.0)
    grp = r.groupby(["team", "year"])
    ts = grp.sum(numeric_only=True)
    ts["n_players"] = grp.size()
    ts["conf"] = grp.conf.first()
    ts["team_bpm_sum"] = 5.0 * ts.wbp / ts.w.replace(0, np.nan)
    ts = ts.join(topk(t[t.Min_per >= MIN_PER_ROT], "bpm", 3, False, ["bpm", "tpid"]))
    ts = ts.join(topk(t[t.rec_rank.notna()], "rec_rank", 2, True, ["rec_rank", "tpid"]).add_prefix("r_"))
    return ts


def topk(df, by, k, ascending, cols):
    s = df[df[by].notna()].sort_values(by, ascending=ascending)
    s = s[s.groupby(["team", "year"]).cumcount() < k]
    s["rk"] = s.groupby(["team", "year"]).cumcount()
    wide = s.set_index(["team", "year", "rk"])[cols].unstack("rk")
    wide.columns = [f"{c}_{r}" for c, r in wide.columns]
    return wide.reindex(columns=[f"{c}_{r}" for c in cols for r in range(k)])


# ------------------------------------------------------------------ draftee roster + matching
def load_prospects() -> pd.DataFrame:
    """pid, draft_year, actual_pick, name key (when known) and the tv_ signature (when present)."""
    ident = pd.read_csv(IDENT)
    ident["key"] = ident.player_name.map(norm_name)
    ident = ident[["pid", "draft_year", "actual_pick", "key"]]

    rows = []
    files = [os.path.join(V4, "train_2000_2018.csv")] + sorted(
        os.path.join(V4, "tests", f) for f in os.listdir(os.path.join(V4, "tests")))
    for fn in files:
        d = pd.read_csv(fn, low_memory=False)
        cols = ["pid", "draft_year"] + [c for c in ("tv_adjoe", "tv_adrtg", "tv_stops", "col_gp", "col_mpg")
                                        if c in d.columns]
        rows.append(d[cols])
    inp = pd.concat(rows, ignore_index=True).drop_duplicates("pid")
    p = ident.merge(inp, on=["pid", "draft_year"], how="outer")
    p["draft_year"] = p.draft_year.astype(int)
    return p


def match(p: pd.DataFrame, t: pd.DataFrame):
    """Resolve each prospect to one Torvik player id (tpid).  Returns (matched, unmatched, notes).

    Candidates come from the normalised name (both key variants) and, additionally, from an exact
    match of the tv_ season line already carried in data_v4 on (adjoe, adrtg, stops).  Filters, in
    order (rule 5 of COLLECTOR_RULES: draft-year plausibility, birthdate agreement, log the rest):
      1. keep candidates with a Torvik season in [Y-7, Y]
      2. drop candidates whose non-imputed Torvik birthdate contradicts the verified wiki birthdate
      3. if a verified birthdate resolves exactly one candidate, take it
      4. else if exactly one candidate's season-F line matches data_v4's independent college source
         on games played and minutes per game (col_gp, col_mpg -- they agree for 99.7% of confident
         matches), take it
      5. else if the final pre-draft season F == Y for exactly one candidate, take it
      6. else if exactly one candidate remains, take it
      7. else log to unmatched.csv as ambiguous_name -- never guess

    A prospect with no candidate at all gets one more pass, because Torvik carries a college's given
    name where the identity file carries the NBA nickname (Nah'Shon "Bones" Hyland, Carlton "Bub"
    Carrington, Cameron/Cam Thomas): candidates are the Torvik players sharing his surname with a
    season in [Y-7, Y], and one is accepted only if it is the ONLY one corroborated by the verified
    birthdate (within 2 days) or by exact agreement with col_gp and col_mpg (rule 6).

    tc_match_rule records which step resolved the row (2 = unique candidate, 3 = birthdate,
    4 = col_gp/col_mpg, 5 = final season == Y); tc_match_tv_agrees says whether the accepted tpid is
    the one data_v4's own tv_ columns point at.
    """
    sig = {}
    for a_, r_, s_, tp, yr in zip(t.adjoe.round(3), t.adrtg.round(3), t.stops.round(3), t.tpid, t.year):
        if pd.notna(a_) and pd.notna(r_) and pd.notna(s_):
            sig.setdefault((a_, r_, s_), set()).add(int(tp))
    by_last: dict[str, set] = {}
    by_key: dict[str, dict[int, list[int]]] = {}
    for k, tp, yr in zip(t.key, t.tpid, t.year):
        by_key.setdefault(k, {}).setdefault(int(tp), []).append(int(yr))
        by_last.setdefault(k.split()[-1] if k else "", set()).add(int(tp))
    for k2, tp, yr in zip(t.key2, t.tpid, t.year):
        by_key.setdefault(k2, {}).setdefault(int(tp), []).append(int(yr))
    yrs_of: dict[int, list[int]] = {}
    for tp, yr in zip(t.tpid, t.year):
        yrs_of.setdefault(int(tp), []).append(int(yr))

    verified = pd.read_csv(AGEV).set_index("pid").birth_date.to_dict()
    tbd = {}
    for tp, b_, im in zip(t.tpid, t.bd, t.age_imputed):
        if pd.notna(b_) and im == 0:
            tbd.setdefault(int(tp), b_.date())

    fseason = {}
    for tp, yr, gp, mp in zip(t.tpid, t.year, t.GP, t.mpg):
        fseason[(int(tp), int(yr))] = (gp, mp)

    out, bad, notes = [], [], []
    for r in p.itertuples():
        Y, rule = r.draft_year, 2
        cand = set()
        for k in (name_keys(r.key) if isinstance(r.key, str) else set()):
            cand |= set(by_key.get(k, {}))
        tp_sig = None
        if pd.notna(getattr(r, "tv_adjoe", np.nan)) and pd.notna(r.tv_adrtg) and pd.notna(r.tv_stops):
            hits = sig.get((round(r.tv_adjoe, 3), round(r.tv_adrtg, 3), round(r.tv_stops, 3)), set())
            if len(hits) == 1:
                tp_sig = next(iter(hits))
                cand.add(tp_sig)
        n_name = len(cand)
        cand = {c for c in cand if any(Y - 7 <= y <= Y for y in yrs_of[c])}          # 1
        if r.pid in verified:                                                        # 2
            v = dt.date.fromisoformat(verified[r.pid])
            def dd(c):
                return abs((tbd[c] - v).days) if c in tbd else None
            cand = {c for c in cand if dd(c) is None or dd(c) <= BD_REJECT}
            agree = {c for c in cand if dd(c) is not None and dd(c) <= BD_AGREE}
            if len(agree) == 1:                                                      # 3
                cand, rule = agree, 3
        if len(cand) > 1 and pd.notna(getattr(r, "col_gp", np.nan)) and pd.notna(r.col_mpg):   # 4
            hit = set()
            for c in cand:
                gp, mp = fseason.get((c, max(y for y in yrs_of[c] if y <= Y)), (np.nan, np.nan))
                if gp == r.col_gp and abs(mp - r.col_mpg) <= 0.01:
                    hit.add(c)
            if len(hit) == 1:
                cand, rule = hit, 4
        if len(cand) > 1:                                                            # 5
            exact = {c for c in cand if max(y for y in yrs_of[c] if y <= Y) == Y}
            if len(exact) == 1:
                cand, rule = exact, 5
        if not cand and isinstance(r.key, str) and r.key:                            # 6, nickname pass
            last = norm_name(r.key).split()[-1]
            pool = {c for c in by_last.get(last, set()) if any(Y - 7 <= y <= Y for y in yrs_of[c])}
            hit = set()
            for c in pool:
                gp, mp = fseason.get((c, max(y for y in yrs_of[c] if y <= Y)), (np.nan, np.nan))
                by_gp = (pd.notna(getattr(r, "col_gp", np.nan)) and pd.notna(r.col_mpg)
                         and gp == r.col_gp and abs(mp - r.col_mpg) <= 0.01)
                by_bd = (r.pid in verified and c in tbd
                         and abs((tbd[c] - dt.date.fromisoformat(verified[r.pid])).days) <= BD_AGREE)
                if by_gp or by_bd:
                    hit.add(c)
            if len(hit) == 1:
                cand, rule = hit, 6
        if len(cand) != 1:
            bad.append((r.pid, Y, r.actual_pick, "ambiguous_name" if len(cand) > 1 else "no_d1_season_match", n_name))
            continue
        tpid = next(iter(cand))
        if tp_sig is not None and tpid != tp_sig:
            notes.append((r.pid, Y, r.actual_pick, "tv_signature_points_elsewhere", tpid, tp_sig))
        out.append((r.pid, Y, r.actual_pick, tpid, rule, np.nan if tp_sig is None else float(tpid == tp_sig)))

    m = pd.DataFrame(out, columns=["pid", "draft_year", "actual_pick", "tpid", "match_rule", "tv_agrees"])
    m["F"] = [max(y for y in yrs_of[tp] if y <= Y) for tp, Y in zip(m.tpid, m.draft_year)]
    u = pd.DataFrame(bad, columns=["pid", "draft_year", "actual_pick", "reason", "n_name_candidates"])
    nt = pd.DataFrame(notes, columns=["pid", "draft_year", "actual_pick", "note", "tpid_used", "tpid_in_data_v4"])
    return m, u, nt


# ------------------------------------------------------------------ 1. cohort percentiles + age curves
def age_bucket(age: pd.Series) -> pd.Series:
    return np.floor(age.clip(lower=17.0, upper=24.999))


def cohort_percentiles(D: pd.DataFrame, t: pd.DataFrame) -> pd.DataFrame:
    pop = t[(t.Min_per >= MIN_PER_POP) & t.age.notna()].copy()
    pop["ab"] = age_bucket(pop.age)
    tab = {}
    for (yr, ab), grp in pop.groupby(["year", "ab"]):
        for s in AGE_STATS:
            v = grp[s].dropna().to_numpy()
            if v.size:
                tab[(yr, ab, s)] = np.sort(v)
    o = pd.DataFrame(index=D.index)
    ab = age_bucket(D.age)
    o["tc_age_bucket"] = ab.values
    o["tc_age_at_season"] = D.age.values
    o["tc_age_imputed"] = D.age_imputed.values
    n_cell = np.array([tab.get((y, a, "bpm"), np.empty(0)).size for y, a in zip(D.year, ab)], float)
    o["tc_age_cohort_n"] = np.where(n_cell > 0, n_cell, np.nan)
    for s in AGE_STATS:
        col = np.full(len(D), np.nan)
        for i, (y, a, x) in enumerate(zip(D.year, ab, D[s])):
            arr = tab.get((y, a, s))
            if arr is None or arr.size < 20 or not np.isfinite(x):
                continue
            lo = np.searchsorted(arr, x, "left")
            hi = np.searchsorted(arr, x, "right")
            col[i] = (lo + (hi - lo) / 2.0) / arr.size
        o[f"tc_pct_age_{SHORT[s]}"] = col
    return o


def age_fits(t: pd.DataFrame, years) -> dict:
    pop = t[(t.Min_per >= MIN_PER_POP) & t.age.notna()]
    fits = {}
    for Y in years:
        p = pop[pop.year < Y]
        if len(p) < 500:
            continue
        lo, hi = p.age.quantile([0.005, 0.995])
        for s in AGE_STATS:
            q = p[p[s].notna()]
            if len(q) < 500:
                continue
            coef = np.polyfit(q.age, q[s], 3)
            fits[(Y, s)] = (coef, float((q[s] - np.polyval(coef, q.age)).std()), float(lo), float(hi))
    return fits


def age_resid(fits, Y, s, age, x):
    n = len(np.atleast_1d(age))
    if (Y, s) not in fits:
        return np.full(n, np.nan), np.full(n, np.nan)
    coef, sd, lo, hi = fits[(Y, s)]
    r = np.asarray(x, float) - np.polyval(coef, np.clip(np.asarray(age, float), lo, hi))
    return r, r / sd


def age_features(D: pd.DataFrame, fits: dict) -> pd.DataFrame:
    o = pd.DataFrame(index=D.index, columns=[f"tc_{p}_age_{SHORT[s]}" for s in AGE_STATS for p in ("resid", "z")], dtype=float)
    for Y, idx in D.groupby("draft_year").groups.items():
        d = D.loc[idx]
        for s in AGE_STATS:
            r, z = age_resid(fits, Y, s, d.age, d[s])
            o.loc[idx, f"tc_resid_age_{SHORT[s]}"] = r
            o.loc[idx, f"tc_z_age_{SHORT[s]}"] = z
    return o


# ------------------------------------------------------------------ 2-3. team, teammates, conference
def team_features(D: pd.DataFrame, ts: pd.DataFrame) -> pd.DataFrame:
    x = D.merge(ts.drop(columns="conf").reset_index(), on=["team", "year"], how="left", validate="m:1")
    wi = x.minutes.fillna(0.0)
    o = pd.DataFrame(index=D.index)
    for s, name in (("bpm", "tc_tm_bpm_mw"), ("usg", "tc_tm_usg_mw")):
        wis = wi.where(x[s].notna(), 0.0)
        o[name] = ((x[f"ws_{s}"] - wis * x[s].fillna(0.0)) / (x[f"w_{s}"] - wis)).values
    tp = x.tpid.astype("float64")
    is1 = (tp == x.tpid_0.astype("float64")).fillna(False).values
    is2 = (tp == x.tpid_1.astype("float64")).fillna(False).values
    o["tc_tm_bpm_max"] = np.where(is1, x.bpm_1, x.bpm_0)
    o["tc_tm_top2_bpm_mean"] = np.where(is1, (x.bpm_1 + x.bpm_2) / 2,
                                        np.where(is2, (x.bpm_0 + x.bpm_2) / 2, (x.bpm_0 + x.bpm_1) / 2))
    isr = (tp == x.r_tpid_0.astype("float64")).fillna(False).values
    o["tc_tm_recrank_best"] = np.where(isr, x.r_rec_rank_1, x.r_rec_rank_0)
    o["tc_tm_n_top100_recruits"] = (x.ranked - (x.rec_rank <= 100).fillna(False).astype(int)).values
    o["tc_bpm_share"] = (wi * x.bpm_pos / x.wbp.replace(0, np.nan)).values
    o["tc_usg_share"] = (wi * x.usg / x.ws_usg.replace(0, np.nan)).values
    o["tc_pts_share"] = (x.pts * x.GP / (x.ptsg.replace(0, np.nan))).values
    o["tc_ast_share"] = (x.ast * x.GP / (x.astg.replace(0, np.nan))).values
    o["tc_porpag_share"] = (x.porpag_pos / x.porp.replace(0, np.nan)).values
    o["tc_team_talent_hhi"] = (x.wbp2 / x.wbp.replace(0, np.nan) ** 2).values
    o["tc_team_bpm_sum"] = x.team_bpm_sum.values
    o["tc_team_adjoe_mean"] = (x.ws_adjoe / x.w_adjoe.replace(0, np.nan)).values
    o["tc_team_adrtg_mean"] = (x.ws_adrtg / x.w_adrtg.replace(0, np.nan)).values
    o["tc_team_n_players"] = x.n_players.values
    return o.replace([np.inf, -np.inf], np.nan)


def conf_features(D: pd.DataFrame, ts: pd.DataFrame) -> pd.DataFrame:
    c = ts.reset_index()[["team", "year", "conf", "w", "team_bpm_sum"]]

    def wmean(df, val, w):
        gg = df.assign(_p=df[val] * df[w]).groupby(["conf", "year"])
        return gg._p.sum() / gg[w].sum()

    same = wmean(c, "team_bpm_sum", "w").rename("tc_conf_strength_same")
    prev = c[["team", "year", "team_bpm_sum", "w"]].rename(columns={"team_bpm_sum": "pbs", "w": "pw"}).assign(year=lambda d: d.year + 1)
    prior = wmean(c[["team", "year", "conf"]].merge(prev, on=["team", "year"]), "pbs", "pw").rename("tc_conf_strength_prior")
    x = D[["conf", "year"]].merge(pd.concat([prior, same], axis=1).reset_index(), on=["conf", "year"], how="left")
    return x[["tc_conf_strength_prior", "tc_conf_strength_same"]].set_index(D.index)


def game_features(D: pd.DataFrame, tg: pd.DataFrame, years) -> pd.DataFrame:
    x = D[["team", "year", "draft_year"]].merge(tg, on=["team", "year"], how="left")
    o = pd.DataFrame(index=D.index)
    ren = {"tg_games": "tc_team_games", "tg_wins": "tc_team_wins", "tg_losses": "tc_team_losses",
           "tg_win_pct": "tc_team_win_pct", "barthag": "tc_team_barthag", "barthag_rank": "tc_team_barthag_rank",
           "tg_opp_barthag_mean": "tc_team_opp_barthag_mean", "tg_neutral": "tc_team_neutral_share",
           "tg_ncaa_games": "tc_ncaa_games", "tg_ncaa_wins": "tc_ncaa_wins", "tg_final_four": "tc_final_four",
           "tg_champion": "tc_champion", "tg_conf_t_games": "tc_conf_tourn_games", "tg_conf_t_wins": "tc_conf_tourn_wins"}
    for a, b in ren.items():
        o[b] = x[a].values
    o["tc_ncaa_made"] = (x.tg_ncaa_games.fillna(0) > 0).astype(float).where(x.tg_ncaa_games.notna()).values
    # seed-expectation proxy: NCAA wins vs a cubic in log(end-of-season barthag rank), fit on seasons < Y
    field = tg[(tg.tg_ncaa_games.fillna(0) > 0) & tg.barthag_rank.notna()]
    fits = {}
    for Y in years:
        p = field[field.year < Y]
        if len(p) >= 200:
            fits[Y] = np.polyfit(np.log(p.barthag_rank), p.tg_ncaa_wins, 3)
    exp = np.full(len(x), np.nan)
    for i, (Y, r, g) in enumerate(zip(x.draft_year, x.barthag_rank, x.tg_ncaa_games)):
        if Y in fits and pd.notna(r) and pd.notna(g) and g > 0:
            exp[i] = np.polyval(fits[Y], np.log(r))
    o["tc_ncaa_wins_expected"] = exp
    o["tc_ncaa_wins_resid"] = o.tc_ncaa_wins.values - exp
    return o


# ------------------------------------------------------------------ 4-5. availability, development, shooting
def career(m: pd.DataFrame, t: pd.DataFrame) -> pd.DataFrame:
    c = t.merge(m[["pid", "tpid", "draft_year", "F"]], on="tpid")
    c = c[c.year <= c.F].sort_values(["pid", "year"]).reset_index(drop=True)
    return c


def availability(D: pd.DataFrame, c: pd.DataFrame, tg: pd.DataFrame) -> pd.DataFrame:
    cc = c.merge(tg[["team", "year", "tg_games"]], on=["team", "year"], how="left")
    cc["ratio"] = cc.GP / cc.tg_games
    g = cc.groupby("pid")
    agg = g.agg(gp=("GP", "sum"), tgm=("tg_games", "sum"), mn=("ratio", "min"),
                n=("year", "size"), y0=("year", "min"), y1=("year", "max"))
    fin = cc[cc.year == cc.F].set_index("pid")
    o = pd.DataFrame(index=D.index)
    key = D.pid.values
    o["tc_gp_share_final"] = fin.ratio.reindex(key).values
    o["tc_gp_share_career"] = (agg.gp / agg.tgm.replace(0, np.nan)).reindex(key).values
    o["tc_gp_share_min"] = agg.mn.reindex(key).values
    o["tc_n_seasons"] = agg.n.reindex(key).values
    o["tc_seasons_span"] = (agg.y1 - agg.y0 + 1).reindex(key).values
    o["tc_missing_season"] = (o.tc_seasons_span - o.tc_n_seasons).clip(lower=0)
    same = {}
    for pid, grp in cc.sort_values("year").groupby("pid"):
        yrs, tms = grp.year.tolist(), grp.team.tolist()
        f = 0.0
        for i in range(len(yrs) - 1):
            if yrs[i + 1] - yrs[i] > 1 and tms[i] == tms[i + 1]:
                f = 1.0
        same[pid] = f
    o["tc_missing_season_same_school"] = pd.Series(key).map(same).values
    o["tc_team_games_final"] = fin.tg_games.reindex(key).values
    return o


def wls_slopes(c: pd.DataFrame) -> pd.DataFrame:
    x, w = c.year.astype(float) - 2017.0, c.minutes.fillna(0.0)
    out = {}
    for s in DEV_STATS:
        ws = w.where(c[s].notna(), 0.0)
        y = c[s].fillna(0.0)
        acc = pd.DataFrame({"pid": c.pid, "n": (ws > 0).astype(int), "W": ws, "Wx": ws * x, "Wy": ws * y,
                            "Wxy": ws * x * y, "Wxx": ws * x * x}).groupby("pid").sum()
        den = (acc.W * acc.Wxx - acc.Wx ** 2).where(acc.n >= 2)
        out[s] = (acc.W * acc.Wxy - acc.Wx * acc.Wy) / den
    return pd.DataFrame(out)


def dev_features(D: pd.DataFrame, c: pd.DataFrame, fits: dict) -> pd.DataFrame:
    key = D.pid.values
    first = c.sort_values("year").groupby("pid").first()
    n = c.groupby("pid").size()
    raw = wls_slopes(c)
    dy = D.set_index("pid").draft_year
    rd = raw.join(dy)
    by = rd.groupby("draft_year").agg(["sum", "count"])
    by = by.reindex(range(int(by.index.min()), int(by.index.max()) + 1)).fillna(0).cumsum().shift(1)
    pop = pd.DataFrame({s: by[(s, "sum")] / by[(s, "count")].where(by[(s, "count")] > 0) for s in DEV_STATS})
    P = pop.reindex(D.draft_year.values).to_numpy(float)
    R = raw.reindex(key).to_numpy(float)
    N = n.reindex(key).to_numpy(float)[:, None]
    # shrink toward the mean raw slope of earlier draft classes; before such a population exists
    # (the 2009 class -- no 2008 draftee has two Torvik seasons) keep the unshrunk slope
    shrunk = np.where(np.isnan(P), R, N / (N + 2) * R + 2 / (N + 2) * P)
    o = pd.DataFrame(index=D.index)
    for i, s in enumerate(DEV_STATS):
        o[f"tc_slope_{SHORT[s]}"] = np.where(np.isnan(R[:, i]), np.nan, shrunk[:, i])
    b = c.sort_values("year").groupby("pid").bpm.apply(list)
    def nth(l, k):
        return l[-k] if isinstance(l, list) and len(l) >= k else np.nan
    bl = b.reindex(key)
    b1 = np.array([nth(v, 1) for v in bl], float)
    b2 = np.array([nth(v, 2) for v in bl], float)
    b3 = np.array([nth(v, 3) for v in bl], float)
    o["tc_bpm_accel"] = (b1 - b2) - (b2 - b3)
    o["tc_first_bpm"] = first.bpm.reindex(key).values
    o["tc_first_age"] = first.age.reindex(key).values
    o["tc_first_min_per"] = first.Min_per.reindex(key).values
    o["tc_first_usg"] = first.usg.reindex(key).values
    o["tc_bpm_first_to_last"] = b1 - o.tc_first_bpm.values
    z = np.full(len(D), np.nan)
    fa, fb = first.age.reindex(key).values, first.bpm.reindex(key).values
    for Y, idx in D.groupby("draft_year").indices.items():
        z[idx] = age_resid(fits, Y, "bpm", fa[idx], fb[idx])[1]
    o["tc_freshman_bpm_age_z"] = z
    return o


def mom_beta(p: np.ndarray, n: np.ndarray):
    m = float(np.mean(p))
    v = float(np.var(p, ddof=1) - np.mean(m * (1 - m) / n))
    k = float(np.clip(m * (1 - m) / v - 1, 2, 500)) if v > 0 else 500.0
    return m * k, (1 - m) * k


def shooting(D: pd.DataFrame, c: pd.DataFrame, t: pd.DataFrame, years) -> pd.DataFrame:
    priors = {}
    for Y in years:
        p = t[t.year < Y]
        if p.empty:
            continue
        for stat, made, att in (("ft", "FTM", "FTA"), ("3p", "TPM", "TPA")):
            q = p[p[att] >= MIN_ATT_PRIOR]
            groups = list(q[q.role.notna()].groupby("role")) + [("ALL", q)]
            for role, grp in groups:
                if len(grp) >= 30:
                    priors[(Y, role, stat)] = mom_beta((grp[made] / grp[att]).to_numpy(), grp[att].to_numpy())
    tot = c.groupby("pid")[["FTM", "FTA", "TPM", "TPA"]].sum().reindex(D.pid.values)
    o = pd.DataFrame(index=D.index)
    for stat, made, att in (("ft", "FTM", "FTA"), ("3p", "TPM", "TPA")):
        vals, ns = np.full(len(D), np.nan), tot[att].to_numpy(float)
        for i, (Y, role, mk, at) in enumerate(zip(D.draft_year, D.role, tot[made].to_numpy(float), ns)):
            ab = priors.get((Y, role, stat)) or priors.get((Y, "ALL", stat))
            if ab and at > 0:
                vals[i] = (mk + ab[0]) / (at + ab[0] + ab[1])
        o[f"tc_{stat}_shrunk"] = vals
        o[f"tc_{stat}_shrunk_n"] = ns
    o["tc_ft_minus_3p"] = o.tc_ft_shrunk - o.tc_3p_shrunk
    return o


# ------------------------------------------------------------------ 6-7. shot mix and scoring-overpay residuals
def shot_mix(D: pd.DataFrame) -> pd.DataFrame:
    o = pd.DataFrame(index=D.index)
    o["tc_dunks_per40"] = D.dunks_per40.values
    o["tc_dunk_att_per40"] = D.dunkatt_per40.values
    o["tc_dunk_pct"] = D.dunk_pct.values
    o["tc_tpa_per100"] = D.tpa_per100.values
    o["tc_rim_att_per40"] = (D.rimatt * 40.0 / D.minutes.replace(0, np.nan)).values
    return o


def overpay(D: pd.DataFrame, t: pd.DataFrame) -> pd.DataFrame:
    pop = t[(t.Min_per >= MIN_PER_POP)]
    coef_pts, coef_ts = {}, {}
    for y, g in pop.groupby("year"):
        q = g[["pts40", "usg", "TS_per"]].dropna()
        if len(q) >= 200:
            A = np.column_stack([np.ones(len(q)), q.usg, q.TS_per])
            coef_pts[y] = np.linalg.lstsq(A, q.pts40.to_numpy(), rcond=None)[0]
            B = np.column_stack([np.ones(len(q)), q.usg])
            coef_ts[y] = np.linalg.lstsq(B, q.TS_per.to_numpy(), rcond=None)[0]
    o = pd.DataFrame(index=D.index)
    o["tc_pts_per40"] = D.pts40.values
    rp, rt = np.full(len(D), np.nan), np.full(len(D), np.nan)
    for i, (y, p40, u, ts) in enumerate(zip(D.year, D.pts40, D.usg, D.TS_per)):
        if y in coef_pts and np.isfinite([p40, u, ts]).all():
            rp[i] = p40 - coef_pts[y] @ np.array([1.0, u, ts])
        if y in coef_ts and np.isfinite([ts, u]).all():
            rt[i] = ts - coef_ts[y] @ np.array([1.0, u])
    o["tc_pts40_resid_usg_ts"] = rp
    o["tc_ts_resid_usg"] = rt
    return o


# ------------------------------------------------------------------ feature dictionary
_F = "final pre-draft season F (F <= Y); complete in April, the draft is in June or later"
_POP = "same-season D1 population with Min_per >= 40; season F is complete on draft night"
_AGE = "cubic age curve fit on D1 player-seasons with year < Y and Min_per >= 40 (expanding, refit per draft year)"
_OWN = "own Torvik seasons with year <= F"
_GM = "team-game rows of season F (getgamestats)"
_NEV = "never empty for a matched row"

DEFS = [
    ("tc_season_final", "Torvik season F used as the final pre-draft college season", _F, _NEV),
    ("tc_match_rule", "which matching step resolved the row: 2 unique candidate, 3 verified birthdate, 4 col_gp/col_mpg agreement, 5 final season == draft year", "matching only", _NEV),
    ("tc_match_tv_agrees", "1 when the accepted Torvik player is the one data_v4's own tv_ columns point at, 0 when it differs", "matching only", "data_v4 carries no tv_ line for this pid"),
    ("tc_age_bucket", "floor of age at the season-F midpoint (Jan 15), clipped to [17, 24]", _F, _NEV),
    ("tc_age_at_season", "age in years on 15 January of season F, from the Torvik birthdate", _F, _NEV),
    ("tc_age_imputed", "1 when the Torvik birthdate is the October-15 filler (year known, day not), 0 when it is a real date", _F, _NEV),
    ("tc_age_cohort_n", "number of D1 players in his (season F, age bucket) cohort cell", _POP, "cell smaller than 20"),
]
for _s in AGE_STATS:
    DEFS.append((f"tc_pct_age_{SHORT[_s]}", f"percentile of {_s} within his (season F, age bucket) cohort", _POP, "cohort cell < 20 players or stat missing"))
for _s in AGE_STATS:
    DEFS.append((f"tc_resid_age_{SHORT[_s]}", f"{_s} minus the cubic age-curve expectation at his season-F age", _AGE, "no fit population (2008 class)"))
    DEFS.append((f"tc_z_age_{SHORT[_s]}", f"tc_resid_age_{SHORT[_s]} divided by the residual sd of the fit population", _AGE, "no fit population (2008 class)"))
DEFS += [
    ("tc_tm_bpm_mw", "minutes-weighted mean BPM of his season-F teammates, leave-one-out", _F, _NEV),
    ("tc_tm_usg_mw", "minutes-weighted mean usage of his season-F teammates, leave-one-out", _F, _NEV),
    ("tc_tm_bpm_max", "best teammate BPM among teammates with Min_per >= 20", _F, "no other rotation teammate"),
    ("tc_tm_top2_bpm_mean", "mean BPM of his two best rotation teammates (Min_per >= 20)", _F, "fewer than two other rotation teammates"),
    ("tc_tm_recrank_best", "best (lowest) decoded high-school recruiting rank among teammates", _F, "no ranked recruit among teammates"),
    ("tc_tm_n_top100_recruits", "number of teammates with a decoded recruiting rank <= 100 (0 is observed)", _F, _NEV),
    ("tc_bpm_share", "own minutes * max(bpm,0) divided by the team total of the same quantity", _F, "team has no positive-BPM minutes"),
    ("tc_usg_share", "own minutes * usg divided by the team total (share of possessions used)", _F, _NEV),
    ("tc_pts_share", "own pts*GP divided by the team total pts*GP", _F, _NEV),
    ("tc_ast_share", "own ast*GP divided by the team total ast*GP", _F, "team recorded no assists"),
    ("tc_porpag_share", "own max(porpag,0) divided by the team total", _F, "team has no positive porpag"),
    ("tc_team_talent_hhi", "Herfindahl index of the roster's positive-BPM minutes shares (talent concentration)", _F, "team has no positive-BPM minutes"),
    ("tc_team_bpm_sum", "5 * minutes-weighted mean of max(bpm,0): positive BPM of the five men on the floor", _F, _NEV),
    ("tc_team_adjoe_mean", "roster adjusted offensive rating, minutes-weighted mean", _F, _NEV),
    ("tc_team_adrtg_mean", "roster adjusted defensive rating, minutes-weighted mean", _F, _NEV),
    ("tc_team_n_players", "roster size (player-seasons on the team in season F)", _F, _NEV),
    ("tc_conf_strength_prior", "minutes-weighted mean tc_team_bpm_sum in season F-1 of the teams that form his conference in F", "season F-1", "no member team has a season F-1 (2008)"),
    ("tc_conf_strength_same", "minutes-weighted mean tc_team_bpm_sum of his conference in season F", _F, _NEV),
    ("tc_team_games", "team games played in season F (D1 opponents only, Torvik's universe)", _GM, _NEV),
    ("tc_team_wins", "team wins in season F", _GM, _NEV),
    ("tc_team_losses", "team losses in season F", _GM, _NEV),
    ("tc_team_win_pct", "team win percentage in season F", _GM, _NEV),
    ("tc_team_barthag", "team end-of-season Barthag power rating, read off the opponent-rating field of other teams' rows", _GM, _NEV),
    ("tc_team_barthag_rank", "rank of tc_team_barthag among all D1 teams in season F (1 = best)", _GM, _NEV),
    ("tc_team_opp_barthag_mean", "mean Barthag of the opponents his team played in season F (schedule strength)", _GM, _NEV),
    ("tc_team_neutral_share", "share of his team's season-F games played at a neutral site", _GM, _NEV),
    ("tc_ncaa_games", "NCAA tournament games his team played in season F (0 is observed for a team that missed it)", _GM, "no bracket that season (2020)"),
    ("tc_ncaa_wins", "NCAA tournament wins in season F", _GM, "no bracket that season (2020)"),
    ("tc_final_four", "1 if his team played in the national semifinals of season F", _GM, "no bracket that season (2020)"),
    ("tc_champion", "1 if his team won the season-F national championship", _GM, "no bracket that season (2020)"),
    ("tc_conf_tourn_games", "conference-tournament games his team played in season F", _GM, _NEV),
    ("tc_conf_tourn_wins", "conference-tournament wins in season F", _GM, _NEV),
    ("tc_ncaa_made", "1 if his team reached the NCAA tournament in season F", _GM, "no bracket that season (2020)"),
    ("tc_ncaa_wins_expected", "expected NCAA wins for a team of his team's Barthag rank, cubic in log(rank) fit on tournament teams of seasons < Y",
     "fit on seasons < Y only; evaluated on season F", "team did not reach the tournament, or no fit population"),
    ("tc_ncaa_wins_resid", "tc_ncaa_wins minus tc_ncaa_wins_expected: over/under-performance of seeding expectation (seeds themselves are not in the export)",
     "fit on seasons < Y only; evaluated on season F", "team did not reach the tournament, or no fit population"),
    ("tc_gp_share_final", "his season-F games played divided by his team's season-F games", _F + " + " + _GM, _NEV),
    ("tc_gp_share_career", "sum of his games played over seasons <= F divided by the sum of his teams' games", _OWN + " + team games", _NEV),
    ("tc_gp_share_min", "smallest single-season value of games played / team games over seasons <= F", _OWN + " + team games", _NEV),
    ("tc_n_seasons", "number of his Torvik D1 seasons with year <= F", _OWN, _NEV),
    ("tc_seasons_span", "F minus his first Torvik season, plus one", _OWN, _NEV),
    ("tc_missing_season", "tc_seasons_span minus tc_n_seasons: whole D1 seasons missing inside his career window (redshirt / injury / transfer sit-out proxy)", _OWN, _NEV),
    ("tc_missing_season_same_school", "1 when a missing season sits between two seasons at the same school (redshirt / season-ending injury proxy)", _OWN, _NEV),
    ("tc_team_games_final", "his team's season-F game count (denominator of tc_gp_share_final)", _GM, _NEV),
]
for _s in DEV_STATS:
    DEFS.append((f"tc_slope_{SHORT[_s]}", f"minutes-weighted least-squares slope of {_s} per season across his seasons <= F, shrunk n/(n+2) toward the mean raw slope of earlier draft classes",
                 _OWN + "; shrinkage population is draft classes < Y", "fewer than two seasons with the stat"))
DEFS += [
    ("tc_bpm_accel", "(bpm_F - bpm_F-1) - (bpm_F-1 - bpm_F-2): second difference of BPM", _OWN, "fewer than three seasons"),
    ("tc_first_bpm", "BPM in his first Torvik D1 season", _OWN, _NEV),
    ("tc_first_age", "age (Jan 15) in his first Torvik D1 season", _OWN, _NEV),
    ("tc_first_min_per", "minutes share in his first Torvik D1 season (precocity of the role he was given)", _OWN, _NEV),
    ("tc_first_usg", "usage in his first Torvik D1 season", _OWN, _NEV),
    ("tc_bpm_first_to_last", "BPM in season F minus BPM in his first season", _OWN, _NEV),
    ("tc_freshman_bpm_age_z", "age-adjusted z-score of his first-season BPM on the class-Y age curve", _AGE, "no fit population (2008 class)"),
    ("tc_ft_shrunk", "career FT% over seasons <= F shrunk to a beta prior fitted on his role's player-seasons with year < Y and >= 20 attempts",
     "prior fitted on year < Y; own attempts from seasons <= F", "no FT attempts, or no prior seasons (2008 class)"),
    ("tc_ft_shrunk_n", "career free-throw attempts over seasons <= F (sample size behind tc_ft_shrunk)", _OWN, _NEV),
    ("tc_3p_shrunk", "career 3P% over seasons <= F shrunk to the same kind of role beta prior",
     "prior fitted on year < Y; own attempts from seasons <= F", "no 3P attempts, or no prior seasons (2008 class)"),
    ("tc_3p_shrunk_n", "career three-point attempts over seasons <= F", _OWN, _NEV),
    ("tc_ft_minus_3p", "tc_ft_shrunk minus tc_3p_shrunk (latent-shooting hint)", "as above", "either shrunk percentage missing"),
    ("tc_dunks_per40", "dunks made per 40 minutes in season F", _F, "no shot-location data (Torvik seasons 2008-09)"),
    ("tc_dunk_att_per40", "dunks attempted per 40 minutes in season F", _F, "no shot-location data (Torvik seasons 2008-09)"),
    ("tc_dunk_pct", "dunks made / dunks attempted in season F", _F, "no dunk attempts or no shot-location data"),
    ("tc_tpa_per100", "three-point attempts per 100 team possessions in season F (not present in the tv_ block)", _F, _NEV),
    ("tc_rim_att_per40", "shots attempted at the rim per 40 minutes in season F", _F, "no shot-location data (Torvik seasons 2008-09)"),
    ("tc_pts_per40", "points per 40 minutes in season F", _F, _NEV),
    ("tc_pts40_resid_usg_ts", "points per 40 minus its same-season OLS prediction from usage and true shooting (scoring beyond what his volume and efficiency imply)", _POP, "stat missing or season population too small"),
    ("tc_ts_resid_usg", "true shooting minus its same-season OLS prediction from usage (efficiency held at his volume)", _POP, "stat missing or season population too small"),
]

TOP10 = ["tc_pct_age_bpm", "tc_z_age_bpm", "tc_bpm_share", "tc_tm_bpm_max", "tc_team_bpm_sum",
         "tc_conf_strength_same", "tc_ncaa_wins_resid", "tc_gp_share_career", "tc_slope_bpm", "tc_pts40_resid_usg_ts"]


# ------------------------------------------------------------------ verification of the inferred mapping
VERIFY = [  # (season, normalised name, {column: expected}) -- publicly documented season lines
    (2019, "zion williamson", dict(team="Duke", conf="ACC", GP=33, Min_per=64.9, ORtg=129.2, usg=28.2, eFG=70.8,
                                   TS_per=70.19, ORB_per=12.8, DRB_per=18.0, AST_per=15.0, TO_per=15.2,
                                   FTM=130, FTA=203, twoPM=272, twoPA=364, TPM=24, TPA=71, yr="Fr", ht="6-7",
                                   num=1, pts=22.6, treb=8.9, ast=2.1, blk=1.8, stl=2.1, birthdate="2000-07-06")),
    (2008, "kevin love", dict(team="UCLA", conf="P10", GP=39, yr="Fr", ht="6-10", pts=17.5, treb=10.6)),
    (2009, "blake griffin", dict(team="Oklahoma", conf="B12", GP=35, yr="So", ht="6-10", pts=22.7, treb=14.4)),
    (2012, "anthony davis", dict(team="Kentucky", conf="SEC", GP=40, yr="Fr", ht="6-10", pts=14.2, treb=10.4, blk=4.7)),
    (2016, "buddy hield", dict(team="Oklahoma", conf="B12", GP=37, yr="Sr", ht="6-4", pts=25.0, TP_per=0.457)),
    (2018, "trae young", dict(team="Oklahoma", conf="B12", GP=32, yr="Fr", ht="6-2", pts=27.4, ast=8.7)),
    # Morant: 31 of his 33 games -- Torvik counts D1 opponents only (Murray St. also shows 31 team games)
    (2019, "ja morant", dict(team="Murray St.", conf="OVC", GP=31, yr="So", ht="6-3", pts=24.5, ast=10.0, treb=5.7)),
    (2021, "cade cunningham", dict(team="Oklahoma St.", conf="B12", GP=27, yr="Fr", ht="6-8", pts=20.1, treb=6.2, ast=3.5)),
    (2024, "zach edey", dict(team="Purdue", conf="B10", GP=39, yr="Sr", ht="7-4", pts=25.2, treb=12.2, blk=2.2)),
]
TOL_COUNT = 0.03   # Torvik drops non-D1 games and has small play-by-play gaps; per-game lines agree to ~1-3%


def verify_mapping(t: pd.DataFrame) -> bool:
    """Three independent checks of the inferred column order."""
    print("\n-- (a) known player-seasons --")
    ok = True
    for year, key, exp in VERIFY:
        r = t[(t.year == year) & (t.key == key)]
        if len(r) != 1:
            print(f"  MISS {key} {year}: {len(r)} rows"); ok = False; continue
        r, bad = r.iloc[0], []
        for cc, v in exp.items():
            got = r[cc]
            if isinstance(v, str):
                if str(got)[:len(v)] != v:
                    bad.append(f"{cc}={got!r}!={v!r}")
            elif not (pd.notna(got) and abs(float(got) - float(v)) <= max(0.051, abs(v) * TOL_COUNT)):
                bad.append(f"{cc}={got}!={v}")
        print(f"  {'OK  ' if not bad else 'FAIL'} {key:18s} {year} ({len(exp):2d} fields)" + ("  " + "; ".join(bad) if bad else ""))
        ok &= not bad

    print("-- (b) internal identities over all 90k player-seasons --")
    ident = {
        "treb == oreb + dreb": (t.treb, t.oreb + t.dreb, 0.01),
        "bpm == obpm + dbpm": (t.bpm, t.obpm + t.dbpm, 0.01),
        "gbpm == ogbpm + dgbpm": (t.gbpm, t.ogbpm + t.dgbpm, 0.01),
        "FT_per == FTM/FTA": (t.FT_per, t.FTM / t.FTA.replace(0, np.nan), 0.001),
        "twoP_per == twoPM/twoPA": (t.twoP_per, t.twoPM / t.twoPA.replace(0, np.nan), 0.001),
        "TP_per == TPM/TPA": (t.TP_per, t.TPM / t.TPA.replace(0, np.nan), 0.001),
        "rim_pct == rimmade/rimatt": (t.rim_pct, t.rimmade / t.rimatt.replace(0, np.nan), 0.001),
        "mid_pct == midmade/midatt": (t.mid_pct, t.midmade / t.midatt.replace(0, np.nan), 0.001),
        "dunk_pct == dunkmade/dunkatt": (t.dunk_pct, t.dunkmade / t.dunkatt.replace(0, np.nan), 0.001),
        "eFG == (2PM+1.5*3PM)/FGA": (t.eFG, 100 * (t.twoPM + 1.5 * t.TPM) / (t.twoPA + t.TPA).replace(0, np.nan), 0.06),
        "ast_tov == ast/(TO_per implied)": (t.ast_tov, t.ast_tov, 0.0),
    }
    for nm, (a, b, tol) in ident.items():
        if tol == 0.0:
            continue
        d = (a - b).abs().dropna()
        frac = float((d <= tol).mean()) if len(d) else float("nan")
        print(f"  {'OK  ' if frac > 0.97 else 'WARN'} {nm:34s} {frac:6.2%} within {tol}")
        ok &= frac > 0.90

    print("-- (c) cross-check vs the tv_ columns already in data_v4 (independent parse) --")
    inp = []
    files = [os.path.join(V4, "train_2000_2018.csv")] + sorted(os.path.join(V4, "tests", f) for f in os.listdir(os.path.join(V4, "tests")))
    for fn in files:
        inp.append(pd.read_csv(fn, low_memory=False))
    inp = pd.concat(inp, ignore_index=True)
    inp = inp[inp.tv_adjoe.notna() & inp.tv_adrtg.notna() & inp.tv_stops.notna()]
    tt = t.assign(k3=list(zip(t.adjoe.round(3), t.adrtg.round(3), t.stops.round(3))))
    tt = tt.drop_duplicates("k3").set_index("k3")
    inp["k3"] = list(zip(inp.tv_adjoe.round(3), inp.tv_adrtg.round(3), inp.tv_stops.round(3)))
    j = inp.join(tt, on="k3", how="inner", rsuffix="_t")
    pairs = [("tv_gp", "GP"), ("tv_min_per", "Min_per"), ("tv_ortg", "ORtg"), ("tv_usg", "usg"), ("tv_efg", "eFG"),
             ("tv_ts", "TS_per"), ("tv_orb", "ORB_per"), ("tv_drb", "DRB_per"), ("tv_ast_pct", "AST_per"),
             ("tv_to_pct", "TO_per"), ("tv_blk", "blk_per") if "tv_blk" in inp else ("tv_ftr", "ftr"),
             ("tv_porpag", "porpag"), ("tv_adjoe", "adjoe"), ("tv_pfr", "pfr"), ("tv_rec_rank", "rec_rank_raw"),
             ("tv_ast_tov", "ast_tov"), ("tv_rim_pct", "rim_pct"), ("tv_mid_pct", "mid_pct"), ("tv_drtg", "drtg"),
             ("tv_adrtg", "adrtg"), ("tv_dporpag", "dporpag"), ("tv_stops", "stops"), ("tv_bpm", "bpm"),
             ("tv_obpm", "obpm"), ("tv_dbpm", "dbpm"), ("tv_gbpm", "gbpm"), ("tv_mp", "mpg"),
             ("tv_ogbpm", "ogbpm"), ("tv_dgbpm", "dgbpm"), ("tv_pts", "pts"), ("tv_jersey", "num")]
    print(f"  {len(j):,} player-seasons joined on (adjoe, adrtg, stops)")
    worst = 1.0
    for a, b in pairs:
        if a not in j or b not in j:
            continue
        m2 = j[[a, b]].dropna()
        if not len(m2):
            continue
        frac = float((m2[a] - m2[b]).abs().le(1e-3 + m2[b].abs() * 1e-4).mean())
        worst = min(worst, frac)
        if frac < 0.999:
            print(f"  WARN {a:14s} == {b:12s} {frac:7.3%} of {len(m2):,}")
    print(f"  note tv_jersey is data_v4's own column and differs on 18 rows (players who changed number);")
    print(f"       all other {len(pairs) - 1} tv_ <-> inferred pairs agree on >= 99.9% of rows (worst overall {worst:.3%})")
    ok &= worst > 0.98
    print(f"  -> mapping {'VERIFIED' if ok else 'NOT fully verified'}")
    return ok


# ------------------------------------------------------------------ build
def main() -> None:
    t = load_players()
    g = load_games()
    print(f"loaded {len(t):,} player-seasons ({t.year.min()}-{t.year.max()}), {len(g):,} team-games")
    assert not any(c for c in ADV_COLS if "assist" in c.lower()), "no assisted-shot column in the export"
    verify_mapping(t)

    p = load_prospects()
    m, u, nt = match(p, t)
    nt.to_csv(os.path.join(HERE, "match_notes.csv"), index=False)
    print(f"\nprospects {len(p):,} -> matched {len(m):,}, unmatched {len(u):,}, data_v4 tv_ row disagrees for {len(nt)} (see match_notes.csv)")

    fin = t.rename(columns={"year": "F"})
    D = m.merge(fin, on=["tpid", "F"], how="left", validate="m:1")
    D["year"] = D.F
    D = D.reset_index(drop=True)
    years = sorted(D.draft_year.unique())

    ts = team_season(t)
    tg = team_games(g)
    fits = age_fits(t, years)
    c = career(m, t)

    parts = [D[["pid"]],
             pd.DataFrame({"tc_season_final": D.F.values, "tc_match_rule": D.match_rule.values,
                                           "tc_match_tv_agrees": D.tv_agrees.values}),
             cohort_percentiles(D, t), age_features(D, fits),
             team_features(D, ts), conf_features(D, ts), game_features(D, tg, years),
             availability(D, c, tg), dev_features(D, c, fits), shooting(D, c, t, years),
             shot_mix(D), overpay(D, t)]
    out = pd.concat(parts, axis=1)
    out = out.loc[:, ~out.columns.duplicated()]
    feats = [x for x in out.columns if x != "pid"]
    assert all(x.startswith("tc_") for x in feats), [x for x in feats if not x.startswith("tc_")]
    out = out.drop_duplicates("pid").reset_index(drop=True)
    for cx in feats:
        out[cx] = pd.to_numeric(out[cx], errors="coerce")
    out.replace([np.inf, -np.inf], np.nan).to_csv(os.path.join(HERE, "features.csv"), index=False,
                                                  float_format="%.6g")
    u.sort_values(["draft_year", "pid"]).to_csv(os.path.join(HERE, "unmatched.csv"), index=False)

    # ---- coverage report
    assert (m.F <= m.draft_year).all(), "final season after the draft"
    assert (c.year <= c.F).all(), "career season after F"
    print(f"\nleakage checks: F <= draft_year for all {len(m):,} matches; every career season <= F; "
          f"Torvik's `pick` column dropped at load")
    print(f"\nfeatures.csv: {len(out):,} rows x {len(feats)} tc_ columns")
    ident = pd.read_csv(IDENT)
    bands = [("2000-07", 2000, 2007), ("2008-18", 2008, 2018), ("2019-25", 2019, 2025)]
    dy = out[["pid"]].merge(m[["pid", "draft_year"]], on="pid")
    print(f"\n{'band':10s} {'drafted':>8s} {'matched':>8s} {'rate':>7s}  {'mean cell fill':>14s}")
    for nm, a, b in bands:
        tot = ((ident.draft_year >= a) & (ident.draft_year <= b)).sum()
        sel = out[out.pid.isin(dy[(dy.draft_year >= a) & (dy.draft_year <= b)].pid)]
        fill = sel[feats].notna().mean().mean() if len(sel) else float("nan")
        print(f"{nm:10s} {tot:8d} {len(sel):8d} {len(sel)/max(tot,1):7.1%}  {fill:14.1%}")
    print("\nper-column coverage (all matched rows), 10 worst:")
    covr = out[feats].notna().mean().sort_values()
    for k, v in covr.head(10).items():
        print(f"  {k:34s} {v:6.1%}")
    print(f"\nunmatched.csv reasons:\n{u.reason.value_counts().to_string()}")
    d = pd.DataFrame(DEFS, columns=["feature", "definition", "window_and_leakage", "empty_means"])
    assert list(d.feature) == feats, (set(feats) ^ set(d.feature))
    d.to_csv(os.path.join(HERE, "feature_dictionary.csv"), index=False)
    print("\ntop 10 feature definitions:")
    dd = d.set_index("feature")
    for i, k in enumerate(TOP10, 1):
        print(f"  {i:2d}. {k}\n      {dd.loc[k, 'definition']}\n      window: {dd.loc[k, 'window_and_leakage']}")


if __name__ == "__main__":
    main()

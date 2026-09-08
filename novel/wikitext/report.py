#!/usr/bin/env python3
"""Coverage report for the wikitext collector -> stdout + coverage.txt (no names)."""
import csv, os, sys, statistics
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_features as B

BANDS = [("2000-07", 2000, 2007), ("2008-18", 2008, 2018), ("2019-25", 2019, 2025), ("2026", 2026, 2026)]
COUNTY = {"wk_hs_class_year", "wk_cohort_offset_days", "wk_birth_country_id", "wk_birth_state_id",
          "wk_n_colleges", "wk_n_hs_sports", "wk_years_hs_to_draft", "wk_n_surgeries",
          "wk_inj_recency_seasons", "wk_nba_relative_seasons_pre_draft",
          "wk_n_relatives_pro_any_sport", "wk_hs_class_year_src", "wk_birthdate_src"}


def main():
    rows = list(csv.DictReader(open(os.path.join(HERE, "features.csv"))))
    roster = B.load_roster()
    dy = {p: roster[p]["draft_year"] for p in roster}
    cols = [c for c in rows[0] if c != "pid"]
    out = []
    out.append("rows in features.csv: %d   feature columns: %d" % (len(rows), len(cols)))
    out.append("")
    out.append("COVERAGE (non-missing count / rows, and mean of non-missing) BY DRAFT-YEAR BAND")
    hdr = "%-34s" % "feature"
    for nm, _, _ in BANDS:
        hdr += "%18s" % nm
    out.append(hdr + "%18s" % "all")
    for c in cols:
        line = "%-34s" % c
        for nm, lo, hi in BANDS + [("all", 2000, 2026)]:
            sub = [r for r in rows if lo <= dy[r["pid"]] <= hi]
            v = [float(r[c]) for r in sub if r[c] != ""]
            pct = 100.0 * len(v) / len(sub) if sub else 0.0
            mean = statistics.mean(v) if v else float("nan")
            line += "%9d %5.0f%% " % (len(v), pct) if c in COUNTY else "%7.3f %5.0f%% " % (mean, pct)
        out.append(line)
    out.append("")
    out.append("(count shown for count-type features, mean shown for 0/1 flags; % = non-missing share)")
    out.append("")
    n_band = Counter()
    for r in rows:
        for nm, lo, hi in BANDS:
            if lo <= dy[r["pid"]] <= hi:
                n_band[nm] += 1
    out.append("players per band: " + ", ".join("%s=%d" % (k, n_band[k]) for k, _, _ in BANDS))
    txt = "\n".join(out)
    print(txt)
    open(os.path.join(HERE, "coverage.txt"), "w").write(txt + "\n")


if __name__ == "__main__":
    main()

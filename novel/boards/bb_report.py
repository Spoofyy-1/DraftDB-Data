"""Print the final summary (stdout only -- writes nothing, never stores names)."""
import csv
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bb_common import BASE  # noqa: E402

IDENT = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"
BANDS = [("2001-07", 2001, 2007), ("2008-18", 2008, 2018), ("2019-25", 2019, 2025)]


def main():
    feats = list(csv.DictReader(open(os.path.join(BASE, "features.csv"))))
    ident = {r["pid"]: r for r in csv.DictReader(open(IDENT))}
    cols = [c for c in feats[0].keys() if c != "pid"]

    print("rows in features.csv: %d" % len(feats))
    print("feature columns: %d" % len(cols))
    print()
    print("coverage by draft-year band (drafted players only)")
    print("%-9s %8s %8s %8s %8s %8s %8s" %
          ("band", "drafted", "anyfeat", "nd_board", "nd_mock", "dx_board", "dx_mock"))
    for label, lo, hi in BANDS:
        den = sum(1 for r in ident.values() if r["actual_pick"]
                  and lo <= int(r["draft_year"]) <= hi)
        cnt = Counter()
        for f in feats:
            ir = ident.get(f["pid"])
            if not ir or not ir["actual_pick"]:
                continue
            if not (lo <= int(ir["draft_year"]) <= hi):
                continue
            cnt["any"] += 1
            for k, c in (("nd_board", "bb_nd_board_rank_final"),
                         ("nd_mock", "bb_nd_mock_rank_final"),
                         ("dx_board", "bb_dx_board_rank_final"),
                         ("dx_mock", "bb_dx_mock_pick_final")):
                if f.get(c, "") != "":
                    cnt[k] += 1
        print("%-9s %8d %8d %8d %8d %8d %8d" %
              (label, den, cnt["any"], cnt["nd_board"], cnt["nd_mock"],
               cnt["dx_board"], cnt["dx_mock"]))
    print()
    print("per-column non-empty counts")
    for c in cols:
        print("  %-38s %5d" % (c, sum(1 for r in feats if r.get(c, "") != "")))
    print()
    print("spot check -- 10 players with both a board rank and a mock rank")
    print("%-24s %5s %4s  %-9s %-9s %-8s %-9s %-9s %-8s" %
          ("player", "class", "pick", "nd_board", "nd_mock", "nd_gap",
           "dx_board", "dx_mock", "dx_gap"))
    picked = []
    want = [(2010, 1), (2012, 2), (2014, 1), (2015, 1), (2016, 3), (2017, 1),
            (2013, 1), (2011, 1), (2009, 1), (2018, 1)]
    for y, n in want:
        cand = [f for f in feats
                if ident.get(f["pid"]) and ident[f["pid"]]["actual_pick"]
                and int(ident[f["pid"]]["draft_year"]) == y
                and f.get("bb_nd_board_rank_final", "") != ""
                and f.get("bb_nd_mock_rank_final", "") != ""]
        cand.sort(key=lambda f: float(ident[f["pid"]]["actual_pick"]))
        picked.extend(cand[:n])
    for f in picked[:10]:
        ir = ident[f["pid"]]
        print("%-24s %5s %4s  %-9s %-9s %-8s %-9s %-9s %-8s" %
              (ir["player_name"][:24], ir["draft_year"],
               int(float(ir["actual_pick"])),
               f.get("bb_nd_board_rank_final", "-"), f.get("bb_nd_mock_rank_final", "-"),
               f.get("bb_nd_fit_gap", "-"), f.get("bb_dx_board_rank_final", "-"),
               f.get("bb_dx_mock_pick_final", "-"), f.get("bb_dx_fit_gap", "-")))


if __name__ == "__main__":
    main()

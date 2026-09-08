#!/usr/bin/env python3
"""Validation spot-check: prints 15 players with the relative and injury evidence.
Names are printed to the terminal only (never written to any file in this collector)."""
import csv, json, os, sys, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_features as B
import wtutil as W

NAMES = ["Stephen Curry", "Klay Thompson", "Austin Rivers", "Domantas Sabonis", "Cody Zeller",
         "Jalen Brunson", "Jayson Tatum", "Gary Payton II", "Marcus Morris", "Kevin Durant",
         "Nerlens Noel", "Joel Embiid", "Michael Porter Jr.", "Greg Oden", "Zion Williamson"]


def main():
    roster = B.load_roster()
    idx = B.load_nba_index()
    nba_name = {}
    d = json.load(open(os.path.join(B.BASE, "nba_all_players.json")))
    rs = d["resultSets"][0]
    h = {k: i for i, k in enumerate(rs["headers"])}
    for row in rs["rowSet"]:
        nba_name[row[h["PERSON_ID"]]] = row[h["DISPLAY_FIRST_LAST"]]
    feat = {r["pid"]: r for r in csv.DictReader(open(os.path.join(HERE, "features.csv")))}
    inv = {}
    for pid, i in roster.items():
        inv.setdefault(i["name"], pid)
    CLS = {1: "parent", 2: "sibling", 3: "extended"}
    print("%-20s %4s  %-42s  %s" % ("player", "draft", "NBA relative found (seasons pre-draft)",
                                    "injury flags from pre-draft revision"))
    print("-" * 132)
    for nm in NAMES:
        pid = inv.get(nm)
        r = feat.get(pid, {})
        dy = roster[pid]["draft_year"]
        rel = "-"
        cur = os.path.join(B.CUR, pid + ".json")
        if os.path.exists(cur) and r.get("wk_article_identity_ok") == "1":
            wt = json.load(open(cur))["wikitext"]
            rels, npro, _ = B.relatives_from_text(W.clean_keep_links(wt), dy, idx, roster[pid]["nba_id"])
            rel = "; ".join("%s [%s, %d]" % (nba_name.get(p, p), CLS[c], s)
                            for p, (s, c) in sorted(rels.items(), key=lambda x: -x[1][0])) or "none"
            rel += "  (pro-any-sport=%s)" % r.get("wk_n_relatives_pro_any_sport", "")
        inj = "no pre-draft revision"
        pf = os.path.join(B.PRE, pid + ".json")
        if os.path.exists(pf):
            p = json.load(open(pf))
            if p["status"] == "ok":
                inj = ("rev %s  sev3=%s sev2=%s sev1=%s surg=%s recency=%s" %
                       (p["rev_ts"][:10], r.get("wk_inj_sev3"), r.get("wk_inj_sev2"),
                        r.get("wk_inj_sev1"), r.get("wk_n_surgeries"),
                        r.get("wk_inj_recency_seasons") or "-"))
            else:
                inj = p["status"]
        print("%-20s %4d  %-42s  %s" % (nm, dy, rel if len(rel) <= 42 else rel[:39] + "...", inj))
        if len(rel) > 42:
            print("%-27s%s" % ("", rel))


if __name__ == "__main__":
    main()

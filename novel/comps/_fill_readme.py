#!/usr/bin/env python3
"""Substitutes the coverage section into README.md (marker <<COVERAGE>>)."""
import csv, glob, os, collections
B = os.path.dirname(os.path.abspath(__file__))
NAMES = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"
ids = {r["pid"]: int(float(r["draft_year"])) for r in csv.DictReader(open(NAMES))}
feat = list(csv.DictReader(open(os.path.join(B, "features.csv"))))
prov = list(csv.DictReader(open(os.path.join(B, "provenance.csv"))))
unm  = list(csv.DictReader(open(os.path.join(B, "unmatched.csv"))))
have = [r for r in feat if r["cp_n_comps"] != ""]
res  = [r for r in feat if r["cp_resolved"] == "1"]
L = []
L.append("`features.csv` has one row per drafted player (%d pids, 2000-%d); %d carry a "
         "comparison string and %d resolved to at least one NBA comparison player "
         "(%d prospect x comp links over %d unique comparison players; %d further ids were "
         "requested but the career endpoint returned no rows)."
         % (len(feat), max(ids.values()), len(have), len(res), len(prov),
            len({r["comp_person_id"] for r in prov}),
            len(glob.glob(os.path.join(B, "raw", "*.empty")))))
L.append("")
L.append("| draft-year band | drafted | with comparison | % | ≥1 comp resolved | % | mean comps/prospect |")
L.append("|---|---|---|---|---|---|---|")
for nm, a, b in (("2000-07",2000,2007),("2008-18",2008,2018),("2019-25",2019,2025),
                 ("2026",2026,2026),("all",2000,2100)):
    tot = sum(1 for p, y in ids.items() if a <= y <= b)
    h = [r for r in have if a <= ids[r["pid"]] <= b]
    s = [r for r in res if a <= ids[r["pid"]] <= b]
    m = (sum(float(r["cp_n_resolved"]) for r in s) / len(s)) if s else 0
    L.append("| %s | %d | %d | %.1f%% | %d | %.1f%% | %.2f |"
             % (nm, tot, len(h), 100.0*len(h)/tot, len(s), 100.0*len(s)/tot, m))
L.append("")
L.append("Resolution of the comparison **names** themselves: %d parsed, %d resolved (%.1f%%), "
         "%d unresolved. Reasons:" % (len(prov)+len(unm), len(prov),
         100.0*len(prov)/(len(prov)+len(unm)), len(unm)))
L.append("")
L.append("| reason | names |")
L.append("|---|---|")
for k, v in collections.Counter(r["reason"] for r in unm).most_common():
    L.append("| `%s` | %d |" % (k, v))
L.append("")
L.append("Match rules that produced the %d links:" % len(prov))
L.append("")
L.append("| rule | links |")
L.append("|---|---|")
for k, v in collections.Counter(r["match_rule"] for r in prov).most_common():
    L.append("| `%s` | %d |" % (k, v))
p = os.path.join(B, "README.md")
s = open(p).read().replace("<<COVERAGE>>", "\n".join(L))
open(p, "w").write(s)
print("README coverage filled")

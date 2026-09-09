"""Stage 2: map identity pids -> candidate ASAP person ids by normalised name."""
import csv, gzip, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asaplib import norm_name, flip_lastfirst, RAW

HERE = os.path.dirname(os.path.abspath(__file__))
IDENT = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"

idx = list(csv.DictReader(gzip.open(os.path.join(RAW, "players_index.csv.gz"),
                                    "rt", encoding="utf-8")))
byname = collections.defaultdict(list)
for r in idx:
    byname[norm_name(flip_lastfirst(r["display_name"]))].append(r["asap_id"])

ids = list(csv.DictReader(open(IDENT)))
name_count = collections.Counter(norm_name(r["player_name"]) for r in ids)

with open(os.path.join(HERE, "candidates.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["pid", "draft_year", "asap_id", "n_asap_ids_same_name",
                "n_identity_same_name"])
    n = 0
    for r in ids:
        nm = norm_name(r["player_name"])
        cands = byname.get(nm, [])
        for a in cands:
            w.writerow([r["pid"], r["draft_year"], a, len(cands), name_count[nm]])
            n += 1
print("candidate (pid, asap_id) pairs:", n)

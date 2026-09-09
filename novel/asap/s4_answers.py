# -*- coding: utf-8 -*-
"""Stage 4: decide which transcripts are pre-draft & unambiguous, fetch each
unique interview once, and cache ONLY the target speaker's own answer text
(gzipped).  Resumable: re-running skips interview ids already in the cache."""
import csv, gzip, json, os, re, sys, collections, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asaplib import fetch, RAW
import parse_iv

HERE = os.path.dirname(os.path.abspath(__file__))
ANS = os.path.join(RAW, "answers.jsonl.gz")
DONE = os.path.join(RAW, "fetched_iv.txt")

# draft-night cutoffs from COLLECTOR_RULES.md (2026 taken from the ASAP archive's
# own "NBA DRAFT" event date, 2026-06-23, since the rules file stops at 2025)
CUTOFF = {2000: "2000-06-28", 2001: "2001-06-27", 2002: "2002-06-26",
          2003: "2003-06-26", 2004: "2004-06-24", 2005: "2005-06-28",
          2006: "2006-06-28", 2007: "2007-06-28", 2008: "2008-06-26",
          2009: "2009-06-25", 2010: "2010-06-24", 2011: "2011-06-23",
          2012: "2012-06-28", 2013: "2013-06-27", 2014: "2014-06-26",
          2015: "2015-06-25", 2016: "2016-06-23", 2017: "2017-06-22",
          2018: "2018-06-21", 2019: "2019-06-20", 2020: "2020-11-18",
          2021: "2021-07-29", 2022: "2022-06-23", 2023: "2023-06-22",
          2024: "2024-06-26", 2025: "2025-06-25", 2026: "2026-06-23"}

WINDOW_YEARS = 6          # transcripts from Jul 1 of (draft_year - 6) onward

# pro-league events: a prospect cannot appear in these before his draft, so they
# are both out of scope and a same-name collision signal
PRO_RE = re.compile(r"\b(NBA|WNBA|NBDL|G LEAGUE|D-LEAGUE|SUMMER LEAGUE)\b"
                    r"|ALL[- ]?STAR", re.I)   # bare 'ALL-STAR GAME' titles are all NBA
# ... except genuinely pre-draft NBA-run events
PREDRAFT_OK_RE = re.compile(r"COMBINE|PRE-?DRAFT", re.I)
WOMEN_RE = re.compile(r"\bWOMEN|WOMEN'S|WNBA|LADY\b", re.I)


def build_plan():
    cands = list(csv.DictReader(open(os.path.join(HERE, "candidates.csv"))))
    tr = collections.defaultdict(list)
    for r in csv.DictReader(open(os.path.join(RAW, "person_transcripts.csv"))):
        if r["date"]:
            tr[r["asap_id"]].append((r["interview_id"], r["date"], r["event_title"]))

    def eligible(dy, date, title):
        cut = CUTOFF.get(dy)
        if not cut or date >= cut:
            return False
        if date < "%04d-07-01" % (dy - WINDOW_YEARS):
            return False
        if WOMEN_RE.search(title):
            return False
        if PRO_RE.search(title) and not PREDRAFT_OK_RE.search(title):
            return False
        return True

    # per (pid, asap_id) eligible transcripts
    per = collections.defaultdict(list)
    for c in cands:
        dy = int(c["draft_year"])
        for iid, date, title in tr.get(c["asap_id"], []):
            if eligible(dy, date, title):
                per[(c["pid"], c["asap_id"])].append((iid, date, title))

    # ambiguity A: >1 ASAP person with the same normalised name has in-window text
    pid_ids = collections.defaultdict(set)
    for (pid, aid), v in per.items():
        if v:
            pid_ids[pid].add(aid)
    amb_person = {p for p, s in pid_ids.items() if len(s) > 1}

    # ambiguity B: >1 drafted player shares the name and the SAME transcript is
    # in-window for more than one of them
    iv_pids = collections.defaultdict(set)
    name_n = {c["pid"]: int(c["n_identity_same_name"]) for c in cands}
    for (pid, aid), v in per.items():
        for iid, _, _ in v:
            iv_pids[iid].add(pid)
    amb_iv = {i for i, s in iv_pids.items() if len(s) > 1}
    amb_name = set()
    for p in pid_ids:
        if name_n.get(p, 1) < 2:
            continue
        for a in pid_ids[p]:
            if any(i in amb_iv for i, _, _ in per[(p, a)]):
                amb_name.add(p)

    plan, dropped = [], []
    for (pid, aid), v in sorted(per.items()):
        if pid in amb_person:
            dropped.append((pid, aid, "multiple_asap_persons_same_name")); continue
        if pid in amb_name:
            dropped.append((pid, aid, "multiple_drafted_players_same_name")); continue
        for iid, date, title in v:
            plan.append((pid, aid, iid, date, title))
    return plan, dropped, amb_person, amb_name


def main():
    plan, dropped, amb_person, amb_name = build_plan()
    need = collections.defaultdict(set)      # interview_id -> {asap_id}
    for pid, aid, iid, date, title in plan:
        need[iid].add(aid)
    print("eligible (pid,interview) pairs: %d ; unique interviews: %d" %
          (len(plan), len(need)), flush=True)
    print("pids dropped as ambiguous: %d person-level, %d name-level" %
          (len(amb_person), len(amb_name)), flush=True)
    with open(os.path.join(HERE, "unmatched.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["pid", "asap_id", "reason"])
        w.writerows(dropped)

    done = set()
    if os.path.exists(DONE):
        done = set(open(DONE).read().split())
    todo = [i for i in sorted(need, key=int) if i not in done]
    print("interviews to fetch: %d (cached %d)" % (len(todo), len(done)), flush=True)

    df = open(DONE, "a")
    for k, iid in enumerate(todo):
        h = fetch("http://www.asapsports.com/show_interview.php?id=%s" % iid)
        if h is None:
            continue
        recs = []
        for aid in sorted(need[iid]):
            p = parse_iv.extract_for(h, aid)
            recs.append({"iv": iid, "asap": aid, "date": p["date"],
                         "event": p["event"], "is_speaker": p["is_speaker"],
                         "n_para": p["n_answer_paras"], "n_turns": p["n_turns"], "ok": p["ok"],
                         "n_spk": len(p["speakers"]), "text": p["text"]})
        with gzip.open(ANS, "at", encoding="utf-8") as g:
            for r in recs:
                g.write(json.dumps(r) + "\n")
        df.write(iid + "\n"); df.flush()
        if k % 100 == 0:
            print("%d/%d iv=%s words=%s" % (k, len(todo), iid,
                  sum(len(r["text"].split()) for r in recs)), flush=True)
    df.close()
    print("stage4 done", flush=True)


if __name__ == "__main__":
    main()

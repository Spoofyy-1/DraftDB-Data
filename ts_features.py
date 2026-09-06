"""Team-season facts (coach, poll rank, tournament) -> pid-keyed ts_* features; coach pipeline computed walk-forward
(coach's prior draftees from classes <= y-6 with complete outcomes)."""
import json,csv,glob,gzip,re,collections,unicodedata,statistics as st
H="/Users/kennakao/Downloads/nba_redraft_handoff"
def norm(s): s=unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower(); s=re.sub(r"\b(jr|sr|ii|iii|iv)\b","",s); return re.sub(r"[^a-z ]","",s).strip()
def fl(v):
    try: return float(v)
    except: return None
TS=json.load(open("wiki_raw/_teamseasons.json"))
COLS=["player_name","team","conf","GP","Min_per","ORtg","usg","eFG","TS_per","ORB_per","DRB_per","AST_per","TO_per","FTM","FTA","FT_per","twoPM","twoPA","twoP_per","TPM","TPA","TP_per","blk_per","stl_per","ftr","yr","ht","num","porpag","adjoe","pfr","year","tpid"]
rows=collections.defaultdict(list)
for fp in sorted(glob.glob("tracking_raw/torvik_*.csv.gz")):
    for r in csv.reader(gzip.open(fp,"rt",errors="ignore")):
        if len(r)<34: continue
        d=dict(zip(COLS,r[:33])); d["_year"]=int(fl(d.get("year")) or 0); rows[norm(d["player_name"])].append(d)
ids=[r for r in csv.DictReader(open(f"{H}/identity_KEEP_SEPARATE/tabular_names.csv"))]
outcome={r["pid"]:(int(float(r["draft_year"])),fl(r.get("y_early_war"))) for r in csv.DictReader(open(f"{H}/data/train_2000_2018.csv")) if fl(r.get("y_early_war")) is not None}
ROUND={"national champion":7,"championship game":6,"final four":5,"elite eight":4,"sweet sixteen":3,"second round":2,"round of 32":2,"first round":1,"round of 64":1,"first four":0.5}
def tourney_round(txt):
    t=(txt or "").lower()
    for k,v in ROUND.items():
        if k in t: return v
    return 0 if t else None
team_of={}; coach_of={}; feats={}
for t in ids:
    dy=int(float(t["draft_year"]))
    if dy<2010: continue
    cand=[d for d in rows.get(norm(t["player_name"]),[]) if d["_year"]<=dy]
    if not cand: continue
    last=max(cand,key=lambda d:(d["_year"],fl(d.get("Min_per")) or 0))
    if dy-last["_year"]>1: continue
    key=f"{last['team'].strip()}|{last['_year']}"; ib=TS.get(key)
    if not ib or ib.get("status")!="ok": continue
    coach=re.sub(r"\(.*?\)|\|.*","",ib.get("coach","")).strip(); coach_of[t["pid"]]=norm(coach); team_of[t["pid"]]=key
    f=dict(pid=t["pid"],ts_ncaa_round=tourney_round(ib.get("result") or ib.get("tourney")),ts_in_ncaa=int(bool(re.search(r"ncaa",(ib.get("tourney") or "").lower()))),
           ts_conf_champ=int(bool(ib.get("champion"))),ts_ap_rank=fl(re.sub(r"[^\d.]","",ib.get("aprank",""))[:2] or None) if ib.get("aprank") else None)
    m=re.search(r"(\d+)\s*[–-]\s*(\d+)",ib.get("record","") or ""); 
    if m: f["ts_win_pct"]=round(int(m.group(1))/max(1,int(m.group(1))+int(m.group(2))),3)
    feats[t["pid"]]=f
# coach pipeline (walk-forward): the coach's prior draftees with complete 5-season outcomes by draft night
year={r["pid"]:int(float(r["draft_year"])) for r in ids}
for pid,f in feats.items():
    y=year[pid]; ch=coach_of.get(pid)
    if not ch: continue
    hist=[outcome[q][1] for q,cq in coach_of.items() if cq==ch and q in outcome and outcome[q][0]<=y-6]
    f["ts_coach_prev_n"]=len(hist)
    if hist: f["ts_coach_prev_mean_war5"]=round(st.mean(hist),3); f["ts_coach_prev_hit_rate"]=round(sum(1 for w in hist if w>=6)/len(hist),3)
cols=["pid"]+sorted({k for r in feats.values() for k in r if k!="pid"})
with open("ts_features.csv","w",newline="") as fh:
    w=csv.DictWriter(fh,fieldnames=cols); w.writeheader(); [w.writerow(r) for r in feats.values()]
print("team-season features:",len(feats),"cols",len(cols),"| coaches:",len(set(coach_of.values())))

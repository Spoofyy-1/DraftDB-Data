"""Assemble the 'weird data' patch (pid-keyed, no names): wp_* attention, txt_* rule-based text, traj_* improvement,
tv_* Torvik, mock_* momentum, prog_* program pipeline (walk-forward safe), misc_* (birth quarter, prep academy, hometown).
Output upload/weird_patch_{train,test}.csv. Idempotent; run again as collectors finish."""
import csv,glob,json,re,os,collections,unicodedata,statistics as st
H="/Users/kennakao/Downloads/nba_redraft_handoff"
def fl(v):
    try: return float(v)
    except: return None
def norm(s): return re.sub(r"[^a-z ]","",unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower()).strip()
split={}; year={}; age={}
TR=list(csv.DictReader(open(f"{H}/data/train_2000_2018.csv")))
for r in TR:
    if 2000<=int(float(r["draft_year"]))<=2018: split[r["pid"]]="train"; year[r["pid"]]=int(float(r["draft_year"])); age[r["pid"]]=fl(r.get("bio_age_at_draft"))
for fp in glob.glob(f"{H}/data/tests/test_*_inputs.csv"):
    yr=int(re.search(r"test_(\d{4})",fp).group(1))
    for r in csv.DictReader(open(fp)): split[r["pid"]]="test"; year[r["pid"]]=yr; age[r["pid"]]=fl(r.get("bio_age_at_draft"))
F=collections.defaultdict(dict)
# ---- attention + infobox
PREP=re.compile(r"img academy|montverde|oak hill|sunrise christian|findlay prep|la lumiere|prolific prep|huntington prep|brewster|wasatch|nba academy|overtime elite|link academy|dream city",re.I)
college_of={}
for fp in glob.glob("wiki_raw/attn_*.json"):
    d=json.load(open(fp)); pid=d["pid"]
    if pid not in split: continue
    f=F[pid]; f["wp_exists"]=d.get("wp_exists",0)
    for k in("wp_created_days_before","wp_revs_pre","wp_revs_90d","wp_revs_365d","wp_editors_90d","wp_editors_pre","wp_size_pre"):
        if d.get(k) is not None: f[k]=d[k]
    ib=d.get("infobox") or {}
    hs=ib.get("high_school",""); f["misc_prep"]=int(bool(PREP.search(hs or "")))
    bp=re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]",r"\1",ib.get("birth_place","") or "")
    f["misc_born_usa"]=int(bool(re.search(r"U\.S\.|United States|, [A-Z]{2}$|Texas|California|Florida|Georgia|Illinois|Ohio|New York|Michigan|Indiana|North Carolina|Virginia|Maryland|New Jersey|Pennsylvania|Tennessee|Arizona|Washington|Minnesota|Wisconsin|Missouri|Louisiana|Alabama|Mississippi|Kentucky|Oregon|Nevada|Utah|Colorado|Oklahoma|Kansas|Arkansas|Massachusetts|Connecticut|Iowa|Nebraska|South Carolina",bp))) if bp else None
    c=ib.get("college","")
    if c:
        teams=re.findall(r"\[\[([^|\]]*)",c) or [c]; college_of[pid]=norm(re.sub(r" men's basketball","",teams[0]))
# ---- program pipeline (walk-forward: only classes whose 5 seasons were complete by draft night, i.e. <= y-6)
outcome={}
for r in TR:
    if fl(r.get("y_early_war")) is not None: outcome[r["pid"]]=(int(float(r["draft_year"])),fl(r["y_early_war"]),r.get("actual_pick") not in("","nan",None))
for pid,prog in college_of.items():
    y=year[pid]; hist=[(outcome[q][1],outcome[q][2]) for q,pq in college_of.items() if q in outcome and pq==prog and outcome[q][0]<=y-6 and outcome[q][0]>=y-16]
    F[pid]["prog_prev_n"]=len(hist)
    if hist: F[pid]["prog_prev_mean_war5"]=round(st.mean(w for w,_ in hist),3); F[pid]["prog_prev_hit_rate"]=round(sum(1 for w,_ in hist if w>=6)/len(hist),3)
# ---- text, trajectory, torvik, mock
def merge(fp,prefix_ok):
    if not os.path.exists(fp): return 0
    n=0
    for r in csv.DictReader(open(fp)):
        if r["pid"] in split:
            for k,v in r.items():
                if k!="pid" and v not in("","None") and k.startswith(prefix_ok): F[r["pid"]][k]=v
            n+=1
    return n
print("text:",merge("txt_features.csv","txt_"),"traj:",merge("traj_features.csv","traj_"),"torvik:",merge("tv_features.csv","tv_"),"torvik2:",merge("tv2_features.csv","tv_"),"teamseason:",merge("ts_features.csv","ts_"),"mock:",merge("mock_features.csv","mock_"),"rsci:",merge("rsci_features.csv",("rsci_","hs_")),"trends:",merge("gt_features.csv","gt_"))
# ---- misc: birth quarter from age (fallback when no Torvik birthdate), hometown state code
STATES={s:i+1 for i,s in enumerate("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())}
for pid in list(F)+[p for p in split if p not in F]:
    f=F[pid]; a=age.get(pid)
    bm=fl(f.get("tv_birth_month"))
    if bm is None and a is not None: bm=int(round(12*(1-(a-int(a)))))%12 or 12
    if bm: f["misc_birth_month"]=int(bm); f["misc_birth_q"]=(int(bm)-1)//3+1
    if f.get("tv_home_state"): f["tv_home_state_code"]=STATES.get(f["tv_home_state"],0); del f["tv_home_state"]
    f.setdefault("wp_exists",0)
for sp in("train","test"):
    rows=[dict(pid=p,**F[p]) for p in split if split[p]==sp and F.get(p)]
    cols=["pid"]+sorted({k for r in rows for k in r if k!="pid"})
    with open(f"upload/weird_patch_{sp}.csv","w",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=cols); w.writeheader(); [w.writerow({c:r.get(c,"") for c in cols}) for r in rows]
    print(sp,"rows",len(rows),"cols",len(cols),"| blocks:",collections.Counter(c.split("_")[0] for c in cols if c!="pid"))

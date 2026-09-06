"""Post-draft G League outcomes per drafted/undrafted prospect (label-side data, TRAINING classes only 2000-2018 + a copy for
tests kept local). From gleague_raw/gl_{base,advanced}_{season}.json. Season i after draft y = G League season starting in
y+i-1 (draft in June y -> season y/y+1 is i=1). Name match on normalized names; ambiguity resolved by age consistency."""
import json,glob,csv,re,unicodedata,collections,os
H="/Users/kennakao/Downloads/nba_redraft_handoff"
def norm(s): return re.sub(r"\s+"," ",re.sub(r"[^a-z ]","",unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower().replace(".",""))).strip()
def strip_suffix(n): return re.sub(r"\b(jr|sr|ii|iii|iv)\b","",n).replace("  "," ").strip()
ids=list(csv.DictReader(open(f"{H}/identity_KEEP_SEPARATE/tabular_names.csv")))
age={}
for r in csv.DictReader(open(f"{H}/data/train_2000_2018.csv")):
    try: age[r["pid"]]=float(r.get("bio_age_at_draft") or "nan")
    except: pass
for fp in glob.glob(f"{H}/data/tests/test_*_inputs.csv"):
    for r in csv.DictReader(open(fp)):
        try: age[r["pid"]]=float(r.get("bio_age_at_draft") or "nan")
        except: pass
by=collections.defaultdict(list)
for r in ids: by[strip_suffix(norm(r["player_name"]))].append((int(float(r["draft_year"])),r["pid"]))
def rows(fp):
    d=json.load(open(fp)); rs=d["resultSets"][0]; h=rs["headers"]; return [dict(zip(h,x)) for x in rs["rowSet"]]
out=collections.defaultdict(dict); matched=set(); nrows=0
for fp in sorted(glob.glob("gleague_raw/gl_base_*.json")):
    s=re.search(r"(\d{4})-\d\d",fp).group(1); y0=int(s); adv={r["PLAYER_ID"]:r for r in rows(fp.replace("gl_base_","gl_advanced_"))} if os.path.exists(fp.replace("gl_base_","gl_advanced_")) else {}
    for r in rows(fp):
        nrows+=1; n=strip_suffix(norm(r["PLAYER_NAME"])); cands=by.get(n,[])
        if not cands: continue
        ok=[]
        for dy,pid in cands:
            i=y0-dy+1
            if 1<=i<=5:
                a=age.get(pid); ga=r.get("AGE")
                if a and ga and abs((a+i-1)-float(ga))>2.5: continue
                ok.append((i,pid))
        if len(ok)!=1: continue
        i,pid=ok[0]; A=adv.get(r["PLAYER_ID"],{}); mn=float(r.get("MIN") or 0)
        f=out[pid]; f[f"y_gl_s{i}_min"]=round(mn,1); f[f"y_gl_s{i}_gp"]=r.get("GP")
        if mn>0: f[f"y_gl_s{i}_pts36"]=round(36*float(r.get("PTS") or 0)/mn,2); f[f"y_gl_s{i}_prod36"]=round(36*(float(r.get("PTS") or 0)+float(r.get("REB") or 0)+float(r.get("AST") or 0)+float(r.get("STL") or 0)+float(r.get("BLK") or 0)-float(r.get("TOV") or 0))/mn,2)
        if A: f[f"y_gl_s{i}_pie"]=A.get("PIE"); f[f"y_gl_s{i}_net"]=A.get("NET_RATING"); f[f"y_gl_s{i}_ts"]=A.get("TS_PCT"); f[f"y_gl_s{i}_usg"]=A.get("USG_PCT")
        matched.add(pid)
cols=["pid"]+sorted({k for f in out.values() for k in f})
w=csv.DictWriter(open("gl_labels.csv","w"),fieldnames=cols); w.writeheader()
for pid,f in out.items(): w.writerow(dict(pid=pid,**f))
dy={r["pid"]:int(float(r["draft_year"])) for r in ids}
print(f"G League rows scanned {nrows}; players matched {len(matched)}; by draft year:", " ".join(f"{y}:{n}" for y,n in sorted(collections.Counter(dy[p] for p in matched).items())))

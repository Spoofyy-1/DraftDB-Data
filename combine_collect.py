"""NBA Draft Combine measurements + athletic tests + shooting drills, 2000-2025 (stats API via the G League host, LeagueID=00).
SeasonYear 'YYYY-YY' <-> draft year YYYY. Cached per year. Then builds cmb_features.csv (pid-keyed) by name + draft-year match and
an anthro patch (bio_combine_* fills for players missing them)."""
import json,os,time,subprocess,csv,re,unicodedata,collections,glob
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
H="/Users/kennakao/Downloads/nba_redraft_handoff"
def get(url,out):
    subprocess.run(["curl","-s","--http1.1","-m","60","-H",f"User-Agent: {UA}","-H","Referer: https://www.nba.com/","-H","Origin: https://www.nba.com","-H","x-nba-stats-origin: stats","-H","x-nba-stats-token: true","-H","Accept: application/json, text/plain, */*","-o",out,url])
    return os.path.getsize(out) if os.path.exists(out) else 0
for y in range(2000,2026):
    out=f"combine_raw/combine_{y}.json"
    if os.path.exists(out) and os.path.getsize(out)>500: continue
    n=get(f"https://stats.gleague.nba.com/stats/draftcombinestats?LeagueID=00&SeasonYear={y}-{str(y+1)[2:]}",out)
    try: rows=len(json.load(open(out))["resultSets"][0]["rowSet"])
    except Exception: rows=-1
    print(y,"bytes",n,"rows",rows,flush=True); time.sleep(2)
def norm(s): return re.sub(r"\s+"," ",re.sub(r"[^a-z ]","",unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower().replace(".",""))).strip()
def strip_suffix(n): return re.sub(r"\b(jr|sr|ii|iii|iv)\b","",n).replace("  "," ").strip()
ids=list(csv.DictReader(open(f"{H}/identity_KEEP_SEPARATE/tabular_names.csv")))
by=collections.defaultdict(list)
for r in ids: by[strip_suffix(norm(r["player_name"]))].append((int(float(r["draft_year"])),r["pid"]))
def made(v):
    m=re.match(r"\s*(\d+)\s*-\s*(\d+)",str(v or ""))
    return (int(m.group(1)),int(m.group(2))) if m else (None,None)
def fl(v):
    try: return float(v)
    except: return None
feat={}; anth={}; matched=0; total=0
for fp in sorted(glob.glob("combine_raw/combine_*.json")):
    y=int(re.search(r"(\d{4})",fp).group(1))
    try: rs=json.load(open(fp))["resultSets"][0]
    except Exception: continue
    hdr=rs["headers"]
    for row in rs["rowSet"]:
        r=dict(zip(hdr,row)); total+=1; n=strip_suffix(norm(r.get("PLAYER_NAME") or f"{r.get('FIRST_NAME','')} {r.get('LAST_NAME','')}"))
        c=[(dy,pid) for dy,pid in by.get(n,[]) if dy==y] or [(dy,pid) for dy,pid in by.get(n,[]) if y<=dy<=y+1]
        if len(c)!=1: continue
        pid=c[0][1]; matched+=1; f={}
        for k,col in (("cmb_body_fat","BODY_FAT_PCT"),("cmb_hand_len","HAND_LENGTH"),("cmb_hand_width","HAND_WIDTH"),("cmb_stand_vert","STANDING_VERTICAL_LEAP"),("cmb_max_vert","MAX_VERTICAL_LEAP"),("cmb_lane_agility","LANE_AGILITY_TIME"),("cmb_mod_lane_agility","MODIFIED_LANE_AGILITY_TIME"),("cmb_sprint","THREE_QUARTER_SPRINT"),("cmb_bench","BENCH_PRESS")):
            v=fl(r.get(col)); 
            if v is not None: f[k]=v
        for k,cols in (("cmb_spot15",[c for c in hdr if c.startswith("SPOT_FIFTEEN")]),("cmb_spotcol",[c for c in hdr if c.startswith("SPOT_COLLEGE")]),("cmb_spotnba",[c for c in hdr if c.startswith("SPOT_NBA")]),("cmb_offdrib",[c for c in hdr if c.startswith("OFF_DRIB")]),("cmb_onmove",[c for c in hdr if c.startswith("ON_MOVE")])):
            m=a=0; ok=False
            for col in cols:
                mm,aa=made(r.get(col))
                if mm is not None: m+=mm; a+=aa; ok=True
            if ok and a>0: f[k+"_pct"]=round(m/a,3); f[k+"_att"]=a
        hw=fl(r.get("HEIGHT_WO_SHOES")); ws=fl(r.get("WINGSPAN")); rc=fl(r.get("STANDING_REACH")); wt=fl(r.get("WEIGHT")); hs=fl(r.get("HEIGHT_W_SHOES"))
        if hw and ws: f["cmb_wing_minus_height"]=round(ws-hw,2)
        if hw and rc: f["cmb_reach_minus_height"]=round(rc-hw,2)
        if wt and hw: f["cmb_bmi"]=round(703*wt/(hw*hw),2)
        if f: feat[pid]=f
        a={}
        if hs: a["bio_combine_height_in"]=hs
        if wt: a["bio_combine_weight_lb"]=wt
        if ws: a["bio_combine_wingspan_in"]=ws
        if rc: a["bio_combine_reach_in"]=rc
        if a: anth[pid]=a
cols=["pid"]+sorted({k for f in feat.values() for k in f})
w=csv.DictWriter(open("cmb_features.csv","w"),fieldnames=cols); w.writeheader()
for pid,f in feat.items(): w.writerow(dict(pid=pid,**f))
cols=["pid","bio_combine_height_in","bio_combine_weight_lb","bio_combine_wingspan_in","bio_combine_reach_in"]
w=csv.DictWriter(open("cmb_anthro.csv","w"),fieldnames=cols); w.writeheader()
for pid,a in anth.items(): w.writerow(dict(pid=pid,**a))
dy={r["pid"]:int(float(r["draft_year"])) for r in ids}
print(f"combine rows {total}, matched {matched} pids; features {len(feat)}, anthro {len(anth)}; by year:", " ".join(f"{y}:{n}" for y,n in sorted(collections.Counter(dy[p] for p in feat).items())))

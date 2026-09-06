"""Torvik advanced player table (public CSV per season) -> per-prospect features: shot diet (rim/mid/dunk), foul rate,
possession-adjusted impact (porpag, dporpag, stops, gbpm), role, exact birthdate, hometown, recruiting rank, and
multi-season trajectories. Matched by normalized name (+team when ambiguous) on the Mac; output pid-keyed tv_features.csv."""
import csv,glob,re,json,unicodedata,collections,datetime as dt
H="/Users/kennakao/Downloads/nba_redraft_handoff"
COLS=["player_name","team","conf","GP","Min_per","ORtg","usg","eFG","TS_per","ORB_per","DRB_per","AST_per","TO_per","FTM","FTA","FT_per","twoPM","twoPA","twoP_per","TPM","TPA","TP_per","blk_per","stl_per","ftr","yr","ht","num","porpag","adjoe","pfr","year","tpid","hometown","rec_rank","ast_tov","rimmade","rimatt","midmade","midatt","rim_pct","mid_pct","dunkmade","dunkatt","dunk_pct","pick","drtg","adrtg","dporpag","stops","bpm","obpm","dbpm","gbpm","mp","ogbpm","dgbpm","oreb","dreb","treb","ast","stl","blk","pts","role","x65","birthdate"]
DRAFT={2010:"2010-06-24",2011:"2011-06-23",2012:"2012-06-28",2013:"2013-06-27",2014:"2014-06-26",2015:"2015-06-25",2016:"2016-06-23",2017:"2017-06-22",2018:"2018-06-21",2019:"2019-06-20",2020:"2020-11-18",2021:"2021-07-29",2022:"2022-06-23",2023:"2023-06-22",2024:"2024-06-26",2025:"2025-06-25",2026:"2026-06-24"}
def norm(s): s=unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower(); s=re.sub(r"\b(jr|sr|ii|iii|iv)\b","",s); return re.sub(r"[^a-z ]","",s).strip()
def fl(v):
    try: return float(v)
    except: return None
rows=collections.defaultdict(list)   # norm name -> list of season dicts
for fp in sorted(glob.glob("tracking_raw/torvik_*.csv")):
    for r in csv.reader(open(fp,errors="ignore")):
        if len(r)<64: continue
        d=dict(zip(COLS,r)); d["_year"]=int(fl(d.get("year")) or fp[-8:-4]); rows[norm(d["player_name"])].append(d)
print("torvik player-seasons:",sum(len(v) for v in rows.values()),"names:",len(rows))
ids=list(csv.DictReader(open(f"{H}/identity_KEEP_SEPARATE/tabular_names.csv")))
# college affiliation from the attention collector's infobox (optional disambiguation)
college={}
for fp in glob.glob("wiki_raw/attn_*.json"):
    d=json.load(open(fp)); c=(d.get("infobox") or {}).get("college","")
    if c: college[d["pid"]]=norm(re.sub(r"\(.*?\)","",re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]",r"\1",c)))
ROLE={"Pure PG":1,"Scoring PG":2,"Combo G":3,"Wing G":4,"Wing F":5,"Stretch 4":6,"PF/C":7,"C":8}
def state_of(h):
    m=re.search(r",\s*([A-Z]{2})\s*$",h or ""); return m.group(1) if m else None
out=[]; c=collections.Counter()
for t in ids:
    dy=int(float(t["draft_year"]))
    if dy<2010: continue
    cand=[d for d in rows.get(norm(t["player_name"]),[]) if d["_year"]<=dy]
    if not cand: c["no_match"]+=1; continue
    col=college.get(t["pid"],"")
    if col and len({d["team"] for d in cand})>1:
        pref=[d for d in cand if norm(d["team"]).split()[0] in col or col.split()[0] in norm(d["team"])]
        if pref: cand=pref
    # keep the player whose last season is the draft year (or the year before), by Torvik id
    last=max(cand,key=lambda d:(d["_year"],fl(d.get("mp")) or 0)); tp=last.get("tpid"); seasons=sorted([d for d in cand if d.get("tpid")==tp],key=lambda d:d["_year"])
    if dy-last["_year"]>1: c["stale"]+=1; continue
    L=seasons[-1]; P=seasons[-2] if len(seasons)>1 else None; c["ok"]+=1
    f=dict(pid=t["pid"],tv_seasons=len(seasons),tv_gap=dy-L["_year"])
    for k,src in [("min_per","Min_per"),("ortg","ORtg"),("usg","usg"),("efg","eFG"),("ts","TS_per"),("orb","ORB_per"),("drb","DRB_per"),("ast_pct","AST_per"),("to_pct","TO_per"),("ftr","ftr"),("pfr","pfr"),("porpag","porpag"),("adjoe","adjoe"),("drtg","drtg"),("adrtg","adrtg"),("dporpag","dporpag"),("stops","stops"),("bpm","bpm"),("obpm","obpm"),("dbpm","dbpm"),("gbpm","gbpm"),("ogbpm","ogbpm"),("dgbpm","dgbpm"),("mp","mp"),("ast_tov","ast_tov"),("rec_rank","rec_rank"),("pts","pts"),("gp","GP")]:
        f["tv_"+k]=fl(L.get(src))
    rim,mid,tpa=fl(L.get("rimatt")) or 0,fl(L.get("midatt")) or 0,fl(L.get("TPA")) or 0; tot=rim+mid+tpa
    f.update(tv_rim_share=round(rim/tot,3) if tot else None,tv_mid_share=round(mid/tot,3) if tot else None,tv_three_share=round(tpa/tot,3) if tot else None,tv_rim_pct=fl(L.get("rim_pct")),tv_mid_pct=fl(L.get("mid_pct")),
             tv_dunk_share=round((fl(L.get("dunkatt")) or 0)/rim,3) if rim else None,tv_dunks_pg=round((fl(L.get("dunkmade")) or 0)/(fl(L.get("GP")) or 1),3),
             tv_role=ROLE.get(L.get("role","").strip()),tv_yr={"Fr":1,"So":2,"Jr":3,"Sr":4}.get(L.get("yr","").strip()),tv_home_state=state_of(L.get("hometown")),tv_home_intl=int(bool(L.get("hometown")) and not state_of(L.get("hometown"))))
    b=L.get("birthdate","")
    if re.match(r"\d{4}-\d{2}-\d{2}",b or ""):
        bd=dt.datetime.strptime(b,"%Y-%m-%d"); f["tv_birth_month"]=bd.month; f["tv_age_exact"]=round((dt.datetime.strptime(DRAFT[dy],"%Y-%m-%d")-bd).days/365.25,2)
    if P:
        for k,src in [("usg","usg"),("ortg","ORtg"),("bpm","bpm"),("min_per","Min_per"),("efg","eFG"),("ts","TS_per"),("ast_pct","AST_per"),("ftr","ftr"),("adjoe","adjoe"),("adrtg","adrtg")]:
            a,b2=fl(L.get(src)),fl(P.get(src)); f["tv_d_"+k]=round(a-b2,3) if a is not None and b2 is not None else None
        bpms=[fl(s.get("bpm")) for s in seasons if fl(s.get("bpm")) is not None]
        if len(bpms)>=2: xs=list(range(len(bpms))); mx=sum(xs)/len(xs); my=sum(bpms)/len(bpms); f["tv_slope_bpm"]=round(sum((x-mx)*(y-my) for x,y in zip(xs,bpms))/sum((x-mx)**2 for x in xs),3)
        f["tv_first_bpm"]=fl(seasons[0].get("bpm")); f["tv_bpm_is_peak"]=int(fl(L.get("bpm"))==max(bpms)) if bpms else None
    out.append(f)
cols=["pid"]+sorted({k for r in out for k in r if k!="pid"})
with open("tv_features.csv","w",newline="") as fh:
    w=csv.DictWriter(fh,fieldnames=cols); w.writeheader(); [w.writerow(r) for r in out]
print("torvik features:",dict(c),"cols",len(cols))

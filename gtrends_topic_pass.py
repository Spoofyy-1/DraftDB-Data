"""Second pass: for records queried by raw name, ask Trends for a topic entity (basketball player) with slow pacing; when one
exists, re-query with the entity mid so common names stop mixing with namesakes. Overwrites the record with kind=topic."""
import json,os,glob,time,random,sys,csv,warnings; warnings.filterwarnings("ignore")
sys.path.insert(0,os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages"))
from pytrends.request import TrendReq
import datetime as dt
src=open("gtrends_collect.py").read(); exec(src[:src.index("pt=TrendReq")])   # reuse H, DRAFT, ids
def day_before(d): return (dt.datetime.strptime(d,"%Y-%m-%d")-dt.timedelta(days=1)).strftime("%Y-%m-%d")
name_of={r["pid"]:r["player_name"] for r in ids}
pt=TrendReq(hl="en-US",tz=0,timeout=(10,30)); n=0; hits=0; r429=0
for f in sorted(glob.glob("trends_raw/gt_*.json")):
    rec=json.load(open(f))
    if rec.get("kind")=="topic" or rec.get("topic_checked"): continue
    pid=rec["pid"]; name=name_of.get(pid)
    if not name: continue
    try:
        sug=pt.suggestions(name); ent=[s for s in sug if "basketball" in (s.get("type","")).lower()]
        rec["topic_checked"]=1
        if ent:
            time.sleep(3+random.random()*2); dy=rec["draft_year"]
            pt.build_payload([ent[0]["mid"],"NBA draft"],timeframe=f"{dy}-01-01 {day_before(DRAFT[dy])}",geo="US"); df=pt.interest_over_time()
            if df is not None and len(df):
                p=df[ent[0]["mid"]].astype(float); a=df["NBA draft"].astype(float); last30=p.tail(30); first90=p.head(90)
                rec.update(status="ok",kind="topic",topic_type=ent[0]["type"],gt_days=len(p),gt_mean=round(float(p.mean()),3),gt_anchor_mean=round(float(a.mean()),3),
                    gt_ratio=round(float(p.mean()/max(1e-6,a.mean())),4),gt_peak_ratio=round(float(p.max()/max(1.0,a.max())),4),gt_last30_ratio=round(float(last30.mean()/max(1e-6,a.tail(30).mean())),4),
                    gt_trend=round(float((last30.mean()+1)/(first90.mean()+1)),3),gt_zero_share=round(float((p==0).mean()),3),gt_days_above10=int((p>=10).sum())); hits+=1
        json.dump(rec,open(f,"w")); n+=1
        time.sleep(6+random.random()*4)
    except Exception as e:
        msg=repr(e)[:100]
        if "429" in msg: r429+=1; time.sleep(120*min(r429,5))
        else: time.sleep(5)
        if r429>=15: print("suggestions endpoint keeps 429ing; stopping topic pass",flush=True); break
    if n%25==0 and n: print(f"topic pass {n} checked, {hits} upgraded, 429s {r429}",flush=True)
print("TOPIC_DONE",n,hits,flush=True)

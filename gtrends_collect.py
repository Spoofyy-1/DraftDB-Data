"""Google Trends pre-draft interest (pytrends). For each drafted player 2010-2026: daily US interest from Jan 1 of the draft
year to the day before the draft, queried together with the anchor term "NBA draft" so values are comparable across players.
Uses the Trends topic entity when Google suggests a basketball-player entity for the name (disambiguates common names).
Cached per pid; gentle pacing with backoff on 429s. Names stay on the Mac; output is pid-keyed."""
import json,os,time,csv,random,sys
sys.path.insert(0,os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages"))
import warnings; warnings.filterwarnings("ignore")
from pytrends.request import TrendReq
H="/Users/kennakao/Downloads/nba_redraft_handoff"
DRAFT={2010:"2010-06-24",2011:"2011-06-23",2012:"2012-06-28",2013:"2013-06-27",2014:"2014-06-26",2015:"2015-06-25",2016:"2016-06-23",2017:"2017-06-22",2018:"2018-06-21",2019:"2019-06-20",2020:"2020-11-18",2021:"2021-07-29",2022:"2022-06-23",2023:"2023-06-22",2024:"2024-06-26",2025:"2025-06-25",2026:"2026-06-24"}
ids=[r for r in csv.DictReader(open(f"{H}/identity_KEEP_SEPARATE/tabular_names.csv")) if r.get("actual_pick") not in("","nan",None) and 2010<=int(float(r["draft_year"]))<=2026]
ids.sort(key=lambda r:-int(float(r["draft_year"])))
pt=TrendReq(hl="en-US",tz=0,timeout=(10,30)); print("players:",len(ids),flush=True)
def day_before(d):
    import datetime as dt; return (dt.datetime.strptime(d,"%Y-%m-%d")-dt.timedelta(days=1)).strftime("%Y-%m-%d")
n=0; fails=0
for r in ids:
    pid=r["pid"]; out=f"trends_raw/gt_{pid}.json"
    if os.path.exists(out): continue
    dy=int(float(r["draft_year"])); name=r["player_name"]; rec=dict(pid=pid,draft_year=dy)
    for attempt in range(4):
        try:
            term=name; kind="name"
            try:
                sug=pt.suggestions(name); ent=[s for s in sug if "basketball" in (s.get("type","")).lower()]
                if ent: term=ent[0]["mid"]; kind="topic"; rec["topic_type"]=ent[0]["type"]
            except Exception: pass
            time.sleep(1.5+random.random())
            pt.build_payload([term,"NBA draft"],timeframe=f"{dy}-01-01 {day_before(DRAFT[dy])}",geo="US")
            df=pt.interest_over_time()
            if df is None or len(df)==0: rec.update(status="empty",kind=kind); break
            p=df[term].astype(float); a=df["NBA draft"].astype(float); n_days=len(p)
            last30=p.tail(30); first90=p.head(90)
            rec.update(status="ok",kind=kind,gt_days=n_days,gt_mean=round(float(p.mean()),3),gt_anchor_mean=round(float(a.mean()),3),gt_ratio=round(float(p.mean()/max(1e-6,a.mean())),4),
                       gt_peak_ratio=round(float(p.max()/max(1.0,a.max())),4),gt_last30_ratio=round(float(last30.mean()/max(1e-6,a.tail(30).mean())),4),
                       gt_trend=round(float((last30.mean()+1)/(first90.mean()+1)),3),gt_zero_share=round(float((p==0).mean()),3),gt_days_above10=int((p>=10).sum()))
            break
        except Exception as e:
            msg=repr(e)[:120]; rec.update(status="err",err=msg)
            if "429" in msg or "Too Many" in msg: time.sleep(60*(attempt+1)); fails+=1
            else: time.sleep(5)
    json.dump(rec,open(out,"w")); n+=1
    time.sleep(2.5+random.random()*2)
    if n%25==0: print(f"{n} done, 429s {fails}",flush=True)
    if fails>=12: print("too many 429s, stopping for now",flush=True); break
print("GT_DONE",flush=True)

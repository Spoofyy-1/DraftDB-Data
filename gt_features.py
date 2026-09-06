"""Google Trends pre-draft interest -> pid-keyed gt_* features (from trends_raw/gt_*.json). Adds class-relative percentile of
the anchored ratio among players of the same draft year that have data. Rerun as the collector fills in."""
import json,glob,csv,collections
recs=[json.load(open(f)) for f in glob.glob("trends_raw/gt_*.json")]
ok=[r for r in recs if r.get("status")=="ok"]
byy=collections.defaultdict(list)
for r in ok: byy[r["draft_year"]].append(r["gt_ratio"])
cols=["pid","gt_ratio","gt_peak_ratio","gt_last30_ratio","gt_trend","gt_zero_share","gt_days_above10","gt_topic","gt_class_pct"]
w=csv.DictWriter(open("gt_features.csv","w"),fieldnames=cols); w.writeheader()
for r in ok:
    ys=sorted(byy[r["draft_year"]]); pct=sum(1 for v in ys if v<r["gt_ratio"])/max(1,len(ys)-1) if len(ys)>1 else None
    w.writerow(dict(pid=r["pid"],gt_ratio=r["gt_ratio"],gt_peak_ratio=r["gt_peak_ratio"],gt_last30_ratio=r["gt_last30_ratio"],gt_trend=r["gt_trend"],
        gt_zero_share=r["gt_zero_share"],gt_days_above10=r["gt_days_above10"],gt_topic=int(r.get("kind")=="topic"),gt_class_pct=round(pct,3) if pct is not None else ""))
print("gt records:",len(recs),"ok:",len(ok),"topic-entity:",sum(1 for r in ok if r.get("kind")=="topic"),"errors:",collections.Counter(r.get("status") for r in recs))

"""Re-evaluate the FROZEN best model on the rebuilt dataset (data v3). No search, no selection: one config.
 1. walk-forward fitness (2014-2018 folds) for the frozen genome   2. ONE sealed blind scoring per season (ledgered)
 3. Wembanyama 2023 diagnostic rank + board predictions for every class -> r7/board_preds_v3.csv
Writes r7/EVAL_V3.json. Run: cd ~/nba/handoff && source ../.venv/bin/activate && python r7/eval_v3.py"""
import sys,os,json,time,numpy as np,pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,ROOT); os.chdir(ROOT)
exec(compile(open(f"{ROOT}/r7/evolve3.py").read().split("lineage=json.load(open(LIN))")[0],"defs","exec"))
DEF={"el":0,"wk":0,"ridge_alpha":30.0,"icl_topk":0,"icl_ctx":"all","resid":0,"knn":0,"cat":0,"ixc":0,"pss":0,"icl_norm":"default","icl_outlier":4.0,"icl_shuffle":"latin","labelmix":"single","hz":0,"covw":0,"risk":"mean","ridge":0,"icl_n":8}
BASE=json.load(open("BEST_MODEL.json"))["genome"]; [BASE.setdefault(k,v) for k,v in DEF.items()]
V1=dict(wf=0.3805,folds={"2014":0.428,"2015":0.401,"2016":0.235,"2017":0.493,"2018":0.400},blind_edge=0.197,ge02=4,wemby=12)
WEMBY="P144ed94c77"; t0=time.time()
print("data version:",json.load(open("data/input_columns.json")).get("version","v1"),"| inputs:",len(json.load(open("data/input_columns.json"))["inputs"]),"| ledger before:",Vt.ledger_count(),flush=True)
mf,wts=fitness(BASE); wf=float(np.mean(list(mf.values())))
print(f"WF v3 {wf:+.4f} (v1 {V1['wf']:+.4f})  folds "+" ".join(f"{y}:{v:+.3f}({v-V1['folds'][str(y)]:+.3f})" for y,v in mf.items())+f"  wts {wts}  ({time.time()-t0:.0f}s)",flush=True)
rows=blind(BASE,"V3 BEST (rebuilt data)",wts); bl=[r for r in rows if r["kind"]=="BLIND"]; e=[r["stack"]-r["draft"] for r in bl]
print(f"BLIND v3 edge {np.mean(e):+.3f} (v1 {V1['blind_edge']:+.3f}) | "+" ".join(f"{r['season']}:{x:+.3f}" for r,x in zip(bl,e))+f" | {sum(x>=0.2 for x in e)}/7 >= .2 | ledger {Vt.ledger_count()}",flush=True)
# boards + Wemby diagnostic
OPTS=opts_of(BASE); base=H.cols_for(OPTS); cols=cols_of(BASE,base); RATE=[c for c in base if c.startswith(("col_","intl_")) and not c.startswith("col_gl_")]
pr,cq=H.fit_prior(W); Btr0=H.build(W,pr,cq,OPTS); HZ=Vt.horizons(); out=[]; wr=None
for y,d0 in sorted(Vt.blind_inputs().items()):
    kk=HZ[y]; Btr,Bte=feat_tx(Btr0,H.build(d0,pr,cq,OPTS),BASE["fx"],W,d0,RATE); st=stats_of(Btr); Btr,Bte=add_feats(Btr,BASE["fx"],st),add_feats(Bte,BASE["fx"],st)
    P=member_preds(BASE,Btr,Bte,cols,W,kk if BASE["hz"] else 5); s=stack(P,Bte,BASE,wts)
    out.append(pd.DataFrame(dict(pid=d0.pid.values,season=y,k=kk,score=s)))
    if y==2023:
        order=list(d0.pid.values[np.argsort(-s)]); wr=(order.index(WEMBY)+1) if WEMBY in order else None
pd.concat(out).to_csv(f"{ROOT}/r7/board_preds_v3.csv",index=False)
print(f"wemby 2023 rank v3 #{wr} (v1 #{V1['wemby']}) | wrote r7/board_preds_v3.csv",flush=True)
res=dict(genome=BASE,wts=wts,wf=wf,folds={str(k):float(v) for k,v in mf.items()},blind_edge=float(np.mean(e)),edges={str(r["season"]):round(x,3) for r,x in zip(bl,e)},ge02=int(sum(x>=0.2 for x in e)),wemby_2023_rank=wr,ledger=Vt.ledger_count(),v1=V1,secs=round(time.time()-t0))
json.dump(res,open(f"{ROOT}/r7/EVAL_V3.json","w"),indent=1)
R=json.load(open("best_results.json")) if os.path.exists("best_results.json") else {"styles":{}}
R["styles"]["V3 BEST (rebuilt data)"]=dict(weights=wts,rows=rows,secs=res["secs"],phase="V3",genome=BASE); json.dump(R,open("best_results.json","w"),indent=1)
print("EVAL_V3_DONE",flush=True)

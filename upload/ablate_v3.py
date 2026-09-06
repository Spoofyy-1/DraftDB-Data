"""Walk-forward-only ablations of the data v3 changes (no blind scoring, no ledger entries). usage: python r7/ablate_v3.py VARIANT
VARIANTS: v3 | nonew (drop the 9 new input columns) | nointl (restore v1 intl_* rows where intl_src>=1) | nocol (undo college fills)
          noanthro (undo measurement fills in train) | v1 (v1 training frame, v1 columns)"""
import sys,os,json,time,numpy as np,pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,ROOT); os.chdir(ROOT)
import honest as H
V=sys.argv[1]; NEW=["bio_measure_src","col_basic_fill","intl_lg_adj_pts36","intl_lg_strength","intl_prev_pts36","intl_season_gap","intl_src","intl_two_minutes","intl_two_pts36"]
TR1=H._num(pd.read_csv(f"{ROOT}/data_v1/train_2000_2018.csv")).set_index("pid")
T=H.TRAIN.set_index("pid")
if V=="nonew": H.FEATS[:]=[c for c in H.FEATS if c not in NEW]
elif V=="nointl":
    m=T["intl_src"].fillna(0)>=1; cols=[c for c in T.columns if c.startswith("intl_") and c in TR1.columns]
    T.loc[m,cols]=TR1.loc[T.index[m],cols].values; print("restored intl rows:",int(m.sum()))
elif V=="nocol":
    m=T["col_basic_fill"].fillna(0)>=1; cols=[c for c in T.columns if c.startswith("col_") and c in TR1.columns]
    T.loc[m,cols]=TR1.loc[T.index[m],cols].values; T.loc[m,"col_basic_fill"]=0; print("undid college fills:",int(m.sum()))
elif V=="noanthro":
    m=T["bio_measure_src"].fillna(0)>=2; cols=[c for c in("bio_combine_wingspan_in","bio_combine_reach_in","bio_combine_height_in","bio_combine_weight_lb","bio_combine_wingspan_minus_height_in") if c in T.columns]
    T.loc[m,cols]=np.nan; T.loc[m,"bio_measure_src"]=0; print("undid measurement fills:",int(m.sum()))
elif V=="v1":
    H.FEATS[:]=[c for c in H.FEATS if c not in NEW]; T=TR1.copy()
elif V!="v3": raise SystemExit("unknown variant")
H.TRAIN=T.reset_index()
exec(compile(open(f"{ROOT}/r7/evolve3.py").read().split("lineage=json.load(open(LIN))")[0],"defs","exec"))
DEF={"el":0,"wk":0,"ridge_alpha":30.0,"icl_topk":0,"icl_ctx":"all","resid":0,"knn":0,"cat":0,"ixc":0,"pss":0,"icl_norm":"default","icl_outlier":4.0,"icl_shuffle":"latin","labelmix":"single","hz":0,"covw":0,"risk":"mean","ridge":0,"icl_n":8}
BASE=json.load(open("BEST_MODEL.json"))["genome"]; [BASE.setdefault(k,v) for k,v in DEF.items()]
t0=time.time(); mf,wts=fitness(BASE); wf=float(np.mean(list(mf.values())))
print(f"ABLATION {V:9s} WF {wf:+.4f}  folds "+" ".join(f"{y}:{v:+.3f}" for y,v in mf.items())+f"  ({time.time()-t0:.0f}s)",flush=True)

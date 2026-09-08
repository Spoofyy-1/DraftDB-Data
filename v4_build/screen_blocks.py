"""Pre-fold label screen for new blocks. Uses ONLY draft classes 2000-2011 (the gate's walk-forward folds are 2012-2018), drafted rows.
For each column: n, rho_raw = mean within-class Spearman with y_early_war_log, rho_res = same vs the residual of y on log(actual pick)
(pooled OLS on the screen years), i.e. information beyond the draft slot. Writes screen_blocks.csv and slim block CSVs."""
import pandas as pd, numpy as np, json, sys
from scipy.stats import spearmanr
PREFIXES=sys.argv[1].split(",") if len(sys.argv)>1 else ["tc_","gl2_","dp_","wt_","sc_","bb_","fy_","dv_","dis_","misc_birth"]
tr=pd.read_csv("staging_v414/train_2000_2018.csv"); ids=pd.read_csv("/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv")[["pid","actual_pick"]]
d=tr.merge(ids,on="pid",how="left"); d=d[(d.draft_year<=2011)&(d.was_drafted==1)&d.actual_pick.notna()&d.y_early_war_log.notna()].copy()
lp=np.log(d.actual_pick.clip(lower=1)); A=np.c_[np.ones(len(d)),lp]; b=np.linalg.lstsq(A,d.y_early_war_log.values,rcond=None)[0]; d["y_res"]=d.y_early_war_log-A@b
print("screen rows",len(d),"classes",d.draft_year.min(),"-",d.draft_year.max(),"| y ~ log(pick) slope",round(b[1],3))
def wcorr(col,y):
    rs=[];ws=[]
    for yr,g in d.groupby("draft_year"):
        m=g[col].notna()&g[y].notna()
        if m.sum()>=12 and g.loc[m,col].nunique()>1:
            r=spearmanr(g.loc[m,col],g.loc[m,y]).correlation
            if not np.isnan(r): rs.append(r); ws.append(m.sum())
    return (np.average(rs,weights=ws) if rs else np.nan), int(sum(ws))
rows=[]
for c in d.columns:
    if any(c.startswith(p) for p in PREFIXES):
        n=int(d[c].notna().sum())
        if n<60: rows.append((c,n,np.nan,np.nan)); continue
        r1,_=wcorr(c,"y_early_war_log"); r2,_=wcorr(c,"y_res"); rows.append((c,n,r1,r2))
S=pd.DataFrame(rows,columns=["col","n","rho_raw","rho_res"]); S["block"]=S.col.str.extract(r"^([a-z0-9]+)_")[0]; S["abs_res"]=S.rho_res.abs()
S.sort_values("abs_res",ascending=False).to_csv("screen_blocks.csv",index=False)
print(S.groupby("block").agg(cols=("col","size"),n_med=("n","median"),abs_res_med=("abs_res","median"),abs_res_max=("abs_res","max")).round(3).to_string())
print("\nTOP 40 by |rho beyond pick| (n>=150):"); print(S[S.n>=150].sort_values("abs_res",ascending=False).head(40).to_string(index=False))
# slim blocks: per block up to 10 columns with |rho_res|>=0.08 and n>=150, skipping near-duplicates (|corr|>0.9 with a kept column)
slim={}
for blk,g in S[(S.n>=150)&(S.abs_res>=0.08)].sort_values("abs_res",ascending=False).groupby("block"):
    keep=[]
    for c in g.col:
        if all(abs(d[[c,k]].corr().iloc[0,1])<0.9 for k in keep): keep.append(c)
        if len(keep)>=10: break
    slim[blk]=keep
json.dump(slim,open("slim_blocks.json","w"),indent=1); print("\nSLIM:",{k:len(v) for k,v in slim.items()}); print(json.dumps(slim,indent=0)[:2500])

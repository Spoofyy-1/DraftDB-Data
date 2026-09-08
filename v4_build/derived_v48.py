"""Derived block dv_* from columns already in data_v4 (no new sources). Fits are done on TRAIN rows only and applied to all.
 dv_length_pc1        length-size composite (Teramoto 2018): PCA-1 of height w/o shoes, standing reach, weight, wingspan, hand length
 dv_athl_pc1          power-quickness composite: PCA-1 of max/standing vertical, -lane agility, -3/4 sprint
 dv_cons_hype_resid   log consensus rank residual after production pct, age, length, position, intl  (market premium unexplained by production)
 dv_athl_premium      part of that residual explained by athleticism (Berger & Daumann 2021: market pays for testing that does not predict)
 dv_pts_resid         pts/36 residual on usage + TS  (Berri: raw scoring is overpaid)
 dv_ts_resid_usg      TS residual on usage
 dv_impact_resid_cons impact residual on log consensus rank (production the market has not priced)
 dv_impact_pct        impact percentile within draft class
 dv_old_unranked_prod (age>=21.5) x (not RSCI top-100) x impact percentile   (steals profile)
 dv_age_ge_23         age >= 23 flag
 dv_cohort_offset_d   birthdate minus Sept 1 of the HS class cohort start (class_year-19); RSCI-ranked players only
 dv_intl_late         international x consensus rank > 30
 dv_tall              height with shoes >= 81 in
"""
import pandas as pd, numpy as np, json, glob
B="data_v4"; tr=pd.read_csv(f"{B}/train_2000_2018.csv"); tr["_split"]="train"
te=pd.concat([pd.read_csv(f).assign(_split="test") for f in sorted(glob.glob(f"{B}/tests/test_*_inputs.csv"))])
df=pd.concat([tr,te],ignore_index=True); T=df._split=="train"
def first(*cols):
    out=pd.Series(np.nan,index=df.index)
    for c in cols:
        if c in df: out=out.fillna(df[c])
    return out
cons=first("vcons_mock_mean_rank","cons_mock_consensus_rank"); lcons=np.log(cons.clip(lower=1))
age=first("col_age","bio_age_at_draft","intl_age"); imp=first("col_impact","intl_impact")
intl=(df["col_gp"].isna() & df["intl_gp"].notna()).astype(float)
def pca1(cols,signs,minp):
    X=df[cols].astype(float)*np.array(signs); mu=X[T].mean(); sd=X[T].std(); Z=(X-mu)/sd
    ok=Z.notna().sum(axis=1)>=minp; Zf=Z.fillna(0.0); C=np.cov(Zf[T & (Z.notna().all(axis=1))].values.T)
    w=np.linalg.eigh(C)[1][:,-1]; w=w*np.sign(w.sum()); s=Zf.values@w; return pd.Series(np.where(ok,s,np.nan),index=df.index)
df["dv_length_pc1"]=pca1(["vcmb_height_without_shoes_in","vcmb_standing_reach_in","vcmb_weight_lb","vcmb_wingspan_in","vcmb_hand_length_in"],[1,1,1,1,1],3)
df["dv_athl_pc1"]=pca1(["vcmb_max_vertical_in","vcmb_standing_vertical_in","vcmb_lane_agility_s","vcmb_three_quarter_sprint_s"],[1,1,-1,-1],2)
df["dv_impact_pct"]=df.groupby("draft_year")[imp.name if imp.name else "col_impact"].transform(lambda s: s.rank(pct=True)) if False else imp.groupby(df.draft_year).rank(pct=True)
def ols_resid(y,Xcols,mask_extra=None):
    X=pd.concat(Xcols,axis=1).astype(float); ok=y.notna()&X.notna().all(axis=1)
    if mask_extra is not None: ok&=mask_extra
    fit=ok&T; A=np.c_[np.ones(fit.sum()),X[fit].values]; beta=np.linalg.lstsq(A,y[fit].values,rcond=None)[0]
    pred=pd.Series(np.nan,index=df.index); pred[ok]=np.c_[np.ones(ok.sum()),X[ok].values]@beta; return y-pred, beta
pos=[df[c].fillna(0) for c in ["vmb_position_pg","vmb_position_sg","vmb_position_sf","vmb_position_pf"] if c in df]
hype,_=ols_resid(lcons,[df.dv_impact_pct,age,df.dv_length_pc1.fillna(df.dv_length_pc1[T].mean()),intl]+pos); df["dv_cons_hype_resid"]=hype
ok=hype.notna()&df.dv_athl_pc1.notna(); A=np.c_[np.ones((ok&T).sum()),df.dv_athl_pc1[ok&T].values]; b=np.linalg.lstsq(A,hype[ok&T].values,rcond=None)[0]
df["dv_athl_premium"]=np.where(ok,b[1]*(df.dv_athl_pc1-df.dv_athl_pc1[T].mean()),np.nan); print("athleticism slope on hype residual (log rank per PC unit):",round(b[1],4))
df["dv_pts_resid"],_=ols_resid(first("col_pts36"),[first("col_usg_pct"),first("col_ts_pct")])
df["dv_ts_resid_usg"],_=ols_resid(first("col_ts_pct"),[first("col_usg_pct")])
df["dv_impact_resid_cons"],_=ols_resid(imp,[lcons])
unranked=(df["rsci_top100"].fillna(0)==0).astype(float)
df["dv_old_unranked_prod"]=((age>=21.5).astype(float)*unranked*df.dv_impact_pct).where(age.notna()&df.dv_impact_pct.notna())
df["dv_age_ge_23"]=(age>=23).astype(float).where(age.notna())
DRAFT={2000:"06-28",2001:"06-27",2002:"06-26",2003:"06-26",2004:"06-24",2005:"06-28",2006:"06-28",2007:"06-28",2008:"06-26",2009:"06-25",2010:"06-24",2011:"06-23",2012:"06-28",2013:"06-27",2014:"06-26",2015:"06-25",2016:"06-23",2017:"06-22",2018:"06-21",2019:"06-20",2020:"11-18",2021:"07-29",2022:"06-23",2023:"06-22",2024:"06-26",2025:"06-25",2026:"06-23"}
ddate=pd.to_datetime(df.draft_year.map(lambda y: f"{int(y)}-{DRAFT[int(y)]}")); birth=ddate-pd.to_timedelta((age*365.25).round(),unit="D")
cls=df.draft_year-df["rsci_years_to_draft"]; cohort=pd.to_datetime((cls-19).dropna().astype(int).astype(str)+"-09-01"); 
off=(birth-cohort.reindex(df.index)).dt.days; df["dv_cohort_offset_d"]=off.where((df["rsci_top100"]==1)&age.notna())
df["dv_intl_late"]=(intl*(cons>30).astype(float)).where(cons.notna())
df["dv_tall"]=(first("vcmb_height_with_shoes_in","bio_height_in")>=81).astype(float).where(first("vcmb_height_with_shoes_in","bio_height_in").notna())
cols=[c for c in df if c.startswith("dv_")]; out=df[["pid"]+cols]; out.to_csv("derived_features.csv",index=False)
print(out.describe().T[["count","mean","std"]].round(3))

"""Data v4 = 'verified inputs': the current v3.5 matrix with the audited-out families removed and replaced by dated/official
sidecars from research/ (feature_provenance quarantine: all bio_, med_, cons_, scout_, 24 unverified college-derived columns).
Replacements keep the engine's column names where code depends on them, with a *_src flag (1 = verified source, 0 = legacy).
  bio_age_at_draft   <- vmb_age_reported_years (dated pre-draft profile) else legacy age (flag 0)  [age is a birth-date fact]
  bio_height_in      <- vcmb height with shoes (official same-year combine) else vmb listed height else legacy (flag)
  bio_weight_lb      <- vcmb weight else vmb listed weight, NO legacy fallback (legacy used current NBA weight)
  bio_pos_code       <- vmb position one-hots else legacy (flag)
  bio_combine_*      <- vcmb_* official same-year combine only (no research fills); bio_bmi_proxy from vcmb only
  bio_country_usa    <- misc_born_usa (pre-draft Wikipedia infobox)
  cons_mock_*        <- vcons_ dated archived mock lists (mean/best/n_sources); big-board column dropped
  med_*, scout_*, cs_* dropped; my cmb_ block dropped in favour of vcmb_ (same official source, hash-verified)
New optional blocks (prefix genes, default off): f50_, ctx_, tctx_, cgd_, slot_, vmb_, vcmb_, vcons_.
Rows, order, pids, labels and metadata are unchanged."""
import pandas as pd, numpy as np, json, gzip, glob, os, re
B="/Users/kennakao/nba/datarebuild/v4_build"; R="/Users/kennakao/nba/datarebuild/research"; OUT=f"{B}/data_v4"; os.makedirs(f"{OUT}/tests",exist_ok=True)
Q=json.load(open(f"{B}/quarantine_lists.json")); drop=set(Q["exact_all_bio_quarantine"]+Q["exact_medical_quarantine"]+Q["exact_consensus_quarantine"]+Q["exact_unverified_college_derived_quarantine"])
META={"pid","draft_year","actual_pick","actual_round","split","was_drafted","declared_only","path"}
def readv(p): return pd.read_csv(p,low_memory=False)
V={"train":readv(f"{R}/verified_inputs_v2_20260906/train_inputs.csv")}
for y in range(2019,2027): V[y]=readv(f"{R}/verified_inputs_v2_20260906/{y}_inputs.csv")
vcols=lambda d:[c for c in d.columns if c.startswith(("vcons_","vmb_","vcmb_","f50_"))]
P={"train":pd.read_csv(gzip.open(f"{R}/r9stacktest_inputs_20260907/package/features_pre2019.csv.gz","rt"))}
for y in range(2019,2026): P[y]=pd.read_csv(gzip.open(f"{R}/r9stacktest_inputs_20260907/package/features_{y}.csv.gz","rt"))
pcols=lambda d:[c for c in d.columns if c.startswith(("ctx_","tctx_","cgd_","slot_"))]
POS={"vmb_position_pg":1,"vmb_position_sg":2,"vmb_position_sf":3,"vmb_position_pf":4,"vmb_position_c":5}
def rebuild(d,v,p,label):
    d=d.copy(); n0=len(d); keep_cols=list(d.columns)
    v=v.set_index("pid"); vv=v[vcols(v)].reindex(d.pid.values); vv.index=d.index
    legacy={c:d[c].copy() for c in ("bio_age_at_draft","bio_height_in","bio_pos_code","misc_born_usa") if c in d.columns}
    d=d.drop(columns=[c for c in d.columns if c in drop or c.startswith(("scout_","med_","cs_","cmb_"))])
    d=pd.concat([d,vv],axis=1)
    # remaps with provenance flags
    age=vv["vmb_age_reported_years"]; d["bio_age_src"]=age.notna().astype(int); d["bio_age_at_draft"]=age.fillna(legacy.get("bio_age_at_draft"))
    h=vv["vcmb_height_with_shoes_in"].fillna(vv["vmb_listed_height_in"]); d["bio_height_src"]=np.where(vv["vcmb_height_with_shoes_in"].notna(),2,np.where(vv["vmb_listed_height_in"].notna(),1,0)); d["bio_height_in"]=h.fillna(legacy.get("bio_height_in"))
    d["bio_weight_lb"]=vv["vcmb_weight_lb"].fillna(vv["vmb_listed_weight_lb"])   # no legacy fallback
    pos=vv[list(POS)].astype(float); pc=pos.idxmax(axis=1).map(POS).where(pos.notna().any(axis=1)); d["bio_pos_src"]=pc.notna().astype(int); d["bio_pos_code"]=pc.fillna(legacy.get("bio_pos_code"))
    m={"bio_combine_height_in":"vcmb_height_without_shoes_in","bio_combine_weight_lb":"vcmb_weight_lb","bio_combine_wingspan_in":"vcmb_wingspan_in","bio_combine_reach_in":"vcmb_standing_reach_in","bio_combine_body_fat_pct":"vcmb_body_fat_pct","bio_combine_hand_length_in":"vcmb_hand_length_in","bio_combine_hand_width_in":"vcmb_hand_width_in"}
    for k,c in m.items(): d[k]=vv[c] if c in vv else np.nan
    for k,pat in (("bio_combine_vertical_standing_in","standing_vert"),("bio_combine_vertical_max_in","max_vert"),("bio_combine_lane_agility_s","lane_agility"),("bio_combine_sprint_s","sprint"),("bio_combine_bench_reps","bench")):
        cc=[c for c in vv.columns if pat in c and not c.endswith(("_att","_made"))]; d[k]=vv[cc[0]] if cc else np.nan
    d["bio_combine_wingspan_minus_height_in"]=d["bio_combine_wingspan_in"]-d["bio_combine_height_in"]
    d["bio_bmi_proxy"]=703*d["bio_combine_weight_lb"]/(d["bio_combine_height_in"]**2)
    d["bio_country_usa"]=legacy.get("misc_born_usa")
    d["cons_mock_consensus_rank"]=vv["vcons_mock_mean_rank"]; d["cons_mock_best_rank"]=vv["vcons_mock_best_rank"]; d["cons_mock_n_sources"]=vv["vcons_mock_n_sources"]
    if p is not None:
        p=p.drop(columns=["draft_year"],errors="ignore").set_index("pid"); pp=p[pcols(p)].reindex(d.pid.values); pp.index=d.index; d=pd.concat([d,pp],axis=1)
    assert len(d)==n0 and (d.pid.values==v.index.reindex(d.pid.values)[0]).all()
    return d
TR=readv(f"{B}/box_data/train_2000_2018.csv"); tr4=rebuild(TR,V["train"],P["train"],"train"); tr4.to_csv(f"{OUT}/train_2000_2018.csv",index=False)
inputs=[c for c in tr4.columns if c not in META and not c.startswith("y_") and c not in ("_k_avail",)]
for y in range(2019,2027):
    te=readv(f"{B}/box_data/tests/test_{y}_inputs.csv"); te4=rebuild(te,V[y],P.get(y),f"test{y}")
    for c in inputs:
        if c not in te4.columns: te4[c]=np.nan
    te4.to_csv(f"{OUT}/tests/test_{y}_inputs.csv",index=False)
json.dump({"inputs":inputs,"version":"v4 verified 2026-09-07","note":"quarantined bio_/med_/cons_/scout_/24 college-derived columns removed; dated/official replacements; see make_v4_inputs.py"},open(f"{OUT}/input_columns.json","w"),indent=1)
te=pd.concat([readv(f"{OUT}/tests/test_{y}_inputs.csv") for y in range(2019,2026)])
def cov(df,pref): 
    cs=[c for c in inputs if c.startswith(pref) and c in df.columns]; return f"{100*df[cs].notna().mean().mean():.0f}%" if cs else "-"
print("inputs:",len(inputs),"| train rows",len(tr4),"| test rows",len(te))
print("coverage train/test by block:"," ".join(f"{p}:{cov(tr4,p)}/{cov(te,p)}" for p in ("col_","intl_","bio_age","bio_height","bio_weight","bio_combine","cons_","hs_","f50_","ctx_","tctx_","cgd_","vcmb_","vmb_","tv_","gt_","rsci_")))
print("age source: verified",int(tr4.bio_age_src.sum()),"/ legacy",int((tr4.bio_age_src==0).sum()),"| height src 2/1/0:",tr4.bio_height_src.value_counts().to_dict(),"| pos verified",int(tr4.bio_pos_src.sum()))
print("consensus (dated) coverage among drafted train rows by year:",tr4[tr4.was_drafted==1].groupby("draft_year")["cons_mock_consensus_rank"].apply(lambda s:f"{s.notna().sum()}/{len(s)}").to_dict() if "was_drafted" in tr4 else "n/a")

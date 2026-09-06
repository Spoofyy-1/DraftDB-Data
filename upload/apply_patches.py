"""Apply pid-keyed data patches to the handoff dataset IN PLACE (data/), after a one-time backup to data_v1/.
Patches (patches/*.csv, no names anywhere):
  intl_patch_{train,test}.csv  international block rebuilt on the LATEST pre-draft season + league strength / two-season columns
  col_patch_{train,test}.csv   basic college line for players who had no college block at all
  anthro_patch_{train,test}.csv published pre-draft measurements for players without combine data (optional)
Rules: never touches outcome columns, pids, row order, draft_year, picks or answers. Empty cell = no change, "NA" = clear to NaN.
Then re-seals the vault (manifest is regenerated on next import). Run with --dry to validate only."""
import pandas as pd, numpy as np, json, os, shutil, glob, sys, hashlib, time, warnings; warnings.filterwarnings("ignore")
HERE=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); DATA=f"{HERE}/data"; V1=f"{HERE}/data_v1"; P=f"{HERE}/patches"
DRY="--dry" in sys.argv; LOG=[]
FORBID={"pid","draft_year","actual_pick","actual_round","split","was_drafted","declared_only","path"}
def load_patch(name):
    fp=f"{P}/{name}"
    if not os.path.exists(fp): LOG.append(f"{name}: not present, skipped"); return None
    d=pd.read_csv(fp,dtype=str,keep_default_na=False)
    bad=[c for c in d.columns if (c in FORBID and c!="pid") or c[:2]=="y_"]; assert not bad,f"patch {name} touches protected columns {bad}"
    return d
def apply(df,patch,label):
    if patch is None: return df,[]
    cols=[c for c in patch.columns if c!="pid"]; pm=patch.set_index("pid"); have=set(df["pid"])
    hit=[p for p in pm.index if p in have]; new=[c for c in cols if c not in df.columns]
    for c in new: df[c]=np.nan
    pos={p:i for i,p in enumerate(df["pid"])}; upd=0; cleared=0
    for p in hit:
        i=pos[p]
        for c in cols:
            v=pm.at[p,c]
            if v=="": continue
            if v=="NA": df.iat[i,df.columns.get_loc(c)]=np.nan; cleared+=1
            else: df.iat[i,df.columns.get_loc(c)]=float(v); upd+=1
    LOG.append(f"{label}: {len(hit)}/{len(pm)} patch rows matched, {upd} cells set, {cleared} cleared, new columns {new}")
    return df,new
def finish(df,newcols):
    if "intl_src" in df.columns: df["intl_src"]=df["intl_src"].fillna(0)
    if "col_basic_fill" in df.columns: df["col_basic_fill"]=df["col_basic_fill"].fillna(0)
    if "bio_measure_src" in df.columns:
        df["bio_measure_src"]=df["bio_measure_src"].where(df["bio_measure_src"].notna(),np.where(df["bio_combine_wingspan_in"].notna(),1.0,0.0))
    if {"bio_combine_wingspan_in","bio_combine_height_in"}<=set(df.columns):
        wmh=df["bio_combine_wingspan_in"]-df["bio_combine_height_in"]; df["bio_combine_wingspan_minus_height_in"]=wmh.where(wmh.between(-6,14))
    return df
t0=time.time(); cols_json=json.load(open(f"{DATA}/input_columns.json")); inputs=list(cols_json["inputs"]); allnew=[]
# ---- train
tr=pd.read_csv(f"{DATA}/train_2000_2018.csv"); n0=len(tr); pid0=list(tr["pid"]); ycols=[c for c in tr.columns if c[:2]=="y_"]; yhash=hashlib.sha256(pd.util.hash_pandas_object(tr[ycols]).values.tobytes()).hexdigest()
for nm,lab in(("intl_patch_train.csv","intl train"),("col_patch_train.csv","college train"),("anthro_patch_train.csv","anthro train"),("weird_patch_train.csv","weird train")):
    tr,new=apply(tr,load_patch(nm),lab); allnew+=new
tr=finish(tr,allnew)
assert len(tr)==n0 and list(tr["pid"])==pid0,"train rows/pids changed"
assert hashlib.sha256(pd.util.hash_pandas_object(tr[ycols]).values.tobytes()).hexdigest()==yhash,"outcome columns changed"
# ---- tests
tests={}
for fp in sorted(glob.glob(f"{DATA}/tests/test_*_inputs.csv")):
    d=pd.read_csv(fp); tests[fp]=(d,len(d),list(d["pid"]))
patches=[(load_patch(nm),lab) for nm,lab in(("intl_patch_test.csv","intl test"),("col_patch_test.csv","college test"),("anthro_patch_test.csv","anthro test"),("weird_patch_test.csv","weird test"))]
for fp,(d,n,pids) in tests.items():
    for pt,lab in patches:
        if pt is None: continue
        sub=pt[pt["pid"].isin(set(pids))]
        if len(sub)==0: continue
        d,new=apply(d,sub,f"{lab} {os.path.basename(fp)}"); allnew+=new
    d=finish(d,allnew); assert len(d)==n and list(d["pid"])==pids,f"{fp} rows/pids changed"; tests[fp]=(d,n,pids)
allnew=sorted(set(c for c in allnew if c not in inputs)); 
# every new column must exist everywhere (add NaN where a file never saw it)
for c in allnew:
    if c not in tr.columns: tr[c]=np.nan
    for fp in tests:
        if c not in tests[fp][0].columns: tests[fp][0][c]=np.nan
for fp in tests: tests[fp]=(finish(tests[fp][0],allnew),tests[fp][1],tests[fp][2])
tr=finish(tr,allnew)
LOG.append(f"new input columns: {allnew}")
LOG.append(f"train wingspan coverage: {tr['bio_combine_wingspan_in'].notna().mean():.3f}; test: "+", ".join(f"{os.path.basename(fp)[5:9]} {d['bio_combine_wingspan_in'].notna().mean():.2f}" for fp,(d,_,_) in tests.items()))
print("\n".join(LOG))
if DRY: print("DRY RUN: nothing written"); sys.exit(0)
if not os.path.exists(V1): shutil.copytree(DATA,V1); print("backup: data/ -> data_v1/")
tr.to_csv(f"{DATA}/train_2000_2018.csv",index=False)
for fp,(d,_,_) in tests.items(): d.to_csv(fp,index=False)
cols_json["inputs"]=inputs+allnew; cols_json["version"]="v3"; cols_json["v3_changes"]=LOG; json.dump(cols_json,open(f"{DATA}/input_columns.json","w"),indent=1)
open(f"{DATA}/DATA_V3_CHANGES.md","w").write("# data v3 (applied %s)\n\n"%time.strftime("%Y-%m-%d %H:%M")+"\n".join("- "+l for l in LOG)+"\n")
man=f"{HERE}/vault/manifest.json"
if os.path.exists(man): os.chmod(man,0o600); os.remove(man); print("vault manifest removed; will re-seal on next import")
print(f"APPLIED in {time.time()-t0:.0f}s")

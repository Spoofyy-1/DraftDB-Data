"""Data v4.8: append novel columns (NBA relatives / birthplace from current Wikipedia infoboxes, mock-board disagreement)
to the verified v4 input files by pid. Usage: python3 add_cols_v48.py [--apply]  (without --apply writes to staging_v48/ only)."""
import pandas as pd, json, sys, os, tarfile
B="data_v4"; OUT="staging_v48"; os.makedirs(OUT+"/tests",exist_ok=True)
adds=[]
if os.path.exists("../relatives_features.csv"):
    r=pd.read_csv("../relatives_features.csv")[["pid","misc_birth_us_state","misc_birth_big_metro"]]; adds.append(r)   # relatives via prose come later (wikitext collector)
d=pd.read_csv("cons_disagreement.csv").rename(columns={"cons_mock_rank_std":"dis_mock_rank_std","cons_mock_rank_range":"dis_mock_rank_range"}); adds.append(d)
adds.append(pd.read_csv("derived_features.csv"))
new=adds[0]
for a in adds[1:]: new=new.merge(a,on="pid",how="outer")
newcols=[c for c in new.columns if c!="pid"]
cols=json.load(open(f"{B}/input_columns.json"))
def merge(fp,dst):
    df=pd.read_csv(fp); df=df.drop(columns=[c for c in newcols if c in df.columns])
    m=df.merge(new,on="pid",how="left"); assert len(m)==len(df); m.to_csv(dst,index=False)
    return {c:int(m[c].notna().sum()) for c in newcols}
cov=merge(f"{B}/train_2000_2018.csv",f"{OUT}/train_2000_2018.csv"); print("train coverage",len(pd.read_csv(f"{B}/train_2000_2018.csv")),cov)
for y in range(2019,2026):
    c=merge(f"{B}/tests/test_{y}_inputs.csv",f"{OUT}/tests/test_{y}_inputs.csv"); print(y,c)
cols["inputs"]=[c for c in cols["inputs"] if c not in newcols]+newcols
json.dump(cols,open(f"{OUT}/input_columns.json","w"),indent=1); print("inputs:",len(cols["inputs"]),"new:",newcols)
if "--apply" in sys.argv:
    with tarfile.open("data_v48.tar.gz","w:gz") as t: t.add(OUT,arcname="data_v48")
    print("wrote data_v48.tar.gz")

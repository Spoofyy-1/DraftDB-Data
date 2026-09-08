"""Generic block merge for data versions: python3 add_block.py --base <dir> --out <dir> --tar <name.tar.gz> --version "<label>" --add f1.csv [f2.csv ...]
Each add file is pid-keyed with numeric columns; columns already present in the base are replaced. Test/train row order preserved."""
import pandas as pd, json, sys, os, tarfile, argparse
a=argparse.ArgumentParser(); a.add_argument("--base",required=True); a.add_argument("--out",required=True); a.add_argument("--tar",required=True); a.add_argument("--version",default=""); a.add_argument("--add",nargs="+",required=True); A=a.parse_args()
os.makedirs(A.out+"/tests",exist_ok=True)
new=None
for fp in A.add:
    df=pd.read_csv(fp); assert "pid" in df and df.pid.is_unique, fp
    bad=[c for c in df.columns if c!="pid" and not pd.api.types.is_numeric_dtype(df[c])]; assert not bad,(fp,bad)
    new=df if new is None else new.merge(df,on="pid",how="outer")
newcols=[c for c in new.columns if c!="pid"]
def merge(src,dst):
    d=pd.read_csv(src); d=d.drop(columns=[c for c in newcols if c in d.columns]); m=d.merge(new,on="pid",how="left"); assert len(m)==len(d); m.to_csv(dst,index=False)
    return int(m[newcols].notna().any(axis=1).sum()),len(m)
print("train",merge(f"{A.base}/train_2000_2018.csv",f"{A.out}/train_2000_2018.csv"))
for f in sorted(os.listdir(f"{A.base}/tests")):
    if f.endswith(".csv"): print(f,merge(f"{A.base}/tests/{f}",f"{A.out}/tests/{f}"))
cols=json.load(open(f"{A.base}/input_columns.json")); cols["inputs"]=[c for c in cols["inputs"] if c not in newcols]+newcols
if A.version: cols["version"]=A.version
json.dump(cols,open(f"{A.out}/input_columns.json","w"),indent=1); print("inputs:",len(cols["inputs"]),"| added:",len(newcols))
with tarfile.open(A.tar,"w:gz") as t: t.add(A.out,arcname=os.path.basename(A.out).replace("staging_","data_"))
print("wrote",A.tar)

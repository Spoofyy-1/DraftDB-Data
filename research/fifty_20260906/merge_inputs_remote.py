"""Left-join feature store to all original input rows; never drop missing players."""
from pathlib import Path
import json
import pandas as pd
ROOT=Path(__file__).resolve().parent;HOME=ROOT.parent.parent
DECLARED=json.loads((HOME/'data/input_columns.json').read_text())['inputs']
out=ROOT/'merged_inputs';out.mkdir(exist_ok=True)
audit=[]
for year in ['train']+list(range(2019,2027)):
    raw_path=HOME/'data/train_2000_2018.csv' if year=='train' else HOME/f'data/tests/test_{year}_inputs.csv'
    x=pd.read_csv(raw_path)
    keep=list(dict.fromkeys(['pid','draft_year']+[c for c in DECLARED if c in x]))
    assert not any(c.startswith('y_') or c in ('actual_pick','actual_round') for c in keep)
    x=x[keep]
    f=pd.read_csv(ROOT/('fifty_train.csv' if year=='train' else f'fifty_test_{year}_inputs.csv')).drop(columns='draft_year')
    n=len(x);merged=x.merge(f,on='pid',how='left',validate='one_to_one');assert len(merged)==n
    merged.to_csv(out/f'{year}_inputs.csv',index=False)
    audit.append(dict(split=year,rows=n,added_features=len(f.columns)-1,matched=int(merged[f.columns[1:]].notna().any(axis=1).sum())))
(out/'join_manifest.json').write_text(json.dumps(audit,indent=2));print(json.dumps(audit))

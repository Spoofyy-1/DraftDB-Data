"""Real pre-2019 workload batch-size benchmark; no model selection or test scores."""
from pathlib import Path
import json,time
import numpy as np,pandas as pd,torch
from scipy.stats import spearmanr
from tabicl import TabICLRegressor
import legacy_kernel as E
ROOT=Path(__file__).resolve().parent;DATA=ROOT/'data';OUT=ROOT/'results'
x=pd.read_csv(DATA/'features.csv');lab=pd.read_csv(DATA/'labels.csv');m=json.load(open(DATA/'manifest.json'));g=json.load(open(DATA/'incumbent.json'))['champ']
assert lab.season_end.max()<=2018
tr=x[x.draft_year.between(2007,2010)].copy().reset_index(drop=True);te=x[(x.draft_year==2012)&(x.was_drafted==1)].copy().reset_index(drop=True)
used=lab[(lab.season_end<=2011)&lab.pid.isin(tr.pid)]
for i in range(1,6):tr[f'y_s{i}_war']=tr.pid.map(used[used.ordinal==i].set_index('pid').war)
cols=[c for c in m['legacy_features'] if c.startswith(('col_','bio_','cons_','intl_'))][:100]
E.setup(cols);y=E.label(tr,E.specs(g)[0],5)
import xgboost as xgb
records=[]
for device in ['cuda','cpu','cuda','cpu']:
    config=dict(E.H.XCFG);config['device']=device;config['objective']='reg:quantileerror';config['quantile_alpha']=.25;config['n_jobs']=3
    t=time.perf_counter();model=xgb.XGBRegressor(**config,random_state=11)
    model.fit(tr[cols],y);pred=model.predict(te[cols]);elapsed=time.perf_counter()-t
    record=dict(device=device,seconds=elapsed)
    if not records:reference=pred
    record['prediction_rank_correlation']=float(spearmanr(pred,reference).statistic)
    records.append(record);print(json.dumps(record),flush=True)
    (OUT/'xgb_placement.json').write_text(json.dumps(records,indent=2))

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
class ReusedWeights(TabICLRegressor):
    pretrained={}
    def _load_model(self):
        key=(str(self.model_path),self.checkpoint_version,str(self.device))
        if key not in self.pretrained:
            super()._load_model()
            self.pretrained[key]=(self.model_,self.model_config_,self.model_path_)
        self.model_,self.model_config_,self.model_path_=self.pretrained[key]
records=[];ref=None
for kind,other in [('fresh',False),('reuse',False),('reuse',True),('reuse',False),('fresh',False)]:
    klass=TabICLRegressor if kind=='fresh' else ReusedWeights
    model=klass(device='cuda',n_estimators=32,batch_size=32,norm_methods='none',outlier_threshold=2,random_state=42,kv_cache=False)
    # An intervening different training subset checks for retained training context.
    ix=np.arange(len(tr))[::2] if other else np.arange(len(tr))
    t=time.perf_counter();model.fit(tr[cols].iloc[ix],y[ix]);pred=model.predict(te[cols]);torch.cuda.synchronize();elapsed=time.perf_counter()-t
    if ref is None:ref=pred.copy()
    record=dict(kind=kind,intervening_other_training_context=other,seconds=elapsed,max_prediction_difference=None if other else float(np.max(np.abs(pred-ref))),same_order=None if other else bool(np.array_equal(np.argsort(pred),np.argsort(ref))))
    records.append(record);print(json.dumps(record),flush=True);(OUT/'weight_reuse.json').write_text(json.dumps(records,indent=2));del model

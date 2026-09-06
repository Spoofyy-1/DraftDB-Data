"""Frozen baseline prediction worker: no answer files in the mount namespace."""
from pathlib import Path
import hashlib,json,time
import numpy as np
import pandas as pd
import legacy_kernel as E
ROOT=Path(__file__).resolve().parent;DATA=ROOT/'data';OUT=ROOT/'results'
def main():
    protocol=json.loads((ROOT/'frozen_protocol.json').read_text())
    for f,h in protocol['files'].items():assert hashlib.sha256((DATA/f).read_bytes()).hexdigest()==h
    for path in ['/home/ubuntu/nba/handoff/vault/answers_2020.csv','/workspace/data/answers_2020.csv']:
        assert not Path(path).exists()
    m=json.loads((DATA/'manifest.json').read_text());g=json.loads((DATA/'incumbent.json').read_text())['champ'];g['noscout']=1
    assert not any(g.get(k) for k in ['beatpick','consres','gltb','midw','el','wk','pss','star','hurdle'])
    x=pd.read_csv(DATA/'features.csv');lab=pd.read_csv(DATA/'labels.csv');test=pd.read_csv(DATA/'inference_inputs.csv')
    assert lab.season_end.max()<=2018
    tr=x[(x.draft_year>=g['win'])&(x.draft_year<=2017)].copy().reset_index(drop=True)
    tr=tr.drop(columns=['actual_pick'],errors='ignore')
    used=lab[lab.pid.isin(tr.pid)&(lab.season_end<=2018)]
    for i in range(1,6):tr[f'y_s{i}_war']=tr.pid.map(used[used.ordinal==i].set_index('pid').war)
    E.setup(m['legacy_features']);opts=E.opts_of(g);base=E.H.cols_for(opts);cols=E.cols_of(g,base);E.H.audit_features(cols)
    prior,cq=E.H.fit_prior(tr)
    pred=[]
    for year in range(2019,2027):
        te=test[test.draft_year==year].copy().reset_index(drop=True)
        assert not set(te.pid)&set(tr.pid)
        for c in m['legacy_features']:
            if c not in te:te[c]=np.nan
        Btr=E.H.build(tr,prior,cq,opts);Bte=E.H.build(te,prior,cq,opts)
        rate=[c for c in base if c.startswith(('col_','intl_')) and not c.startswith('col_gl_')]
        Btr,Bte=E.feat_tx(Btr,Bte,g['fx'],tr,te,rate)
        st=E.stats_of(Btr);Btr=E.add_feats(Btr,g['fx'],st);Bte=E.add_feats(Bte,g['fx'],st)
        k=int(protocol['horizons'].get(str(year),5))
        members=E.member_preds(g,Btr,Bte,cols,tr,k);score=E.stack(members,Bte,g,protocol['weights'])
        assert np.isfinite(score).all()
        pred.extend(dict(pid=pid,season=year,score=float(s),k=k) for pid,s in zip(te.pid,score))
        print(json.dumps(dict(year=year,n=len(te),train_rows=len(tr),training_season_cutoff=2018,status='predictions_saved_in_memory')),flush=True)
    frame=pd.DataFrame(pred);frame.to_csv(OUT/'predictions.csv',index=False)
    freeze=dict(created=time.time(),prediction_sha256=hashlib.sha256((OUT/'predictions.csv').read_bytes()).hexdigest(),protocol_sha256=hashlib.sha256((ROOT/'frozen_protocol.json').read_bytes()).hexdigest(),rows=len(frame))
    (OUT/'prediction_freeze.json').write_text(json.dumps(freeze,indent=2))
    print('FROZEN_PREDICTIONS_READY',flush=True)
if __name__=='__main__':main()

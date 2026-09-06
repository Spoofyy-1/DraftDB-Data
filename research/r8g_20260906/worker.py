"""Registered incumbent data ablation, development only, no test access.

This diagnostic does not select a replacement based on the previous confirmation.
Legacy input variants are explicitly uncertified pending source-provenance review.
"""
import os
os.environ['OMP_NUM_THREADS']='3';os.environ['OPENBLAS_NUM_THREADS']='3'
from pathlib import Path
import json,time,traceback,hashlib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import legacy_kernel as E

ROOT=Path(__file__).resolve().parent;DATA=ROOT/'data';OUT=ROOT/'results';OUT.mkdir(exist_ok=True)
def write(s):
    s['updated']=time.time();t=OUT/'state.tmp';t.write_text(json.dumps(s,indent=2,allow_nan=False));t.replace(OUT/'state.json')
def rho(p,w):
    value=float(spearmanr(p,w).statistic);return value if np.isfinite(value) else 0.
def run_variant(vid,vseed=0,variant_override=None):
    m=json.load(open(DATA/'manifest.json'))
    for f,h in m['files'].items(): assert hashlib.sha256((DATA/f).read_bytes()).hexdigest()==h
    x=pd.read_csv(DATA/'features.csv');lab=pd.read_csv(DATA/'labels.csv')
    g=json.load(open(DATA/'incumbent.json'))['champ']
    assert not any(g.get(k) for k in ['beatpick','consres','gltb','midw','el','wk','pss','star','hurdle'])
    assert g['labelmix']=='single' and g['meta']=='rankavg'
    for path in ['/home/ubuntu/nba/handoff/vault/answers_2020.csv','/home/ubuntu/nba/handoff/data/tests/test_2020_inputs.csv']:
        try: open(path).read(1)
        except (FileNotFoundError,PermissionError): pass
        else: raise AssertionError('Unexpected access to test files')
    variants=json.load(open(ROOT/'plan.json'))['variants']
    weights={'rich':(0.,.75,.25),'thin':(.5,0.,.5)}
    plan=json.load(open(ROOT/'plan.json'))
    os.environ['SEED_SHIFT']=str(vseed)
    v=variant_override or next(v for v in variants if v['id']==vid)
    variants=[v]
    state=dict(candidates=[])
    for v in variants:
        start=time.time()
        try:
            gg={**g,'noscout':v['noscout'],'win':v.get('window',g['win']),'hw':v.get('hw',g['hw']),'icl_n':v.get('icl_n',g['icl_n']),'M':v.get('M',g['M'])}
            features=[c for c in m['legacy_features'] if not any(c.startswith(pre) for pre in v['drop'])]+[c for c in m['context_features'] if v['context'] and c.startswith(v['context'])]
            for c in m['legacy_features']:
                if any(c.startswith(pre) for pre in v['drop']): x[c]=np.nan
            features+=v.get('extras',[])
            E.setup(features);rows=[]
            for year in plan['folds']:
                cutoff=year-1;k=min(5,2018-year)
                tr=x[(x.draft_year>=int(gg['win']))&(x.draft_year<=cutoff-1)].copy()
                if v['drafted_only']:tr=tr[tr.was_drafted==1].copy()
                if v.get('mature'):tr=tr[tr.draft_year<=cutoff-k].copy()
                te=x[(x.draft_year==year)&(x.was_drafted==1)].copy()
                tr=tr.reset_index(drop=True);te=te.reset_index(drop=True)
                assert not set(tr.pid)&set(te.pid)
                used=lab[(lab.season_end<=cutoff)&lab.pid.isin(tr.pid)]
                assert (used.season_end<=cutoff).all()
                for i in range(1,6):
                    vals=used[used.ordinal==i].set_index('pid').war
                    tr[f'y_s{i}_war']=tr.pid.map(vals)
                opts=E.opts_of(gg);base=E.H.cols_for(opts);cols=E.cols_of(gg,base)
                E.H.audit_features(cols)
                prior,cq=E.H.fit_prior(tr)
                Btr=E.H.build(tr,prior,cq,opts);Bte=E.H.build(te,prior,cq,opts)
                rate=[c for c in base if c.startswith(('col_','intl_')) and not c.startswith('col_gl_')]
                Btr,Bte=E.feat_tx(Btr,Bte,gg['fx'],tr,te,rate)
                st=E.stats_of(Btr);Btr=E.add_feats(Btr,gg['fx'],st);Bte=E.add_feats(Bte,gg['fx'],st)
                import xgboost as xgb
                yy_train=E.label(tr,E.specs(gg)[0],k)
                selector=xgb.XGBRegressor(max_depth=3,n_estimators=300,learning_rate=.05,subsample=.8,colsample_bytree=.6,n_jobs=2,device='cpu',tree_method='hist',random_state=11).fit(Btr[cols],yy_train)
                top=[c for _,c in sorted(zip(selector.feature_importances_,cols),reverse=True)[:v['topk']]]
                p=E.H.predict('tabicl',Btr[top],yy_train,Bte[top],E.cfg_of('tabicl',gg,top))
                preds={'tabicl':p}
                truth=lab[(lab.season_end<=2018)&(lab.ordinal<=k)].groupby('pid').war.sum()
                yy=te.pid.map(truth).fillna(0)
                row=dict(season=year,k=k,n=len(te),ntrain=len(tr),cutoff=cutoff,max_label_season=int(used.season_end.max()),
                         stack=rho(p,yy),draft=rho(-te.actual_pick,yy),members={model:rho(score,yy) for model,score in preds.items()})
                row['predictions']=[dict(pid=pid,score=float(score)) for pid,score in zip(te.pid,p)]
                rows.append(row);print(json.dumps(dict(variant=v['id'],fold=row)),flush=True)
            entry=dict(config={'id':v['id'],**v},score=float(np.mean([r['stack'] for r in rows])),rows=rows,seconds=round(time.time()-start,1))
        except Exception as e:
            traceback.print_exc();entry=dict(config={'id':v['id'],**v},error=str(e),seconds=round(time.time()-start,1))
        return entry

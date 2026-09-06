"""Bounded research, selected only on pre-2019 outcomes; no vault/test loader.

The worker is launched in a filesystem/network sandbox. Candidate set is committed
before execution. Confirmation is evaluated once after selection, never used to retry.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS','6')
os.environ.setdefault('OPENBLAS_NUM_THREADS','6')
from pathlib import Path
import json, time, hashlib, argparse, traceback
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, norm, rankdata
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import ExtraTreesRegressor

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
OUT=ROOT/'results'
OUT.mkdir(exist_ok=True)
BANNED={'pid','draft_year','actual_pick','actual_round','was_drafted','declared_only','source_season'}

def assert_features(cols):
    assert cols and not (set(cols)&BANNED)
    assert not any(c.startswith(('y_','scout_','prog_','ts_coach_')) for c in cols)

def verify_files():
    m=json.load(open(DATA/'manifest.json'))
    for f,h in m['files'].items():
        assert hashlib.sha256((DATA/f).read_bytes()).hexdigest()==h, f'Data changed: {f}'
    return m

def asof_target(features, labels, predicted_year, k):
    """Earlier draft cohorts with at least one nominal season of observation.

Late debuts remain censored at the actual calendar cutoff; no later WAR is read
into the target. The target is observed WAR, not a claim of complete future WAR.
    """
    cutoff=int(predicted_year)-1
    tr=features[features.draft_year<=cutoff-1].copy()
    used=labels[(labels.season_end<=cutoff)&(labels.ordinal<=k)&labels.pid.isin(tr.pid)]
    assert (tr.draft_year<predicted_year).all()
    assert (used.season_end<=cutoff).all()
    sums=used.groupby('pid').war.sum()
    tr['target_raw']=tr.pid.map(sums).fillna(0.)
    tr['target']=tr.groupby('draft_year').target_raw.transform(
        lambda x:norm.ppf((x.rank(method='average')-.5)/len(x)))
    return tr,used

def metric(p,y):
    r=float(spearmanr(p,y).statistic)
    return r if np.isfinite(r) else 0.

def candidates():
    out=[]
    for block in ['core','no_market','no_international','context_base','core_context_base','core_team','core_growth','core_skill','core_all','context_all']:
        for family,params in [('ridge',{'alpha':30}),('ridge',{'alpha':300}),
                              ('xgb',{'depth':2}),('xgb',{'depth':3}),
                              ('et',{}),('cat',{})]:
            out.append(dict(id=f'{block}:{family}:{next(iter(params.values()),0)}',block=block,family=family,**params))
    # TabICL is reserved for a small prespecified set to bound runtime and search multiplicity.
    for block in ['core','core_all','context_all']:
        out.append(dict(id=f'{block}:tabicl:8',block=block,family='tabicl'))
    return out

def columns(c,m):
    block=c['block']; core=m['core']; ctx=m['context']
    if block=='core': cols=core
    elif block=='no_market': cols=[x for x in core if not x.startswith('cons_')]
    elif block=='no_international': cols=[x for x in core if not x.startswith('intl_')]
    elif block=='context_base': cols=[x for x in ctx if x.startswith('ctx_base_')]
    elif block=='context_all': cols=ctx
    else:
        suffix=block.removeprefix('core_')
        prefix={'context_base':'ctx_base_','team':'ctx_team_','growth':'ctx_growth_','skill':'ctx_skill_','all':'ctx_'}[suffix]
        cols=core+[x for x in ctx if x.startswith(prefix)]
    assert_features(cols)
    return cols

def fit_predict(c,tr,te,cols,seed=2718):
    # Drop all-empty columns using training rows only.
    cols=[v for v in cols if tr[v].notna().any()]
    assert_features(cols)
    A=tr[cols].replace([np.inf,-np.inf],np.nan)
    B=te[cols].replace([np.inf,-np.inf],np.nan)
    y=tr.target.to_numpy()
    family=c['family']
    if family=='ridge':
        model=make_pipeline(SimpleImputer(strategy='median',add_indicator=True),StandardScaler(),Ridge(alpha=c['alpha']))
    elif family=='et':
        model=make_pipeline(SimpleImputer(strategy='median',add_indicator=True),ExtraTreesRegressor(n_estimators=350,min_samples_leaf=6,max_features=.7,n_jobs=6,random_state=seed))
    elif family=='xgb':
        from xgboost import XGBRegressor
        model=XGBRegressor(n_estimators=350,max_depth=c['depth'],learning_rate=.025,min_child_weight=10,
                           reg_lambda=20,reg_alpha=2,subsample=.8,colsample_bytree=.7,
                           tree_method='hist',device='cuda',n_jobs=6,random_state=seed)
    elif family=='cat':
        from catboost import CatBoostRegressor
        model=CatBoostRegressor(iterations=450,depth=3,learning_rate=.025,l2_leaf_reg=15,
                                loss_function='RMSE',thread_count=6,random_seed=seed,verbose=False,allow_writing_files=False)
    elif family=='tabicl':
        from tabicl import TabICLRegressor
        model=TabICLRegressor(device='cuda',n_estimators=8,random_state=seed)
    else: raise ValueError(family)
    model.fit(A,y)
    return model.predict(B)

def evaluate(c,years,x,labels,m,seed=2718):
    rows=[]; predictions={}
    for year in years:
        k=min(5,2018-year)
        tr,used=asof_target(x,labels,year,k)
        te=x[x.draft_year==year].copy()
        assert len(tr)>=100 and len(te)>=30
        assert not set(tr.pid)&set(te.pid)
        p=fit_predict(c,tr,te,columns(c,m),seed)
        truth=labels[(labels.season_end<=2018)&(labels.ordinal<=k)].groupby('pid').war.sum()
        y=te.pid.map(truth).fillna(0).to_numpy()
        predictions[year]={'pid':te.pid.tolist(),'pred':p.tolist(),'truth':y.tolist(),'pick':te.actual_pick.tolist()}
        rows.append(dict(season=year,k=k,n=len(te),ntrain=len(tr),cutoff=year-1,
                         max_label_season=int(used.season_end.max()),stack=metric(p,y),draft=metric(-te.actual_pick,y)))
    return rows,predictions

def write_state(state):
    state['updated']=time.time()
    temp=OUT/'state.tmp'
    temp.write_text(json.dumps(state,indent=2,allow_nan=False))
    temp.replace(OUT/'state.json')

def self_test():
    # An actual delayed-debut example: season ordinal 1 is two years after the draft.
    f=pd.DataFrame({'pid':['a','b'],'draft_year':[2010,2012]})
    l=pd.DataFrame({'pid':['a','a','b'],'draft_year':[2010,2010,2012],
                    'ordinal':[1,2,1],'season_end':[2012,2015,2013],'war':[1.,999.,999.]})
    tr,used=asof_target(f,l,2013,2)
    assert tr.pid.tolist()==['a'] and tr.target_raw.tolist()==[1.]
    l2=l.copy();l2.loc[l2.season_end>2012,'war']=-1234567
    tr2,_=asof_target(f,l2,2013,2)
    assert tr.target_raw.equals(tr2.target_raw)
    for bad in ['actual_pick','draft_year','y_s1_war','scout_motor']:
        try: assert_features(['col_gp',bad])
        except AssertionError: pass
        else: raise AssertionError(f'Accepted forbidden feature: {bad}')
    # All preprocessing fits occur within model.fit(A,y); B is predict-only.
    for path in ['/home/ubuntu/nba/handoff/vault/answers_2020.csv','/home/ubuntu/nba/handoff/data/tests/test_2020_inputs.csv']:
        if os.environ.get('R8_SANDBOX')=='1':
            try: open(path).read(1)
            except (FileNotFoundError,PermissionError): pass
            else: raise AssertionError(f'Sandbox exposes forbidden file {path}')
    print('PASS: cutoff, delayed debut, future-label perturbation, forbidden features, sandbox paths',flush=True)

def main():
    self_test();m=verify_files()
    x=pd.read_csv(DATA/'features.csv');labels=pd.read_csv(DATA/'labels.csv')
    assert x.pid.is_unique and (x.draft_year<=2018).all() and (labels.season_end<=2018).all()
    plan=candidates()
    plan_path=OUT/'preregistered_plan.json'
    if plan_path.exists(): raise RuntimeError('Existing run: choose a new output directory, do not overwrite evidence')
    plan_path.write_text(json.dumps(dict(candidates=plan,manifest=m,created=time.time()),indent=2))
    state=dict(status='running',phase='pre-2019 development',target=.60,completed=0,total=len(plan),
               candidates=[],best=None,confirmation=None,test_result=None,
               message='No 2019-2026 outcomes or inputs are accessible to this worker.',started=time.time())
    write_state(state)
    cache={}
    for c in plan:
        state['current']=c['id'];write_state(state);start=time.time()
        try:
            rows,preds=evaluate(c,m['tuning_folds'],x,labels,m)
            score=float(np.mean([r['stack'] for r in rows]))
            entry=dict(config=c,score=score,rows=rows,seconds=round(time.time()-start,1))
            cache[c['id']]=preds
        except Exception as e:
            entry=dict(config=c,error=f'{type(e).__name__}: {e}',seconds=round(time.time()-start,1))
            traceback.print_exc()
        state['candidates'].append(entry);state['completed']+=1
        good=[v for v in state['candidates'] if 'score' in v]
        if good: state['best']=max(good,key=lambda v:v['score'])
        write_state(state)
        print(json.dumps(entry),flush=True)
    good=sorted([v for v in state['candidates'] if 'score' in v],key=lambda v:-v['score'])
    assert good
    # A fixed equal-rank blend of the top three different model families; weights never
    # fit against the same fold used to claim a gain. Compare only in development.
    chosen=[]
    for v in good:
        if v['config']['family'] not in [z['config']['family'] for z in chosen]: chosen.append(v)
        if len(chosen)==3: break
    ens_rows=[]
    for year in m['tuning_folds']:
        pp=[cache[v['config']['id']][year] for v in chosen]
        p=np.mean([rankdata(z['pred'])/len(z['pred']) for z in pp],axis=0)
        ens_rows.append(dict(season=year,stack=metric(p,pp[0]['truth'])))
    ens_score=float(np.mean([r['stack'] for r in ens_rows]))
    use_ensemble=ens_score>good[0]['score']
    selected=chosen if use_ensemble else good[:1]
    frozen=dict(kind='equal_rank_blend' if use_ensemble else 'single',members=[v['config'] for v in selected],
                development_score=ens_score if use_ensemble else good[0]['score'],
                selection='2012-2014 only; confirmation not yet accessed',frozen_at=time.time())
    (OUT/'frozen_selection.json').write_text(json.dumps(frozen,indent=2))
    state['phase']='one-time pre-2019 confirmation';state['selection']=frozen;write_state(state)
    confirm=[];member_outputs=[]
    for v in selected:
        rr,pp=evaluate(v['config'],m['confirmation_folds'],x,labels,m,seed=3141)
        member_outputs.append((rr,pp))
    for i,year in enumerate(m['confirmation_folds']):
        pp=[v[1][year] for v in member_outputs]
        p=np.mean([rankdata(z['pred'])/len(z['pred']) for z in pp],axis=0)
        row=dict(member_outputs[0][0][i]);row['stack']=metric(p,pp[0]['truth']);confirm.append(row)
    state['confirmation']=dict(score=float(np.mean([r['stack'] for r in confirm])),rows=confirm,
                               role='One-time confirmation; cannot be used to select or retry candidates')
    state['status']='completed';state['phase']='bounded research complete'
    state['message']='Selection frozen. No blind test score claimed. Review provenance limits before a single locked test evaluation.'
    write_state(state);print(json.dumps(state['confirmation']),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true');args=p.parse_args()
    if args.self_test: self_test()
    else:
        try: main()
        except Exception as e:
            traceback.print_exc()
            path=OUT/'state.json';state=json.load(open(path)) if path.exists() else {}
            state.update(status='failed',message=f'{type(e).__name__}: {e}');write_state(state)
            raise

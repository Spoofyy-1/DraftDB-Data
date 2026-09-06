"""Only TabICL's requested ensemble count changes; source X designs stay frozen."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import importlib.util,json,hashlib,time,copy
import numpy as np
R=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('r8y_frozen_x',R/'x_reference/worker.py');X=importlib.util.module_from_spec(spec);spec.loader.exec_module(X);B=X.B

def plan():return json.loads((R/'plan.json').read_text())
def references():return {(e['config']['id'],e['seed']):e for e in json.loads((R/'references.json').read_text())['records']}
def design(fold,context,p):
    _,bp,_,_=B._prepared()
    if context=='baseline':
        v=next(v for v in bp['variants'] if v['id']=='baseline');a,b,f=B._design(fold,v,bp);return a,b,f,None
    xp=X.load_plan();v=next(v for v in xp['variants'] if v['id']==context);return X.design_pair(fold,v,xp,bp)
def constructor(p,variant,seed):
    from tabicl import TabICLRegressor
    kwargs={**p['model_constructor'],'n_estimators':variant['n_estimators'],'random_state':seed}
    model=TabICLRegressor(**kwargs);actual=model.get_params(deep=False)
    assert all(actual[k]==v for k,v in kwargs.items())
    return model,kwargs

def run_variant(vid,seed):
    start=time.time();p=plan();v=next(v for v in p['variants'] if v['id']==vid);assert seed in p['seeds']
    E,bp,g,folds=B._prepared();os.environ['SEED_SHIFT']=str(seed);rows=[]
    for fold in folds:
        atr,ate,families,pair=design(fold,v['context'],p);E.H.audit_features(list(atr));model,kwargs=constructor(p,v,seed)
        model.fit(atr.astype(float),fold['yy']);raw=np.asarray(model.predict(ate.astype(float)),dtype=float)
        assert len(raw)==len(ate) and np.isfinite(raw).all()
        pred,ties=B._canonical_predictions(ate,raw,fold['te'].pid.tolist());score=B.rho(pred,fold['truth'])
        generator=model.ensemble_generator_;effective=sum(len(group) for group in generator.ensemble_configs_.values());width=int(generator.n_features_in_)
        assert effective==min(v['n_estimators'],width)
        audit={**fold['audit'],'input_columns':list(atr),'families':families,'registered_model_parameters':kwargs,'canonical_prediction_ties':ties,'raw_feature_count':len(atr.columns),'training_nonconstant_columns':int((atr.nunique()>1).sum())}
        if pair is not None:audit['pair_design']=pair
        rows.append({'season':fold['year'],'k':fold['k'],'n':len(ate),'ntrain':len(atr),'cutoff':fold['cutoff'],'max_label_season':fold['audit']['max_label_season'],'stack':score,'draft':B.rho(-fold['te'].actual_pick,fold['truth']),'members':{'tabicl':score},'audit':audit,
                     'capacity':{'requested':v['n_estimators'],'effective_estimators':effective,'effective_features':width,'effective_constructor':{k:model.get_params(deep=False)[k] for k in kwargs}},
                     'predictions':[{'pid':pid,'score':float(a),'raw_score':float(b)} for pid,a,b in zip(fold['te'].pid,pred,raw)]})
    return {'config':v,'seed':seed,'task_id':f'{vid}_seed{seed}','rows':rows,'score':float(np.mean([r['stack'] for r in rows])),'seconds':round(time.time()-start,2),'diagnostic_only':True}

def validate_entry(entry,p=None):
    p=p or plan();v=next(v for v in p['variants'] if v['id']==entry['config']['id']);assert entry['config']==v and entry['seed']in p['seeds'] and entry['diagnostic_only']
    assert entry['task_id']==f"{v['id']}_seed{entry['seed']}" and len(entry['rows'])==3
    ref=references()[(v['context'],entry['seed'])];assert np.isclose(entry['score'],np.mean([r['stack'] for r in entry['rows']]))
    for row,old in zip(entry['rows'],ref['rows']):
        assert row['season']==old['season'] and row['cutoff']==old['cutoff'];B._validate_tie_record(row)
        a=copy.deepcopy(row['audit']);b=copy.deepcopy(old['audit']);a.pop('canonical_prediction_ties');b.pop('canonical_prediction_ties');b['registered_model_parameters']['n_estimators']=v['n_estimators'];assert a==b
        c=row['capacity'];assert c['requested']==v['n_estimators'] and c['effective_features']==row['audit']['training_nonconstant_columns']
        assert c['effective_estimators']==min(v['n_estimators'],c['effective_features']) and c['effective_constructor']==row['audit']['registered_model_parameters']
        if v['n_estimators']==32:assert row['audit']==old['audit'] and row['predictions']==old['predictions'] and row['stack']==old['stack']
    if v['n_estimators']==32:assert entry['score']==ref['score']

def summarize_matched(entries):
    p=plan();tasks={}
    for entry in entries:
        validate_entry(entry,p);key=(entry['config']['context'],entry['config']['n_estimators'],entry['seed']);assert key not in tasks;tasks[key]=entry
    missing=[f'{c}_n32_seed{s}' for c in p['contexts'] for s in p['seeds'] if (c,32,s)not in tasks]
    common={'completed_tasks':len(tasks),'expected_tasks':p['execution']['task_count'],'reference_replays_passed':6-len(missing),'reference_replays_pending':missing,'interpretation_allowed':not missing,'diagnostic_only':True,'automatic_promotion':False}
    if missing:return {**common,'size_results':[]}
    results=[]
    def row(c,n,s,y):return next(r for r in tasks[(c,n,s)]['rows'] if r['season']==y)
    for n in p['sizes']:
        if not all((c,n,s)in tasks for c in p['contexts'] for s in p['seeds']):continue
        paired=[{'seed':s,'season':y,'baseline':row('baseline',n,s,y)['stack'],'pair':row('pair06_RR',n,s,y)['stack'],'pair_minus_baseline':row('pair06_RR',n,s,y)['stack']-row('baseline',n,s,y)['stack'],
                 'baseline_minus_n32':row('baseline',n,s,y)['stack']-row('baseline',32,s,y)['stack'],'pair_minus_n32':row('pair06_RR',n,s,y)['stack']-row('pair06_RR',32,s,y)['stack']} for s in p['seeds'] for y in p['folds']]
        keys=['pair_minus_baseline','baseline_minus_n32','pair_minus_n32']
        results.append({'requested_n':n,'baseline_mean':float(np.mean([r['baseline'] for r in paired])),'pair_mean':float(np.mean([r['pair'] for r in paired])),**{k:float(np.mean([r[k] for r in paired])) for k in keys},
                        'fold_differences':{str(y):{k:float(np.mean([r[k] for r in paired if r['season']==y])) for k in keys} for y in p['folds']},'seed_differences':{str(s):{k:float(np.mean([r[k] for r in paired if r['seed']==s])) for k in keys} for s in p['seeds']},'paired_rows':paired,
                        'effective_counts':{c:sorted({r['capacity']['effective_estimators'] for s in p['seeds'] for r in tasks[(c,n,s)]['rows']}) for c in p['contexts']}})
    return {**common,'size_results':results,'metric':'Pre2019 mean-fold Spearman, not classification accuracy','capacity_note':p['capacity_note'],'requested_to_evaluated':p.get('requested_to_evaluated',{})}

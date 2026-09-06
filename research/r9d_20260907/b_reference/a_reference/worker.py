"""Final-design ablations, preserving X source preparation and model settings."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import json,hashlib,importlib.util,time,copy,collections
import numpy as np
R=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('r9a_frozen_x',R/'x_reference/worker.py');X=importlib.util.module_from_spec(spec);spec.loader.exec_module(X);B=X.B
_PLAN=None;_REF=None;_FULL={}
def load_plan():
    global _PLAN
    if _PLAN is None:
        p=json.loads((R/'plan.json').read_text());m=json.loads((R/'source_manifest.json').read_text())
        for name,h in m['files'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==h,name
        assert hashlib.sha256((R/'queue_runtime.py').read_bytes()).hexdigest()==m['verified_scheduler_sha256']
        assert p['diagnostic_only'] and p['no_confirmation_or_test_scoring'] and len(p['variants'])*len(p['seeds'])==3810
        xp=X.load_plan()
        for key in ['folds','seeds','permutation_seeds','model_constructor','ordering_policy']:assert p[key]==xp[key]
        assert len(p['columns'])==47 and p['columns']==sorted(set(p['columns']))
        _PLAN=p
    return _PLAN

def references():
    global _REF
    if _REF is None:_REF={e['seed']:e for e in json.loads((R/'references.json').read_text())['records']}
    return _REF

def full_design(fold):
    year=fold['year']
    if year not in _FULL:
        _,bp,_,_=B._prepared();xp=X.load_plan();v=next(v for v in xp['variants'] if v['id']=='pair06_RR')
        atr,ate,families,pair=X.design_pair(fold,v,xp,bp)
        old=next(r for r in references()[0]['rows'] if r['season']==year)
        assert list(atr)==list(ate)==old['audit']['input_columns']
        assert families==old['audit']['families'] and pair==old['audit']['pair_design']
        for k,value in fold['audit'].items():assert old['audit'][k]==value,(year,k)
        assert [B._hash(k) for k in B._exact_vector_keys(ate)]==old['audit']['canonical_prediction_ties']['row_vector_hashes']
        _FULL[year]=(atr,ate,families,pair)
    return _FULL[year]

def apply_variant(original,metadata,v,role):
    p=load_plan();assert sorted(original)==p['columns'] and role in ['train','validation']
    affected=v['columns'];assert len(affected)==len(set(affected)) and set(affected)<=set(original)
    keep=[c for c in original if c not in affected]
    if v['kind']=='delete':
        assert len(affected)in [1,2];out=original.drop(columns=affected).copy();invariants=None
    else:
        assert v['kind']=='permutation' and len(affected)==1 and v['permutation_seed']in p['permutation_seeds']
        out=original.copy();before=original[affected]
        values=B._vector_shuffle(before,metadata,'fifty:registered_input:'+affected[0],v['permutation_seed'],role)
        assert values.isna().equals(before.isna());out[affected]=values
        invariants={'original':B._vector_invariants(before,metadata),'permuted':B._vector_invariants(values,metadata),'changed_observed_values':int((values.notna()&values.ne(before)).sum().sum())}
        assert invariants['original']==invariants['permuted']
    assert out[keep].equals(original[keep]) and out.index.equals(original.index)
    audit={'full_columns':list(original),'final_columns':list(out),'full_matrix_hash':B._matrix_hash(original),'final_matrix_hash':B._matrix_hash(out),'unaffected_columns':keep,'original_unaffected_hash':B._matrix_hash(original[keep]),'final_unaffected_hash':B._matrix_hash(out[keep]),'permutation':invariants}
    return out,audit

def design(fold,v):
    atr,ate,families,pair=full_design(fold)
    tr,a=apply_variant(atr,fold['tr'],v,'train');te,b=apply_variant(ate,fold['te'],v,'validation')
    return tr,te,families,pair,{'kind':v['kind'],'columns':v['columns'],'permutation_seed':v.get('permutation_seed'),'train':a,'validation':b,'plan_sha256':hashlib.sha256((R/'plan.json').read_bytes()).hexdigest()}

def run_variant(vid,seed):
    p=load_plan();v=next(v for v in p['variants'] if v['id']==vid);assert seed in p['seeds']
    if vid==p['reference_id']:return X.run_variant(vid,seed)
    start=time.time();E,bp,g,folds=B._prepared();os.environ['SEED_SHIFT']=str(seed);rows=[]
    for fold in folds:
        atr,ate,families,pair,proof=design(fold,v);E.H.audit_features(list(atr))
        model,kwargs=B.make_registered_model(E.cfg_of('tabicl',g,list(atr)));assert kwargs=={**p['model_constructor'],'random_state':seed}
        model.fit(atr.astype(float),fold['yy']);raw=np.asarray(model.predict(ate.astype(float)),dtype=float)
        assert len(raw)==len(ate) and np.isfinite(raw).all()
        pred,ties=B._canonical_predictions(ate,raw,fold['te'].pid.tolist());score=B.rho(pred,fold['truth'])
        rows.append({'season':fold['year'],'k':fold['k'],'n':len(ate),'ntrain':len(atr),'cutoff':fold['cutoff'],'max_label_season':fold['audit']['max_label_season'],'stack':score,'draft':B.rho(-fold['te'].actual_pick,fold['truth']),'members':{'tabicl':score},
        'audit':{**fold['audit'],'input_columns':list(atr),'families':families,'pair_design':pair,'registered_model_parameters':kwargs,'canonical_prediction_ties':ties,'raw_feature_count':len(atr.columns),'training_nonconstant_columns':int((atr.nunique()>1).sum()),'ablation':proof},
        'predictions':[{'pid':pid,'score':float(a),'raw_score':float(b)} for pid,a,b in zip(fold['te'].pid,pred,raw)]})
    return {'config':v,'seed':seed,'task_id':f'{vid}_seed{seed}','rows':rows,'score':float(np.mean([r['stack'] for r in rows])),'seconds':round(time.time()-start,2),'diagnostic_only':True}

def validate_entry(entry,p=None):
    p=p or load_plan();v=next(v for v in p['variants'] if v['id']==entry['config']['id']);seed=entry['seed']
    assert 'error'not in entry and entry['diagnostic_only'] and entry['config']==v and seed in p['seeds']
    assert entry['task_id']==f"{v['id']}_seed{seed}" and [r['season'] for r in entry['rows']]==p['folds']
    assert np.isfinite(entry['score']) and np.isclose(entry['score'],np.mean([r['stack'] for r in entry['rows']]),rtol=0,atol=1e-15)
    ref=references()[seed]
    if v['id']==p['reference_id']:X.exact_reference(entry,ref);return
    for row,old in zip(entry['rows'],ref['rows']):
        B._validate_tie_record(row);a=row['audit'];o=old['audit'];year=row['season']
        assert row['cutoff']==year-1 and a['max_label_season']<=year-1 and a['training_max_draft_year']<=year-2
        for key in ['season','k','n','ntrain','cutoff','max_label_season']:assert row[key]==old[key]
        assert [r['pid'] for r in row['predictions']]==[r['pid'] for r in old['predictions']]
        for key in o:
            if key not in ['input_columns','canonical_prediction_ties','raw_feature_count','training_nonconstant_columns']:assert a[key]==o[key],key
        expected=[c for c in o['input_columns'] if v['kind']!='delete' or c not in v['columns']]
        assert a['input_columns']==expected and a['raw_feature_count']==len(expected) and a['training_nonconstant_columns']<=len(expected)
        proof=a['ablation'];assert proof['kind']==v['kind'] and proof['columns']==v['columns'] and proof['permutation_seed']==v.get('permutation_seed')
        assert proof['plan_sha256']==hashlib.sha256((R/'plan.json').read_bytes()).hexdigest()
        for role in ['train','validation']:
            z=proof[role];assert z['full_columns']==o['input_columns'] and z['final_columns']==expected
            assert z['unaffected_columns']==[c for c in o['input_columns'] if c not in v['columns']]
            assert z['original_unaffected_hash']==z['final_unaffected_hash']
            if v['kind']=='delete':assert z['permutation'] is None and z['final_matrix_hash']==z['original_unaffected_hash']
            else:assert z['permutation']['original']==z['permutation']['permuted'] and z['permutation']['original']['columns']==v['columns']

def summarize_matched(entries):
    p=load_plan();tasks={};full_hashes=collections.defaultdict(set);streams=collections.defaultdict(set)
    for entry in entries:
        validate_entry(entry,p);key=(entry['config']['id'],entry['seed']);assert key not in tasks;tasks[key]=entry
        if entry['config']['id']!=p['reference_id']:
            for row in entry['rows']:
                for role in ['train','validation']:
                    proof=row['audit']['ablation'][role];full_hashes[(row['season'],role)].add(proof['full_matrix_hash'])
                    streams[(entry['config']['id'],row['season'],role)].add(proof['final_matrix_hash'])
    assert all(len(v)==1 for v in list(full_hashes.values())+list(streams.values()))
    missing=[f"{p['reference_id']}_seed{s}" for s in p['seeds'] if (p['reference_id'],s)not in tasks]
    common={'completed_tasks':len(tasks),'expected_tasks':3810,'reference_replays_passed':3-len(missing),'reference_replays_pending':missing,'interpretation_allowed':not missing,'diagnostic_only':True,'automatic_promotion':False,'metric':'Pre2019 mean fold Spearman, not classification accuracy'}
    if missing:return {**common,'ablations':[],'permutation_controls':[]}
    baseline=float(np.mean([tasks[(p['reference_id'],s)]['score'] for s in p['seeds']]))
    def paired(v):
        if not all((v['id'],s)in tasks for s in p['seeds']):return None
        rows=[{'seed':s,'season':a['season'],'score':a['stack'],'full_score':b['stack'],'delta':a['stack']-b['stack']} for s in p['seeds'] for a,b in zip(tasks[(v['id'],s)]['rows'],tasks[(p['reference_id'],s)]['rows'])]
        return {'id':v['id'],'kind':v['kind'],'columns':v['columns'],'source_fields':[p['column_meanings'][c] for c in v['columns']],'real_mean':float(np.mean([r['score'] for r in rows])),'mean_delta_vs_full':float(np.mean([r['delta'] for r in rows])),
        'fold_deltas':{str(y):float(np.mean([r['delta'] for r in rows if r['season']==y])) for y in p['folds']},'seed_deltas':{str(s):float(np.mean([r['delta'] for r in rows if r['seed']==s])) for s in p['seeds']},'paired_rows':rows}
    deletions=[];perms=[]
    for v in p['variants']:
        if v['id']==p['reference_id']:continue
        result=paired(v)
        if result is not None:
            if v['kind']=='delete':deletions.append(result)
            else:result['permutation_seed']=v['permutation_seed'];perms.append(result)
    controls=[]
    for c in p['columns']:
        group=[r for r in perms if r['columns']==[c]]
        if len(group)==3:
            rows=[r for item in group for r in item['paired_rows']]
            controls.append({'column':c,'source_field':p['column_meanings'][c],'permutation_mean':float(np.mean([r['score'] for r in rows])),'permutation_minus_full':float(np.mean([r['delta'] for r in rows])),'full_minus_permutation':-float(np.mean([r['delta'] for r in rows])),
            'fold_deltas':{str(y):float(np.mean([r['delta'] for r in rows if r['season']==y])) for y in p['folds']},'seed_deltas':{str(s):float(np.mean([r['delta'] for r in rows if r['seed']==s])) for s in p['seeds']}})
    return {**common,'full_score':baseline,'ablations':deletions,'permutation_arms':perms,'permutation_controls':controls,'completed_deletions':len(deletions),'expected_deletions':1128,'pending_tasks':3810-len(tasks),'limitations':p['controls']}

"""Matched pair diagnostics on the unchanged W source-only backbone."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import sys,importlib.util,json,hashlib,time,traceback,collections
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
sys.path.append(str(ROOT/'base'))
spec=importlib.util.spec_from_file_location('r8x_frozen_base',ROOT/'base/worker.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)


def load_plan():
    plan=json.loads((ROOT/'plan.json').read_text());manifest=json.loads((ROOT/'source_manifest.json').read_text())
    assert plan['diagnostic_only'] and plan['no_confirmation_or_test_scoring']
    assert len(plan['variants'])*len(plan['seeds'])==318
    for name,expected in manifest['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
    assert hashlib.sha256((ROOT/'queue_runtime.py').read_bytes()).hexdigest()==manifest['verified_scheduler_sha256']
    baseplan=json.loads((ROOT/'base/plan.json').read_text())
    for key in ['folds','seeds','permutation_seeds','model_constructor','ordering_policy','source_filter']:assert plan[key]==baseplan[key],key
    assert plan['pairs']==plan['registration']['pairs'] and all(pair==sorted(pair) for pair in plan['pairs'])
    return plan


def pair_values(frame,pair,arm,seed,role):
    original=frame[pair].astype(float).copy();values=original.copy()
    assert pair==sorted(pair) and arm in ['RR','RP','PR','PP']
    if arm=='PP':values=B._vector_shuffle(original,frame,'fifty:pair_joint:'+':'.join(pair),seed,role)
    else:
        for i,feature in enumerate(pair):
            if arm[i]=='P':values[feature]=B._vector_shuffle(original[[feature]],frame,'fifty:'+feature,seed,role)[feature]
    assert values.isna().equals(original.isna())
    marginal={f:B._vector_invariants(values[[f]],frame) for f in pair}
    assert marginal=={f:B._vector_invariants(original[[f]],frame) for f in pair}
    joint=B._vector_invariants(values,frame);original_joint=B._vector_invariants(original,frame)
    if arm in ['RR','PP']:assert joint==original_joint
    for i,f in enumerate(pair):
        if arm[i]=='R':assert values[f].equals(original[f])
    return values,{'features':pair,'matrix_hash':B._matrix_hash(values),'original_matrix_hash':B._matrix_hash(original),
                   'field_matrix_hashes':{f:B._matrix_hash(values[[f]]) for f in pair},
                   'original_field_matrix_hashes':{f:B._matrix_hash(original[[f]]) for f in pair},
                   'marginals':marginal,'joint_invariants':joint,'original_joint_invariants':original_joint,
                   'changed_observed_values':int((values.notna()&values.ne(original)).sum().sum())}


def design_pair(fold,variant,plan,baseplan):
    baseline=next(v for v in baseplan['variants'] if v['id']=='baseline')
    atr,ate,families=B._design(fold,baseline,baseplan)
    pair=variant['pair'];assert pair in plan['pairs'] and pair==sorted(pair)
    assert all(f in fold['source_columns']['fifty'] for f in pair)
    audit={'features':pair,'slots':plan['pair_slots'],'arm':variant['arm'],'permutation_seed':variant['permutation_seed'],'plan_sha256':hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest()}
    for role,frame,target in [('train',fold['tr'],atr),('validation',fold['te'],ate)]:
        before=B._matrix_hash(target);values,proof=pair_values(frame,pair,variant['arm'],variant['permutation_seed'],role)
        for f,slot in zip(pair,plan['pair_slots']):target[slot]=values[f]
        assert before==B._matrix_hash(target.iloc[:,:45])
        proof['fixed_background_matrix_hash']=before;audit[role]=proof
    assert list(atr)==list(ate)==fold['audit']['ordered_base_columns']+['slot_037','slot_038','slot_039','slot_040']+plan['pair_slots']
    assert len(atr.columns)==47
    return atr,ate,families,audit


def run_variant(vid,seed):
    started=time.time();plan=load_plan();variant=next(v for v in plan['variants'] if v['id']==vid)
    assert seed in plan['seeds']
    if 'pair'not in variant:
        record=B.run_variant(vid,seed);record['task_id']=f'{vid}_seed{seed}';record['seed']=seed;return record
    try:
        E,baseplan,g,folds=B._prepared();os.environ['SEED_SHIFT']=str(seed);rows=[]
        for fold in folds:
            atr,ate,families,proof=design_pair(fold,variant,plan,baseplan);E.H.audit_features(list(atr))
            model,kwargs=B.make_registered_model(E.cfg_of('tabicl',g,list(atr)))
            assert kwargs=={**plan['model_constructor'],'random_state':seed}
            model.fit(atr.astype(float),fold['yy']);raw=np.asarray(model.predict(ate.astype(float)),dtype=float)
            assert len(raw)==len(ate) and np.isfinite(raw).all()
            pred,ties=B._canonical_predictions(ate,raw,fold['te'].pid.tolist());score=B.rho(pred,fold['truth'])
            row={'season':fold['year'],'k':fold['k'],'n':len(ate),'ntrain':len(atr),'cutoff':fold['cutoff'],'max_label_season':fold['audit']['max_label_season'],
                 'stack':score,'draft':B.rho(-fold['te'].actual_pick,fold['truth']),'members':{'tabicl':score},
                 'audit':{**fold['audit'],'input_columns':list(atr),'families':families,'pair_design':proof,'registered_model_parameters':kwargs,
                          'canonical_prediction_ties':ties,'raw_feature_count':len(atr.columns),'training_nonconstant_columns':int((atr.nunique()>1).sum())},
                 'predictions':[{'pid':pid,'score':float(p),'raw_score':float(r)} for pid,p,r in zip(fold['te'].pid,pred,raw)]}
            rows.append(row)
        record={'config':variant,'seed':seed,'score':float(np.mean([r['stack'] for r in rows])),'rows':rows,'diagnostic_only':True,'seconds':round(time.time()-started,1)}
    except Exception as error:
        traceback.print_exc();record={'config':variant,'seed':seed,'diagnostic_only':True,'error':repr(error),'seconds':round(time.time()-started,1)}
    record['task_id']=f'{vid}_seed{seed}';return record


def exact_reference(record,reference):
    assert record['config']==reference['config'] and record['score']==reference['score'] and record['seed']==reference['seed']
    assert len(record['rows'])==len(reference['rows'])
    for a,b in zip(record['rows'],reference['rows']):
        assert a['season']==b['season'] and a['stack']==b['stack'] and a['predictions']==b['predictions']
        assert a['audit']==b['audit']


def validate_entry(entry,plan=None):
    plan=plan or load_plan();config=next(v for v in plan['variants'] if v['id']==entry['config']['id'])
    assert 'error'not in entry and entry['config']==config and entry['seed']in plan['seeds'] and entry['diagnostic_only']
    assert entry['task_id']==f"{config['id']}_seed{entry['seed']}" and len(entry['rows'])==3
    assert [r['season'] for r in entry['rows']]==plan['folds']
    assert np.isclose(entry['score'],np.mean([r['stack'] for r in entry['rows']]))
    for row in entry['rows']:
        a=row['audit'];year=row['season'];B._validate_tie_record(row)
        assert row['cutoff']==year-1 and a['max_label_season']<=year-1 and a['training_max_draft_year']<=year-2
        assert a['source_only_baseline'] and a['ordering_policy_hash']==B._hash(plan['ordering_policy'])
        assert a['registered_model_parameters']=={**plan['model_constructor'],'random_state':entry['seed']}
        prefix=a['ordered_base_columns']+['slot_037','slot_038','slot_039','slot_040']
        assert set(a['families'])=={'consensus'} or ('pair'not in config and set(a['families'])=={'consensus','fifty'})
        if 'pair'in config:
            proof=a['pair_design'];assert proof['features']==config['pair'] and proof['slots']==plan['pair_slots'] and proof['arm']==config['arm'] and proof['permutation_seed']==config['permutation_seed']
            assert proof['plan_sha256']==hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest()
            assert a['input_columns']==prefix+plan['pair_slots'] and a['raw_feature_count']==47
            for role in ['train','validation']:
                p=proof[role];assert p['features']==config['pair'] and set(p['marginals'])==set(config['pair'])
                if config['arm']in ['RR','PP']:assert p['joint_invariants']==p['original_joint_invariants']
                for i,f in enumerate(config['pair']):
                    if config['arm'][i]=='R':assert p['field_matrix_hashes'][f]==p['original_field_matrix_hashes'][f]
        else:
            expected=prefix+([] if config['id']=='baseline' else ['slot_041'])
            assert a['input_columns']==expected and a['raw_feature_count']==len(expected)
    if 'pair'not in config:
        references=json.loads((ROOT/'w_reference.json').read_text())['records']
        exact_reference(entry,next(r for r in references if r['config']['id']==config['id'] and r['seed']==entry['seed']))


def summarize_matched(entries):
    plan=load_plan();tasks={};streams=collections.defaultdict(set)
    for entry in entries:
        validate_entry(entry,plan);key=(entry['config']['id'],entry['seed']);assert key not in tasks;tasks[key]=entry
    for year in plan['folds']:
        rows=[next(r for r in e['rows'] if r['season']==year) for e in tasks.values()]
        for key in ['study_hash','ordered_base_columns','base_columns_hash','training_pid_hash','validation_pid_hash','training_labels_hash','training_matrix_hash','validation_matrix_hash','source_selection_hash','ordering_policy_hash']:
            assert len({B._hash(r['audit'][key]) for r in rows})<=1,(year,key)
        for role in ['train','validation']:
            assert len({r['audit']['families']['consensus'][role]['matrix_hash'] for r in rows})<=1
    refs=[(vid,s) for vid in plan['reference_ids'] for s in plan['seeds']];missing_refs=[f'{vid}_seed{s}' for vid,s in refs if (vid,s)not in tasks]
    for (vid,seed),entry in tasks.items():
        v=entry['config']
        if 'pair'not in v:continue
        for row in entry['rows']:
            for role in ['train','validation']:
                p=row['audit']['pair_design'][role]
                mode=('joint',tuple(v['pair']),v['permutation_seed']) if v['arm']=='PP' else None
                for i,f in enumerate(v['pair']):
                    fieldmode=mode if mode else ('real' if v['arm'][i]=='R' else v['permutation_seed'])
                    streams[(f,fieldmode,row['season'],role)].add(p['field_matrix_hashes'][f])
    assert all(len(values)==1 for values in streams.values()),'Pair value/control stream changed across arms/pairs/model seeds'
    common={'completed_tasks':len(tasks),'expected_tasks':318,'diagnostic_only':True,'automatic_promotion':False,'reference_replays_passed':18-len(missing_refs),'reference_replays_pending':missing_refs,'interpretation_allowed':not missing_refs}
    if missing_refs:return {**common,'pairs':[],'pending':plan['pairs']}
    baseline=float(np.mean([tasks[('baseline',s)]['score'] for s in plan['seeds']]))
    singles={f:float(np.mean([tasks[(f+'_real',s)]['score'] for s in plan['seeds']])) for f in plan['selected_features']}
    results=[];pending=[]
    for i,pair in enumerate(plan['pairs']):
        variants=[v for v in plan['variants'] if v.get('pair')==pair]
        if not all((v['id'],s)in tasks for v in variants for s in plan['seeds']):pending.append(pair);continue
        paired=[]
        def row_of(vid,seed,year):return next(r for r in tasks[(vid,seed)]['rows'] if r['season']==year)
        for seed in plan['seeds']:
            for year in plan['folds']:
                real=row_of(f'pair{i:02d}_RR',seed,year);controls={a:[row_of(f'pair{i:02d}_{a}_{p}',seed,year) for p in plan['permutation_seeds']] for a in ['RP','PR','PP']}
                for control in sum(controls.values(),[]):
                    for key in ['input_columns','raw_feature_count','training_nonconstant_columns']:assert real['audit'][key]==control['audit'][key]
                    for role in ['train','validation']:
                        a=real['audit']['pair_design'][role];b=control['audit']['pair_design'][role]
                        for key in ['features','marginals','original_joint_invariants','original_matrix_hash','original_field_matrix_hashes','fixed_background_matrix_hash']:assert a[key]==b[key]
                means={a:float(np.mean([r['stack'] for r in records])) for a,records in controls.items()}
                paired.append({'seed':seed,'season':year,'RR':real['stack'],**means,'gain_A_given_B':real['stack']-means['PR'],'gain_B_given_A':real['stack']-means['RP'],'joint_gain':real['stack']-means['PP']})
        mean=lambda field:float(np.mean([r[field] for r in paired]))
        fold={str(y):{f:float(np.mean([r[f] for r in paired if r['season']==y])) for f in ['gain_A_given_B','gain_B_given_A','joint_gain']} for y in plan['folds']}
        seed_gains={str(s):{f:float(np.mean([r[f] for r in paired if r['seed']==s])) for f in ['gain_A_given_B','gain_B_given_A','joint_gain']} for s in plan['seeds']}
        candidate=mean('gain_A_given_B')>0 and mean('gain_B_given_A')>0 and all(min(v['gain_A_given_B'],v['gain_B_given_A'])>0 for v in fold.values()) and mean('RR')>max(singles[f] for f in pair)
        results.append({'id':f'pair{i:02d}','features':pair,'real_mean':mean('RR'),'control_means':{a:mean(a) for a in ['RP','PR','PP']},'gain_A_given_B':mean('gain_A_given_B'),'gain_B_given_A':mean('gain_B_given_A'),'joint_gain':mean('joint_gain'),
                        'real_minus_baseline_context_only':mean('RR')-baseline,'real_minus_single_context_only':{f:mean('RR')-singles[f] for f in pair},'fold_gains':fold,'seed_gains':seed_gains,'paired_rows':paired,'exploratory_complement_candidate':candidate})
    return {**common,'baseline_score_context_only':baseline,'single_scores_context_only':singles,'pairs':results,'pending':pending,'metric':'Pre2019 mean fold Spearman, not classification accuracy','interpretation':plan['controls']['limitations']}

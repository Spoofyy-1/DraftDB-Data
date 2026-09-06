"""Single-feature/control, canonical tie and summary checks without models."""
from pathlib import Path
import copy
import hashlib
import json
import numpy as np
import pandas as pd
import worker as W

ROOT=Path(__file__).resolve().parent
plan,manifest,x,labels=W._load_inputs()
assert len(plan['variants'])==41 and plan['execution']['task_count']==123
reference=json.loads((ROOT/'baseline_reference.json').read_text())
for name,digest in reference['source_data_hashes'].items():
    assert hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()==digest
assert hashlib.sha256((ROOT/'r8t_reference/worker.py').read_bytes()).hexdigest()==manifest['parent_r8t_worker_sha256']
assert hashlib.sha256((ROOT/'r8t_reference/plan.json').read_bytes()).hexdigest()==manifest['parent_r8t_plan_sha256']
base=plan['baseline_source_variant']['context_features']
folds=[];designs={};shuffle_checks=0;coverage={}
for year in plan['folds']:
    tr=W._canonical_rows(x[x.draft_year.between(plan['backbone']['window'],year-2)])
    te=W._canonical_rows(x[(x.draft_year==year)&x.was_drafted.eq(1)])
    used=labels[(labels.season_end<=year-1)&labels.pid.isin(tr.pid)]
    assert not set(used.pid)&set(te.pid) and used.season_end.max()<=year-1
    sources={};selection={};coverage[str(year)]={}
    for family in plan['families']:
        sources[family],selection[family]=W._eligible_columns(tr,plan['families'][family],plan['source_filter'])
    assert sources==plan['training_eligibility_registration'][str(year)] and len(sources['bio'])==10
    for feature in plan['single_features']:
        coverage[str(year)][feature]={}
        for role,frame in [('train',tr),('validation',te)]:
            values=frame[[feature]].astype(float);inv=W._vector_invariants(values,frame);counts=[]
            for seed in plan['permutation_seeds']:
                shuffled=W._vector_shuffle(values,frame,'bio:'+feature,seed,role)
                rev=frame.iloc[::-1];other=W._vector_shuffle(rev[[feature]],rev,'bio:'+feature,seed,role)
                pd.testing.assert_frame_equal(shuffled,other.reindex(frame.index))
                assert W._vector_invariants(shuffled,frame)==inv
                counts.append(int((values.notna()&values.ne(shuffled)).sum().sum()));shuffle_checks+=1
            coverage[str(year)][feature][role]={k:inv[k] for k in ['observed_rows','swappable_observed_rows','immovable_observed_rows']}
            coverage[str(year)][feature][role]['changed_values']=dict(zip(map(str,plan['permutation_seeds']),counts))
    audit={'study_hash':'fixture_only','ordered_base_columns':base,'base_columns_hash':W._hash(base),
           'training_pid_hash':W._hash(tr.pid.tolist()),'validation_pid_hash':W._hash(te.pid.tolist()),
           'training_labels_hash':'fixture_only','training_matrix_hash':W._matrix_hash(tr[base]),'validation_matrix_hash':W._matrix_hash(te[base]),
           'source_selection':selection,'source_selection_hash':W._hash(selection),'training_max_draft_year':int(tr.draft_year.max()),
           'max_label_season':int(used.season_end.max()),'source_only_baseline':True,'diagnostic_only':True,'ordering_policy_hash':W._hash(plan['ordering_policy'])}
    fold={'year':year,'cutoff':year-1,'k':min(5,2018-year),'tr':tr,'te':te,'btr':tr[base].copy(),'bte':te[base].copy(),'source_columns':sources,'audit':audit}
    for variant in plan['variants']:
        atr,ate,families=W._design(fold,variant,plan)
        assert not any(c.startswith(('bio_','med_','cons_','vcmb_')) or c in ['actual_pick','pid','draft_year'] for c in atr)
        assert list(atr)[41:45]==[plan['slot_mapping'][c] for c in plan['families']['consensus']]
        if variant['feature']:assert list(atr)[-1]==plan['common_bio_slot'] and families['bio']['train']['features']==[variant['feature']]
        raw=np.arange(len(ate),dtype=float)/len(ate);pred,ties=W._canonical_predictions(ate,raw,te.pid.tolist())
        designs[(year,variant['id'])]={'audit':{**audit,'input_columns':list(atr),'raw_feature_count':len(atr.columns),
            'training_nonconstant_columns':int((atr.nunique()>1).sum()),'families':families,'canonical_prediction_ties':ties},
            'predictions':[{'pid':pid,'score':float(p),'raw_score':float(r)} for pid,p,r in zip(te.pid,pred,raw)]}
    folds.append(fold)

# Fixtures never become model inputs, research results or displayed runs.
fixtures=[]
for variant in plan['variants']:
    for seed in plan['seeds']:
        rows=[]
        for fold in folds:
            score=.3+(fold['year']-2012)*.01+seed/100000
            if variant['bio_arm']=='real':score+=(plan['single_features'].index(variant['feature'])-5)*.01
            design=copy.deepcopy(designs[(fold['year'],variant['id'])]);design['audit']['registered_model_parameters']={**plan['model_constructor'],'random_state':seed}
            rows.append({'season':fold['year'],'stack':score,'n':len(fold['te']),'ntrain':len(fold['tr']),
                         'cutoff':fold['cutoff'],'max_label_season':fold['audit']['max_label_season'],**design})
        fixtures.append({'task_id':f"{variant['id']}_seed{seed}",'config':dict(variant),'seed':seed,'score':float(np.mean([r['stack'] for r in rows])),'rows':rows,'diagnostic_only':True})
summary=W.summarize_matched(fixtures)
assert summary['completed_tasks']==123 and not summary['pending']
for stat in summary['statistics']:assert np.isclose(stat['paired_mean_gain'],(plan['single_features'].index(stat['id'])-5)*.01)
assert W.summarize_matched(fixtures[:-1])['pending']==[plan['single_features'][-1]]
tests=[]
def rejects(name,mutate):
    changed=copy.deepcopy(fixtures);target=next(r for r in changed if r['config']['id']==plan['single_features'][0]+'_shuffle9317');mutate(target)
    try:W.summarize_matched(changed)
    except AssertionError:tests.append(name)
    else:raise AssertionError('Tamper accepted: '+name)
rejects('wrong_single_field',lambda r:r['rows'][0]['audit']['families']['bio']['train'].__setitem__('features',[plan['single_features'][1]]))
rejects('wrong_common_slot',lambda r:r['rows'][0]['audit']['input_columns'].__setitem__(-1,'actual_pick'))
rejects('changed_consensus',lambda r:r['rows'][0]['audit']['families']['consensus']['train'].__setitem__('matrix_hash','bad'))
rejects('changed_mask',lambda r:r['rows'][0]['audit']['families']['bio']['train']['invariants'].__setitem__('mask_hash','bad'))
rejects('future_label_cutoff',lambda r:r['rows'][0]['audit'].__setitem__('max_label_season',2012))
rejects('constructor_seed',lambda r:r['rows'][0]['audit']['registered_model_parameters'].__setitem__('random_state',999))
rejects('raw_prediction',lambda r:r['rows'][0]['predictions'][0].__setitem__('raw_score',999.))
rejects('duplicate_vector_hash',lambda r:r['rows'][0]['audit']['canonical_prediction_ties'].__setitem__('row_vector_hashes',['0'*64]*r['rows'][0]['n']))
tiny=pd.DataFrame({'x':[np.nan,np.nan,1.,1.+1e-15,0.,-0.]});raw=np.asarray([.1,.3,.4,.6,.8,1.]);pids=list('abcdef')
pred,ties=W._canonical_predictions(tiny,raw,pids)
assert pred[0]==pred[1]==.2 and pred[4]==pred[5]==.9 and pred[2]==raw[2] and pred[3]==raw[3]
perm=np.arange(6)[::-1];other,_=W._canonical_predictions(tiny.iloc[perm],raw[perm],[pids[i] for i in perm]);assert np.array_equal(pred,other[perm])
report={'passed':True,'gpu_models_run':0,'cpu_selector_run':False,'task_count':123,'source_file_hashes_checked':len(reference['source_data_hashes']),
        'shuffle_order_checks':shuffle_checks,'designs':len(designs),'matched_single_summary_fixture':True,'incomplete_results_withheld':True,
        'tamper_rejections':tests,'exact_duplicate_ties_and_no_quantization':True,'coverage':coverage,
        'server_preflight_required':'Both U and unchanged copied T CPU preparation must exactly match completed T college_consensus baseline, including full45-column matrices, labels, pids and columns.'}
(ROOT/'preflight.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='coverage'},indent=2))

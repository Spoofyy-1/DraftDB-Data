"""Input/control and audit-tamper fixtures. No estimator fitting or new scores."""
from pathlib import Path
import json,copy,collections
import numpy as np,pandas as pd
import worker as X
ROOT=Path(__file__).resolve().parent
plan=X.load_plan();B=X.B;baseplan,manifest,x,labels=B._load_inputs()
reference=json.loads((ROOT/'w_reference.json').read_text());refs=reference['records'];baseline=[e for e in refs if e['config']['id']=='baseline'][0]
assert len(plan['variants'])==106 and len(refs)==18
assert plan['selected_features']==sorted(r['id'] for r in reference['matched_summary']['statistics'] if r['real_minus_baseline_context_only']>0 and min(r['fold_gains'].values())>0 and min(r['seed_gains'].values())>0)
assert not X.summarize_matched([])['interpretation_allowed']
checks=0;reorder_checks=0;fixture_rows={};coverage={}

def joint_bags(frame,values):
    out=collections.defaultdict(collections.Counter)
    for i,row in values.iterrows():
        vals=tuple(None if pd.isna(v) else float(v).hex() for v in row)
        key=(int(frame.loc[i,'draft_year']),tuple(pd.isna(v) for v in row))
        out[key][vals]+=1
    return dict(out)

for year in plan['folds']:
    tr=B._canonical_rows(x[x.draft_year.between(2007,year-2)]);te=B._canonical_rows(x[(x.draft_year==year)&x.was_drafted.eq(1)])
    expected=next(r for r in baseline['rows'] if r['season']==year);cols=expected['audit']['ordered_base_columns']
    sources={family:B._eligible_columns(tr,fields,plan['source_filter'])[0] for family,fields in baseplan['families'].items()}
    assert all(f in sources['fifty'] for f in plan['selected_features'])
    audit=copy.deepcopy(expected['audit']);audit['training_matrix_hash']=B._matrix_hash(tr[cols]);audit['validation_matrix_hash']=B._matrix_hash(te[cols])
    fold={'year':year,'tr':tr,'te':te,'btr':tr[cols].copy(),'bte':te[cols].copy(),'source_columns':sources,'audit':audit}
    coverage[str(year)]={f:{'training_observed':int(tr[f].notna().sum()),'training_unique':int(tr[f].nunique())} for f in plan['selected_features']}
    for variant in [v for v in plan['variants'] if 'pair'in v]:
        atr,ate,families,proof=X.design_pair(fold,variant,plan,baseplan)
        assert list(atr)==cols+['slot_037','slot_038','slot_039','slot_040','slot_041','slot_042'] and atr.shape[1]==47
        pair=variant['pair'];arm=variant['arm'];seed=variant['permutation_seed']
        for role,frame in [('train',tr),('validation',te)]:
            values,p=X.pair_values(frame,pair,arm,seed,role)
            reverse,_=X.pair_values(frame.iloc[::-1],pair,arm,seed,role)
            pd.testing.assert_frame_equal(values,reverse.reindex(frame.index));reorder_checks+=1
            assert values.isna().equals(frame[pair].isna())
            if arm=='PP':assert joint_bags(frame,values)==joint_bags(frame,frame[pair])
            for i,f in enumerate(pair):
                assert joint_bags(frame,values[[f]])==joint_bags(frame,frame[[f]])
                if arm[i]=='R':pd.testing.assert_series_equal(values[f],frame[f].astype(float))
                elif arm!='PP':
                    expected_single=B._vector_shuffle(frame[[f]].astype(float),frame,'fifty:'+f,seed,role)
                    pd.testing.assert_series_equal(values[f],expected_single[f])
        raw=np.arange(len(te),dtype=float)/len(te);canonical,ties=B._canonical_predictions(ate,raw,te.pid.tolist())
        # Fixture predictions are deliberately artificial audit-test records only.
        # Reference base audit hashes remain fixed; actual CPU preparation is a separate mandatory server check.
        fa=copy.deepcopy(expected['audit']);fa.update(input_columns=list(atr),raw_feature_count=47,training_nonconstant_columns=int((atr.nunique()>1).sum()),pair_design=proof,canonical_prediction_ties=ties)
        fa['families']={'consensus':copy.deepcopy(expected['audit']['families']['consensus'])}
        fixture_rows[(variant['id'],year)]={'season':year,'n':len(te),'ntrain':len(tr),'cutoff':year-1,'max_label_season':expected['max_label_season'],'audit':fa,
            'predictions':[{'pid':pid,'raw_score':float(r),'score':float(p)} for pid,r,p in zip(te.pid,raw,canonical)]}
        checks+=1
fixtures=copy.deepcopy(refs)
for e in fixtures:e['task_id']=f"{e['config']['id']}_seed{e['seed']}"
for v in [v for v in plan['variants'] if 'pair'in v]:
    for seed in plan['seeds']:
        rows=[]
        for year in plan['folds']:
            row=copy.deepcopy(fixture_rows[(v['id'],year)]);row['audit']['registered_model_parameters']={**plan['model_constructor'],'random_state':seed}
            row['stack']={'RR':.5,'RP':.4,'PR':.42,'PP':.35}[v['arm']];rows.append(row)
        fixtures.append({'config':copy.deepcopy(v),'seed':seed,'score':float(np.mean([r['stack'] for r in rows])),'rows':rows,'diagnostic_only':True,'task_id':f"{v['id']}_seed{seed}"})
summary=X.summarize_matched(fixtures)
assert summary['interpretation_allowed'] and summary['reference_replays_passed']==18 and len(summary['pairs'])==10
for r in summary['pairs']:
    assert np.isclose(r['gain_A_given_B'],.08) and np.isclose(r['gain_B_given_A'],.1) and np.isclose(r['joint_gain'],.15)
    assert r['exploratory_complement_candidate']
assert not X.summarize_matched([e for e in fixtures if e['task_id']!='baseline_seed0'])['interpretation_allowed']
assert len(X.summarize_matched(fixtures[:-1])['pending'])==1
rejections=[]
def rejects(name,mutate,reference_target=False):
    changed=copy.deepcopy(fixtures);entry=changed[0] if reference_target else next(e for e in changed if e['config']['id']=='pair00_PP_9317')
    mutate(entry)
    try:X.summarize_matched(changed)
    except AssertionError:rejections.append(name)
    else:raise AssertionError('Tamper accepted: '+name)
rejects('changed_reference',lambda e:e['rows'][0]['predictions'][0].__setitem__('raw_score',999.),True)
rejects('changed_marginal',lambda e:e['rows'][0]['audit']['pair_design']['train']['marginals'].__setitem__(plan['selected_features'][0],{}))
rejects('changed_joint_distribution',lambda e:e['rows'][0]['audit']['pair_design']['train'].__setitem__('joint_invariants',{}))
rejects('changed_slots',lambda e:e['rows'][0]['audit']['input_columns'].__setitem__(-1,'actual_pick'))
rejects('future_label_season',lambda e:e['rows'][0]['audit'].__setitem__('max_label_season',2012))
rejects('changed_consensus',lambda e:e['rows'][0]['audit']['families']['consensus']['train'].__setitem__('matrix_hash','changed'))
rejects('changed_constructor',lambda e:e['rows'][0]['audit']['registered_model_parameters'].__setitem__('random_state',999))
rejects('changed_background',lambda e:e['rows'][0]['audit']['pair_design']['train'].__setitem__('fixed_background_matrix_hash','changed'))
report={'passed':True,'models_fitted':0,'diagnostic_fixture_predictions_never_used_as_model_data':True,'task_count':318,'pair_fold_designs':checks,'reorder_checks':reorder_checks,'whole_pair_joint_bags_checked':True,'conditional_streams_exact_W_single_streams':True,'training_eligibility':coverage,'reference_gate_tasks':18,'reference_gating_fixture_passed':True,'conditional_gain_direction_fixture_passed':True,'tamper_rejections':rejections,'server_CPU_replay_required':True}
(ROOT/'preflight.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='training_eligibility'},indent=2))

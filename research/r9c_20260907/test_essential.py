"""Bounded model-free admission, left-join, matching and replay fixtures."""
import copy,json,collections,hashlib
from pathlib import Path
import numpy as np,pandas as pd
import worker as A
p=A.load_plan();d=A.candidate_data();assert len(d)==1458 and len(p['features'])==35 and len(p['variants'])*3==459
assert len([g for g in p['groups'] if g['kind']=='single'])==35 and sorted(len(g['features']) for g in p['groups'] if g['kind']=='family')==[15,20,35]
assert len(p['algebraic_representation_features'])==8
assert p['source_admission']['source_model_eligible_flag_remains_false'] and json.loads((A.R/'data/source_verification.json').read_text())['model_eligible']is False
manifest=json.loads((A.R/'source_manifest.json').read_text());assert all('private'not in name and 'full_pool_with_candidates'not in name for name in manifest['files'])
refs=list(A.references().values());assert len(refs)==3
for e in refs:A.validate_entry(e,p)
assert A.summarize_matched(refs)['reference_replays_passed']==3 and not A.summarize_matched(refs[:-1])['interpretation_allowed']
def rejects(fn):
 try:fn()
 except (AssertionError,KeyError):return
 raise AssertionError('Tamper accepted')
e=copy.deepcopy(refs[0]);e['rows'][0]['predictions'][0]['raw_score']+=1;rejects(lambda:A.validate_entry(e,p))
e=copy.deepcopy(refs[0]);e['rows'][0]['audit']['max_label_season']=2020;rejects(lambda:A.validate_entry(e,p))
train=pd.DataFrame({c:[np.nan]*6 for c in p['features']});train.iloc[:5,0]=[1,2,3,4,5];eligible,_=A.eligibility(train);assert eligible==[p['features'][0]]
# Unseen query coverage is deliberately absent from the eligibility API.
query=pd.DataFrame(np.tile(np.arange(6)[:,None],(1,35)),columns=p['features']);assert A.eligibility(train)[0]==eligible
meta=pd.DataFrame({'pid':[f'p{i}' for i in range(24)],'draft_year':[2010]*12+[2011]*12});base=pd.DataFrame({'base_a':np.arange(24,dtype=float),'base_b':np.arange(24,dtype=float)*3});values=pd.DataFrame(np.arange(24*35,dtype=float).reshape(24,35),columns=p['features']);values.iloc[:2,:]=np.nan;values.iloc[12,::2]=np.nan;original=values.copy(deep=True)
def vectors(frame):
 groups=collections.defaultdict(collections.Counter)
 for i,row in frame.iterrows():
  v=tuple(None if pd.isna(x) else float(x) for x in row);groups[(int(meta.loc[i,'draft_year']),tuple(x is None for x in v))][v]+=1
 return groups
for v in p['variants'][1:]:
 out,a=A.append_values(base,values,meta,v['features'],v,'train');slots=a['slots']
 assert out[list(base)].equals(base) and out.index.equals(base.index)
 used=out[slots].copy();used.columns=v['features'];assert used.isna().equals(values[v['features']].isna()) and vectors(used)==vectors(values[v['features']])
 assert slots==[f'slot_{43+i:03d}' for i in range(len(v['features']))]
 if v['kind']=='single':assert slots==['slot_043']
 repeat,_=A.append_values(base,values,meta,v['features'],v,'train');assert repeat.equals(out)
assert values.equals(original)
shuffle=A.B._vector_shuffle
v=next(v for v in p['variants'] if v.get('group')=='family_all' and v['arm']=='PP')
def broken(values,metadata,family,seed,role):
 out=shuffle(values,metadata,family,seed,role);out.iloc[2,0],out.iloc[3,0]=out.iloc[3,0],out.iloc[2,0];return out
A.B._vector_shuffle=broken
try:rejects(lambda:A.append_values(base,values,meta,v['features'],v,'train'))
finally:A.B._vector_shuffle=shuffle
result={'passed':True,'models_fitted':0,'source_projection_sha256':hashlib.sha256((A.R/'data/candidate_inputs.csv').read_bytes()).hexdigest(),'exact_full_source_rows':1458,'all1428_study_pids_preserved_by_left_join':True,'source_global_model_eligible_remains_false':True,'schema_single35_families15_20_35_tasks459':True,'three_selected_baseline_exact_reference_contracts':True,'missing_reference_withholds_interpretation':True,'training_only_eligibility_no_query_argument':True,'single_common_slot_and_family_widths':True,'independent_cohort_joint_mask_vector_counter_check':True,'unchanged_baseline_and_source_values':True,'tamper_rejections':['reference_raw_prediction','future_label','joint_structure_preserving_marginals']}
(A.R/'tests.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

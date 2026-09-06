"""Small model-free schema, full-reference and joint-vector control fixtures."""
import copy,itertools,json,collections
from pathlib import Path
import numpy as np,pandas as pd
import worker as A
p=A.load_plan();cols=p['columns'];selected=p['selected_columns'];new=[v for v in p['variants'] if v['id']not in p['reference_ids']];deletes=[v for v in new if v['kind']=='delete'];perms=[v for v in new if v['kind']=='permutation']
assert len(p['variants'])*3==330 and len(deletes)==16 and len(perms)==78 and len(p['reference_ids'])==16
subsets={s for size in [2,3,4,5] for s in itertools.combinations(selected,size)}
assert {tuple(v['columns']) for v in deletes}=={s for s in subsets if len(s)>=3}
assert {(tuple(v['columns']),v['permutation_seed']) for v in perms}==set(itertools.product(subsets,p['permutation_seeds']))
refs=list(A.references().values());assert len(refs)==48
for r in refs:A.validate_entry(r,p)
assert A.summarize_matched(refs)['reference_replays_passed']==48
assert not A.summarize_matched(refs[:-1])['interpretation_allowed']
def rejects(fn):
    try:fn()
    except (AssertionError,KeyError):return
    raise AssertionError('Tamper accepted')
for key in ['raw_score','score']:
    r=copy.deepcopy(refs[0]);r['rows'][0]['predictions'][0][key]+=0.01;rejects(lambda:A.validate_entry(r,p))
r=copy.deepcopy(refs[-1]);r['rows'][0]['audit']['max_label_season']=2020;rejects(lambda:A.validate_entry(r,p))
r=copy.deepcopy(refs[-1]);r['rows'][0]['audit']['registered_model_parameters']['n_estimators']=64;rejects(lambda:A.validate_entry(r,p))
meta=pd.DataFrame({'pid':[f'p{i}' for i in range(24)],'draft_year':[2010]*12+[2011]*12})
original=pd.DataFrame(np.arange(24*47,dtype=float).reshape(24,47),columns=cols);original.iloc[0:2,:]=np.nan;original.iloc[12,::2]=np.nan;before=original.copy(deep=True)
def independent_vectors(frame):
    groups=collections.defaultdict(collections.Counter)
    for i,row in frame.iterrows():
        vec=tuple(None if pd.isna(v) else float(v) for v in row);groups[(int(meta.loc[i,'draft_year']),tuple(v is None for v in vec))][vec]+=1
    return groups
for v in new:
    out,proof=A.apply_variant(original,meta,v,'train');keep=[c for c in cols if c not in v['columns']]
    assert out[keep].equals(original[keep]) and proof['original_unaffected_hash']==proof['final_unaffected_hash']
    if v['kind']=='delete':assert list(out)==keep
    else:
        assert out.isna().equals(original.isna()) and independent_vectors(out[v['columns']])==independent_vectors(original[v['columns']])
        repeat,_=A.apply_variant(original,meta,v,'train');assert out.equals(repeat)
assert original.equals(before)
shuffle=A.B._vector_shuffle
def broken_joint(values,metadata,family,seed,role):
    out=shuffle(values,metadata,family,seed,role);out.iloc[2,0],out.iloc[3,0]=out.iloc[3,0],out.iloc[2,0];return out
A.B._vector_shuffle=broken_joint
try:rejects(lambda:A.apply_variant(original,meta,perms[0],'train'))
finally:A.B._vector_shuffle=shuffle
bad=copy.deepcopy(perms[0]);bad['columns']=['actual_pick'];rejects(lambda:A.apply_variant(original,meta,bad,'train'))
bad=copy.deepcopy(perms[0]);bad['permutation_seed']=999;rejects(lambda:A.apply_variant(original,meta,bad,'train'))
result={'passed':True,'models_fitted':0,'new_deletion_subsets':16,'joint_permutation_subsets':26,'joint_permutation_variants':78,'tasks':330,'exact_A_reference_contracts':48,'missing_reference_blocks_interpretation':True,'independent_joint_vector_cohort_and_mask_counter_check':True,'unchanged_columns_order_and_original_immutability':True,'tamper_rejections':['raw_prediction','canonical_prediction','future_label','constructor','joint_covariance_without_marginal_change','unregistered_predictor','unregistered_permutation_seed']}
(Path(__file__).parent/'tests.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

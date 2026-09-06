"""Small model-free schema, reference and control fixtures."""
import copy,itertools,json
from pathlib import Path
import numpy as np,pandas as pd
import worker as A
p=A.load_plan();cols=p['columns'];deletes=[v for v in p['variants'] if v.get('kind')=='delete'];perms=[v for v in p['variants'] if v.get('kind')=='permutation']
assert len(p['variants'])*3==3810 and len(deletes)==1128 and len(perms)==141
assert {tuple(v['columns']) for v in deletes}=={(c,) for c in cols}|set(itertools.combinations(cols,2))
assert {(v['columns'][0],v['permutation_seed']) for v in perms}==set(itertools.product(cols,p['permutation_seeds']))
assert len({v['id'] for v in p['variants']})==1270
refs=list(A.references().values())
for r in refs:A.validate_entry(r,p)
assert A.summarize_matched(refs)['reference_replays_passed']==3
assert not A.summarize_matched(refs[:-1])['interpretation_allowed']
def rejects(fn):
    try:fn()
    except (AssertionError,KeyError):return
    raise AssertionError('Tamper accepted')
for key in ['raw_score','score']:
    r=copy.deepcopy(refs[0]);r['rows'][0]['predictions'][0][key]+=0.01;rejects(lambda:A.validate_entry(r,p))
r=copy.deepcopy(refs[0]);r['rows'][0]['audit']['max_label_season']=2020;rejects(lambda:A.validate_entry(r,p))
r=copy.deepcopy(refs[0]);r['rows'][0]['audit']['registered_model_parameters']['n_estimators']=64;rejects(lambda:A.validate_entry(r,p))
meta=pd.DataFrame({'pid':[f'p{i}' for i in range(24)],'draft_year':[2010]*12+[2011]*12})
original=pd.DataFrame(np.arange(24*47,dtype=float).reshape(24,47),columns=cols);original.iloc[0:2,:]=np.nan;original.iloc[12,::2]=np.nan
before=original.copy(deep=True)
for v in [x for x in deletes if len(x['columns'])==1]+[deletes[47],deletes[len(deletes)//2],deletes[-1]]+perms:
    out,proof=A.apply_variant(original,meta,v,'train')
    keep=[c for c in cols if c not in v['columns']];assert out[keep].equals(original[keep]) and proof['original_unaffected_hash']==proof['final_unaffected_hash']
    if v['kind']=='delete':assert list(out)==keep
    else:
        assert out.isna().equals(original.isna());assert proof['permutation']['original']==proof['permutation']['permuted']
        repeat,_=A.apply_variant(original,meta,v,'train');assert out.equals(repeat)
assert original.equals(before)
bad=copy.deepcopy(perms[0]);bad['columns']=['actual_pick'];rejects(lambda:A.apply_variant(original,meta,bad,'train'))
bad=copy.deepcopy(perms[0]);bad['permutation_seed']=999;rejects(lambda:A.apply_variant(original,meta,bad,'train'))
result={'passed':True,'models_fitted':0,'schema_complete':{'single_deletions':47,'double_deletions':1081,'permutation_variants':141,'fits':3810},'exact_full_X_references':3,'missing_reference_blocks_interpretation':True,'all47_permutation_mask_cohort_marginal_and_reproducibility_tests':True,'unaffected_values_order_and_original_immutability':True,'rejected':['raw_prediction','canonical_prediction','future_label','constructor','unregistered_predictor','unregistered_permutation_seed']}
(Path(__file__).parent/'tests.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

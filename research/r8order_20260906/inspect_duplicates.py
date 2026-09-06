"""Label-free attribution of order-audit inversions by a certified margin bound.

Reuse only saved pre2019 baseline predictions, never outcome labels or scores.
Their complete vector hash must match the audited model's baseline exactly.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
audit=json.loads((ROOT/'results/order_audit.json').read_text())
state=json.loads((ROOT.parent/'r8r/results/state.json').read_text())
entry=next(x for x in state['candidates'] if x['config']['id']=='baseline' and x['seed']==0)
fold=next(x for x in entry['rows'] if x['season']==2012)
query=pd.read_csv(ROOT/'data/query_inputs.csv')
cols=audit['ordered_base_columns']
lookup={r['pid']:r['score'] for r in fold['predictions']}
reference=np.asarray([lookup[pid] for pid in query.pid],dtype=float)
assert hashlib.sha256(reference.tobytes()).hexdigest()==audit['records'][0]['restored_prediction_hash']
assert fold['audit']['ordered_base_columns']==cols
assert fold['audit']['training_matrix_hash']==audit['training_matrix_hash']
assert fold['audit']['validation_matrix_hash']==audit['query_matrix_hash']
assert fold['audit']['training_labels_hash']==audit['training_label_hash']
groups=[list(map(int,indices)) for indices in query.groupby(cols,dropna=False,sort=False).indices.values()]
membership=np.empty(len(query),dtype=int)
for gid,indices in enumerate(groups):membership[indices]=gid
upper=np.triu(np.ones((len(query),len(query)),dtype=bool),1)
distinct=(membership[:,None]!=membership[None,:])&upper
minimum_distinct_gap=float(np.abs(reference[:,None]-reference[None,:])[distinct].min())
duplicates=[]
for indices in groups:
    if len(indices)<2:continue
    rows=query.iloc[indices]
    duplicates.append({'zero_based_query_positions':indices,'pids':rows.pid.tolist(),
                       'size':len(indices),'pairs':len(indices)*(len(indices)-1)//2,
                       'all_features_missing':bool(rows[cols].isna().all().all()),
                       'observed_features':rows.iloc[0][cols].dropna().to_dict(),
                       'baseline_prediction_min':float(reference[indices].min()),
                       'baseline_prediction_max':float(reference[indices].max())})
cases=[]
for record in audit['records']:
    delta=record['comparison']['max_abs_delta']
    cases.append({'case':record['case'],'strict_pair_order_inversions':record['comparison']['strict_pair_order_inversions'],
                  'max_abs_delta':delta,'minimum_distinct_vector_baseline_gap':minimum_distinct_gap,
                  'distinct_vector_inversions_excluded_by_margin_bound':bool(minimum_distinct_gap>2*delta),
                  'reason':'Each changed score is within max_abs_delta of baseline; pairwise gaps can change by at most twice that bound.'})
result={'status':'passed','no_new_model_predictions':True,'no_outcome_scoring':True,
        'reused_baseline_prediction_hash_exact_match':True,'original_study_matrix_and_label_hashes_exact_match':True,
        'query_rows':len(query),'distinct_input_vectors':len(groups),'duplicate_groups':duplicates,
        'minimum_distinct_vector_baseline_gap':minimum_distinct_gap,
        'all_observed_inversions_provably_within_exact_duplicate_vectors':all(r['distinct_vector_inversions_excluded_by_margin_bound'] for r in cases),
        'cases':cases,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(ROOT/'results/duplicate_analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['cases','duplicate_groups']}))
print(json.dumps(duplicates))

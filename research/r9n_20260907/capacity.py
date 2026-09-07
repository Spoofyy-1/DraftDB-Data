"""No-model profile admission and complete prepared-ensemble deduplication."""
from pathlib import Path
import json,sys
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'code'));import preprocessing as P;import stack_core as C

def scan(root=ROOT):
 root=Path(root);protocol=json.loads((root/'code/protocol.json').read_text());designs={};rejected={}
 for profile in protocol['profiles']:
  per={}
  try:
   for year in protocol['outer_years']:
    folder=root/'source_inputs'/f'f50_game_team_y{year}'
    with np.load(folder/'training.npz',allow_pickle=False)as t,np.load(folder/'inference.npz',allow_pickle=False)as q:
     cols=protocol['panels'][0]['columns'];X=pd.DataFrame(t['X'],columns=cols);query=pd.DataFrame(q['X'],columns=cols)
     for seed in protocol['seeds']:
      d=P.prepare(X,t['y'],query,profile,seed,protocol,t['pid'].tolist(),q['pid'].tolist());per[f'{year}:{seed}']=d
   designs[profile['id']]=per
  except (ValueError,FloatingPointError,OverflowError)as e:rejected[profile['id']]={'exception':type(e).__name__,'reason':str(e),'entire_profile_excluded_before_model_fits':True,'completed_fold_seed_checks':list(per)}
  print(json.dumps({'CPU_profile':profile['id'],'admitted':profile['id']in designs}),flush=True)
 assert protocol['baseline_profile_id']in designs,'Frozen baseline preprocessing failed; no study can proceed'
 ordered=[protocol['baseline_profile_id']]+[p['id']for p in protocol['profiles']if p['id']!=protocol['baseline_profile_id']and p['id']in designs]
 signatures={pid:P.equality_signature(designs[pid])for pid in ordered};representatives={};mapping={}
 for pid in ordered:representatives.setdefault(signatures[pid],pid);mapping[pid]=representatives[signatures[pid]]
 return {'passed':True,'model_fits':0,'GPU_predictions':0,'requested_profiles':len(protocol['profiles']),'rejected_profiles':rejected,'requested_to_evaluated':mapping,'distinct_admitted_profiles':len(set(mapping.values())),'equality_signatures':signatures,'designs':designs,'no_outcome_score_selection':True}
if __name__=='__main__':
 result=scan();path=ROOT/'results/preprocessing_scan.json';path.parent.mkdir(exist_ok=True)
 with path.open('x')as f:f.write(json.dumps(result,indent=2,allow_nan=False)+'\n')

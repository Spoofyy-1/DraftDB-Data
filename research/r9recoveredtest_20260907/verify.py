"""Host-only checks of frozen inputs, GPU evidence and fixed blend arithmetic."""
from pathlib import Path
import hashlib,json,os
import numpy as np
from scipy.stats import rankdata

ROOT=Path(__file__).resolve().parent
MODES=['per_seed_0','per_seed_101','per_seed_202','family_seed_rank_average']
RECIPES=['recovered_gen11','prior_baseline','always_rich','individual_tabicl','individual_ridge','individual_hybrid']
COUNTS={'selector':4,'ridge':1,'tabicl':12,'residual_q25':9}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save_new(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
def pins(root=ROOT):
 a=read(root/'launch_authorization.json');plan=read(root/'plan.json')
 assert a['model_fits_authorized'] and a['benchmark_scoring_authorized']
 assert a['plan_sha256']==sha(root/'plan.json') and a['frozen_sha256']==sha(root/'frozen.json')
 for name,h in read(root/'frozen.json')['files'].items():assert sha(root/name)==h,name
 assert a['cpu_preflight_sha256']==sha(root/'results/cpu_preflight.json')
 assert read(root/'results/cpu_preflight.json')['passed']
 assert plan['years']==list(range(2019,2026)) and plan['primary_recipe']=='recovered_gen11'
 assert plan['primary_mode']=='family_seed_rank_average' and not plan['benchmark_selection_allowed']
 return plan
def arithmetic(seed_members,thin):
 n=len(thin);mat={k:np.vstack([np.rint(2*rankdata(s[k])).astype(np.int64) for s in seed_members]) for k in ['tabicl','ridge','hybrid']}
 def blends(t,r,h,den):
  z={'recovered_gen11':np.where(thin,4*h,t+3*r),'prior_baseline':np.where(thin,2*h+2*r,3*t+r),'always_rich':t+3*r}
  out={k:rankdata(v)/n for k,v in z.items()}
  out.update(individual_tabicl=t/den,individual_ridge=r/den,individual_hybrid=h/den)
  return out
 out={f'per_seed_{s}':blends(*(mat[k][i] for k in mat),2*n) for i,s in enumerate([0,101,202])}
 out['family_seed_rank_average']=blends(*(mat[k].sum(axis=0) for k in mat),6*n)
 return out
def validate(r,t,root=ROOT):
 folder=root/'inputs'/t['id'];m=read(folder/'manifest.json');pre=read(root/'results/jobs'/t['id']/'preflight.json')
 assert sha(folder/'manifest.json')==t['input_manifest_sha256']==r['input_manifest_sha256']==pre['input_manifest_sha256']
 assert r['task_id']==t['id'] and r['outer_year']==t['year'] and r['target_mode']=='prefix5'
 assert r['protocol_sha256']==sha(root/'code/protocol.json')==pre['protocol_sha256']
 assert r['label_audit']==m['label_audit']==pre['label_audit']
 assert not r['query_outcomes_accessed'] and not r['query_outcome_labels_accessed'] and not r['training_targets_exported'] and not r['weights_fitted']
 assert r['fit_counts']==COUNTS and r['namespace_proof']['passed']
 assert r['runtime']==pre['runtime'] and r['training_rows']==pre['training_rows']
 with np.load(folder/'inference.npz',allow_pickle=False) as z:q=z['pid'].tolist()
 assert r['query_pids']==q and r['columns']==m['columns'] and r['coverage']==pre['coverage']
 assert r['full_training_target_hash']==m['label_audit']['target_hash']
 assert len(r['inner_stages'])==3 and len(r['seed_results'])==3
 selectors=[r['full_selector']]+[x['selector'] for x in r['inner_stages']]
 for x in selectors:
  assert x['effective_constructor']['learner']['generic_param']['device']=='cuda:0'
  assert not x['query_or_held_labels_seen'] and len(x['selected_columns'])==100
 for x in r['inner_stages']:
  assert x['train_rows']+x['held_rows']==r['training_rows'] and len(x['records'])==3
  assert x['selector']['training_target_hash']==x['training_target_hash']
 tabs=[y['model_audit'] for x in r['inner_stages'] for y in x['records']]+[x['members']['tabicl']['model_audit'] for x in r['seed_results']]
 for x in tabs:
  assert x['actual_devices'] and all(d.startswith('cuda') for d in x['actual_devices'])
  assert x['requested_ensemble_count']==32 and x['effective_ensemble_count']>0
  assert not x['query_labels_seen'] and len(x['input_columns'])==100
 for i,s in enumerate([0,101,202]):
  row=r['seed_results'][i];assert row['seed_shift']==s and row['tabicl_seed']==42+s
  assert row['members']['ridge']['model_audit']['parameters']=={'alpha':300,'solver':'auto'}
  assert row['members']['ridge']['model_audit']['preprocessing']['standardized_training_hash']==pre['Ridge_standardized_training_hash']
  assert row['members']['ridge']['model_audit']['standardized_query_hash']==pre['Ridge_standardized_query_hash']
  for b,seed in zip(row['members']['hybrid']['bags'],[11+s,12+s,13+s]):
   a=b['model_audit'];assert b['seed']==seed and a['tree_count']==800 and not a['query_labels_seen']
   assert a['effective_constructor']['learner']['generic_param']['device']=='cuda:0'
 members=[{k:np.array(x['members'][k]['canonical_predictions']) for k in ['tabicl','ridge','hybrid']} for x in r['seed_results']]
 expected=arithmetic(members,np.array(r['coverage']['query_thin_mask'],dtype=bool))
 assert set(r['prediction_sets'])==set(MODES)
 for mode in MODES:
  assert set(r['prediction_sets'][mode])==set(RECIPES)
  for recipe in RECIPES:
   v=np.asarray(r['prediction_sets'][mode][recipe]);assert v.shape==(len(q),) and np.isfinite(v).all()
   assert np.array_equal(v,expected[mode][recipe]),(mode,recipe)
 return {'passed':True,'year':t['year'],'rows':len(q),'training_rows':r['training_rows'],'model_fits':26,'prediction_vectors_reconstructed':24,'actual_label_max':m['label_audit']['max_actual_label_season']}

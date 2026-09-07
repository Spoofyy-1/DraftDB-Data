"""Host-only scorer: every immutable prediction must exist before answers open."""
from pathlib import Path
import fcntl,hashlib,json,os,time
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from verify import ROOT,MODES,RECIPES,read,sha,save_new,pins,validate
OUT=ROOT/'results';VAULT=ROOT.parent/'vault'
def correlation(a,b):
 if len(a)<3 or len(np.unique(a))<2 or len(np.unique(b))<2:return None
 v=float(spearmanr(a,b).statistic);return v if np.isfinite(v) else None
def mean(values):return float(np.mean(values)) if all(v is not None for v in values) else None
def validate_freeze():
 plan=pins();f=read(OUT/'prediction_freeze.json')
 assert f['all_seven_predictions_complete_before_answers'] and f['plan_sha256']==sha(ROOT/'plan.json')
 assert f['scorer_sha256']==sha(Path(__file__)) and f['frozen_sha256']==sha(ROOT/'frozen.json')
 assert set(f['tasks'])=={t['id'] for t in plan['tasks']}
 records={}
 for t in plan['tasks']:
  e=f['tasks'][t['id']];assert e['file']==f"jobs/{t['id']}/result.json" and sha(OUT/e['file'])==e['sha256']
  r=read(OUT/e['file']);validate(r,t);records[t['year']]=r
 return plan,records
def score():
 plan,records=validate_freeze();freeze_sha=sha(OUT/'prediction_freeze.json')
 ledger=VAULT/'r9_frozen_benchmark_ledger.jsonl'
 with Path(str(ledger)+'.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);lines=ledger.read_text().splitlines(keepends=True) if ledger.exists() else [];previous='GENESIS'
  for line in lines:
   saved=json.loads(line);assert saved['prev']==previous,'Ledger chain changed';previous=hashlib.sha256(line.encode()).hexdigest()
   if saved['prediction_freeze_sha256']==freeze_sha:
    if not (OUT/'test_result.json').exists():save_new(OUT/'test_result.json',saved['result'])
    else:assert read(OUT/'test_result.json')==saved['result']
    return saved['result']
  assert not (OUT/'test_result.json').exists(),'Never overwrite a scored result'
  # First outcome-file access occurs after every prediction and freeze check.
  rows=[]
  for year in plan['years']:
   k=plan['horizons'][str(year)];fields=[f'y_s{i}_war' for i in range(1,k+1)];p=VAULT/f'answers_{year}.csv'
   assert sha(p)==plan['answer_hashes'][str(year)],'Benchmark bytes changed'
   a=pd.read_csv(p,usecols=['pid','actual_pick']+fields,float_precision='round_trip').dropna(subset=['actual_pick'])
   r=records[year];assert a.pid.is_unique and set(a.pid)==set(r['query_pids'])
   a=a.set_index('pid').loc[r['query_pids']];values=a[fields].to_numpy(dtype=float);assert not np.isinf(values).any()
   truth=np.nan_to_num(values,nan=0).sum(axis=1);observed=np.isfinite(values).all(axis=1)
   row={'season':year,'k':k,'n_full':len(a),'n_complete_target':int(observed.sum()),'actual_label_max':r['label_audit']['max_actual_label_season'],'training_rows':r['training_rows'],'answer_sha256':sha(p),'metrics':{}}
   for scope,mask in [('full_legacy',np.ones(len(a),dtype=bool)),('complete_target_subset',observed)]:
    m={mode:{recipe:correlation(np.array(r['prediction_sets'][mode][recipe])[mask],truth[mask]) for recipe in RECIPES} for mode in MODES}
    row['metrics'][scope]={'predictions':m,'draft':correlation(-a.actual_pick.to_numpy()[mask],truth[mask])}
   rows.append(row)
  aggregates={}
  for scope in ['full_legacy','complete_target_subset']:
   aggregates[scope]={'predictions':{mode:{recipe:mean([r['metrics'][scope]['predictions'][mode][recipe] for r in rows]) for recipe in RECIPES} for mode in MODES},'draft':mean([r['metrics'][scope]['draft'] for r in rows])}
  primary=aggregates['full_legacy']['predictions'][plan['primary_mode']][plan['primary_recipe']]
  result={'protocol':'Fixed recovered-gen11 adaptation on2019–2025','scored_at':time.time(),'prediction_freeze_sha256':freeze_sha,'primary_recipe':plan['primary_recipe'],'primary_mode':plan['primary_mode'],'primary_score':primary,'matched_2020_2025_score':mean([r['metrics']['full_legacy']['predictions'][plan['primary_mode']][plan['primary_recipe']] for r in rows if r['season']>=2020]),'rows':rows,'aggregate':aggregates,'units':'Spearman rho; multiply by100, not percent exact positions','limitations':plan['limitations'],'no_test_feedback_tuning':True,'new_model_promotion':False,'controls_diagnostic_not_selection':True}
  line=json.dumps({'prev':previous,'prediction_freeze_sha256':freeze_sha,'result':result},allow_nan=False)+'\n'
  with ledger.open('a') as f:f.write(line);f.flush();os.fsync(f.fileno())
  save_new(OUT/'test_result.json',result);return result
if __name__=='__main__':
 r=score();print(json.dumps({'scored':True,'primary_score':r['primary_score'],'matched_2020_2025_score':r['matched_2020_2025_score'],'test_result_sha256':sha(OUT/'test_result.json')}))

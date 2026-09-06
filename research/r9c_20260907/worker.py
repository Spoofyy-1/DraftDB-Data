"""Approved35-column diagnostic additions on a frozen selected A/B baseline."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import importlib.util,json,hashlib,copy,time,collections
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('r9c_frozen_b',R/'b_reference/worker.py');P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P);B=P.B;X=P.X
_PLAN=None;_REF=None;_DATA=None;_BASE={};_EXTRA={}
def load_plan():
 global _PLAN
 if _PLAN is None:
  p=json.loads((R/'plan.json').read_text());m=json.loads((R/'source_manifest.json').read_text())
  for name,h in m['files'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==h,name
  assert hashlib.sha256((R/'queue_runtime.py').read_bytes()).hexdigest()==m['verified_scheduler_sha256']
  assert p['diagnostic_only'] and p['no_confirmation_or_test_scoring'] and len(p['variants'])*len(p['seeds'])==459
  assert len(p['features'])==35 and len(set(p['features']))==35 and len(p['groups'])==38
  for key in ['folds','seeds','permutation_seeds','model_constructor','ordering_policy']:assert p[key]==P.load_plan()[key]
  assert p['source_admission']==json.loads((R/'diagnostic_admission.json').read_text()) and p['source_admission']['source_model_eligible_flag_remains_false']
  assert json.loads((R/'data/source_verification.json').read_text())['model_eligible']is False
  _PLAN=p
 return _PLAN

def references():
 global _REF
 if _REF is None:_REF={e['seed']:e for e in json.loads((R/'references.json').read_text())['records']}
 return _REF

def source_worker():return P if load_plan()['baseline']['source']=='r9b' else P.A

def candidate_data():
 global _DATA
 if _DATA is None:
  p=load_plan();path=R/'data/candidate_inputs.csv'
  assert hashlib.sha256(path.read_bytes()).hexdigest()==p['source_admission']['source_candidate_sha256']
  d=pd.read_csv(path,dtype={'pid':str});assert list(d)==p['source_schema'] and len(d)==1458 and d.pid.is_unique and d.pid.notna().all()
  assert d.draft_year.between(2000,2018).all() and np.isfinite(d[p['features']].stack().dropna().to_numpy(dtype=float)).all()
  master=pd.read_csv(B.DATA/'features.csv',usecols=['pid','draft_year'],dtype={'pid':str})
  assert len(master)==1428 and master.pid.is_unique and set(master.pid)<=set(d.pid)
  joined=master.merge(d,on=['pid','draft_year'],how='left',sort=False,validate='one_to_one',indicator=True)
  assert len(joined)==len(master) and joined.pid.tolist()==master.pid.tolist() and joined['_merge'].eq('both').all()
  _DATA=d.set_index('pid',drop=False)
 return _DATA

def eligibility(train):
 p=load_plan();counts={c:{'observed':int(train[c].notna().sum()),'unique':int(train[c].nunique())} for c in p['features']}
 selected=[c for c in p['features'] if counts[c]['observed']>=p['eligibility']['minimum_observed_training_rows'] and counts[c]['unique']>=p['eligibility']['minimum_unique_training_values']]
 return selected,counts

def extra_frames(fold):
 year=fold['year']
 if year not in _EXTRA:
  d=candidate_data();p=load_plan();frames={}
  for role,key in [('train','tr'),('validation','te')]:
   meta=fold[key];part=d.loc[meta.pid.tolist()].copy();assert part.pid.tolist()==meta.pid.tolist() and part.draft_year.tolist()==meta.draft_year.tolist()
   frame=part[p['features']].astype(float);frame.index=meta.index;frames[role]=frame
  selected,counts=eligibility(frames['train']);_EXTRA[year]=(frames,selected,counts)
 return _EXTRA[year]

def baseline_design(fold):
 year=fold['year']
 if year not in _BASE:
  p=load_plan();sw=source_worker();v=p['baseline']['config']
  if v['id']=='pair06_RR':atr,ate,families,pair=sw.full_design(fold);ablation=None
  else:atr,ate,families,pair,ablation=sw.design(fold,v)
  old=next(r for r in references()[0]['rows'] if r['season']==year)
  assert list(atr)==list(ate)==old['audit']['input_columns'] and families==old['audit']['families'] and pair==old['audit']['pair_design']
  if ablation is not None:assert ablation==old['audit']['ablation']
  for key,value in fold['audit'].items():assert old['audit'][key]==value
  assert [B._hash(k) for k in B._exact_vector_keys(ate)]==old['audit']['canonical_prediction_ties']['row_vector_hashes']
  _BASE[year]=(atr,ate)
 return _BASE[year]

def append_values(base,values,metadata,features,v,role):
 assert features and set(features)<=set(values) and v['arm']in ['RR','PP']
 original=values[features].astype(float).copy()
 if v['arm']=='RR':added=original.copy()
 else:added=B._vector_shuffle(original,metadata,'fifty:new_college_source:'+':'.join(features),v['permutation_seed'],role)
 before=B._vector_invariants(original,metadata);after=B._vector_invariants(added,metadata)
 assert original.isna().equals(added.isna()) and before==after
 slots=[f'slot_{43+i:03d}' for i in range(len(features))];assert not set(slots)&set(base)
 out=base.copy()
 for c,slot in zip(features,slots):out[slot]=added[c]
 assert out[list(base)].equals(base) and out.index.equals(base.index)
 return out,{'features':features,'slots':slots,'original_invariants':before,'used_invariants':after,'original_values_hash':B._matrix_hash(original),'used_values_hash':B._matrix_hash(added),'baseline_matrix_hash':B._matrix_hash(base),'retained_baseline_matrix_hash':B._matrix_hash(out[list(base)]),'final_matrix_hash':B._matrix_hash(out),'changed_observed_values':int((added.notna()&added.ne(original)).sum().sum())}

def design(fold,v):
 atr,ate=baseline_design(fold);frames,eligible,counts=extra_frames(fold);features=[c for c in v['features'] if c in eligible]
 tr,a=append_values(atr,frames['train'],fold['tr'],features,v,'train');te,b=append_values(ate,frames['validation'],fold['te'],features,v,'validation')
 return tr,te,{'group':v['group'],'requested_features':v['features'],'eligible_features':features,'training_only_counts':counts,'arm':v['arm'],'permutation_seed':v['permutation_seed'],'train':a,'validation':b,'plan_sha256':hashlib.sha256((R/'plan.json').read_bytes()).hexdigest(),'source_sha256':load_plan()['source_admission']['source_candidate_sha256']}

def run_variant(vid,seed):
 p=load_plan();v=next(v for v in p['variants'] if v['id']==vid);assert seed in p['seeds']
 if vid==p['reference_id']:return source_worker().run_variant(vid,seed)
 start=time.time();E,bp,g,folds=B._prepared();os.environ['SEED_SHIFT']=str(seed);rows=[]
 for fold in folds:
  atr,ate,proof=design(fold,v);E.H.audit_features(list(atr));model,kwargs=B.make_registered_model(E.cfg_of('tabicl',g,list(atr)));assert kwargs=={**p['model_constructor'],'random_state':seed}
  model.fit(atr.astype(float),fold['yy']);raw=np.asarray(model.predict(ate.astype(float)),dtype=float);assert len(raw)==len(ate) and np.isfinite(raw).all()
  pred,ties=B._canonical_predictions(ate,raw,fold['te'].pid.tolist());score=B.rho(pred,fold['truth']);old=next(r for r in references()[seed]['rows'] if r['season']==fold['year'])
  audit={**copy.deepcopy(old['audit']),'input_columns':list(atr),'registered_model_parameters':kwargs,'canonical_prediction_ties':ties,'raw_feature_count':len(atr.columns),'training_nonconstant_columns':int((atr.nunique()>1).sum()),'candidate_addition':proof}
  rows.append({'season':fold['year'],'k':fold['k'],'n':len(ate),'ntrain':len(atr),'cutoff':fold['cutoff'],'max_label_season':fold['audit']['max_label_season'],'stack':score,'draft':old['draft'],'members':{'tabicl':score},'audit':audit,
  'predictions':[{'pid':pid,'score':float(a),'raw_score':float(b)} for pid,a,b in zip(fold['te'].pid,pred,raw)]})
 return {'config':v,'seed':seed,'task_id':f'{vid}_seed{seed}','rows':rows,'score':float(np.mean([r['stack'] for r in rows])),'seconds':round(time.time()-start,2),'diagnostic_only':True}

def validate_entry(entry,p=None):
 p=p or load_plan();v=next(v for v in p['variants'] if v['id']==entry['config']['id']);seed=entry['seed']
 assert 'error'not in entry and entry['diagnostic_only'] and entry['config']==v and seed in p['seeds']
 assert entry['task_id']==f"{v['id']}_seed{seed}" and [r['season'] for r in entry['rows']]==p['folds'] and np.isclose(entry['score'],np.mean([r['stack'] for r in entry['rows']]),rtol=0,atol=1e-15)
 ref=references()[seed]
 if v['id']==p['reference_id']:X.exact_reference(entry,ref);return
 for row,old in zip(entry['rows'],ref['rows']):
  B._validate_tie_record(row);a=row['audit'];o=old['audit'];year=row['season']
  assert row['cutoff']==year-1 and a['max_label_season']<=year-1 and a['training_max_draft_year']<=year-2
  for key in ['season','k','n','ntrain','cutoff','max_label_season']:assert row[key]==old[key]
  assert [x['pid'] for x in row['predictions']]==[x['pid'] for x in old['predictions']]
  for key in o:
   if key not in ['input_columns','canonical_prediction_ties','raw_feature_count','training_nonconstant_columns']:assert a[key]==o[key],key
  proof=a['candidate_addition'];assert proof['group']==v['group'] and proof['requested_features']==v['features'] and proof['arm']==v['arm'] and proof['permutation_seed']==v['permutation_seed']
  assert proof['plan_sha256']==hashlib.sha256((R/'plan.json').read_bytes()).hexdigest() and proof['source_sha256']==p['source_admission']['source_candidate_sha256']
  eligible=[c for c in v['features'] if proof['training_only_counts'][c]['observed']>=5 and proof['training_only_counts'][c]['unique']>=2];assert proof['eligible_features']==eligible and eligible
  slots=[f'slot_{43+i:03d}' for i in range(len(eligible))];assert a['input_columns']==o['input_columns']+slots and a['raw_feature_count']==len(a['input_columns'])
  for role in ['train','validation']:
   z=proof[role];assert z['features']==eligible and z['slots']==slots and z['original_invariants']==z['used_invariants'] and z['baseline_matrix_hash']==z['retained_baseline_matrix_hash']
   if v['arm']=='RR':assert z['original_values_hash']==z['used_values_hash'] and z['changed_observed_values']==0

def summarize_matched(entries):
 p=load_plan();tasks={};base_hashes=collections.defaultdict(set);streams=collections.defaultdict(set)
 for entry in entries:
  validate_entry(entry,p);key=(entry['config']['id'],entry['seed']);assert key not in tasks;tasks[key]=entry
  if entry['config']['id']!=p['reference_id']:
   for row in entry['rows']:
    for role in ['train','validation']:
     proof=row['audit']['candidate_addition'][role];base_hashes[(row['season'],role)].add(proof['baseline_matrix_hash']);streams[(entry['config']['id'],row['season'],role)].add(proof['used_values_hash'])
 assert all(len(v)==1 for v in list(base_hashes.values())+list(streams.values()))
 missing=[f"{p['reference_id']}_seed{s}" for s in p['seeds'] if (p['reference_id'],s)not in tasks]
 common={'completed_tasks':len(tasks),'expected_tasks':459,'reference_replays_passed':3-len(missing),'reference_replays_pending':missing,'interpretation_allowed':not missing,'diagnostic_only':True,'automatic_promotion':False,'metric':'Pre2019 mean fold Spearman, not classification accuracy'}
 if missing:return {**common,'feature_groups':[]}
 baseline=float(np.mean([tasks[(p['reference_id'],s)]['score'] for s in p['seeds']]))
 results=[];pending=[]
 for group in p['groups']:
  real=group['id']+'_real';control=[group['id']+f'_perm_{t}' for t in p['permutation_seeds']]
  if not all((vid,s)in tasks for vid in [real]+control for s in p['seeds']):pending.append(group['id']);continue
  rows=[]
  for seed in p['seeds']:
   for year in p['folds']:
    one=lambda vid:next(r for r in tasks[(vid,seed)]['rows'] if r['season']==year)
    r=one(real);cs=[one(vid) for vid in control];base=one(p['reference_id'])
    for c in cs:
     for key in ['input_columns','raw_feature_count','training_nonconstant_columns']:assert r['audit'][key]==c['audit'][key]
     ar=r['audit']['candidate_addition'];ac=c['audit']['candidate_addition'];assert ar['training_only_counts']==ac['training_only_counts'] and ar['eligible_features']==ac['eligible_features']
     for role in ['train','validation']:
      for key in ['features','slots','original_invariants','original_values_hash','baseline_matrix_hash']:assert ar[role][key]==ac[role][key]
    control_mean=float(np.mean([c['stack'] for c in cs]));rows.append({'seed':seed,'season':year,'real':r['stack'],'permuted':control_mean,'baseline':base['stack'],'paired_gain':r['stack']-control_mean,'real_minus_baseline':r['stack']-base['stack']})
  fields=['paired_gain','real_minus_baseline'];results.append({**group,'real_mean':float(np.mean([r['real'] for r in rows])),'control_mean':float(np.mean([r['permuted'] for r in rows])),'paired_mean_gain':float(np.mean([r['paired_gain'] for r in rows])),'real_minus_baseline_context_only':float(np.mean([r['real_minus_baseline'] for r in rows])),
  'fold_gains':{str(y):{f:float(np.mean([r[f] for r in rows if r['season']==y])) for f in fields} for y in p['folds']},'seed_gains':{str(s):{f:float(np.mean([r[f] for r in rows if r['seed']==s])) for f in fields} for s in p['seeds']},'paired_rows':rows})
 return {**common,'baseline_score':baseline,'baseline':p['baseline'],'feature_groups':results,'pending':pending,'source_admission':p['source_admission'],'limitations':p['controls']}

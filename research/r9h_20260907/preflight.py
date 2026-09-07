"""Observed-label admission registration only. No fitting, selector or GPU execution."""
from pathlib import Path
import os,json,hashlib,itertools,importlib.util,copy
import numpy as np
import pandas as pd
from scipy.special import ndtri
ROOT=Path(__file__).resolve().parent;REF=Path(os.environ.get('R9H_REFERENCE','/reference'));OUT=ROOT/'results';DATA=ROOT/'data'
G_SHA='2673d0245e317f934a1295a311ba0d49262226df67b61615cc7576856f733b37'
def h(raw):return hashlib.sha256(raw).hexdigest()
def canon(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def save(path,v):path.write_bytes(json.dumps(v,indent=2,allow_nan=False).encode()+b'\n')
def values_hash(a):
 a=np.asarray(a,dtype=np.float64);a=np.where(a==0.,0.,a);mask=np.isnan(a);a=np.where(mask,0.,a);return h(canon(list(a.shape))+mask.tobytes()+a.tobytes())
def canonical_rows(frame):
 assert frame.pid.is_unique
 return frame.iloc[sorted(range(len(frame)),key=lambda i:(h(str(frame.iloc[i].pid).encode()),str(frame.iloc[i].pid)))].copy().reset_index(drop=True)
def admit(data,labels,year,policy):
 cutoff=year-1;horizon=policy['horizon'];base=data[(data.draft_year>=policy['start'])&(data.draft_year<=year-policy['gap'])].copy()
 if policy['population']=='drafted':base=base[base.was_drafted==1]
 assert not labels.duplicated(['pid','ordinal']).any()
 dated=labels[(labels.season_end<=cutoff)&labels.ordinal.between(1,horizon)&np.isfinite(labels.war)].copy()
 dated=dated[dated.pid.isin(base.pid)]
 complete=dated.groupby('pid').ordinal.agg(lambda x:sorted(x)==list(range(1,horizon+1)))
 tr=canonical_rows(base[base.pid.isin(complete[complete].index)])
 facts=dated[dated.pid.isin(tr.pid)].sort_values(['pid','ordinal']).reset_index(drop=True)
 totals=facts.groupby('pid').war.sum();cumulative=tr.pid.map(totals).to_numpy(dtype=float);assert np.isfinite(cumulative).all()
 clipped=np.clip(cumulative,-40.,40.);target=np.empty(len(tr),dtype=float)
 for cohort in tr.draft_year.unique():
  mask=(tr.draft_year==cohort).to_numpy();n=int(mask.sum());r=pd.Series(clipped[mask]).rank(method='average').to_numpy();target[mask]=ndtri(np.clip((r-.5)/n,.01,.99))
 assert np.isfinite(target).all()and len(facts)==len(tr)*horizon
 assert not len(facts)or facts.season_end.max()<=cutoff
 return tr,target,cumulative,clipped,facts

def tests():
 # Synthetic values are unit fixtures only; never saved to the registered model data.
 d=pd.DataFrame({'pid':['a','b','c','d','e'],'draft_year':[2007]*5,'was_drafted':[1]*5})
 l=pd.DataFrame([['a',1,2008,1.],['b',1,2008,2.],['c',1,2013,99.],['d',2,2009,3.],['e',1,2008,0.]],columns=['pid','ordinal','season_end','war']);p={'start':2000,'gap':1,'population':'all','horizon':1}
 a=admit(d,l,2012,p);assert set(a[0].pid)=={'a','b','e'} and len(a[1])==3
 changed=l.copy();changed.loc[changed.season_end>2011,'war']=-99999.;b=admit(d,changed,2012,p);assert a[0].equals(b[0])and np.array_equal(a[1],b[1])
 changed=pd.concat([l,pd.DataFrame([['c',2,2014,1000.]],columns=l.columns)],ignore_index=True);b=admit(d,changed,2012,p);assert a[0].equals(b[0])and np.array_equal(a[1],b[1])
 assert len(admit(d,l,2012,{**p,'horizon':2})[0])==0
 knownzero=np.where(a[0].pid.to_numpy()=='e')[0][0];assert a[2][knownzero]==0.
 assert not np.array_equal(a[1],np.zeros(len(a[1])))
 reordered=admit(d.iloc[::-1],l.iloc[::-1],2012,p);assert a[0].equals(reordered[0])and np.array_equal(a[1],reordered[1])
 duplicate=pd.concat([l,l.iloc[[0]]],ignore_index=True)
 try:admit(d,duplicate,2012,p)
 except AssertionError:pass
 else:raise AssertionError('Duplicate facts accepted')
 return {'future_cutoff_values_and_existence_ignored':True,'missing_ordinal_or_unknown_label_never_zero_filled':True,'known_zero_retained':True,'row_order_invariance':True,'duplicate_fact_rejected':True,'synthetic_fixture_not_model_data':True}

def main():
 OUT.mkdir(exist_ok=True);DATA.mkdir(exist_ok=True);unit_tests=tests()
 frozen_raw=(REF/'frozen.json').read_bytes();assert h(frozen_raw)==G_SHA;frozen=json.loads(frozen_raw)
 for name,digest in frozen['files'].items():assert h((REF/name).read_bytes())==digest,name
 spec=importlib.util.spec_from_file_location('r9h_frozen_G',REF/'worker.py');G=importlib.util.module_from_spec(spec);spec.loader.exec_module(G)
 def forbidden(*a,**k):raise AssertionError('No model fit or selector preparation permitted')
 G.B._prepared=forbidden;G.run_variant=forbidden;G.D.run_variant=forbidden
 bp,manifest,data,labels=G.B._load_inputs();assert data.draft_year.max()<=2018 and labels.season_end.max()<=2018
 refs=G.D.references();folds=G.load_plan()['folds'];seeds=G.load_plan()['seeds'];columns=sorted(refs[0]['rows'][0]['audit']['input_columns']);assert len(columns)==44
 mapping={slot:feature for feature,slot in bp['slot_mapping'].items()};audit=refs[0]['rows'][0]['audit'];mapping.update(dict(zip(audit['pair_design']['slots'],audit['pair_design']['features'])))
 actual_fields=[mapping.get(c,c)for c in columns];assert not any(c.startswith(('bio_','med_','cons_','y_'))or c in ['pid','draft_year','actual_pick','was_drafted','qid']for c in actual_fields)
 def matrix(frame):return frame[actual_fields].astype(float).rename(columns=dict(zip(actual_fields,columns)))
 queries={};query_cache={}
 for year in folds:
  k=min(5,2018-year);te=canonical_rows(data[(data.draft_year==year)&(data.was_drafted==1)]);xq=matrix(te);used=labels[(labels.season_end<=2018)&labels.ordinal.between(1,k)&np.isfinite(labels.war)]
  exact=used.groupby('pid').ordinal.agg(lambda a:sorted(a)==list(range(1,k+1)));mask=te.pid.isin(exact[exact].index).to_numpy();assert mask.any()
  truth=te.pid.map(used.groupby('pid').war.sum()).fillna(0).to_numpy(dtype=float);baseline=[]
  for seed in seeds:
   old=next(r for r in refs[seed]['rows']if r['season']==year);assert te.pid.tolist()==[v['pid']for v in old['predictions']]
   assert set(columns)==set(old['audit']['input_columns']);original=xq[old['audit']['input_columns']];assert G.B._matrix_hash(original)==G.support()['source_designs'][str(year)]['query_hash']
   prediction=np.asarray([v['score']for v in old['predictions']]);assert G.B.rho(prediction,truth)==old['stack'];baseline.append({'seed':seed,'legacy_full_query_score':old['stack'],'observed_mask_score':G.B.rho(prediction[mask],truth[mask]),'prediction_hash':values_hash(prediction)})
  np.savez_compressed(DATA/f'query_{year}.npz',X=xq.to_numpy(),legacy_truth=truth,observed_truth_mask=mask,pid=np.asarray(te.pid.tolist(),dtype=str))
  queries[str(year)]={'year':year,'horizon':k,'all_query_rows':len(te),'observed_mask_rows':int(mask.sum()),'unknown_incomplete_rows':int((~mask).sum()),'query_pids':te.pid.tolist(),'observed_truth_mask':mask.tolist(),'pid_hash':h(canon(te.pid.tolist())),'matrix_hash':values_hash(xq),'legacy_truth_hash':values_hash(truth),'observed_mask_hash':h(mask.tobytes()),'original_B_reference_scores_both_prespecified_metrics':baseline}
  query_cache[year]=xq.to_numpy()
 policies=[];payloads={};payload_keys={};counts_by_policy={}
 for start,gap,pop,horizon in itertools.product([2000,2007,2008],[1,2],['all','drafted'],range(1,6)):
  policy={'start':start,'gap':gap,'population':pop,'horizon':horizon};pid=f's{start}_gap{gap}_{pop}_h{horizon}';audits=[];arrays={};parts=[]
  for year in folds:
   tr,yy,cumulative,clipped,facts=admit(data,labels,year,policy);cohorts={str(int(k)):int(v)for k,v in tr.groupby('draft_year').size().items()};reasons=[]
   if len(tr)<40:reasons.append('fewer_than_40_observed_training_rows')
   if any(n<5 for n in cohorts.values()):reasons.append('admitted_cohort_fewer_than_5_observed_rows')
   x=matrix(tr);assert not np.isinf(x.to_numpy()).any()and not set(tr.pid)&set(queries[str(year)]['query_pids'])
   facts_columns=['pid','draft_year','ordinal','season_end','war'];fact_records=facts[facts_columns].to_dict(orient='records')
   row={'year':year,'cutoff':year-1,'rows':len(tr),'cohort_counts':cohorts,'valid':not reasons,'exclusion_reasons':reasons,'pid_hash':h(canon(tr.pid.tolist())),'matrix_hash':values_hash(x),'target_hash':values_hash(yy),'cumulative_WAR_hash':values_hash(cumulative),'clipped_WAR_hash':values_hash(clipped),'source_fact_hash':h(canon(fact_records)),'source_fact_rows':len(facts),'max_label_season':int(facts.season_end.max())if len(facts)else None,'training_max_cohort':int(tr.draft_year.max())if len(tr)else None,'training_pids':tr.pid.tolist()}
   audits.append(row);parts.append({'matrix_hash':row['matrix_hash'],'target_hash':row['target_hash'],'query_matrix_hash':queries[str(year)]['matrix_hash'],'columns':columns});arrays[year]={'X':x.to_numpy(),'y':yy,'pid':np.asarray(tr.pid.tolist(),dtype=str),'draft_year':tr.draft_year.to_numpy(),'source_cumulative_WAR':cumulative}
  valid=all(a['valid']for a in audits);key=h(canon(parts));canonical=None
  if valid:
   canonical=payload_keys.setdefault(key,pid)
   if canonical==pid:
    payloads[pid]={'id':pid,'representative_policy':policy,'payload_hash':key,'folds':audits}
    for year,a in arrays.items():np.savez_compressed(DATA/f'{pid}_{year}.npz',**a)
  policies.append({'id':pid,**policy,'valid':valid,'canonical_payload':canonical,'payload_hash':key,'folds':audits})
 valid=[p for p in policies if p['valid']];excluded=[p for p in policies if not p['valid']]
 dplan=G.D.load_plan();base={**dplan['model_constructor'],'norm_methods':'none','outlier_threshold':2.,'n_estimators':32};base.pop('random_state',None)
 profiles={'B_tabicl32':{'model':'TabICLRegressor','parameters':base},'E_tabicl16_o0p5':{'model':'TabICLRegressor','parameters':{**base,'n_estimators':16,'outlier_threshold':.5}},'F_catboost200':{'model':'CatBoostRegressor','parameters':{'iterations':200,'task_type':'GPU','devices':'0','thread_count':2,'gpu_ram_part':.18,'random_strength':1,'allow_writing_files':False,'bootstrap_type':'Bayesian','boosting_type':'Plain','use_best_model':False,'verbose':False,'loss_function':'MAE','depth':7,'learning_rate':.1,'l2_leaf_reg':1,'bagging_temperature':1,'nan_mode':'Max'}}}
 from tabicl import TabICLRegressor
 from catboost import CatBoostRegressor
 for profile in profiles.values():
  for seed in seeds:
   params={**profile['parameters'],('random_state'if profile['model']=='TabICLRegressor'else'random_seed'):seed};model=(TabICLRegressor if profile['model']=='TabICLRegressor'else CatBoostRegressor)(**params);actual=model.get_params();assert all(actual[k]==v for k,v in params.items())
 variants=[{'id':'drop5_001','kind':'original_B_exact_reference','original_column_and_target_policy':True}]
 for payload_id in payloads:
  for profile in profiles:variants.append({'id':payload_id+'_'+profile,'kind':'observed_label_policy','payload_id':payload_id,'profile':profile})
 plan={'study':'R9h observed-label training admission diagnostic','status':'CPU registered; root review required before GPU launch','diagnostic_only':True,'no_confirmation_or_test_scoring':True,'no_model_promotion':True,'folds':folds,'seeds':seeds,'columns':columns,'physical_source_fields':actual_fields,'column_order':'Alphabetical stable predictor-column names; identical across new policies/profiles; excludes original target-derived feature order. Original B references retain their original frozen design.','row_order':'Train/query SHA256(pid), then pid tie-break; IDs never predictors. Preserve all query PIDs; exact identical-input predictions receive one average score.','training_target':'Require observed finite ordinals1..h with season_end<=Y-1; never fill missing WAR with zero. Sum observed WAR, clip[-40,40], then average-tied cohort Gaussianrank using ONLY admitted training rows: ndtri(clip((rank-0.5)/n,.01,.99)).','policy_grid':{'start':[2000,2007,2008],'gap':[1,2],'population':['all','drafted'],'horizon':[1,2,3,4,5]},'minimum_training_rows_every_fold':40,'minimum_players_each_admitted_cohort':5,'policies':policies,'canonical_payloads':list(payloads.values()),'profiles':profiles,'variants':variants,'execution':{'workers':4,'task_count':len(variants)*3,'model_fit_authorized':False},'queries':queries,'evaluation':'Always report BOTH prespecified metrics: full-query legacy missing-to-zero truth, and fixed observed-truth mask requiring every ordinal1..k by2018. Same full query prediction population for both; paired original B comparisons on the identical mask. Never choose whichever score is better. Neither is a certified complete-population benchmark.','limitations':['Incomplete historical candidate population','Observed-label admission and observed-truth masks may select survivors; source-gap is not proven career zero','Retrospective source/label vintages remain uncertified','Reused pre2019 development folds; no heldout2019+ data or scores'],'reference_gate':'Three exact original B raw/canonical/score/audit replays before interpretation; also score those fixed predictions on the registered observed-truth masks.'}
 save(ROOT/'plan.json',plan)
 source={'reference_study':'r9g','reference_frozen_sha256':G_SHA,'reference_files':frozen['files'],'preflight_code_sha256':h(Path(__file__).read_bytes()),'data_files':{str(p.relative_to(ROOT)):{'sha256':h(p.read_bytes()),'bytes':p.stat().st_size}for p in sorted(DATA.glob('*.npz'))}}
 save(ROOT/'source_manifest.json',source)
 summary={'passed':True,'models_fitted':0,'raw_policies':len(policies),'valid_policies':len(valid),'excluded_policies':len(excluded),'exact_distinct_matrix_target_payloads':len(payloads),'profiles':len(profiles),'registered_tasks':len(variants)*3,'baseline_references':3,'query_counts':{y:{k:q[k]for k in ['all_query_rows','observed_mask_rows','unknown_incomplete_rows']}for y,q in queries.items()},'new_label_missing_to_zero':False,'fixed_column_order':True,'new_source_data':False,'GPU_launch_authorized':False,'tests':unit_tests,'registered_data_files':len(source['data_files']),'registration_sha256':h((ROOT/'plan.json').read_bytes())}
 save(OUT/'preflight_summary.json',summary);print(json.dumps(summary),flush=True)
if __name__=='__main__':main()

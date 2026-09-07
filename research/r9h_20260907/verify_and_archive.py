"""Model-free verification of observed-label policies, both metrics and lossless backup."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import hashlib,json,gzip,time,math,copy
import numpy as np
import pandas as pd
from scipy.special import ndtri
import worker as X
import preflight as P
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results';ARCHIVE=OUT/'task_archives'
EXPECTED_FROZEN='22e68b8bee7902d65ed0f1c7a2d04bde3fc6521f5f872339faead15416c24d0e'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def write_json(path,data):
 raw=(json.dumps(data,indent=2,allow_nan=False)+'\n').encode();tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_bytes(raw);tmp.replace(path)
def file_info(path):return {'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size}
def no_fit(*args,**kwargs):raise AssertionError('No model fitting/inference or selector preparation in verification')
def source_replay(p):
 bp,manifest,data,labels=X.B._load_inputs();assert data.draft_year.max()<=2018 and labels.season_end.max()<=2018
 assert data.pid.is_unique and not labels.duplicated(['pid','ordinal']).any()
 columns=p['columns'];fields=p['physical_source_fields'];assert len(columns)==len(fields)==44 and columns==sorted(columns)
 ref=X.D.references()[0]['rows'][0]['audit'];mapping={slot:field for field,slot in bp['slot_mapping'].items()};mapping.update(zip(ref['pair_design']['slots'],ref['pair_design']['features']))
 assert fields==[mapping.get(c,c)for c in columns]
 assert not any(c.startswith(('bio_','med_','cons_','y_'))or c in ['pid','draft_year','actual_pick','was_drafted','qid']for c in fields)
 def matrix(frame):return frame[fields].to_numpy(dtype=float)
 query_proof=[]
 for year in p['folds']:
  q=p['queries'][str(year)];te=P.canonical_rows(data[(data.draft_year==year)&(data.was_drafted==1)]);k=min(5,2018-year)
  dated=labels[(labels.season_end<=2018)&labels.ordinal.between(1,k)&np.isfinite(labels.war)]
  wide=dated.pivot(index='pid',columns='ordinal',values='war').reindex(index=te.pid,columns=range(1,k+1));mask=wide.notna().all(axis=1).to_numpy();truth=te.pid.map(dated.groupby('pid').war.sum()).fillna(0).to_numpy(dtype=float)
  with np.load(ROOT/'data'/f'query_{year}.npz',allow_pickle=False)as stored:
   assert set(stored.files)=={'X','legacy_truth','observed_truth_mask','pid'}
   assert stored['pid'].tolist()==te.pid.tolist()==q['query_pids'];assert np.array_equal(stored['X'],matrix(te),equal_nan=True)
   assert np.array_equal(stored['legacy_truth'],truth)and np.array_equal(stored['observed_truth_mask'],mask)
  assert mask.tolist()==q['observed_truth_mask']and int(mask.sum())==q['observed_mask_rows']and len(te)==q['all_query_rows']
  assert X.values_hash(matrix(te))==q['matrix_hash']and X.values_hash(truth)==q['legacy_truth_hash']and sha(mask.tobytes())==q['observed_mask_hash']
  query_proof.append({'year':year,'rows':len(te),'observed_rows':int(mask.sum()),'source_matrix_truth_mask_PID_replayed':True})
 policy_proof=[];payloads={}
 for policy in p['policies']:
  parts=[]
  for a in policy['folds']:
   year=a['year'];h=policy['horizon'];cutoff=year-1
   base=data[(data.draft_year>=policy['start'])&(data.draft_year<=year-policy['gap'])]
   if policy['population']=='drafted':base=base[base.was_drafted==1]
   dated=labels[(labels.season_end<=cutoff)&labels.ordinal.between(1,h)&np.isfinite(labels.war)&labels.pid.isin(base.pid)]
   wide=dated.pivot(index='pid',columns='ordinal',values='war').reindex(index=base.pid,columns=range(1,h+1));admitted=wide.index[wide.notna().all(axis=1)]
   tr=P.canonical_rows(base[base.pid.isin(admitted)]);facts=dated[dated.pid.isin(tr.pid)].sort_values(['pid','ordinal']).reset_index(drop=True)
   cumulative=tr.pid.map(facts.groupby('pid').war.sum()).to_numpy(dtype=float);clipped=np.clip(cumulative,-40,40);yy=np.empty(len(tr),dtype=float)
   for cohort,indices in tr.groupby('draft_year').indices.items():
    rank=pd.Series(clipped[indices]).rank(method='average').to_numpy();yy[indices]=ndtri(np.clip((rank-.5)/len(indices),.01,.99))
   assert np.isfinite(cumulative).all()and np.isfinite(yy).all()and len(facts)==len(tr)*h
   assert not len(facts)or facts.season_end.max()<=cutoff
   assert set(facts.ordinal)==set(range(1,h+1))if len(facts)else True
   cohorts={str(int(k)):int(v)for k,v in tr.groupby('draft_year').size().items()};reasons=[]
   if len(tr)<40:reasons.append('fewer_than_40_observed_training_rows')
   if any(n<5 for n in cohorts.values()):reasons.append('admitted_cohort_fewer_than_5_observed_rows')
   x=matrix(tr);fact_columns=['pid','draft_year','ordinal','season_end','war']
   expected={'year':year,'cutoff':cutoff,'rows':len(tr),'cohort_counts':cohorts,'valid':not reasons,'exclusion_reasons':reasons,'pid_hash':sha(P.canon(tr.pid.tolist())),'matrix_hash':X.values_hash(x),'target_hash':X.values_hash(yy),'cumulative_WAR_hash':X.values_hash(cumulative),'clipped_WAR_hash':X.values_hash(clipped),'source_fact_hash':sha(P.canon(facts[fact_columns].to_dict(orient='records'))),'source_fact_rows':len(facts),'max_label_season':int(facts.season_end.max())if len(facts)else None,'training_max_cohort':int(tr.draft_year.max())if len(tr)else None,'training_pids':tr.pid.tolist()}
   assert expected==a,policy['id'];parts.append({'matrix_hash':a['matrix_hash'],'target_hash':a['target_hash'],'query_matrix_hash':p['queries'][str(year)]['matrix_hash'],'columns':columns})
   if policy['valid']:
    arrays={'X':x,'y':yy,'pid':np.asarray(tr.pid.tolist(),dtype=str),'draft_year':tr.draft_year.to_numpy(),'source_cumulative_WAR':cumulative};key=(policy['canonical_payload'],year)
    if key not in payloads:
     with np.load(ROOT/'data'/f'{key[0]}_{year}.npz',allow_pickle=False)as stored:
      assert set(stored.files)==set(arrays)
      for name,array in arrays.items():
       actual=stored[name];assert actual.dtype.kind!='O';assert np.array_equal(actual,array,equal_nan=True)if array.dtype.kind in 'fci'else np.array_equal(actual,array)
     payloads[key]=arrays
   policy_proof.append({'policy_id':policy['id'],'year':year,'all_registered_audit_fields_exact':True,'observed_training_rows':len(tr),'horizon':h,'max_label_season':expected['max_label_season'],'valid':a['valid']})
  assert sha(P.canon(parts))==policy['payload_hash']and policy['valid']==all(a['valid']for a in policy['folds'])
 assert len(payloads)==63 and len(policy_proof)==180
 distinct={}
 for policy in p['policies']:
  if policy['valid']:assert distinct.setdefault(policy['payload_hash'],policy['id'])==policy['canonical_payload']
 assert len(distinct)==21 and sum(v['valid']for v in p['policies'])==42
 for item in p['canonical_payloads']:
  original=next(v for v in p['policies']if v['id']==item['id']);assert item['folds']==original['folds']and item['payload_hash']==original['payload_hash']
 manifest=json.loads((ROOT/'source_manifest.json').read_text());assert len(manifest['data_files'])==66
 for name,info in manifest['data_files'].items():assert file_info(ROOT/name)==info
 proof={'passed':True,'model_fits':0,'selector_fits':0,'independent_pivot_admission_and_rank_reconstruction':True,'policy_fold_audits':180,'training_payload_files_exact':63,'query_payload_files_exact':3,'all_66_arrays_reconstructible_from_pinned_pre2019_G_source':True,'anonymous_PIDs_only':True,'fixed44_predictors':True,'no_identity_crosswalk_raw_articles_or_539column_payloads':True,'no_unknown_training_WAR_zero_fill':True,'fully_observed_requested_ordinals':True,'all_training_source_seasons_at_or_before_fold_cutoff':True,'admitted_row_cohort_ranks_only':True,'deduped_distinct_payloads':21,'queries':query_proof,'policies':policy_proof,'negative_fixtures':P.tests()}
 write_json(OUT/'source_replay_verification.json',proof);return proof

def main():
 start=time.perf_counter();assert sha((ROOT/'frozen.json').read_bytes())==EXPECTED_FROZEN;p=X.plan();frozen=json.loads((ROOT/'frozen.json').read_text());assert len(frozen['files'])==81;X.environment()
 X.B._prepared=no_fit;X.run_variant=no_fit;X.D.run_variant=no_fit
 from tabicl import TabICLRegressor
 from catboost import CatBoostRegressor
 TabICLRegressor.fit=no_fit;TabICLRegressor.predict=no_fit;CatBoostRegressor.fit=no_fit;CatBoostRegressor.predict=no_fit
 source_replay(p)
 expected=[f"{v['id']}_seed{s}"for v in p['variants']for s in p['seeds']];assert len(expected)==len(set(expected))==192
 assert json.loads((OUT/'preregistered_plan.json').read_text())=={'plan':p,'plan_sha256':sha((ROOT/'plan.json').read_bytes()),'files':frozen['files']}
 assert json.loads((OUT/'queue_registration.json').read_text())=={'registration_hash':EXPECTED_FROZEN,'initial_records_sha256':sha(b'[]'),'task_ids':expected,'workers':4,'snapshot_seconds':3.,'summary_seconds':20.}
 completion=json.loads((OUT/'completion.json').read_text());assert completion['status']=='completed'and completion['tasks']==192 and completion['no_model_promotion']and completion['both_metrics_saved']
 state=json.loads((OUT/'state.json').read_text());assert state['status']=='completed'and state['completed']==state['total']==192 and state['active_workers']==0 and not state.get('error')and state.get('test_result')is None and state.get('confirmation')is None
 gate=json.loads((OUT/'reference_gate.json').read_text());assert gate=={'passed':True,'original_B_references':3,'all_before_new_model_fits':True,'frozen_sha256':EXPECTED_FROZEN}
 paths={q.stem:q for q in (OUT/'tasks').glob('*.json')};assert set(paths)==set(expected)
 rawlog=(OUT/'completed.jsonl').read_bytes();assert rawlog.endswith(b'\n');logs=[json.loads(line)for line in rawlog.splitlines()];log={e['task_id']:e for e in logs};assert len(log)==len(logs)==192 and set(log)==set(expected)
 assert {e['task_id']for e in logs[:3]}=={f'drop5_001_seed{s}'for s in p['seeds']}
 records=[];record_info=[];scores=0;effective_widths={}
 for tid in expected:
  path=paths[tid];assert not path.is_symlink();raw=path.read_bytes();e=json.loads(raw);assert e['task_id']==tid and log[tid]['file']==tid+'.json'and sha(raw)==log[tid]['sha256']and raw==json.dumps(e,sort_keys=True,separators=(',',':'),allow_nan=False).encode();X.validate_entry(e)
  for row in e['rows']:
   assert len(row['predictions'])==p['queries'][str(row['season'])]['all_query_rows'];assert all(math.isfinite(v['raw_score'])and math.isfinite(v['score'])for v in row['predictions']);scores+=2
   if e['config']['kind']=='observed_label_policy':
    atr,ate,tr,te,a,q=X.payload(e['config']['payload_id'],row['season']);profile=e['config']['profile'];model,kwargs=X.constructor(profile,e['seed']);audit=row['audit'];design=row['model_design']
    values={'input_columns':p['columns'],'training_matrix_hash':a['matrix_hash'],'validation_matrix_hash':q['matrix_hash'],'training_labels_hash':a['target_hash'],'training_pid_hash':a['pid_hash'],'validation_pid_hash':q['pid_hash'],'training_max_draft_year':a['training_max_cohort'],'max_label_season':a['max_label_season'],'registered_model_parameters':kwargs,'source_fact_hash':a['source_fact_hash'],'source_fact_rows':a['source_fact_rows'],'observed_mask_hash':q['observed_mask_hash'],'no_unknown_training_labels':True}
    assert {k:v for k,v in audit.items()if k!='canonical_prediction_ties'}==values and row['ntrain']==len(atr)and row['n']==len(ate)and row['cutoff']==row['season']-1
    if p['profiles'][profile]['model']=='TabICLRegressor':
     from tabicl._sklearn.regressor import TransformToNumerical,EnsembleGenerator
     import inspect
     encoded=TransformToNumerical().fit_transform(atr);filtered=inspect.getmodule(EnsembleGenerator).UniqueFeatureFilter().fit(encoded);width=int(filtered.n_features_out_)
     assert design['effective_constructor']==model.get_params(deep=False)and design['effective_features']==width and design['effective_estimators']==min(width,kwargs['n_estimators'])
     effective_widths[(e['config']['payload_id'],row['season'])]={'payload_id':e['config']['payload_id'],'season':row['season'],'input_columns':44,'effective_columns':width,'kept_columns':[c for c,keep in zip(p['columns'],filtered.features_to_keep_)if keep],'all_constant_fallback':not any(len(np.unique(encoded[:,i]))>1 for i in range(encoded.shape[1]))}
     assert design['module_attributes']and design['actual_devices']and all(v.startswith('cuda')for v in design['actual_devices'])
    else:
     actual=design['effective_constructor'];assert actual['task_type']=='GPU'and design['tree_count']==actual['iterations']==200 and actual['random_seed']==e['seed']
     for key in ['loss_function','depth','learning_rate','l2_leaf_reg','bagging_temperature','nan_mode','bootstrap_type','boosting_type','random_strength','use_best_model']:
      value=kwargs[key]
      if isinstance(value,(int,float))and not isinstance(value,bool):assert np.isclose(actual[key],value,rtol=2e-7,atol=1e-9)
      else:assert actual[key]==value
  records.append(e);record_info.append({'task_id':tid,'file':'tasks/'+tid+'.json','sha256':sha(raw),'bytes':len(raw)})
 summary=X.summarize(records);assert summary==state['matched_summary']and summary['reference_replays_passed']==3 and summary['interpretation_allowed']and len(summary['configurations'])==63
 assert all(set(c)>= {'legacy','observed'}for c in summary['configurations'])
 candidates={c['task_id']:c for c in state['candidates']};assert set(candidates)==set(expected)
 for e in records:
  c=candidates[e['task_id']];assert all(c[k]==e[k]for k in ['config','seed','score','seconds','legacy_score','observed_score'])and c['rows']==[{'season':r['season'],'stack':r['stack'],'observed_stack':r['observed_mask_score']}for r in e['rows']]
 write_json(OUT/'matched_summary.json',summary)
 write_json(OUT/'effective_width_verification.json',{'passed':True,'source':'Pinned TabICL TransformToNumerical and UniqueFeatureFilter, trained on frozen X only','model_fits':0,'records':list(effective_widths.values()),'smallest_effective_width':min(v['effective_columns']for v in effective_widths.values()),'largest_effective_width':max(v['effective_columns']for v in effective_widths.values()),'all_constant_fallback_is_uninformative':True})
 print('Verified192 immutable records,81 frozen files,3 exact B references,66 source payloads and all63 configurations on BOTH metrics.',flush=True)
 # Fixed plan order and 32 MB uncompressed chunks guarantee generous room below 40 MB gzip limit.
 ARCHIVE.mkdir(exist_ok=True);groups=[];group=[];size=0
 for info in record_info:
     if group and size+info['bytes']+1>32_000_000:groups.append(group);group=[];size=0
     group.append(info);size+=info['bytes']+1
 if group:groups.append(group)
 chunks=[]
 for index,group in enumerate(groups):
     name=f'tasks_{index:03d}.jsonl.gz';path=ARCHIVE/name;tmp=path.with_suffix('.tmp');uncompressed=hashlib.sha256();nbytes=0
     with tmp.open('wb') as file:
         with gzip.GzipFile(filename='',mode='wb',fileobj=file,mtime=0,compresslevel=6) as stream:
             for info in group:
                 raw=(OUT/info['file']).read_bytes();assert sha(raw)==info['sha256'];line=raw+b'\n';stream.write(line);uncompressed.update(line);nbytes+=len(line)
     assert tmp.stat().st_size<40_000_000
     if path.exists():assert file_info(path)==file_info(tmp);tmp.unlink()
     else:tmp.replace(path)
     restored_hash=hashlib.sha256();restored_bytes=0;count=0
     with gzip.open(path,'rb') as stream:
         for info in group:
             line=stream.readline();assert line.endswith(b'\n');raw=line[:-1]
             assert len(raw)==info['bytes'] and sha(raw)==info['sha256'] and raw==(OUT/info['file']).read_bytes()
             restored_hash.update(line);restored_bytes+=len(line);count+=1
         assert stream.read()==b''
     assert restored_hash.hexdigest()==uncompressed.hexdigest() and restored_bytes==nbytes and count==len(group)
     for line,info in enumerate(group):info.update(chunk=name,line_1based=line+1)
     chunks.append({'file':'task_archives/'+name,**file_info(path),'records':count,'uncompressed_bytes':nbytes,'uncompressed_sha256':uncompressed.hexdigest(),'roundtrip_exact':True})
 assert {p.name for p in ARCHIVE.glob('*.gz')}=={Path(c['file']).name for c in chunks}
 archive={'format':'gzip of exact original task JSON bytes, each followed by one LF; recover each original file by removing exactly that terminal LF','ordering':'frozen plan variant order, then registered model seed order','gzip':{'mtime':0,'filename':'','compresslevel':6},'chunk_compressed_limit_bytes':40_000_000,'chunk_uncompressed_target_bytes':32_000_000,'frozen_manifest_sha256':EXPECTED_FROZEN,'record_count':len(record_info),'original_bytes':sum(i['bytes'] for i in record_info),'compressed_bytes':sum(c['bytes'] for c in chunks),'all_roundtrips_exact':True,'chunks':chunks,'records':record_info}
 write_json(OUT/'task_archive_manifest.json',archive)
 proof={'passed':True,'models_fitted':0,'model_predictions_run':0,'records':192,'reference_replays_exact':3,'reference_gate_before_new_fits':True,'frozen_files_unchanged':81,'frozen_manifest_sha256':EXPECTED_FROZEN,'preregistration_exact':True,'queue_registration_exact':True,'append_log_all_hashes_exact':True,'append_log_sha256':sha(rawlog),'complete_summary_recomputed_exact':True,'compact_candidates_exact':True,'configuration_summaries_both_metrics':63,'saved_fold_metric_values_recomputed_exact':scores,'installed_source_hashes_exact':True,'actual_GPU_constructors_validated':True,'source_replay':file_info(OUT/'source_replay_verification.json'),'effective_widths':file_info(OUT/'effective_width_verification.json'),'source_payloads_reconstructed':66,'no_unknown_training_WAR_zero_fill':True,'all_pre2019_development_only':True,'no_model_promotion':True,'task_archive_manifest':file_info(OUT/'task_archive_manifest.json'),'chunks':len(chunks),'original_bytes':archive['original_bytes'],'compressed_bytes':archive['compressed_bytes'],'max_chunk_bytes':max(c['bytes']for c in chunks),'all_record_roundtrips_byte_exact':True,'queue_elapsed_seconds':completion['elapsed_seconds'],'verification_seconds':time.perf_counter()-start,'verification_code_sha256':sha(Path(__file__).read_bytes()),'summary':file_info(OUT/'matched_summary.json')}
 write_json(OUT/'run_verification.json',proof)
 (OUT/'report.md').write_text(f'R9h verification passed:192 immutable task records and their complete append log;81 frozen files;three exact original B references before the new fits;63 configuration summaries with BOTH prespecified metrics;{scores} saved fold-metric values recomputed. Actual CUDA/constructor settings, training-only encoder/filter effective widths and estimator caps, fixed seeds, native NaNs, exact input-vector tie handling and full query populations match the registration. No model fitting, inference or held-out access occurred during this audit.\n\nAll66 prepared payloads were reconstructed array-for-array from the pinned, already public pre2019 G source. An independent pivot-based admission check reproduced all60 policies across three folds, their source-fact/calendar hashes and21 distinct payloads. Every admitted training row has all finite observed ordinals of its requested horizon before the fold cutoff. No unknown training WAR is replaced with zero; cohort Gaussian ranks use admitted training rows only. Known observed zero values remain legitimate.\n\nTabICL effective widths range1–44 after its installed training-only numeric encoder and constant-column filter. Some early h4/h5 folds retain only4/1 columns; if every feature is constant, the installed filter retains one uninformative fallback column. This limits interpretation of those policies. Frozen44 input values and requested settings were not changed.\n\nBoth legacy full-query and fixed observed-truth-mask scores remain diagnostics. The observed masks cover28/55,26/50,28/53 query rows; observed-survivor selection, incomplete historical candidates, retrospective sources and reused development folds remain limitations. No model promotion,60% goal claim or clean complete-population benchmark claim.\n\n{len(chunks)} deterministic gzip chunks preserve all{archive["original_bytes"]:,} original raw bytes in{archive["compressed_bytes"]:,} compressed bytes. Every record is restored byte-exact, with per-record and chunk hashes. All raw files stay remote; only the explicit public allowlist is proposed for publication. The66 numeric/anonymous-PID payloads are admitted to that allowlist solely because exact reconstruction from already public G inputs was verified; no private identity crosswalk, raw article or original539-column data is included.\n')
 public_names=set(frozen['files'])|{'frozen.json','verify_and_archive.py','run_verify_sandbox.sh'}
 public_names|={'results/'+name for name in ['preregistered_plan.json','queue_registration.json','completion.json','state.json','completed.jsonl','reference_gate.json','runtime_preflight.json','launch_verification.json','matched_summary.json','task_archive_manifest.json','run_verification.json','report.md','source_replay_verification.json','effective_width_verification.json']}
 public_names|={'results/'+c['file']for c in chunks}
 public={'study':'r9h','files':{name:file_info(ROOT/name)for name in sorted(public_names)},'raw_task_files_preserved_remote':True,'all_raw_tasks_losslessly_included_in_chunks':True,'record_count':192,'no_heldout_inputs_or_outcomes':True,'public_data_admission':{'66_numeric_anonymous_PID_payloads_exactly_reconstructed_from_already_public_G_source':True,'reference_public_package':'research/r9g_20260907','proof':'results/source_replay_verification.json','private_crosswalks_raw_articles_539column_payloads_included':False},'both_prespecified_metrics_retained':True}
 public['total_bytes']=sum(x['bytes']for x in public['files'].values());write_json(OUT/'PUBLIC_ALLOWLIST.json',public)
 print(json.dumps(proof),flush=True);print(json.dumps({'public_files':len(public['files']),'public_bytes':public['total_bytes'],'public_allowlist':file_info(OUT/'PUBLIC_ALLOWLIST.json')}),flush=True)
if __name__=='__main__':main()

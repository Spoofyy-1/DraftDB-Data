"""Model-free G verification, full saved-checkpoint/blend replay and lossless backup."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import hashlib,json,gzip,math,time,tempfile
import numpy as np
import pandas as pd
import worker as X
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results';ARCHIVE=OUT/'task_archives'
EXPECTED_FROZEN='2673d0245e317f934a1295a311ba0d49262226df67b61615cc7576856f733b37'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def write_json(path,data):
 raw=(json.dumps(data,indent=2,allow_nan=False)+'\n').encode();tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_bytes(raw);tmp.replace(path)
def file_info(path):return {'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size}
def no_fit(*args,**kwargs):raise AssertionError('No model fitting/inference in verification')
def truth_only_folds():
 # Reconstruct historical evaluation population/truth without rerunning any selector or predictor.
 data=pd.read_csv(X.B.DATA/'features.csv');labels=pd.read_csv(X.B.DATA/'labels.csv')
 assert data.draft_year.max()<=2018 and labels.season_end.max()<=2018
 folds=[]
 for year in X.load_plan()['folds']:
  te=X.B._canonical_rows(data[(data.draft_year==year)&(data.was_drafted==1)]);k=min(5,2018-year)
  truth=te.pid.map(labels[(labels.season_end<=2018)&(labels.ordinal<=k)].groupby('pid').war.sum()).fillna(0)
  for seed in X.load_plan()['seeds']:
   old=next(r for r in X.D.references()[seed]['rows']if r['season']==year)
   assert old['k']==k and old['n']==len(te)and [v['pid']for v in old['predictions']]==te.pid.tolist()
  folds.append({'year':year,'te':te,'truth':truth})
 return folds

def source_replay(folds):
 # Construct frozen columns directly from pinned source values; no selector is rerun.
 bp,manifest,data,labels=X.B._load_inputs();import legacy_kernel as E
 incumbent=json.loads((X.B.DATA/'incumbent.json').read_text())['champ'];g={**incumbent,'hw':bp['backbone']['hw'],'win':bp['backbone']['window']}
 mapping={slot:feature for feature,slot in bp['slot_mapping'].items()};matrices={};proof=[]
 for fold in folds:
  year=fold['year'];old=next(r for r in X.D.references()[0]['rows']if r['season']==year);a=old['audit'];cutoff=year-1;k=old['k']
  tr=X.B._canonical_rows(data[(data.draft_year>=g['win'])&(data.draft_year<=year-2)]);te=X.B._canonical_rows(data[(data.draft_year==year)&(data.was_drafted==1)])
  used=labels[(labels.season_end<=cutoff)&labels.pid.isin(tr.pid)]
  for ordinal in range(1,6):tr[f'y_s{ordinal}_war']=tr.pid.map(used[used.ordinal==ordinal].set_index('pid').war)
  yy=E.label(tr,E.specs(g)[0],k);assert (yy<0).any()and np.isfinite(yy).all()
  colmap={**mapping,**dict(zip(a['pair_design']['slots'],a['pair_design']['features']))};columns=a['input_columns']
  atr=pd.DataFrame({c:tr[colmap.get(c,c)].astype(float)for c in columns},index=tr.index);ate=pd.DataFrame({c:te[colmap.get(c,c)].astype(float)for c in columns},index=te.index)
  registered=X.support()['source_designs'][str(year)]
  assert X.B._matrix_hash(atr)==registered['train_hash']and X.B._matrix_hash(ate)==registered['query_hash']and X.D.h(yy)==registered['training_target_hash']
  assert X.B._hash(tr.pid.tolist())==a['training_pid_hash']and X.B._hash(te.pid.tolist())==a['validation_pid_hash']
  assert [X.B._hash(v)for v in X.B._exact_vector_keys(ate)]==a['canonical_prediction_ties']['row_vector_hashes']
  assert hashlib.sha256(np.asarray(yy,dtype=np.float64).tobytes()).hexdigest()==a['training_labels_hash']and used.season_end.max()<=cutoff and tr.draft_year.max()<=year-2
  fold.update(tr=tr,te=te,yy=yy);matrices[year]=(atr,ate)
 X.design=lambda f:matrices[f['year']]
 for fold in folds:
  atr,ate,yy,qid,order=X.ordered_training(fold);assert order==X.support()['source_designs'][str(fold['year'])]['training_order'];matrix=X.training_matrix(atr,yy,qid)
  assert np.array_equal(matrix.get_label(),yy.astype(np.float32))and not {'pid','draft_year','actual_pick','qid'}&set(atr)
  proof.append({'year':fold['year'],'matrix_target_PID_order_group_hashes_exact':True,'negative_targets_preserved':True,'no_selector_or_model_fits':True})
 gpu=json.loads((OUT/'gpu_fixture.json').read_text());assert gpu['passed']and gpu['models_scored']==0 and gpu['frozen_manifest_sha256']==EXPECTED_FROZEN and len(gpu['fixtures'])==2
 for e in gpu['fixtures']:assert e['actual_device']=='cuda:0'and e['negative_labels_present']and not e['scored'];X.validate_effective(e['effective_constructor'],e['constructor'])
 write_json(OUT/'source_replay_verification.json',{'passed':True,'model_fits':0,'predictors':44,'folds':proof,'query_order_and_ties_preserved':True,'qid_training_metadata_only':True,'GPU_fixtures_and_CUDA_configurations_verified':True})

def verify_resume(records,rawlog):
 root=OUT/'runtime_resumes/20260907T0407Z';before=json.loads((root/'before_resume.json').read_text());cp=json.loads((root/'checkpoint_verification.json').read_text());recovery=json.loads((root/'recovery_snapshot.json').read_text());old=json.loads((root/'state.json').read_text())
 for name,info in before['snapshots'].items():assert file_info(root/name)==info
 for name in ['preparation.json','queue_registration.json','gpu_fixture.json','sequential_launch.json']:assert (root/name).read_bytes()==(OUT/name).read_bytes()
 assert before['unit']['Result']=='timeout'and before['unit']['ExecMainStatus']=='15'and before['unit']['RuntimeMaxUSec']=='2h'
 assert cp['durable_records']==cp['log_records']==old['completed']==952 and cp['frozen_files_verified']==64 and cp['exact_B_references']==3 and not cp['scientific_changes']
 prefix=b''.join(rawlog.splitlines(keepends=True)[:952]);assert sha(prefix)==cp['log_sha256']=='96fcb7c691147252f3882281217f5e07e9b89f2cfde4168a7450438e1aee412f'
 ids=[json.loads(line)['task_id']for line in prefix.splitlines()];mapped={tid:sha((OUT/'tasks'/(tid+'.json')).read_bytes())for tid in ids};assert sha(json.dumps(mapped,sort_keys=True,separators=(',',':')).encode())==cp['ordered_task_hash_map_sha256']=='cf391353ddf8ce7cc2b4f5b26ce84b98bf5f6a649a5ea4edc8d34a66f78a0a45'
 assert recovery['state']['completed']>=952 and recovery['reference_replays_passed']==3 and recovery['scientific_files_changed']==False
 actual={e['task_id']:e for e in records}
 for candidate in old['candidates']:
  record=actual[candidate['task_id']]
  assert all(candidate[k]==record[k]for k in ['config','seed','score','seconds'])
 return {'passed':True,'runtime_only_resume':True,'retained_exact_records':952,'remaining_records_added':779,'original_log_exact_prefix':True,'retained_task_hash_map_exact':True,'original_timeout_preserved':True,'original_invocation':before['unit']['InvocationID'],'resumed_invocation':recovery['unit']['InvocationID'],'all_evidence_files':{str(p.relative_to(ROOT)):file_info(p)for p in sorted(root.glob('*'))if p.is_file()}}

def main():
 start=time.perf_counter();frozen_raw=(ROOT/'frozen.json').read_bytes();assert sha(frozen_raw)==EXPECTED_FROZEN;frozen=json.loads(frozen_raw);assert len(frozen['files'])==64
 for name,digest in frozen['files'].items():assert sha((ROOT/name).read_bytes())==digest,name
 p=X.load_plan();expected=[f"{v['id']}_seed{s}"for v in p['variants']for s in p['seeds']];assert len(expected)==len(set(expected))==1731 and len(p['variants'])==577
 X.environment()
 # Explicitly block scientific model fitting and inference, including selector preparation.
 X.B._prepared=no_fit;X.run_variant=no_fit;X.D.run_variant=no_fit
 from tabicl import TabICLRegressor
 import xgboost as xgb
 TabICLRegressor.fit=no_fit;TabICLRegressor.predict=no_fit;xgb.train=no_fit;xgb.XGBRegressor.fit=no_fit
 folds=truth_only_folds();source_replay(folds);fold_by_year={f['year']:f for f in folds}
 assert json.loads((OUT/'preregistered_plan.json').read_text())=={'plan':p,'plan_sha256':sha((ROOT/'plan.json').read_bytes()),'files':frozen['files']}
 queue=json.loads((OUT/'queue_registration.json').read_text());assert queue=={'registration_hash':EXPECTED_FROZEN,'initial_records_sha256':sha(b'[]'),'task_ids':expected,'workers':4,'snapshot_seconds':3.,'summary_seconds':20.}
 completion=json.loads((OUT/'completion.json').read_text());assert completion['status']=='completed'and completion['tasks']==1731 and completion['no_model_promotion']and completion['saved_blends_complete']
 state=json.loads((OUT/'state.json').read_text());assert state['status']=='completed'and state['completed']==state['total']==1731 and state['active_workers']==0 and not state.get('error')and state.get('test_result')is None and state.get('confirmation')is None
 paths={q.stem:q for q in (OUT/'tasks').glob('*.json')};assert set(paths)==set(expected)
 rawlog=(OUT/'completed.jsonl').read_bytes();assert rawlog.endswith(b'\n');log={}
 for line in rawlog.splitlines():
  e=json.loads(line);tid=e['task_id'];assert tid not in log and e['file']==tid+'.json';log[tid]=e
 assert set(log)==set(expected);records=[];record_info=[];scores=0
 for tid in expected:
  path=paths[tid];assert not path.is_symlink();raw=path.read_bytes();entry=json.loads(raw);assert entry['task_id']==tid and sha(raw)==log[tid]['sha256']and raw==json.dumps(entry,sort_keys=True,separators=(',',':'),allow_nan=False).encode();X.validate_entry(entry,p)
  for row in entry['rows']:
   assert row['cutoff']==row['season']-1 and row['max_label_season']<=row['cutoff']and row['audit']['training_max_draft_year']<=row['season']-2
   fold=fold_by_year[row['season']];cp_rows=[row]if entry['config']['id']==p['reference_id']else row['checkpoints']
   if entry['config']['id']!=p['reference_id']:
    assert [cp['ntree_end']for cp in cp_rows]==[200,600,1200]and row['tree_count']==1200 and set(row['evaluation_sets'])<= {'learn'}
    X.validate_effective(row['effective_constructor'],X.params(entry['config'],entry['seed']));assert row['evaluation_sets']==[]
    assert row['training_order']==X.support()['source_designs'][str(row['season'])]['training_order']
    assert all(cp['iteration_range']==[0,cp['ntree_end']]for cp in cp_rows)
   for cp in cp_rows:
    assert [v['pid']for v in cp['predictions']]==fold['te'].pid.tolist()and all(math.isfinite(v['score'])and math.isfinite(v['raw_score'])for v in cp['predictions'])
    assert X.B.rho([v['score']for v in cp['predictions']],fold['truth'])==cp['stack'];scores+=1
  records.append(entry);record_info.append({'task_id':tid,'file':'tasks/'+tid+'.json','sha256':sha(raw),'bytes':len(raw)})
 summary=X.summarize_matched(records);assert summary==state['matched_summary']and summary['reference_replays_passed']==3 and summary['interpretation_allowed']and len(summary['configurations'])==576
 candidates={c['task_id']:c for c in state['candidates']};assert set(candidates)==set(expected)
 for e in records:
  c=candidates[e['task_id']];assert all(c[k]==e[k]for k in ['config','seed','score','seconds'])and c['rows']==[{'season':r['season'],'stack':r['stack']}for r in e['rows']]
 recovery=verify_resume(records,rawlog);write_json(OUT/'recovery_verification.json',recovery);write_json(OUT/'matched_summary.json',summary)
 print('Verified1731 immutable records,3 exact B references,64 frozen files,15,561 saved fold-checkpoint scores and952 preserved timeout records.',flush=True)
 # Recompute every registered saved-output blend in a temporary directory, compare bytes, then remove only that temporary replay.
 import postprocess
 X.B._prepared=lambda:(None,None,None,folds)
 with tempfile.TemporaryDirectory(prefix='.verify_blends_',dir=OUT)as temporary:
  replay=Path(temporary);result=postprocess.process(records,replay);assert result==state['saved_blends']and result['recipes']==76032 and result['configurations']==576
  generated=sorted(q for q in replay.rglob('*')if q.is_file())
  for q in generated:assert file_info(q)==file_info(OUT/q.relative_to(replay)),str(q.relative_to(replay))
  blend_verified={'passed':True,'all_registered_recipes':76032,'configurations':576,'same_seed_and_fixed_three_seed_average':True,'all_checkpoints':p['tree_checkpoints'],'all_anchors':p['blend_diagnostic']['anchors'],'all_alpha_steps':p['blend_diagnostic']['alpha_steps'],'all_saved_predictions_metrics_and_gzip_bytes_recomputed_exact':True,'files':len(generated),'no_model_fits':True}
 write_json(OUT/'blend_verification.json',blend_verified);print('Verified all76,032 registered blend recipes and576 gzip artifacts byte-exact.',flush=True)
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
 proof={'passed':True,'models_fitted':0,'model_predictions_run':0,'records':1731,'reference_replays_exact':3,'frozen_files_unchanged':64,'frozen_manifest_sha256':EXPECTED_FROZEN,'preregistration_exact':True,'queue_registration_exact':True,'append_log_all_hashes_exact':True,'append_log_sha256':sha(rawlog),'complete_summary_recomputed_exact':True,'compact_candidates_exact':True,'distinct_XGBoost_configurations':576,'XGBoost_fit_tasks':1728,'saved_fold_checkpoint_scores_recomputed_exact':scores,'checkpoint_rounds':[200,600,1200],'installed_source_hashes_exact':True,'actual_GPU_constructors_validated':True,'source_matrix_order_group_target_replay':file_info(OUT/'source_replay_verification.json'),'all_pre2019_development_only':True,'no_model_promotion':True,'blend_verification':file_info(OUT/'blend_verification.json'),'blend_recipes':76032,'task_archive_manifest':file_info(OUT/'task_archive_manifest.json'),'chunks':len(chunks),'original_bytes':archive['original_bytes'],'compressed_bytes':archive['compressed_bytes'],'max_chunk_bytes':max(c['bytes']for c in chunks),'all_record_roundtrips_byte_exact':True,'resumed_queue_elapsed_seconds':completion['elapsed_seconds'],'retained_exact_records':952,'resumed_new_records':779,'recovery_verification':file_info(OUT/'recovery_verification.json'),'verification_seconds':time.perf_counter()-start,'verification_code_sha256':sha(Path(__file__).read_bytes()),'summary':file_info(OUT/'matched_summary.json')}
 write_json(OUT/'run_verification.json',proof)
 (OUT/'report.md').write_text(f'R9g verification passed:1731 immutable records and their log hashes,3 exact B baseline replays,64 frozen files and{scores:,} saved fold/checkpoint scores match. The576 XGBoost configurations were fit at1,200 trees and every200/600/1,200 checkpoint was retained. Actual GPU constructor parameters, fixed seeds, native NaNs, cohort grouping/order and original targets, canonical input ties, training-calendar cutoffs and query populations were verified. No model fitting, inference or held-out evaluation occurred in this audit.\n\nAll76,032 registered saved-output rank-blend recipes were independently regenerated from saved predictions with both frozen B/E anchors, all11 alpha weights and both same-seed/equal-three-seed modes. Every prediction, metric, summary, manifest and deterministic per-configuration gzip file matches byte-for-byte. No favorable-seed selection or model promotion. Reused-development, retrospective-source and missing-label limitations remain.\n\nThe first unit reached its registered2h cap after952 durable records. All952 original records and the exact952-line log prefix survive unchanged;779 missing tasks were completed after a runtime-only restart. Original timeout, restart and recovery evidence are included. No scientific registration, code, input or completed result changed.\n\nAll raw files remain remote. {len(chunks)} deterministic task gzip chunks preserve{archive["original_bytes"]:,} raw bytes in{archive["compressed_bytes"]:,} compressed bytes; every raw-record roundtrip is exact and each chunk is below40MB. The manifest records per-record hashes, original names, chunk/line mappings and compressed/uncompressed hashes. The full blend artifacts are also retained. No new study is selected by this verification.\n')
 public_names=set(frozen['files'])|{'frozen.json','verify_and_archive.py','run_verify_sandbox.sh'}
 public_names|={'results/'+name for name in ['preregistered_plan.json','queue_registration.json','preparation.json','completion.json','state.json','completed.jsonl','sequential_launch.json','queue_verification.json','CPU_preparation.json','gpu_fixture.json','matched_summary.json','task_archive_manifest.json','run_verification.json','report.md','recovery_verification.json','blend_manifest.json','blend_summary.json','postprocess_progress.json','blend_verification.json','source_replay_verification.json']}
 public_names|={'results/'+c['file']for c in chunks}
 public_names|={str(q.relative_to(ROOT))for q in (OUT/'blend_diagnostics').glob('*.gz')}
 public_names|=set(recovery['all_evidence_files'])
 public={'study':'r9g','files':{name:file_info(ROOT/name)for name in sorted(public_names)},'raw_task_files_preserved_remote':True,'all_raw_tasks_losslessly_included_in_chunks':True,'all_saved_blend_predictions_preserved':True,'record_count':1731,'no_heldout_inputs_or_outcomes':True}
 public['total_bytes']=sum(x['bytes']for x in public['files'].values());write_json(OUT/'PUBLIC_ALLOWLIST.json',public)
 print(json.dumps(proof),flush=True);print(json.dumps({'public_files':len(public['files']),'public_bytes':public['total_bytes'],'public_allowlist':file_info(OUT/'PUBLIC_ALLOWLIST.json')}),flush=True)
if __name__=='__main__':main()

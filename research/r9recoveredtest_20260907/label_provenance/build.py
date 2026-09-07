"""Private recovered-stack expanding label exports. CPU only; no vault/scorer."""
from pathlib import Path
import argparse,csv,hashlib,importlib.util,json,os
import numpy as np
import pandas as pd
K_CODE='6b89764345f5920d383540d1138977217c94cbd7cbca1de33f2ea718437676f7'
BROKER_CODE='33291890f4a634be3aa38e9d99156e85b439e06451e791a5d05aaa0240a27e8b'
FEATURE_MANIFEST='9ba8624cfe079fb1a91f80e0c10a662a0694f29ddafcf4f0e9bcfd3995c58225'
CALENDAR_FREEZE='f824ece03e0eeefc3f3c3cacb2215d5c0376785c0130d88f316ad7268db0e90c'
FIELDS=['pid','draft_year','label_value','y','prefix_length','season_end_max']
FACTS=['pid','draft_year','ordinal','season_end','war']
def canon(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(v).hexdigest()
def sha(p):return digest(Path(p).read_bytes())
def read(p):return json.loads(Path(p).read_text())
def frame(p,**kw):return pd.read_csv(p,dtype={'pid':str},float_precision='round_trip',**kw)
def write(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def load(p):
 assert sha(p)==K_CODE
 spec=importlib.util.spec_from_file_location('recovered_pinned_K',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def payload(K,pool,facts,year):
 arrays,used=K.prefix_payload(pool,facts,year,start=2007,discount=.85)
 arrays['season_end_max']=pd.Series(arrays['pid']).map(used.groupby('pid').season_end.max()).to_numpy(dtype=np.int64)
 assert list(arrays)==FIELDS and np.all(arrays['season_end_max']<=year-1)
 return arrays,used
def canonical_facts(f):return f[FACTS].sort_values(['pid','ordinal']).reset_index(drop=True)

def main(a):
 os.umask(0o077);assert not a.output.exists(),'Never overwrite registered exports'
 R=a.project;K=load(R/'r9k_labelprep/build.py');broker=K.load_broker(R/'calendar_broker_prototype/broker.py')
 F=R/'r9stacktest_features/package';L=R/'r9stacktest_calendar';C=R/'calendar_broker_prototype';S=C/'source'
 assert sha(F/'manifest.json')==FEATURE_MANIFEST and sha(L/'freeze.json')==CALENDAR_FREEZE
 fm=read(F/'manifest.json');lf=read(L/'freeze.json');pins={str(F/'manifest.json'):FEATURE_MANIFEST,str(L/'freeze.json'):CALENDAR_FREEZE,str(R/'r9k_labelprep/build.py'):K_CODE,str(C/'broker.py'):BROKER_CODE}
 metas={}
 for key in ['pre2019']+[str(y) for y in range(2019,2026)]:
  p=F/f'metadata_{key}.csv';assert sha(p)==fm['outputs'][p.name]['sha256'];pins[str(p)]=sha(p);m=frame(p)
  assert list(m)==['pid','draft_year','was_drafted'] and m.pid.is_unique and m.was_drafted.isin([0,1]).all()
  assert m.draft_year.between(2000,2018).all() if key=='pre2019' else m.draft_year.eq(int(key)).all()
  metas[key]=m
 assert len(metas['pre2019'])==1428
 sourcepath=S/'historical_RAPTOR_by_player.csv';identitypath=S/'tabular_names.csv'
 source=pd.read_csv(sourcepath,usecols=['player_name','player_id','season','war_total'],dtype={'player_name':str,'player_id':str,'season':np.int64,'war_total':str})
 identities=pd.read_csv(identitypath,usecols=['pid','draft_year','player_name']);assert identities.pid.is_unique
 prepared=[];queries={};calendar_proof=[];replay2019=None
 for year in range(2019,2026):
  pool=pd.concat([metas['pre2019']]+[metas[str(y)] for y in range(2019,year)],ignore_index=True)
  assert pool.pid.is_unique and pool.draft_year.lt(year).all()
  q=K.canonical_rows(metas[str(year)].loc[metas[str(year)].was_drafted.eq(1)])
  for name in ['manifest.json','training_labels.csv']:
   p=L/str(year)/name;assert sha(p)==lf['files'][f'{year}/{name}'];pins[str(p)]=sha(p)
  h1m=read(L/str(year)/'manifest.json');old=R/'r9test_label_exports'/str(year);om=read(old/'manifest.json')
  assert sha(old/'manifest.json')==h1m['source_manifest_sha256'];pins[str(old/'manifest.json')]=sha(old/'manifest.json')
  bundle=C/'bundles'/str(year);bm=read(bundle/'manifest.json')
  assert sha(bundle/'manifest.json')==om['source_manifest_sha256']==h1m['broker_manifest_sha256']
  assert sha(bundle/'training_labels.csv')==bm['files']['training_labels.csv']==om['source_labels_sha256']==h1m['broker_labels_sha256']
  assert bm['predicted_draft_year']==year and bm['permitted_season_end']==year-1
  assert bm['actual_label_max']<=year-1 and all(y<year for y in bm['eligible_answer_cohorts_opened'])
  assert sha(sourcepath)==bm['source']['sha256'] and sha(identitypath)==bm['identity_sha256']
  pins.update({str(bundle/'manifest.json'):sha(bundle/'manifest.json'),str(bundle/'training_labels.csv'):sha(bundle/'training_labels.csv'),str(sourcepath):sha(sourcepath),str(identitypath):sha(identitypath)})
  facts=canonical_facts(frame(bundle/'training_labels.csv'))
  assert len(facts)==bm['training_labels'] and not facts.duplicated(['pid','ordinal']).any()
  assert facts.draft_year.lt(year).all() and facts.season_end.le(year-1).all() and np.isfinite(facts.war).all()
  assert facts.season_end.gt(facts.draft_year).all() and facts.ordinal.between(1,5).all()
  assert not set(facts.pid)&set(q.pid)
  oldh1=canonical_facts(frame(L/str(year)/'training_labels.csv'))
  pd.testing.assert_frame_equal(canonical_facts(facts[facts.ordinal.eq(1)]),oldh1,check_exact=True)
  # Calendar/source comparison touches only already permitted earlier facts.
  dated=source[source.season.le(year-1)].copy();priorids=identities[identities.draft_year.lt(year)].copy()
  calendar,reasons=broker.eligible_calendar(dated,priorids,year);lookup=calendar.set_index(['pid','ordinal']);worst=0.
  for row in facts.itertuples():
   assert (row.pid,row.ordinal) in lookup.index
   c=lookup.loc[(row.pid,row.ordinal)]
   assert int(c.draft_year)==row.draft_year and int(c.season_end)==row.season_end
   delta=abs(float(c.reference_war)-float(row.war));assert delta<=1e-5;worst=max(worst,delta)
  arrays,used=payload(K,pool,facts,year)
  counts=K.validate_admission({k:arrays[k] for k in FIELDS[:-1]},year,q.pid)
  if year==2019:
   rawpath=R/'data/train_2000_2018.csv';assert sha(rawpath)==bm['inputs'][0]['sha256'];pins[str(rawpath)]=sha(rawpath)
   eligible={pid:sorted(g.ordinal.astype(int).tolist()) for pid,g in calendar.groupby('pid')}
   sparse=[]
   with rawpath.open() as f:
    for row in csv.DictReader(f):
     assert int(row['draft_year'])<year
     if row['pid'] in eligible:
      entry={'pid':row['pid']}
      for ordinal in eligible[row['pid']]:entry[f'y_s{ordinal}_war']=row.get(f'y_s{ordinal}_war','')
      sparse.append(entry)
   rawfacts,rawaudit=broker.verify_eligible_labels(calendar,pd.DataFrame(sparse,columns=['pid']+K.TARGETS))
   pd.testing.assert_frame_equal(canonical_facts(rawfacts),facts,check_exact=True)
   replay,rf=payload(K,pool,rawfacts,year)
   assert all(np.array_equal(replay[k],arrays[k]) for k in FIELDS)
   replay2019={'year':2019,'rows':len(arrays['pid']),'full_original_broker_facts_reconstructed_exact':True,'all_six_prefix_arrays_exact':True,'no_2019_answers_opened':True,'raw_eligible_ordinal_cells_only':True,'broker_label_verification':rawaudit}
  # Existing inference bundle contains predictors and IDs only, never answers.
  previous=R/'r9stacktest/bundles'/str(year);pm=read(previous/'manifest.json')
  assert sha(previous/'inference.npz')==pm['files']['inference.npz'];pins[str(previous/'manifest.json')]=sha(previous/'manifest.json');pins[str(previous/'inference.npz')]=sha(previous/'inference.npz')
  with np.load(previous/'inference.npz',allow_pickle=False) as z:
   assert set(z.files)=={'X','pid'} and np.array_equal(z['pid'],q.pid.to_numpy(dtype=str))
  query={'year':year,'rows':len(q),'pid_hash':digest(canon(q.pid.tolist())),'row_order':'SHA256(pid), then pid','full_provided_drafted_pool':True,'exact_r9stacktest_query_order':True}
  queries[str(year)]=query
  audit={'prediction_year':year,'permitted_season_end':year-1,'calendar_source_max':bm['calendar_source_max'],'source_export_max_label_season':int(facts.season_end.max()),'max_actual_label_season':int(used.season_end.max()),'partial_calendar':bm['partial_calendar'],'missing_calendar_seasons':bm['missing_calendar_seasons'],'source_fact_rows':len(facts),'all_source_facts_actual_calendar_rechecked':True,'max_source_WAR_difference':worst,'identity_exclusions':reasons,'source_eligible_label_mismatch_players':bm['label_verification']['eligible_label_mismatch_players'],'eligible_prior_answer_cohorts_in_existing_broker':bm['eligible_answer_cohorts_opened'],'answer_files_opened_by_this_exporter':False}
  calendar_proof.append(audit)
  metadata={'mode':'prefix5','prediction_year':year,'cutoff_season_end':year-1,'cap':5,'training_rows':len(arrays['pid']),'cohort_counts':counts,'prefix_length_counts':{str(i):int(np.sum(arrays['prefix_length']==i)) for i in range(1,6)},'max_actual_label_season':int(used.season_end.max()),'source_fact_rows':len(used),'source_fact_hash':digest(canon(used[FACTS].to_dict(orient='records'))),'pid_hash':digest(canon(arrays['pid'].tolist())),'array_hashes':{k:K.values_hash(v) for k,v in arrays.items() if k!='pid'},'query_pid_hash':query['pid_hash'],'array_fields':FIELDS,'source_hashes':pins,'calendar_audit':audit,'all_labels_finite_observed':True,'missing_training_labels_zero_filled':False,'query_PID_disjoint':True,'X_exported':False,'query_truth_exported':False,'contiguous_observed_prefix':True,'label_value_definition':'sum .85**(ordinal-1)*observed_WAR over contiguous prefix1..m<=5','target_transform':'clip[-40,40], then within admitted cohort ndtri(clip((average_rank-.5)/n,.01,.99))','start_cohort':2007,'population':'all provided earlier feature rows with observed contiguous prefix','labels_outside_feature_pool_excluded':int((~facts.pid.isin(pool.pid)).sum())}
  prepared.append((year,arrays,used,metadata,q))
 assert all(sha(Path(p))==v for p,v in pins.items())
 a.output.mkdir(parents=True,mode=0o700);exports=[];qd=a.output/'queries';qd.mkdir(mode=0o700)
 for year,arrays,facts,meta,q in prepared:
  d=a.output/'training/prefix5'/str(year);d.mkdir(parents=True,mode=0o700)
  np.savez_compressed(d/'training.npz',**arrays);facts.to_csv(d/'eligible_label_facts.csv',index=False)
  meta.update(training_npz_sha256=sha(d/'training.npz'),private_facts_file_sha256=sha(d/'eligible_label_facts.csv'))
  write(d/'manifest.json',meta)
  exports.append({'mode':'prefix5','year':year,'rows':len(arrays['pid']),'relative_path':str(d.relative_to(a.output)),'training_npz_sha256':sha(d/'training.npz'),'manifest_sha256':sha(d/'manifest.json'),'max_actual_label_season':meta['max_actual_label_season'],'cap':5,'pid_hash':meta['pid_hash']})
  np.savez_compressed(qd/f'{year}.npz',pid=q.pid.to_numpy(dtype=str),draft_year=q.draft_year.to_numpy(dtype=np.int64));queries[str(year)]['query_npz_sha256']=sha(qd/f'{year}.npz')
 summary={'status':'prepared_CPU_only_no_models','exports':exports,'query_metadata':queries,'calendar_audits':calendar_proof,'replay2019':replay2019,'source_hashes':pins,'builder_sha256':sha(Path(__file__)),'all_source_hashes_unchanged':True,'private_data_authority_only':True,'model_runs':0,'predictions_scored':0,'network_requests':0,'query_outcomes_or_vault_or_scoring_opened':False,'training_predictors_exported':False,'target_choice':'Fixed archived gen11 semantics supplied before this preparation; no benchmark-score selection','limitations':['Verified NBA calendar ends2022;2024/2025 training omits2023/2024 label seasons','Observed prefix admission and incomplete inherited feature population remain limitations','WAR and predictor source vintages are retrospective and not fully certified','Existing2019–2025 benchmark has been reused historically; no pristine-holdout claim']}
 write(a.output/'manifest.json',summary)
 for p in a.output.rglob('*'):p.chmod(0o700 if p.is_dir() else 0o600)
 a.output.chmod(0o700)
 print(json.dumps({'status':summary['status'],'manifest_sha256':sha(a.output/'manifest.json'),'replay2019':replay2019,'years':[{'year':e['year'],'rows':e['rows'],'query_rows':queries[str(e['year'])]['rows'],'actual_label_max':e['max_actual_label_season']} for e in exports]},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())

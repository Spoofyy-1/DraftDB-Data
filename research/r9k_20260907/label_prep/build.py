"""CPU-only R9K private label exports. No query truth, predictors, models or network."""
from pathlib import Path
import argparse,csv,hashlib,importlib.util,json,os,collections
import numpy as np
import pandas as pd
from scipy.special import ndtri
EXPECTED_H_FROZEN='22e68b8bee7902d65ed0f1c7a2d04bde3fc6521f5f872339faead15416c24d0e'
EXPECTED_BROKER='33291890f4a634be3aa38e9d99156e85b439e06451e791a5d05aaa0240a27e8b'
H_ID='s2000_gap1_drafted_h2'
POLICIES=('h_'+H_ID,'prefix_s2007_gap1_all_d085')
FACT_COLUMNS=['pid','draft_year','ordinal','season_end','war']
TARGETS=[f'y_s{i}_war' for i in range(1,6)]

def canon(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def h(raw):return hashlib.sha256(raw).hexdigest()
def sha(path):return h(Path(path).read_bytes())
def values_hash(a):
 a=np.asarray(a,dtype=np.float64);a=np.where(a==0.,0.,a);mask=np.isnan(a);a=np.where(mask,0.,a)
 return h(canon(list(a.shape))+mask.tobytes()+a.tobytes())
def load_broker(path):
 assert sha(path)==EXPECTED_BROKER
 spec=importlib.util.spec_from_file_location('r9k_pinned_broker',path);b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b);return b

def canonical_rows(frame):
 assert frame.pid.is_unique
 return frame.iloc[sorted(range(len(frame)),key=lambda i:(h(str(frame.iloc[i].pid).encode()),str(frame.iloc[i].pid)))].copy().reset_index(drop=True)
def gaussian_target(values,cohorts):
 values=np.asarray(values,dtype=float);cohorts=np.asarray(cohorts);assert len(values)==len(cohorts) and np.isfinite(values).all()
 clipped=np.clip(values,-40.,40.);target=np.empty(len(values),dtype=float)
 for cohort in np.unique(cohorts):
  mask=cohorts==cohort;n=int(mask.sum());rank=pd.Series(clipped[mask]).rank(method='average').to_numpy()
  target[mask]=ndtri(np.clip((rank-.5)/n,.01,.99))
 assert np.isfinite(target).all();return target

def verify_cutoff(broker,source,identities,raw_rows,pool,year):
 """Cutoff and fixed membership precede identity uniqueness or target access."""
 cutoff=year-1
 earlier=pool[pool.draft_year.lt(year)].copy();assert earlier.pid.is_unique
 prior_ids=identities[identities.draft_year.lt(year)&identities.pid.isin(earlier.pid)].copy()
 assert prior_ids.pid.is_unique and len(prior_ids)==len(earlier)
 years=earlier.set_index('pid').draft_year;assert prior_ids.pid.map(years).eq(prior_ids.draft_year).all()
 dated=source[source.season.le(cutoff)].copy()
 assert dated.empty or dated.season.max()<=cutoff
 # A future source identity/season can neither create nor resolve an earlier match.
 calendar,reasons=broker.eligible_calendar(dated,prior_ids,year)
 assert calendar.empty or calendar.season_end.le(cutoff).all()
 sparse=[];cells_read=0
 for pid,group in calendar.groupby('pid',sort=False):
  if pid not in raw_rows:continue
  raw=raw_rows[pid];assert int(raw['draft_year'])==int(years.at[pid])<year
  record={'pid':pid}
  for r in group.itertuples():
   key=f'y_s{r.ordinal}_war';record[key]=raw.get(key,'');cells_read+=1
  sparse.append(record)
 sparse=pd.DataFrame(sparse,columns=['pid']+TARGETS)
 accepted,verification=broker.verify_eligible_labels(calendar,sparse)
 accepted=accepted[accepted.pid.isin(earlier.pid)].sort_values(['pid','ordinal']).reset_index(drop=True)
 assert not accepted.duplicated(['pid','ordinal']).any()
 assert accepted.empty or accepted.season_end.le(cutoff).all() and accepted.draft_year.lt(year).all() and np.isfinite(accepted.war).all()
 return accepted,{'identity_exclusions':reasons,'label_verification':verification,'eligible_calendar_rows':len(calendar),'eligible_raw_ordinal_cells_accessed':cells_read,'cutoff_before_source_identity_matching':True,'fixed_membership_before_project_identity_matching':True}

def prefix_payload(pool,facts,year,start=2007,discount=.85):
 base=pool[pool.draft_year.ge(start)&pool.draft_year.lt(year)].copy()
 assert not facts.duplicated(['pid','ordinal']).any()
 permitted=facts[facts.pid.isin(base.pid)&facts.season_end.le(year-1)].copy()
 items=[];used=[]
 for pid,g in permitted.groupby('pid',sort=False):
  ordinal={int(r.ordinal):r for r in g.itertuples()};prefix=[]
  for k in range(1,6):
   r=ordinal.get(k)
   if r is None or not np.isfinite(r.war):break
   prefix.append(r)
  if not prefix:continue
  dates=[int(r.season_end) for r in prefix];assert dates==sorted(set(dates))
  year0=int(base.set_index('pid').at[pid,'draft_year']);assert all(year0<s<=year-1 for s in dates)
  value=float(sum((discount**(int(r.ordinal)-1))*float(r.war) for r in prefix))
  items.append({'pid':pid,'draft_year':year0,'label_value':value,'prefix_length':len(prefix)})
  used += [dict(pid=pid,draft_year=year0,ordinal=int(r.ordinal),season_end=int(r.season_end),war=float(r.war)) for r in prefix]
 tr=canonical_rows(pd.DataFrame(items,columns=['pid','draft_year','label_value','prefix_length']))
 if tr.empty:raise ValueError('No observed prefix rows')
 facts=pd.DataFrame(used,columns=FACT_COLUMNS).sort_values(['pid','ordinal']).reset_index(drop=True)
 arrays={'pid':tr.pid.to_numpy(dtype=str),'draft_year':tr.draft_year.to_numpy(dtype=np.int64),'label_value':tr.label_value.to_numpy(dtype=np.float64),'y':gaussian_target(tr.label_value.to_numpy(),tr.draft_year.to_numpy()),'prefix_length':tr.prefix_length.to_numpy(dtype=np.int64)}
 return arrays,facts

def validate_admission(arrays,year,query_pids):
 n=len(arrays['pid']);assert set(arrays)=={'pid','draft_year','label_value','y','prefix_length'}
 assert all(len(v)==n and np.asarray(v).dtype.kind!='O' for v in arrays.values())
 assert len(set(arrays['pid']))==n and all(arrays['draft_year']<year)
 assert np.isfinite(arrays['label_value']).all() and np.isfinite(arrays['y']).all()
 assert np.array_equal(gaussian_target(arrays['label_value'],arrays['draft_year']),arrays['y'])
 assert ((arrays['prefix_length']>=1)&(arrays['prefix_length']<=5)).all()
 assert not set(arrays['pid'])&set(query_pids)
 counts={str(int(y)):int(np.sum(arrays['draft_year']==y)) for y in np.unique(arrays['draft_year'])}
 if n<40:raise ValueError('Fewer than40 observed training rows')
 if any(v<5 for v in counts.values()):raise ValueError('Admitted cohort has fewer than5 rows')
 return counts

def h_payload(hroot,policy,year,hplan,hsource,hfrozen,pool,legacy_facts,verified):
 audit=next(r for r in policy['folds'] if r['year']==year);path=hroot/'data'/f"{policy['canonical_payload']}_{year}.npz";rel=str(path.relative_to(hroot))
 assert sha(path)==hsource['data_files'][rel]['sha256']==hfrozen['files'][rel]
 with np.load(path,allow_pickle=False) as z:
  assert set(z.files)=={'X','y','pid','draft_year','source_cumulative_WAR'}
  # X is intentionally neither loaded nor exported. Query NPZ files are unopened.
  a={k:z[k].copy() for k in ['pid','draft_year','source_cumulative_WAR','y']}
 assert a['pid'].tolist()==audit['training_pids'] and h(canon(a['pid'].tolist()))==audit['pid_hash']
 assert values_hash(a['source_cumulative_WAR'])==audit['cumulative_WAR_hash'] and values_hash(a['y'])==audit['target_hash']
 facts=legacy_facts[legacy_facts.pid.isin(a['pid'])&legacy_facts.ordinal.between(1,2)&legacy_facts.season_end.le(year-1)].sort_values(['pid','ordinal']).reset_index(drop=True)
 facts['war']=pd.to_numeric(facts.war,errors='raise')
 assert h(canon(facts[FACT_COLUMNS].to_dict(orient='records')))==audit['source_fact_hash']
 assert len(facts)==2*len(a['pid'])
 lookup=verified.set_index(['pid','ordinal']);bad=[]
 for r in facts.itertuples():
  if (r.pid,r.ordinal) not in lookup.index:bad.append({'pid':r.pid,'ordinal':int(r.ordinal),'reason':'H_fact_absent_from_cutoff_broker'});continue
  x=lookup.loc[(r.pid,r.ordinal)]
  if int(x.draft_year)!=r.draft_year or int(x.season_end)!=r.season_end or float(x.war)!=float(r.war):bad.append({'pid':r.pid,'ordinal':int(r.ordinal),'reason':'H_fact_differs_from_cutoff_broker'})
 if bad:raise HReplayMismatch(year,bad)
 total=a['pid'];replayed=pd.Series(total).map(facts.groupby('pid').war.sum()).to_numpy(dtype=float)
 assert np.array_equal(replayed,a['source_cumulative_WAR'])
 metadata=pool.set_index('pid').loc[total];assert np.array_equal(metadata.draft_year.to_numpy(),a['draft_year']) and metadata.was_drafted.eq(1).all() and metadata.draft_year.ge(2000).all()
 arrays={'pid':a['pid'],'draft_year':a['draft_year'],'label_value':a['source_cumulative_WAR'],'y':a['y'],'prefix_length':np.full(len(a['pid']),2,dtype=np.int64)}
 return arrays,facts,{'H_policy':H_ID,'H_payload':rel,'H_payload_sha256':sha(path),'H_source_fact_hash':audit['source_fact_hash'],'H_ordered_arrays_exact':True,'every_H_fact_reverified_at_its_cutoff':True}
class HReplayMismatch(Exception):
 def __init__(self,year,rows):self.year=year;self.rows=rows;super().__init__(f'{len(rows)} H facts failed cutoff-broker replay in{year}; frozen H unchanged')

def main(args):
 hroot=args.hroot;project=args.project;output=args.output
 assert not output.exists(),'Use a new private output root; never overwrite frozen exports'
 hfrozen_raw=(hroot/'frozen.json').read_bytes();assert h(hfrozen_raw)==EXPECTED_H_FROZEN;hfrozen=json.loads(hfrozen_raw)
 for name in ['plan.json','source_manifest.json']:assert sha(hroot/name)==hfrozen['files'][name]
 hplan=json.loads((hroot/'plan.json').read_text());hs=json.loads((hroot/'source_manifest.json').read_text());policy=next(r for r in hplan['policies'] if r['id']==H_ID);assert policy['valid']
 base=project/'r9g/d_reference/b_reference/a_reference/x_reference/base/data';feature=base/'features.csv';label=base/'labels.csv'
 for p in [feature,label]:assert sha(p)==hs['reference_files'][str(p.relative_to(project/'r9g'))]
 pool=pd.read_csv(feature,usecols=['pid','draft_year','was_drafted']);assert pool.pid.is_unique and len(pool)==1428 and pool.draft_year.between(2000,2018).all()
 legacy=pd.read_csv(label,usecols=FACT_COLUMNS,dtype={'war':str});assert legacy.season_end.le(2018).all()
 broker=load_broker(args.broker)
 source=pd.read_csv(args.source,usecols=['player_name','player_id','season','war_total'],dtype={'player_name':str,'player_id':str,'season':np.int64,'war_total':str})
 identities=pd.read_csv(args.identity,usecols=['pid','draft_year','player_name']);raw={}
 with args.rawtrain.open() as f:
  for r in csv.DictReader(f):
   year=int(r['draft_year']);assert 2000<=year<=2018
   if r['pid'] in set(pool.pid):
    assert r['pid'] not in raw;raw[r['pid']]={k:r.get(k,'') for k in ['pid','draft_year']+TARGETS}
 assert len(raw)==1428
 source_paths=[args.source,args.identity,args.rawtrain,args.broker,feature,label,hroot/'frozen.json',hroot/'plan.json',hroot/'source_manifest.json']
 pins={str(p):sha(p) for p in source_paths};prepared=[];brokers={}
 for year in [2012,2013,2014]:
  verified,ba=verify_cutoff(broker,source,identities,raw,pool,year);brokers[str(year)]=ba
  control,controlfacts,proof=h_payload(hroot,policy,year,hplan,hs,hfrozen,pool,legacy,verified)
  prefix,prefixfacts=prefix_payload(pool,verified,year)
  for name,arrays,facts,extra in [(POLICIES[0],control,controlfacts,proof),(POLICIES[1],prefix,prefixfacts,{'discount':.85,'contiguous_observed_prefix':True,'maximum_prefix_length':5,'unknown_or_gap_stops_prefix':True})]:
   cohorts=validate_admission(arrays,year,hplan['queries'][str(year)]['query_pids'])
   metadata={'policy':name,'prediction_year':year,'cutoff_season_end':year-1,'training_rows':len(arrays['pid']),'cohort_counts':cohorts,'max_actual_label_season':int(facts.season_end.max()),'all_labels_finite_observed':True,'missing_training_labels_zero_filled':False,'query_PID_disjoint':True,'query_pid_hash':hplan['queries'][str(year)]['pid_hash'],'source_fact_hash':h(canon(facts[FACT_COLUMNS].to_dict(orient='records'))),'source_fact_rows':len(facts),'pid_hash':h(canon(arrays['pid'].tolist())),'label_value_hash':values_hash(arrays['label_value']),'y_hash':values_hash(arrays['y']),'draft_year_hash':values_hash(arrays['draft_year']),'prefix_length_hash':values_hash(arrays['prefix_length']),'array_fields':list(arrays),'prefix_length_counts':{str(i):int(np.sum(arrays['prefix_length']==i)) for i in range(1,6)},'target_transform':'clip label_value to[-40,40]; Gaussian rank within admitted cohort only: ndtri(clip((average_rank-.5)/n,.01,.99))','label_value_definition':'unweighted sum of observed ordinals1,2' if name==POLICIES[0] else 'sum .85**(ordinal-1)*observed_WAR over contiguous prefix1..m<=5','source_hashes':pins,'broker_audit':ba,'query_truth_exported':False,'X_exported':False,'source_population_warning':'Original fixed1428 retrospectively selected and incomplete population; observed-label admission can select survivors. Diagnostic only.',**extra}
   prepared.append((name,year,arrays,facts,metadata))
 assert all(sha(Path(p))==v for p,v in pins.items())
 output.mkdir(parents=True,mode=0o700);summaries=[]
 for name,year,arrays,facts,m in prepared:
  out=output/name/str(year);out.mkdir(parents=True,mode=0o700)
  np.savez_compressed(out/'training.npz',**arrays)
  # Facts remain private to the data authority; never copy this CSV into workers.
  facts[FACT_COLUMNS].to_csv(out/'eligible_label_facts.csv',index=False)
  m['training_npz_sha256']=sha(out/'training.npz');m['private_facts_file_sha256']=sha(out/'eligible_label_facts.csv')
  (out/'manifest.json').write_text(json.dumps(m,indent=2,allow_nan=False)+'\n')
  summaries.append({'policy':name,'year':year,'rows':len(arrays['pid']),'prefix_length_counts':m['prefix_length_counts'],'source_fact_rows':len(facts),'path':str(out),'training_npz_sha256':m['training_npz_sha256'],'manifest_sha256':sha(out/'manifest.json')})
 summary={'status':'prepared_no_models','all_H_controls_exact_and_broker_reverified':True,'exports':summaries,'source_hashes':pins,'builder_sha256':sha(Path(__file__)),'private_data_authority_only':True,'network_requests':0,'model_runs':0,'query_truth_exported':False,'X_exported':False,'all_source_hashes_unchanged':True}
 (output/'manifest.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
 for p in output.rglob('*'):p.chmod(0o700 if p.is_dir() else 0o600)
 output.chmod(0o700);print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':
 ap=argparse.ArgumentParser()
 for name in ['project','hroot','output','broker','source','identity','rawtrain']:ap.add_argument('--'+name,type=Path,required=True)
 args=ap.parse_args()
 try:main(args)
 except HReplayMismatch as e:
  report=Path(__file__).parent/'H_REPLAY_FAILURE_PRIVATE.json';report.write_text(json.dumps({'year':e.year,'mismatches':e.rows,'frozen_H_changed':False,'exports_created':False},indent=2)+'\n');report.chmod(0o600);raise

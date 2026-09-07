"""Assemble source-backed174 and exactH44 inputs; no outcomes, models, or network."""
from pathlib import Path
import csv,datetime as dt,hashlib,json,math
from zoneinfo import ZoneInfo
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parent;W=ROOT.parent;PINS={}
META=['pid','draft_year','was_drafted']
def h(b):return hashlib.sha256(b).hexdigest()
def pin(p,expected=None):
 p=Path(p);v=h(p.read_bytes());assert expected is None or v==expected,str(p);PINS[str(p)]=v;return p

def js(p):return json.loads(pin(p).read_text())
def sha_record(x):return x if isinstance(x,str) else x['sha256']
def certified(package,name,allow='PUBLIC_ALLOWLIST.json'):
 m=js(W/package/allow)
 if package=='verified_combine':
  assert name in m['copy_only_these_files']
  expected=js(W/package/'data/manifest.json')['output_files']['train_inputs.csv'] if name=='data/train_inputs.csv' else None
  return pin(W/package/name,expected)
 return pin(W/package/name,sha_record(m['files'][name]))
def frame(p,columns,roundtrip=True):
 d=pd.read_csv(pin(p),usecols=columns,float_precision='round_trip' if roundtrip else None);d=d[columns];assert d.pid.is_unique and not d[['pid','draft_year']].isna().any().any();assert d.draft_year.between(2000,2018).all();return d

def records(p):return list(csv.DictReader(pin(p).read_text().splitlines()))
def values_hash(a):
 a=np.asarray(a,dtype=np.float64);a=np.where(a==0.,0.,a);m=np.isnan(a);a=np.where(m,0.,a);return h(json.dumps(list(a.shape),sort_keys=True,separators=(',',':')).encode()+m.tobytes()+a.tobytes())
def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False,default=lambda v:v.item())+'\n')
def merge(base,source,cols):
 assert source.pid.is_unique and not any(c in base for c in cols)
 common=source[source.pid.isin(base.pid)][['pid','draft_year']].merge(base[['pid','draft_year']],on='pid',suffixes=('_source','_base'),validate='one_to_one')
 assert (common.draft_year_source==common.draft_year_base).all(), 'Conflicting cohort for existingPID'
 x=base.merge(source[['pid','draft_year']+cols],on=['pid','draft_year'],how='left',sort=False,validate='one_to_one');assert x[META].equals(base[META]);return x

def validate_capture(s):
 assert s['feature_eligible'] and s['status']=='verified_predraft_mock';d=dt.date.fromisoformat(s['draft_date']);assert d.year==s['draft_year']
 c=dt.datetime.combine(d,dt.time(),ZoneInfo('America/New_York')).astimezone(dt.timezone.utc)
 assert dt.datetime.fromisoformat(s['cutoff_utc'])==c and dt.datetime.fromisoformat(s['source_available_by_utc'])<c
 assert dt.date.fromisoformat(s['source_last_updated_date'])<d

def bio_source_id(s):return s.get('source_id',f"{s['publisher']}_{s['draft_year']}")
def validate_game_row(p,group):
 y=p['draft_year'];season=p['source_season'];assert season<=y
 if group=='game':
  assert p['game_join_reason'] is None;a,b=p['player_game_min_date'],p['player_game_max_date']
 else:
  assert p['team_join_reason'] is None and p['team_cached_games']>=20 and 0<=y-season<=1;a,b=p['team_game_min_date'],p['team_game_max_date']
 assert f'{season-1}-07-01'<=a<=b<=f'{season}-05-31' and b<p['registered_draft_date']
 assert p['registered_draft_date'].startswith(str(y)+'-')

def main(source_only=False):
 hp=js(W/'r9h/plan.json');hc=hp['columns'];physical=hp['physical_source_fields'];assert len(hc)==44
 frozen=js(W/'r8w/data/manifest.json')['files']
 def old(name,columns):return frame(pin(W/'r8w/data'/name,frozen[name]),columns,False)
 base=old('features.csv',META+physical[:38]);assert len(base)==1428 and base.was_drafted.isin([0,1]).all()
 fifty_dict=js(pin(W/'r8w/data/fifty_dictionary.json',frozen['fifty_dictionary.json']))
 fcols=[x['name'] for x in fifty_dict] if isinstance(fifty_dict,list) else list(fifty_dict)
 assert len(fcols)==50
 f=old('fifty_features.csv',['pid','draft_year']+fcols)
 c=old('consensus_features.csv',['pid','draft_year']+physical[38:42])
 input_manifest=js(W/'r9test/bundle_manifests/2019.json')
 authoritative=frame(pin(ROOT/'base_H44_physical.csv',sha_record(input_manifest['files']['train_features.csv'])),META+physical,True)
 assert len(authoritative)==1428 and authoritative[META].equals(base[META])
 panel44=authoritative.rename(columns=dict(zip(physical,hc)))[META+hc]
 assert values_hash(authoritative[physical].to_numpy(float))==input_manifest['old_H_matrix_hash']
 idx=panel44.set_index('pid');replays=[]
 if not source_only:
  for y,q in hp['queries'].items():
   actual=values_hash(idx.loc[q['query_pids'],hc].to_numpy(float));assert actual==q['matrix_hash'],('Hquery',y,actual,q['matrix_hash']);replays.append({'kind':'query','year':int(y),'matrix_hash':actual})
  for p in hp['canonical_payloads']:
   for a in p['folds']:
    actual=values_hash(idx.loc[a['training_pids'],hc].to_numpy(float));assert actual==a['matrix_hash'],('Htraining',p['id'],a['year'],actual,a['matrix_hash']);replays.append({'kind':'training','id':p['id'],'year':a['year'],'matrix_hash':actual})
 print(json.dumps({'H44_exact_feature_replays':len(replays),'rows':len(base)}),flush=True)
 # RemainingF50 must come from the same immutable original parser/source asH's selectedtwo.
 fm=js(pin(W/'r8w/data/fifty_metadata.json',frozen['fifty_metadata.json']));traces=js(pin(W/'r8w/data/fifty_lineage.json',frozen['fifty_lineage.json']))
 assert 45 not in [int(k) for k in fm['source_fields']]
 assert all(int(p.split('_')[1].split('.')[0])<=2018 for p in fm['source_hashes'])
 ts={t['pid']:t for t in traces};assert len(ts)==len(traces)
 for r in f[['pid','draft_year']].itertuples(index=False):
  if not f.loc[f.pid==r.pid,fcols].notna().any(axis=None):continue
  t=ts[r.pid];assert t['draft_year']==r.draft_year and 0<=r.draft_year-t['focal']['season']<=1
  assert all(v['season']<=r.draft_year and v['source']in fm['source_hashes'] for v in t['history']+t['team'])
  assert all(v['tpid']==t['focal']['tpid'] for v in t['history']) and not t['team_has_duplicate_tpid']
  assert t['history'][-1]==t['focal'] and t['history']==sorted(t['history'],key=lambda v:v['season'])
  assert all(v['season']==t['focal']['season'] and v['team']==t['focal']['team'] and v['source']==t['focal']['source'] for v in t['team'])
  assert len({v['season'] for v in t['history']})==len(t['history'])
 # Official same-cohort combine; hashes and provenance already certify parsed measurements/drill cells.
 cm=js(certified('verified_combine','data/manifest.json'));cc=cm['features'];cf=frame(certified('verified_combine','data/train_inputs.csv'),['pid','draft_year']+cc)
 cp=records(certified('verified_combine','data/row_provenance.csv'));cpm={(r['pid'],int(r['draft_year'])):r for r in cp if int(r['draft_year'])<=2018};cs={r['filename']:r for r in cm['source_files'] if r['source_year']<=2018}
 for r in cf.itertuples(index=False):
  if not any(pd.notna(getattr(r,k)) for k in cc):continue
  p=cpm[(r.pid,r.draft_year)];s=cs[p['source_filename']];assert int(p['source_year'])==r.draft_year==s['source_year'] and s['all_row_seasons_verified'] and 0<=int(p['source_row'])<s['rows']
  assert s['parameters']['SeasonYear']==f'{r.draft_year}-{str(r.draft_year+1)[-2:]}' and p['match_method']in ['unique_nba_id','unique_exact_same_cohort_name']
 # Bios use disjoint historical packages, fixed selected source row; no publisher coalescing.
 bm=js(certified('verified_mock_bio','manifest.json'));bc=bm['features'];bf0=frame(certified('verified_mock_bio','features_eligible.csv'),['pid','draft_year']+bc)
 bf1=frame(certified('verified_mock_bio_extension','features_training_2015_2018.csv'),['pid','draft_year']+bc);assert bf0.draft_year.max()<=2014 and bf1.draft_year.min()>=2015
 bf=pd.concat([bf0,bf1],ignore_index=True);assert bf.pid.is_unique
 ss0=js(certified('verified_consensus','validated_sources.json','public_manifest.json'));ss1=js(certified('verified_consensus_extension','validated_sources.json','public_manifest.json'))
 ss={bio_source_id(s):s for s in ss0+ss1 if s['draft_year']<=2018}
 bp0=records(certified('verified_mock_bio','row_provenance.csv'));bp1=records(certified('verified_mock_bio_extension','row_provenance.csv'));sel=records(certified('verified_mock_bio_extension','selected_sources.csv'));selected={r['pid']:r for r in sel if int(r['draft_year'])<=2018}
 bp={(r['pid'],r['source_id']):r for r in bp0+bp1 if int(r['draft_year'])<=2018}
 for r in bf.itertuples(index=False):
  sid=selected[r.pid]['source_id'] if r.draft_year>=2015 else next(p['source_id'] for p in bp0 if p['pid']==r.pid)
  p=bp[(r.pid,sid)];s=ss[sid];validate_capture(s);assert int(p['draft_year'])==r.draft_year==s['draft_year']
  assert p['capture_utc']==s['source_available_by_utc'] and p['draft_date']==s['draft_date'] and p['table_sha256']==s['table_sha256'] and p['html_sha256']==s['html_sha256']
 # Group-validity/cutoff-gated35candidate sidecar, not raw-game projection.
 gm=js(certified('college_player_games_v1','schema_manifest.json'));gc=gm['candidate_numeric_fields'];tc=list(js(certified('team_context_v1','feature_dictionary.json')));gf=frame(certified('college_context_join_v1','candidate_inputs.csv'),['pid','draft_year']+gc+tc)
 gp=js(W/'college_context_join_v1/join_provenance.json');gpm={(r['pid'],r['draft_year']):r for r in gp};assert len(gpm)==len(gp)
 source_pins=js(certified('college_context_join_v1','input_pins.json'))
 for name in ['college_player_games_v1/PUBLIC_ALLOWLIST.json','college_player_games_v1/source_manifest.json','team_context_v1/PUBLIC_ALLOWLIST.json','team_context_v1/team_context_train_candidates.csv','team_context_v1/provenance.csv','fifty_audit/source_row_lineage.json']:
  pin(W/name,source_pins[name])
 for r in gf.itertuples(index=False):
  p=gpm[(r.pid,r.draft_year)]
  for group,cols in [('game',gc),('team',tc)]:
   observed=[pd.notna(getattr(r,k)) for k in cols]
   assert all(observed) or not any(observed)
   if any(observed):validate_game_row(p,group)
   else:assert p[group+'_join_reason'] is not None
 if source_only:
  print(json.dumps({'source_guards_passed':True,'H44_replay_not_checked_in_source_only_mode':True,'exports_written':False}));return
 adds=sorted(set(fcols)-set(physical[42:]))+cc+bc+gc+tc;assert len(adds)==130 and len(set(adds))==130 and not set(adds)&set(hc)
 result=panel44.copy();groups={}
 for name,src,cols in [('F50',f,sorted(set(fcols)-set(physical[42:]))),('combine',cf,cc),('dated_bio',bf,bc),('player_game',gf,gc),('team_context',gf,tc)]:
  result=merge(result,src,cols);groups[name]={'columns':cols,'table_rows':len(src),'covered_base_rows':int(result[cols].notna().any(axis=1).sum()),'outside_base_source_rows':int((~src.pid.isin(base.pid)).sum()),'covered_by_cohort':{str(int(y)):int(d[cols].notna().any(axis=1).sum()) for y,d in result.groupby('draft_year')},'observed_by_column':{k:int(result[k].notna().sum()) for k in cols}}
 ac=sorted(adds);pc=hc+ac;result=result[META+pc];assert len(pc)==174 and result[META+hc].equals(panel44)
 assert not np.isinf(result[pc].to_numpy(float)).any()
 for file,data,cols in [('pairedpanel44.csv',panel44,hc),('panel174.csv',result,pc)]:
  data.to_csv(ROOT/file,index=False,float_format='%.17g');reload=pd.read_csv(ROOT/file,float_precision='round_trip');assert reload[META].equals(data[META]);assert values_hash(reload[cols].to_numpy(float))==values_hash(data[cols].to_numpy(float))
 manifest={'status':'assembled_diagnostic_source_panels','model_eligible':False,'rows':1428,'metadata_columns':META,'columns44':hc,'columns174':pc,'physical_source_mapping44':dict(zip(hc,physical)),'added_columns':ac,'source_sha256':PINS,'outputs':{f:{'sha256':h((ROOT/f).read_bytes()),'matrix_hash':values_hash(d[cols].to_numpy(float)),'columns':len(cols)} for f,d,cols in [('pairedpanel44.csv',panel44,hc),('panel174.csv',result,pc)]},'pid_order_sha256':h(json.dumps(base.pid.tolist(),separators=(',',':')).encode()),'H_input_only_matrix_replays':replays,'family_coverage':groups,'H44_shared_exact':True,'future_data_or_outcomes_used':False,'forbidden_removed_columns':['ctx_base_fta','ctx_base_ftm','ctx_base_mid_made'],'train_only_schema_policy':'Full174 names prespecified; actual per-fold selection/normalization uses permitted training rows only. Parent/model runner owns selection and labels.','limitations':['Original1428population maintained; historically complete draft universe unproved.','Officialcombine/sourceyear and archivebio dates checked; existing source vintage/identity limitations retained.','College annual/game/team reconstructed retrospectively. Date/validity gates hold to frozen source records, while publication revisions/schedule completeness/DNP definitions remain uncertified.','H44 exact values are frozen, including original consensus coverage; later available source values do not fill its missing cells.','174 includes derived/correlated values; no predictive benefit or55percent claim is inferred from feature count.','No model, labelNPZ, outcome, actual-pick or heldout-score source was read by this builder.']}
 dump(ROOT/'panel_manifest.json',manifest);print(json.dumps({'rows':1428,'columns':174,'H_replays':len(replays),'family_covered':{k:v['covered_base_rows'] for k,v in groups.items()}}))
if __name__=='__main__':
 import sys
 main(source_only='--sources-only' in sys.argv)

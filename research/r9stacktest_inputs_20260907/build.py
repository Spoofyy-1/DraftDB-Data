"""Input-only extension of frozen M/N panels. No NBA labels, test scores, or models."""
from pathlib import Path
import ast,collections,csv,datetime as dt,gzip,hashlib,io,json,math,re,os,shutil
import numpy as np,pandas as pd
R=Path(__file__).resolve().parent;H=R.parent;S=R/'source';OUT=R/'package'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def js(p):return json.loads(Path(p).read_text())
def dump(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def ah(a):
 a=np.asarray(a,dtype=np.float64);a=np.where(a==0,0.,a);m=np.isnan(a)
 return hashlib.sha256(json.dumps(list(a.shape),separators=(',',':')).encode()+m.tobytes()+np.where(m,0.,a).tobytes()).hexdigest()
def decoded(p):
 b=p.read_bytes();return gzip.decompress(b)if b[:2]==b'\x1f\x8b'else b
def projected_module(name,functions,constants,extend):
 p=R/'source_code'/name;tree=ast.parse(p.read_text());nodes=[]
 for n in tree.body:
  if isinstance(n,ast.FunctionDef)and n.name in functions:nodes.append(n)
  elif isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id in constants for t in n.targets):nodes.append(n)
 assert {n.name for n in nodes if isinstance(n,ast.FunctionDef)}==set(functions)
 class Extension(ast.NodeTransformer):
  def visit_Constant(self,n):
   if extend and n.value==2018:return ast.copy_location(ast.Constant(2025),n)
   return n
 module=ast.fix_missing_locations(Extension().visit(ast.Module(body=nodes,type_ignores=[])))
 ns=dict(globals());exec(compile(module,str(p),'exec'),ns)
 return ns
P=projected_module('player_original.py',['hashed','clean','integer','key_for','parse','parse_annual_records','assess_group','apply_annual_issues','group_records'],['COUNTS','ANNUAL','SIX'],True)
T=projected_module('team_original.py',['parse_game'],['STAT'],True)
F=projected_module('team_features_original.py',['divide','features'],[],False)
GAME=['cgd_observed_gp']+['cgd_'+x+'_pg'for x in P['COUNTS'].values()]
def players(y):
 annual,issues=P['parse_annual_records'](csv.reader(io.StringIO(gzip.decompress((S/f'torvik_{y}.csv.gz').read_bytes()).decode())),y)
 bad=collections.defaultdict(set);wide=P['apply_annual_issues'](annual,issues,bad);parsed=[];rawgroups=collections.Counter();invalid=collections.Counter();raw=json.loads(decoded(R/'raw'/f'player_{y}.bin'))
 for row in raw:
  key=None
  try:key=P['key_for'](row,y);rawgroups[key]+=1
  except(AssertionError,ValueError,TypeError,IndexError):pass
  try:k,g=P['parse'](row,y);parsed.append((k,g))
  except(AssertionError,ValueError,TypeError,IndexError)as e:
   invalid[str(e)]+=1
   if key:bad[key].add('invalid_game_record')
   else:wide=True
 records,bad,duplicates=P['group_records'](parsed,bad);out={}
 for key in set(rawgroups)|set(annual)|set(records):
  if wide:bad[key].add('unassignable_invalid_source_or_annual_row_in_season')
  gs=records.get(key,[]);ar=annual.get(key,[]);gp,tot,reasons=P['assess_group'](key,gs,ar,bad[key])
  out[key]={'values':{GAME[0]:float(gp),**{'cgd_'+n+'_pg':tot[n]/gp for n in P['COUNTS'].values()}}if not reasons else{},'reasons':reasons,'annual_row':ar[0]['source_row_zero_based']if len(ar)==1 else None,'min_date':min([g['date']for g in gs],default=None),'max_date':max([g['date']for g in gs],default=None)}
 return out,{'rows':len(raw),'invalid_rows':sum(invalid.values()),'invalid_reasons':dict(invalid),'duplicates':duplicates,'unassignable_blocks_season':wide,'groups':len(out),'valid_groups':sum(not x['reasons']for x in out.values())}
def teams(y):
 raw=json.loads(decoded(R/'raw'/f'team_{y}.bin'));ids=collections.Counter(str(r[0])for r in raw);counts=collections.Counter(t for r in raw for t in r[3:5]);bad=collections.Counter();groups={};reasons=collections.Counter()
 for row in raw:
  try:
   assert ids[str(row[0])]==1,'duplicate_source_game_id';g=T['parse_game'](row,y)
  except(AssertionError,ValueError,TypeError,IndexError)as e:
   reasons[str(e)]+=1
   for t in row[3:5]:bad[t]+=1
   continue
  for side in[0,1]:
   team=g['teams'][side];a=groups.setdefault(team,{'validated_games':0,**{'team_'+k:0 for k in T['STAT']},**{'opponent_'+k:0 for k in T['STAT']},'min_date':g['date'],'max_date':g['date']})
   a['validated_games']+=1;a['min_date']=min(a['min_date'],g['date']);a['max_date']=max(a['max_date'],g['date'])
   for k in T['STAT']:a['team_'+k]+=g['sides'][side][k];a['opponent_'+k]+=g['sides'][1-side][k]
 out={}
 for team,a in groups.items():
  okay=bad[team]==0 and a['validated_games']==counts[team]and a['validated_games']>=20
  v=F['features'](a)if okay else{}
  if any(x is None or not math.isfinite(x)for x in v.values()):okay=False;v={}
  out[team]={'values':v,'okay':okay,'min_date':a['min_date'],'max_date':a['max_date'],'games':a['validated_games'],'invalid_games':bad[team]}
 return out,{'rows':len(raw),'invalid_rows':sum(reasons.values()),'invalid_reasons':dict(reasons),'groups':len(out),'valid_groups':sum(x['okay']for x in out.values())}
def game_team(trace,pg,tg,cutoff):
 y=trace['draft_year'];f=trace['focal'];season=f['season'];assert 0<=y-season<=1 and not trace['team_has_duplicate_tpid']
 p=pg.get((season,str(f['tpid']),f['team']));t=tg.get(f['team']);v={};why={};proof={}
 if not p or p['reasons']:why['game']='missing_or_quarantined_source_group'
 elif p['annual_row']!=f['source_row']:raise AssertionError('annual_row_mismatch')
 elif not p['max_date']<cutoff:why['game']='not_before_draft'
 else:v.update(p['values']);why['game']=None;proof['game_dates']=[p['min_date'],p['max_date']]
 if not t or not t['okay']:why['team']='missing_or_quarantined_team_season'
 elif not t['max_date']<cutoff:why['team']='not_before_draft'
 else:v.update(t['values']);why['team']=None;proof['team_dates']=[t['min_date'],t['max_date']];proof['team_games']=t['games']
 return v,why,proof
def write(name,d,cols):
 path=OUT/name;d.to_csv(path,index=False,float_format='%.17g');q=pd.read_csv(path,float_precision='round_trip')
 assert q[['pid','draft_year']].equals(d[['pid','draft_year']])
 if cols:assert np.array_equal(q[cols].to_numpy(float),d[cols].to_numpy(float),equal_nan=True)
 return {'sha256':sha(path),'rows':len(d),'columns':list(d.columns),'matrix_hash':ah(d[cols].to_numpy(float))if cols else None}
def main():
 os.umask(0o077);OUT.mkdir(exist_ok=True)
 pins=js(S/'local_pins.json')
 for n,h in pins.items():assert sha(R/n)==h,n
 downloads=js(R/'source_downloads.json');assert len(downloads)==14
 for e in downloads:assert sha(R/e['path'])==e['sha256']
 pm=js(H/'r9k/panels/panel_manifest.json');assert sha(H/'r9k/panels/panel_manifest.json')=='cd95bb4aac53de85b3099af44877ed98b4de22fb9067fc21b6f61f5bac5f2588'
 path=H/'r9k/panels/panel174.csv';assert sha(path)==pm['outputs']['panel174.csv']['sha256'];protocol=js(H/'r9m/code/protocol.json')
 cols=next(x['columns']for x in protocol['panels']if x['id']=='f50_game_team');base=pm['columns44'];assert len(cols)==127 and cols[:44]==base
 fcols=[c for c in cols if c.startswith('f50_')];tcols=[c for c in cols if c.startswith('tctx_')];assert len(fcols)==48 and len(tcols)==20 and set(GAME)==set(c for c in cols if c.startswith('cgd_'))
 old=pd.read_csv(path,usecols=['pid','draft_year','was_drafted']+cols,float_precision='round_trip')[['pid','draft_year','was_drafted']+cols];idx=old.set_index('pid');assert len(old)==1428 and old.draft_year.le(2018).all()and old.pid.is_unique
 replays=[]
 for y in[2012,2013,2014]:
  for panel,width in[('base44',44),('f50_game_team',127)]:
   p=H/'r9m/inputs'/f'{panel}_y{y}';m=js(p/'manifest.json')
   for name in['training.npz','inference.npz']:
    assert sha(p/name)==m['files'][name]['sha256']
    with np.load(p/name,allow_pickle=False)as z:ids=z['pid'];x=z['X']
    assert np.array_equal(idx.loc[ids,cols[:width]].to_numpy(float),x,equal_nan=True)
    replays.append({'year':y,'panel':panel,'input':name,'rows':len(ids),'matrix_hash':ah(x),'feature_and_pid_only_read':True})
 outputs={'features_pre2019.csv':write('features_pre2019.csv',old[['pid','draft_year']+cols],cols),'metadata_pre2019.csv':write('metadata_pre2019.csv',old[['pid','draft_year','was_drafted']],[])}
 lineage=js(S/'lineage.json');traces={t['pid']:t for t in lineage};assert len(traces)==len(lineage)
 fm=js(S/'fifty_manifest.json');bm=js(S/'base_manifest.json');assert bm['columns']==base
 cuts=js(S/'draft_dates.json');source_stats={};pgs={};tgs={}
 for y in range(2018,2026):
  assert sha(S/f'torvik_{y}.csv.gz')==fm['source_hashes'][f'torvik_{y}.csv.gz']
  pgs[y],ps=players(y);tgs[y],ts=teams(y);source_stats[str(y)]={'player':ps,'team':ts}
  print(json.dumps({'source_year':y,**source_stats[str(y)]}),flush=True)
 # Exact2018replay of the extracted arithmetic and unchanged validity rules.
 ref=pd.read_csv(S/'reference_game_team.csv',float_precision='round_trip').set_index('pid');checked=0
 for pid,t in traces.items():
  if t['draft_year']!=2018 or t['focal']['season']!=2018 or pid not in ref.index:continue
  v,why,proof=game_team(t,pgs[t['focal']['season']],tgs[t['focal']['season']],'2018-06-21')
  a=np.array([v.get(c,np.nan)for c in GAME+tcols]);b=ref.loc[pid,GAME+tcols].to_numpy(float)
  assert np.array_equal(a,b,equal_nan=True),('2018_arithmetic_replay',pid,np.nanmax(np.abs(a-b)))
  checked+=1
 assert checked>50
 coverage={};provenance=[]
 for y in range(2019,2026):
  bpath=S/f'base_{y}.csv';assert sha(bpath)==bm['output_files'][f'inputs_{y}.csv']['sha256']
  b=pd.read_csv(bpath,float_precision='round_trip');assert list(b.columns)==['pid','draft_year']+base and b.pid.is_unique and b.draft_year.eq(y).all()
  f=pd.read_csv(S/f'f50_{y}.csv',usecols=['pid','draft_year']+fcols,float_precision='round_trip');assert f.pid.is_unique and f.draft_year.eq(y).all()
  f=f.set_index('pid');records=[]
  for row in b.to_dict('records'):
   pid=row['pid'];t=traces.get(pid);v={};why={'game':'no_focal_lineage','team':'no_focal_lineage'};proof={}
   if t:
    assert t['draft_year']==y and t['history'][-1]==t['focal'] and t['history']==sorted(t['history'],key=lambda x:x['season'])
    assert len({x['season']for x in t['history']})==len(t['history'])
    assert all(x['season']<=y and x['source']in fm['source_hashes']for x in t['history']+t['team'])
    assert all(x['tpid']==t['focal']['tpid']for x in t['history'])
    assert all(x['season']==t['focal']['season']and x['team']==t['focal']['team']for x in t['team'])
    s=t['focal']['season'];v,why,proof=game_team(t,pgs[s],tgs[s],cuts[str(y)])
   if pid in f.index:
    assert t is not None,'F50_value_without_lineage'
    v.update(f.loc[pid,fcols].to_dict())
   row.update({c:v.get(c,np.nan)for c in cols[44:]});records.append(row)
   provenance.append({'pid':pid,'draft_year':y,'source_season':t['focal']['season']if t else None,'cutoff':cuts[str(y)],'join_status':why,**proof})
  d=pd.DataFrame(records)[['pid','draft_year']+cols];assert not np.isinf(d[cols].to_numpy(float)).any()
  assert np.array_equal(d[base].to_numpy(float),b[base].to_numpy(float),equal_nan=True)
  meta=pd.read_csv(S/f'metadata_{y}.csv');assert meta[['pid','draft_year']].equals(d[['pid','draft_year']])and meta.was_drafted.isin([0,1]).all()
  outputs[f'features_{y}.csv']=write(f'features_{y}.csv',d,cols);outputs[f'metadata_{y}.csv']=write(f'metadata_{y}.csv',meta,[])
  coverage[str(y)]={'rows':len(d),'drafted_rows':int(meta.was_drafted.sum()),'base44':int(d[base].notna().any(axis=1).sum()),'f50':int(d[fcols].notna().any(axis=1).sum()),'game':int(d[GAME].notna().any(axis=1).sum()),'team':int(d[tcols].notna().any(axis=1).sum()),'all127_missing':int(d[cols].isna().all(axis=1).sum()),'observed_by_column':{c:int(d[c].notna().sum())for c in cols}}
 dump(OUT/'source_join_provenance.json',provenance)
 m={'status':'input_only_package_ready_for_root_review','model_eligible':False,'columns127':cols,'columns44':base,'base44_indices':list(range(44)),'physical_mapping44':pm['physical_source_mapping44'],'outputs':outputs,'source_files':{**pins,**{e['path']:e['sha256']for e in downloads},'r9k/panels/panel174.csv':sha(path)},'source_statistics':source_stats,'M_exact_feature_replays':replays,'2018_exact_game_team_replay_rows':checked,'coverage':coverage,'NBA_labels_or_scores_read':False,'draft_order_read':False,'no_fitting_or_imputation':True,'limits':['Retrospective annual and game snapshots; original publication vintage and complete schedule remain unproved.','Same frozen127definitions, source arithmetic and validity rules retained; only source-year scope extended to2025.','Original1428historicalpopulation and full providedfutureuniverses retained; population construction unverified.','Quarantined or unavailable college-source groups remainmissing with reasons; no mean or zero filling.','Actualdraft membership kept only in separate metadata and is not a predictor.','Future cohort features may enter expandingtraining only after that cohort; root calendarbroker owns observedlabels and actualseasoncutoffs.','Base44 consensus keeps prior proven capture dates and coverage; international coverage remainslimited.']}
 dump(OUT/'manifest.json',m);print(json.dumps({'status':m['status'],'manifest_sha256':sha(OUT/'manifest.json'),'replays':len(replays),'2018rows':checked,'coverage':{y:{k:v for k,v in c.items()if k!='observed_by_column'}for y,c in coverage.items()}}),flush=True)
if __name__=='__main__':main()

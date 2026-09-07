from pathlib import Path
import importlib.util,json,hashlib,ast
import numpy as np,pandas as pd
R=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('inputbuild',R/'build.py');B=importlib.util.module_from_spec(s);s.loader.exec_module(B)
m=B.js(R/'package/manifest.json');assert m['NBA_labels_or_scores_read']is False and m['draft_order_read']is False
assert len(m['columns127'])==127 and m['columns127'][:44]==m['columns44'];assert 45 not in B.P['ANNUAL'];assert '45'not in B.js(R/'source/fifty_manifest.json')['source_fields']
checks=[]
for name,e in m['outputs'].items():
 p=R/'package'/name;assert B.sha(p)==e['sha256'];d=pd.read_csv(p,float_precision='round_trip')
 assert list(d.columns)==e['columns']and len(d)==e['rows']and d.pid.is_unique
 if name.startswith('features'):
  assert list(d.columns)==['pid','draft_year']+m['columns127']
  assert B.ah(d[m['columns127']].to_numpy(float))==e['matrix_hash']
 else:assert list(d.columns)==['pid','draft_year','was_drafted']and d.was_drafted.isin([0,1]).all()
 if 'pre2019'not in name:assert d.draft_year.eq(int(name.split('_')[1].split('.')[0])).all()
 else:assert d.draft_year.le(2018).all()
 checks.append({'file':name,'rows':len(d),'sha256':e['sha256']})
for y in range(2019,2026):
 full=pd.read_csv(R/'package'/f'features_{y}.csv',float_precision='round_trip')
 base=pd.read_csv(R/'source'/f'base_{y}.csv',float_precision='round_trip')
 assert full[['pid','draft_year']].equals(base[['pid','draft_year']])
 assert np.array_equal(full[m['columns44']].to_numpy(float),base[m['columns44']].to_numpy(float),equal_nan=True)
for x in B.js(R/'package/source_join_provenance.json'):
 for name in['game_dates','team_dates']:
  if name in x:assert x[name][1]<x['cutoff']and str(x['source_season']-1)+'-07-01'<=x[name][0]<=x[name][1]<=str(x['source_season'])+'-05-31'
 if x['join_status']['team']is None:assert x['team_games']>=20
# Data-free failure fixtures prove original numerical/dateguards are active after scopeextension.
raw=json.loads(B.decoded(R/'raw/player_2019.bin'))
valid=next(x for x in raw if B.P['key_for'](x,2019)and len(x)==53)
fixtures=[]
for field,value in[(0,'20200101'),(52,2020),(23,999999),(42,6)]:
 c=list(valid);c[field]=value
 try:B.P['parse'](c,2019)
 except(AssertionError,ValueError,TypeError,IndexError):fixtures.append({'field':field,'rejected':True})
 else:raise AssertionError(('failed_fixture',field))
proof={'status':'passed','manifest_sha256':B.sha(R/'package/manifest.json'),'checked_output_files':checks,'future_base44_exact':True,'feature_only_column_allowlist':True,'annual_pick_index45_excluded':True,'future_group_dates_and_team_minimum_checked':True,'invalid_player_game_fixtures':fixtures,'same_source_2018_reference_rows':m['2018_exact_game_team_replay_rows'],'M_exact_feature_matrix_replays':len(m['M_exact_feature_replays']),'source_code_sha256':{str(p.relative_to(R)):B.sha(p)for p in[R/'build.py',R/'fetch.py',*sorted((R/'source_code').glob('*.py'))]},'support_file_sha256':{str(p.relative_to(R)):B.sha(p)for p in[R/'source/reference_game_team.csv',R/'raw/player_2018.bin',R/'raw/team_2018.bin',R/'source/torvik_2018.csv.gz',R/'source/local_pins.json']},'models_run':0,'NBA_labels_or_scores_read':False,'root_review_required_before_admission':True}
B.dump(R/'verification.json',proof);print(json.dumps({'status':'passed','output_files':len(checks),'fixtures':len(fixtures),'verification_sha256':B.sha(R/'verification.json')}))

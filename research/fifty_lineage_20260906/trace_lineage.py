"""Audit exact existing F50 joins and preserve raw row references; no feature changes."""
from pathlib import Path
import csv,gzip,hashlib,importlib.util,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('builder',ROOT/'collectors/build_fifty.py');B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
REPO=Path('/Users/kennakao/nba/datarebuild')
rows=[]
for path in sorted((REPO/'tracking_raw').glob('torvik_*.csv.gz')):
    year=int(path.name.split('_')[1].split('.')[0])
    for i,row in enumerate(csv.reader(gzip.open(path,'rt'))):
        assert len(row)==67 and int(row[31])==year
        d=dict(name=B.norm(row[0]),team=row[1],season=year,tpid=row[32],source=path.name,source_row=i)
        d['minutes']=pd.to_numeric(row[4],errors='coerce')
        d['allowed_values_hash']=hashlib.sha256(json.dumps([row[j] for j in sorted(B.FIELDS)],separators=(',',':')).encode()).hexdigest()
        rows.append(d)
raw=pd.DataFrame(rows)
duplicates=raw[raw.duplicated(['season','team','tpid'],keep=False)]
byname={k:v for k,v in raw.groupby('name')};byteam={k:v for k,v in raw.groupby(['season','team'])}
ident=pd.read_csv(REPO/'identity/tabular_names.csv',usecols=['pid','draft_year','player_name'])
existing=json.loads((ROOT/'fifty/manifest.json').read_text())
old={p['pid']:p for p in existing['provenance']};traces=[]
def refs(frame):
    return frame[['season','team','tpid','source','source_row','allowed_values_hash']].to_dict('records')
for p in ident.itertuples():
    if p.pid not in old:continue
    c=byname[B.norm(p.player_name)];c=c[c.season<=p.draft_year]
    lastyear=int(c.season.max());last=c[c.season==lastyear];assert last.tpid.nunique()==1
    last=last.sort_values('minutes').iloc[-1]
    hist=c[c.tpid==last.tpid].sort_values(['season','minutes']).drop_duplicates('season',keep='last')
    team=byteam[(lastyear,last.team)]
    assert old[p.pid]['source_season']==lastyear and old[p.pid]['history_seasons']==hist.season.astype(int).tolist()
    assert (hist.season<=p.draft_year).all() and (team.season<=p.draft_year).all()
    traces.append(dict(pid=p.pid,draft_year=int(p.draft_year),focal=refs(last.to_frame().T)[0],history=refs(hist),team=refs(team),team_has_duplicate_tpid=bool(team.tpid.duplicated().any())))
assert len(traces)==len(old)
out=ROOT/'fifty_audit'
(out/'source_row_lineage.json').write_text(json.dumps(traces,indent=2))
summary=dict(raw_rows=len(raw),same_team_player_duplicate_rows=len(duplicates),same_team_player_duplicate_groups=int(duplicates.groupby(['season','team','tpid']).ngroups),players_traced=len(traces),traced_players_with_duplicate_team_rows=sum(t['team_has_duplicate_tpid'] for t in traces),all_existing_focal_and_history_selections_reproduced=True,features_changed=False,limitation='Adds exact source row pointers; retrospective publication vintage and cohort-universe restrictions remain. Does not expose or use raw NBA pick field.')
(out/'lineage_audit.json').write_text(json.dumps(summary,indent=2))
if len(duplicates):duplicates.to_csv(out/'duplicate_source_rows.csv',index=False)
print(json.dumps(summary))

"""Compare a numeric projection of two official box scores to source arrays.

Official tables were available through the web tool. Direct HTTP returned403,
so this does not claim an archived full HTML response or its hash.
"""
from pathlib import Path
import datetime as dt, hashlib, json

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'college_oliver_reconstruction'
FIELDS=['fgm','fga','fg3m','fg3a','ftm','fta','orb','drb','trb','ast','stl','blk','tov','pf','pts']


def verify():
    checks=[]
    for reference in json.loads((ROOT/'official_boxscore_projection.json').read_text()):
        source=SOURCE/'private'/f"season{reference['season']}.bin"
        matches=[]
        for index,row in enumerate(json.loads(source.read_bytes())):
            pieces=str(row[1]).split('/')
            try:date=dt.datetime.strptime(str(row[1]),'%m/%d/%Y' if len(pieces[-1])==4 else '%m/%d/%y').date().isoformat()
            except ValueError:continue
            if date==reference['game_date'] and set(row[3:5])==set(reference['team_names']):matches.append((index,row))
        assert len(matches)==1, 'Ambiguous source game'
        index,row=matches[0]
        assert int(row[2])==reference['team_player_minutes']
        for name,expected in zip(reference['team_names'],reference['teams']):
            side=row[3:5].index(name);offset=5+15*side
            for field in FIELDS:
                assert float(row[offset+FIELDS.index(field)])==expected[field], (name,field)
        checks.append({'source_season':reference['season'],'game_date':reference['game_date'],
                       'official_url':reference['source_url'],'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                       'source_row_zero_based':index,'row_width':len(row),'basic_count_cells_exact':30,
                       'team_player_minutes_exact':True,'source_teams_exact_after_explicit_Michigan_State_abbreviation':True})
    result={'status':'Two official game totals match the parsed raw schema', 'checks':checks,
            'count_cells_compared':sum(x['basic_count_cells_exact'] for x in checks),
            'official_projection_sha256':hashlib.sha256((ROOT/'official_boxscore_projection.json').read_bytes()).hexdigest(),
            'scope':'Independent schema spot checks only; not global schedule completeness, every-game validation or original-vintage certification',
            'official_full_HTML_snapshots_obtained':False, 'direct_HTTP_status':403}
    (ROOT/'schema_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':verify()

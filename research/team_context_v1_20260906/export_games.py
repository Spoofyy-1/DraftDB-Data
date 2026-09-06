"""Persist the validated game facts without raw page text or team names."""
from pathlib import Path
import collections,csv,datetime as dt,gzip,hashlib,json

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'college_oliver_reconstruction'
FIELDS=['fgm','fga','fg3m','fg3a','ftm','fta','orb','drb','trb','ast','stl','blk','tov','pf','pts']


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    allow=json.loads((SOURCE/'PUBLIC_ALLOWLIST.json').read_text())
    for name in ['team_game_lineage.csv.gz','team_season_totals_candidate.csv','coverage.json']:
        assert sha(SOURCE/name)==allow['files'][name]['sha256']
    coverage=json.loads((SOURCE/'coverage.json').read_text())
    sources={}
    for item in coverage:
        season=item['source_season'];assert 2008<=season<=2018
        p=SOURCE/'private'/f'season{season}.bin';assert sha(p)==item['source_sha256']
        sources[season]=json.loads(p.read_bytes())
    output=[];aggregate={};seen=set()
    with gzip.open(SOURCE/'team_game_lineage.csv.gz','rt') as stream:
        for lineage in csv.DictReader(stream):
            year=int(lineage['source_season']);index=int(lineage['source_row_zero_based']);side=int(lineage['side_zero_based'])
            assert side in [0,1];raw=sources[year][index]
            tid='team_'+hashlib.sha256(raw[3+side].encode()).hexdigest()[:20]
            gid='game_'+hashlib.sha256(f'{year}:{raw[0]}'.encode()).hexdigest()[:20]
            assert tid==lineage['team_id'] and gid==lineage['game_id']
            key=(year,tid,gid);assert key not in seen;seen.add(key)
            date=dt.datetime.strptime(str(raw[1]),'%m/%d/%Y' if len(str(raw[1]).split('/')[-1])==4 else '%m/%d/%y').date()
            assert dt.date(year-1,7,1)<=date<=dt.date(year,5,31)
            row={'source_season':year,'team_id':tid,'game_id':gid,'game_date':date.isoformat(),
                 'team_player_minutes':int(raw[2]),'source_row_zero_based':index,'side_zero_based':side}
            for prefix,which in [('team_',side),('opponent_',1-side)]:
                offset=5+15*which
                for i,name in enumerate(FIELDS):row[prefix+name]=int(float(raw[offset+i]))
            output.append(row)
            a=aggregate.setdefault((year,tid),collections.Counter())
            a['validated_games']+=1
            for name,value in row.items():
                if name in ['team_player_minutes']+[p+k for p in ['team_','opponent_'] for k in FIELDS]:a[name]+=value
    with (SOURCE/'team_season_totals_candidate.csv').open() as stream:
        totals=list(csv.DictReader(stream))
    assert len(aggregate)==len(totals)
    for row in totals:
        a=aggregate[(int(row['source_season']),row['team_id'])]
        for name,value in a.items():assert value==int(row[name]), (name,value,row[name])
    p=ROOT/'validated_team_game_facts.csv.gz'
    with p.open('wb') as raw_stream:
        with gzip.GzipFile(filename='',mode='wb',fileobj=raw_stream,mtime=0) as zipped:
            import io
            with io.TextIOWrapper(zipped,encoding='utf-8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(output[0]));writer.writeheader();writer.writerows(output)
    result={'team_game_rows':len(output),'unique_games':len(output)//2,'team_seasons':len(aggregate),
            'all_aggregate_numeric_cells_reproduced_exactly':True,'source_years':[2008,2018],
            'team_names_or_player_identities_exported':False,'NBA_data_read':False,
            'sha256':sha(p),'bytes':p.stat().st_size,'status':'Validated historical numeric facts; source vintage/completeness limitations preserved'}
    (ROOT/'game_export_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()

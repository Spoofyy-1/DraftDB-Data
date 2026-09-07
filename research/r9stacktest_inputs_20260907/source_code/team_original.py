"""Team/opponent dependency pilot, with no player impact features or model joins."""
from pathlib import Path
import collections,csv,datetime as dt,hashlib,json,math,re
import pandas as pd
R=Path(__file__).resolve().parent
RAW=Path('/Users/kennakao/nba/datarebuild/tracking_raw')
STAT=['fgm','fga','fg3m','fg3a','ftm','fta','orb','drb','trb','ast','stl','blk','tov','pf','pts']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def team_id(name):return 'team_'+hashlib.sha256(name.encode()).hexdigest()[:20]
def parse_game(row, year):
    assert 2008<=year<=2018 and len(row) in [39,40], 'year_or_width'
    assert all(isinstance(row[i],str) and row[i].strip() for i in [3,4]) and row[3]!=row[4], 'team_identity'
    assert re.fullmatch(r'\d{1,2}/\d{1,2}/(?:\d{2}|\d{4})',str(row[1])), 'date_format'
    parts=str(row[1]).split('/'); day=dt.datetime.strptime(row[1],'%m/%d/%Y' if len(parts[-1])==4 else '%m/%d/%y').date()
    assert dt.date(year-1,7,1)<=day<=dt.date(year,5,31), 'outside_source_season'
    minutes=float(row[2]);assert minutes>=200 and minutes<=400 and minutes%25==0, 'unverified_minutes'
    sides=[]
    for start in [5,20]:
        vals=[float(v) for v in row[start:start+15]]
        assert all(math.isfinite(v) and v>=0 and v.is_integer() for v in vals),'noninteger_box_count'
        s=dict(zip(STAT,map(int,vals)))
        assert s['fgm']<=s['fga'] and s['fg3m']<=s['fgm'] and s['fg3m']<=s['fg3a']<=s['fga'] and s['ftm']<=s['fta'],'made_attempt_bounds'
        assert s['orb']+s['drb']==s['trb'],'rebound_identity'
        assert 2*s['fgm']+s['fg3m']+s['ftm']==s['pts'],'points_identity'
        assert s['ast']<=s['fgm'],'assists_exceed_makes'
        sides.append(s)
    for own,opp in [(sides[0],sides[1]),(sides[1],sides[0])]:
        assert own['stl']<=opp['tov'] and own['blk']<=opp['fga']-opp['fgm'],'cross_team_count_bounds'
    return {'game_id':str(row[0]),'date':str(day),'year':year,'team_minutes':int(minutes),'teams':[row[3],row[4]],'sides':sides}

def main():
    coverage=[];quarantine=[];source_games=[];aggregate={}; identities={}; provenance=[];schema_crosscheck=[]
    ledger={r['key']:r for r in json.loads((R/'network_ledger.json').read_text())}
    all_player_inventory=[];local_sources=[]
    for year in range(2008,2019):
        file=R/'private'/f'season{year}.bin';assert sha(file)==ledger[f'season{year}']['sha256'];raw=json.loads(file.read_bytes())
        source_ids=collections.Counter(str(r[0]) for r in raw)
        raw_teams=collections.Counter(t for r in raw for t in r[3:5]);rejected_teams=collections.Counter();valid=[];reasons=collections.Counter()
        for i,row in enumerate(raw):
            try:
                assert source_ids[str(row[0])]==1,'duplicate_source_game_id'
                game=parse_game(row,year)
                valid.append((i,game))
            except (AssertionError,ValueError,TypeError,IndexError) as e:
                reason=str(e) or type(e).__name__;reasons[reason]+=1
                for team in row[3:5]:rejected_teams[team]+=1
                quarantine.append({'source_season':year,'source_row_zero_based':i,'source_file_sha256':sha(file),'reason':reason})
        for i,game in valid:
            gid='game_'+hashlib.sha256(f"{year}:{game['game_id']}".encode()).hexdigest()[:20]
            for side in [0,1]:
                team,opponent=game['teams'][side],game['teams'][1-side];tid=team_id(team);identities[tid]=team
                record={'source_season':year,'team_id':tid,'game_id':gid,'game_date':game['date'],'team_player_minutes':game['team_minutes'],**{'team_'+k:v for k,v in game['sides'][side].items()},**{'opponent_'+k:v for k,v in game['sides'][1-side].items()}}
                source_games.append(record)
                key=(year,tid)
                if key not in aggregate:aggregate[key]={'source_season':year,'team_id':tid,'validated_games':0,'raw_source_games':raw_teams[team],'rejected_source_games':rejected_teams[team], 'team_player_minutes':0,**{'team_'+k:0 for k in STAT},**{'opponent_'+k:0 for k in STAT},'min_date':game['date'],'max_date':game['date'],'publication_vintage_verified':False,'model_eligible':False}
                a=aggregate[key];a['validated_games']+=1;a['team_player_minutes']+=game['team_minutes'];a['min_date']=min(a['min_date'],game['date']);a['max_date']=max(a['max_date'],game['date'])
                for k in STAT:a['team_'+k]+=record['team_'+k];a['opponent_'+k]+=record['opponent_'+k]
                provenance.append({'source_season':year,'team_id':tid,'game_id':gid,'source_row_zero_based':i,'side_zero_based':side,'source_sha256':ledger[f'season{year}']['sha256']})
        coverage.append({'source_season':year,'source_game_rows':len(raw),'validated_game_rows':len(valid),'rejected_game_rows':len(raw)-len(valid),'source_team_names':len(raw_teams),'teams_all_cached_games_pass':sum(rejected_teams[t]==0 for t in raw_teams),'min_valid_date':min(g['date'] for _,g in valid),'max_valid_date':max(g['date'] for _,g in valid),'reasons':dict(reasons),'source_sha256':sha(file),'source_url':ledger[f'season{year}']['url'],'retrieved_at_utc':ledger[f'season{year}']['retrieved_at_utc'],'original_publication_date':None})
        # Read only explicit historical basic fields. Never materialize index45.
        p=RAW/f'torvik_{year}.csv.gz';cols=[1,3,13,14,16,17,19,20,31,54,57,58,60,61,62,63]
        player=pd.read_csv(p,header=None,usecols=cols,dtype=str);assert player[31].astype(int).eq(year).all()
        gp=pd.to_numeric(player[3]);total_points=2*pd.to_numeric(player[16])+3*pd.to_numeric(player[19])+pd.to_numeric(player[13]);reported_mean=pd.to_numeric(player[63]);tolerance=gp*.00005+1e-8
        inconsistent=(total_points-gp*reported_mean).abs()>tolerance
        integer_inconsistent={str(c):int(((pd.to_numeric(player[c])*gp-(pd.to_numeric(player[c])*gp).round()).abs()>tolerance).sum()) for c in [57,58,60,61,62,63]}
        all_player_inventory.append({'source_season':year,'player_rows':len(player),'basic_points_vs_per_game_times_gp_inconsistent':int(inconsistent.sum()),'four_decimal_fields_fail_unique_integer_at_listed_gp':integer_inconsistent,'exact_tov_total_column_present':False,'exact_pf_total_column_present':False,'exact_mp_total_column_present':False,'player_impact_features_admitted':0})
        local_sources.append({'source':p.name,'sha256':sha(p),'read_indices':cols,'raw_pick_index45_read':False})
    # Independent author endpoint repeats a labeled team's raw game array.
    raw2012=json.loads((R/'private/season2012.bin').read_bytes());byid={str(row[0]):row for row in raw2012}
    for game in json.loads((R/'private/kentucky2012.bin').read_bytes()):
        nested=json.loads(game[29]);source=byid[str(game[24])]
        assert nested[:34]==source[1:35]
        assert 'Kentucky' in source[3:5]
        schema_crosscheck.append({'source_game_id_sha256':hashlib.sha256(str(game[24]).encode()).hexdigest(),'basic_team_payload_exact':True})
    pd.DataFrame(list(aggregate.values())).to_csv(R/'team_season_totals_candidate.csv',index=False)
    pd.DataFrame(provenance).to_csv(R/'team_game_lineage.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    pd.DataFrame(source_games[:80]).to_csv(R/'team_game_numeric_pilot.csv',index=False)
    (R/'coverage.json').write_text(json.dumps(coverage,indent=2));(R/'quarantine.json').write_text(json.dumps(quarantine,indent=2))
    (R/'player_dependency_inventory.json').write_text(json.dumps(all_player_inventory,indent=2));(R/'local_source_lineage.json').write_text(json.dumps(local_sources,indent=2))
    (R/'schema_crosscheck.json').write_text(json.dumps({'team':'Kentucky','season':2012,'source_game_arrays_matched':len(schema_crosscheck),'both_payloads_share_upstream_source':True,'does_not_substitute_for_independent_official_schema_validation':True},indent=2))
    (R/'private/team_identity_crosswalk.json').write_text(json.dumps(identities,indent=2))
    summary={'years':11,'raw_game_rows':sum(c['source_game_rows'] for c in coverage),'validated_game_rows':sum(c['validated_game_rows'] for c in coverage),'rejected_game_rows':sum(c['rejected_game_rows'] for c in coverage),'team_season_candidate_rows':len(aggregate),'exact_schema_game_crosschecks':len(schema_crosscheck),'current_player_impact_features_created':0,'original_vintage_verified':False,'no_current_impact_numbers_used':True,'no_NBA_outcomes_or_models':True,'candidate_status':'Team/opponent dependency candidates only; original schema/vintage, schedule completeness and exact player TOV/PF/MP still require proof'}
    (R/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

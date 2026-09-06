"""Fixed-sample source arithmetic audit; no model, outcome or population joins."""
from pathlib import Path
import collections,csv,datetime as dt,gzip,hashlib,json,math
R=Path(__file__).resolve().parent
TEAM_SOURCE=R.parent/'college_oliver_reconstruction'
GAME_MAP={23:'two_m',24:'two_a',25:'three_m',26:'three_a',27:'ft_m',28:'ft_a',33:'points',34:'orb',35:'drb',36:'ast',37:'tov',38:'stl',39:'blk',42:'pf'}
IDENTITY_MAP={0:'date',5:'opponent',6:'source_game_id',47:'team',48:'name',51:'source_player_id',52:'source_season'}
GAME_READ_INDICES=sorted([*GAME_MAP,*IDENTITY_MAP])
ANNUAL_COUNT_MAP={13:'ft_m',14:'ft_a',16:'two_m',17:'two_a',19:'three_m',20:'three_a'}
ANNUAL_PG_MAP={57:'orb',58:'drb',60:'ast',61:'stl',62:'blk',63:'points'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pid(source_id,year):return 'college_'+hashlib.sha256(f'{year}:{source_id}'.encode()).hexdigest()[:20]
def parse(row,year=2018):
    assert 2008<=year<=2018 and len(row)==53,'year_or_schema'
    assert int(row[52])==year and float(row[52])==year,'source_season'
    day=dt.datetime.strptime(str(row[0]),'%Y%m%d').date()
    assert dt.date(year-1,7,1)<=day<=dt.date(year,5,31),'game_date_cutoff'
    assert all(isinstance(row[i],str) and row[i].strip() for i in [5,6,47,48]),'identity'
    assert row[5]!=row[47],'same_teams'
    assert int(row[51])==float(row[51]) and int(row[51])>0,'player_id'
    out={v:row[k] for k,v in IDENTITY_MAP.items()};out['date']=day.isoformat();out['source_player_id']=str(int(row[51]))
    for k,v in GAME_MAP.items():
        z=float(row[k]);assert math.isfinite(z) and z>=0 and z.is_integer(),'invalid_count';out[v]=int(z)
    assert out['two_m']<=out['two_a'] and out['three_m']<=out['three_a'] and out['ft_m']<=out['ft_a'],'made_attempt_bounds'
    assert 2*out['two_m']+3*out['three_m']+out['ft_m']==out['points'],'scoring_identity'
    assert out['pf']<=5,'personal_fouls_bounds'
    return out

def load():
    reg=json.loads((R/'sample_registration.json').read_text())
    ledger=json.loads((R/'network_ledger.json').read_text());entry=next(x for x in ledger if x.get('key')=='player_games2018_compressed')
    f=R/'private/player_games2018_compressed.bin';assert sha(f)==entry['sha256'],'player_source_hash'
    assert sha(R/'private/fixed_source_sample.csv')==reg['private_sample_csv_sha256'],'sample_hash'
    assert sha(Path('/Users/kennakao/nba/datarebuild/tracking_raw/torvik_2018.csv.gz'))==reg['source_sha256'],'annual_source_hash'
    with (R/'private/fixed_source_sample.csv').open() as stream:
        sample=list(csv.DictReader(stream))
    assert len(sample)==12 and [int(s['source_row_zero_based']) for s in sample]==reg['source_rows_zero_based'],'fixed_sample'
    assert all(s['1']==reg['source_team'] and int(s['31'])==reg['source_year'] for s in sample),'sample_cohort'
    tg=TEAM_SOURCE/'private/season2018.bin';entry_team=next(x for x in json.loads((TEAM_SOURCE/'network_ledger.json').read_text()) if x.get('key')=='season2018')
    assert sha(tg)==entry_team['sha256'],'team_source_hash'
    games=[]
    for i,row in enumerate(json.loads(gzip.decompress(f.read_bytes()))):
        # Identity projection fixes the sample before looking at numeric counts.
        if row[47]==reg['source_team']:
            g=parse(row);g['source_row_zero_based']=i;games.append(g)
    team=[]
    for i,row in enumerate(json.loads(tg.read_bytes())):
        if reg['source_team'] in row[3:5]:
            day=dt.datetime.strptime(row[1],'%m/%d/%Y' if len(row[1].split('/')[-1])==4 else '%m/%d/%y').date()
            assert dt.date(2017,7,1)<=day<=dt.date(2018,5,31)
            side=0 if row[3]==reg['source_team'] else 1;start=5+15*side
            team.append({'date':day.isoformat(),'team':reg['source_team'],'opponent':row[4-side], 'source_row_zero_based':i,'count_values':list(map(lambda x:int(float(x)),row[start:start+15]))})
    return reg,entry,entry_team,sample,games,team

def build():
    reg,entry,entry_team,sample,games,team=load();by_team={}
    for t in team:
        key=(t['date'],t['team'],t['opponent']);assert key not in by_team,'duplicate_team_game';by_team[key]=t
    seen=set()
    for g in games:
        key=(g['source_player_id'],g['source_game_id']);assert key not in seen,'duplicate_player_game';seen.add(key)
        key2=(g['date'],g['team'],g['opponent']);assert key2 in by_team,'unmatched_team_game'
        assert g['points']<=by_team[key2]['count_values'][14],'player_exceeds_team_points'
    records=[];comparisons=[];lineage=[];identities=[];totals=[]
    for s in sample:
        subset=[g for g in games if g['source_player_id']==s['32']]
        assert subset and all(g['name']==s['0'] for g in subset),'sample_identity'
        subject=pid(s['32'],2018);gp=len(subset);assert gp==int(s['3']),'annual_gp_mismatch'
        counts={k:sum(g[k] for g in subset) for k in GAME_MAP.values()}
        assert all(counts[k]==int(s[str(i)]) for i,k in ANNUAL_COUNT_MAP.items()),'annual_shooting_mismatch'
        means={f'cgd_{k}_pg':v/gp for k,v in counts.items()}
        assert all(math.isfinite(v) for v in means.values())
        records.append({'source_subject_id':subject,'source_season':2018,**means})
        totals.append({'source_subject_id':subject,'source_season':2018,'player_games':gp,**counts})
        for i,k in ANNUAL_PG_MAP.items():
            old=float(s[str(i)]);new=counts[k]/gp
            comparisons.append({'source_subject_id':subject,'source_season':2018,'raw_annual_column':i,'statistic':k,'annual_appended_pg':old,'same_subset_game_total':counts[k],'same_subset_player_games':gp,'same_subset_pg':new,'matches_with_four_decimal_rounding':abs(old-new)<=.00005001})
        for g in subset:
            t=by_team[(g['date'],g['team'],g['opponent'])]
            lineage.append({'source_subject_id':subject,'source_season':2018,'game_date':g['date'],'player_source_row_zero_based':g['source_row_zero_based'],'team_source_row_zero_based':t['source_row_zero_based'],'player_source_sha256':entry['sha256'],'team_source_sha256':entry_team['sha256']})
        identities.append({'source_subject_id':subject,'source_season':2018,'raw_player_id':s['32'],'source_name':s['0'],'source_team':s['1'],'annual_source_row_zero_based':int(s['source_row_zero_based']),'annual_gp':gp,'annual_mpg':float(s['54'])})
    def csvout(name,rows):
        with (R/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    official_pg=[]
    ev=json.loads((R/'official_evidence.json').read_text())
    sample_by_row={int(s['source_row_zero_based']):s for s in sample}
    for fact in ev['official_player_facts']:
        s=sample_by_row[fact['source_annual_row_zero_based']]
        for idx,key in {54:'minutes',57:'orb',58:'drb',63:'points'}.items():
            if key in fact:
                mean=fact[key]/fact['games'];published=float(s[str(idx)])
                official_pg.append({'source_subject_id':pid(s['32'],2018),'raw_annual_column':idx,'statistic':key,'official_all_games_total':fact[key],'official_player_games':fact['games'],'annual_appended_pg':published,'official_total_per_game':mean,'matches_four_decimal_rounding':abs(mean-published)<=.00005001})
    assert all(x['matches_four_decimal_rounding'] for x in official_pg),'official_pg_mismatch'
    csvout('official_pg_denominator_comparison.csv',official_pg)
    csvout('same_subset_basics_candidate.csv',records);csvout('same_subset_totals.csv',totals);csvout('annual_pg_comparison.csv',comparisons);csvout('game_lineage.csv',lineage)
    (R/'private/identity_crosswalk.json').write_text(json.dumps(identities,indent=2))
    game_keys={(g['date'],g['team'],g['opponent']) for g in games}
    missing=[{k:v for k,v in t.items() if k!='count_values'} for t in team if (t['date'],t['team'],t['opponent']) not in game_keys]
    cache_totals=[sum(t['count_values'][i] for t in team) for i in range(15)]
    evidence=json.loads((R/'official_evidence.json').read_text());official=evidence['ovc_team_all_games_counts'];stat=['fgm','fga','three_m','three_a','ft_m','ft_a','orb','drb','trb','ast','stl','blk','tov','pf','points']
    check=[{'statistic':k,'cache_total':v,'official_total':official[k],'equal':v==official[k]} for k,v in zip(stat,cache_totals) if k in official]
    summary={'fixed_sample_players':12,'limited_minutes_le15':sum(float(s['54'])<=15 for s in sample),'player_game_source_rows_total':entry['rows'],'source_compressed_bytes':entry['bytes'],'team_player_game_rows':len(games),'fixed_sample_player_game_rows':len(lineage),'team_game_cache_games':len(team),'player_game_source_distinct_team_games':len(game_keys),'excluded_team_cache_games':missing,'annual_GP_exact_matches':12,'annual_shooting_count_exact_matches':72,'appended_pg_checks':len(comparisons),'appended_pg_mismatches':sum(not x['matches_with_four_decimal_rounding'] for x in comparisons),'official_all_game_pg_checks_matched':len(official_pg),'candidate_numeric_columns':len(GAME_MAP),'all_sample_rows_retained':True,'official_team_total_checks':check,'model_eligible':False,'reasons_excluded':['Historical source publication/revision vintage remains unverified.','2018 fixed-team pilot does not prove identical definitions in other source years.','Official comparison reveals AST/BLK count discrepancies with unresolved cause; no guessed replacement applied.','No exact player minute totals have been established; no per-minute statistics or Oliver ratings created.'],'requests_used':len(json.loads((R/'network_ledger.json').read_text())),'heldout_data_or_models_used':False,'annual_raw_pick_index45_read':False}
    (R/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
    return summary
if __name__=='__main__':build()

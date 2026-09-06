"""Historical source-only player game projections and quarantined aggregates.

No model/player population joins, advanced ratings, NBA fields or post2018 sources.
"""
from pathlib import Path
import argparse,collections,csv,datetime as dt,gzip,hashlib,io,json,math,shutil
from collect import decode,FLOOR
R=Path(__file__).resolve().parent
RAW=Path('/Users/kennakao/nba/datarebuild/tracking_raw')
REF=R.parent/'college_denominator_audit'
COUNTS={23:'two_m',24:'two_a',25:'three_m',26:'three_a',27:'ft_m',28:'ft_a',33:'points',34:'orb',35:'drb',36:'ast',37:'tov',38:'stl',39:'blk',42:'pf'}
IDENTITY={0:'date',5:'opponent',6:'raw_game_id',47:'team',48:'name',51:'raw_player_id',52:'source_season'}
READ_INDICES=sorted([*COUNTS,*IDENTITY])
ANNUAL={0:'name',1:'team',3:'gp',13:'ft_m',14:'ft_a',16:'two_m',17:'two_a',19:'three_m',20:'three_a',31:'source_season',32:'raw_player_id'}
SIX=['two_m','two_a','three_m','three_a','ft_m','ft_a']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def hashed(prefix,*parts):return prefix+'_'+hashlib.sha256(json.dumps(parts,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()[:24]
def clean(s):
    assert isinstance(s,str) and s.strip(),'invalid_identity_string'
    return s.strip()
def integer(v):
    assert not isinstance(v,bool),'boolean_not_count'
    x=float(v);assert math.isfinite(x) and x>=0 and x.is_integer(),'noninteger_or_nonfinite_count';return int(x)
def key_for(row,year):
    assert isinstance(row,list) and len(row)==53,'unsupported_schema'
    assert integer(row[52])==year,'wrong_source_season'
    source_id=integer(row[51]);assert source_id>0,'invalid_player_id'
    return (year,str(source_id),clean(row[47]))
def parse(row,year):
    assert 2008<=year<=2018,'outside_year_scope'
    key=key_for(row,year)
    date=str(row[0]);assert len(date)==8 and date.isdigit(),'invalid_date_format'
    day=dt.datetime.strptime(date,'%Y%m%d').date()
    assert dt.date(year-1,7,1)<=day<=dt.date(year,5,31),'date_outside_season'
    g={v:integer(row[k]) for k,v in COUNTS.items()}
    assert g['two_m']<=g['two_a'] and g['three_m']<=g['three_a'] and g['ft_m']<=g['ft_a'],'made_attempt_bounds'
    assert 2*g['two_m']+3*g['three_m']+g['ft_m']==g['points'],'points_identity'
    assert g['pf']<=5,'personal_foul_bounds'
    g.update(source_season=year,raw_player_id=key[1],team=key[2],name=clean(row[48]),opponent=clean(row[5]),raw_game_id=clean(row[6]),date=day.isoformat())
    assert g['team']!=g['opponent'],'same_team_opponent'
    return key,g

def freeze_manifest():
    path=R/'source_manifest.json'
    if path.exists():return json.loads(path.read_text())
    ledger=json.loads((R/'network_ledger.json').read_text());assert len(ledger)<=10
    assert [x['source_season'] for x in ledger]==list(range(2017,2017-len(ledger),-1)),'collection_order'
    source=[]
    for x in ledger:
        if x.get('status')==200 and x.get('decoded_success'):
            source.append({**x,'path':x['private_file'],'reused':False})
    old=json.loads((REF/'network_ledger.json').read_text());e=next(x for x in old if x.get('key')=='player_games2018_compressed')
    source.append({'source_season':2018,'url':e['url'],'path':'../college_denominator_audit/private/player_games2018_compressed.bin','sha256':e['sha256'],'bytes':e['bytes'],'rows':e['rows'],'reused':True,'status':200,'retrieved_at_utc':e['retrieved_at_utc'],'original_publication_date':None,'model_eligible':False})
    for x in source:
        assert sha(R/x['path'])==x['sha256'],'game_source_changed'
        p=RAW/f"torvik_{x['source_season']}.csv.gz";x['annual_source']={'filename':p.name,'sha256':sha(p),'allowed_indices':list(ANNUAL),'forbidden_index45_used':False}
    manifest={'sources':sorted(source,key=lambda x:x['source_season']),'game_read_indices':READ_INDICES,'annual_read_indices':list(ANNUAL),'model_eligible':False,'frozen_before_per_player_comparisons':True}
    path.write_text(json.dumps(manifest,indent=2));return manifest

def parse_annual_records(reader,year):
    assert 2008<=year<=2018,'outside_year_scope'
    groups=collections.defaultdict(list);invalid=[]
    for i,row in enumerate(reader):
        key=None
        try:
            # Only this explicit projection is inspected; annual index45 is ignored.
            projected={name:row[idx] for idx,name in ANNUAL.items()}
            assert integer(projected['source_season'])==year,'annual_wrong_year'
            rid=integer(projected['raw_player_id']);assert rid>0,'annual_bad_id'
            key=(year,str(rid),clean(projected['team']))
            groups.setdefault(key,[])  # Preserve a recoverable malformed source identity.
            a={name:integer(projected[name]) for name in ['gp',*SIX]}
            a.update(name=clean(projected['name']),source_row_zero_based=i)
            groups[key].append(a)
        except (AssertionError,ValueError,TypeError,IndexError) as err:
            invalid.append({'source_season':year,'annual_source_row_zero_based':i,'source_subject_id':hashed('subject',*key) if key else None,'reason':str(err) or type(err).__name__})
    return groups,invalid

def annual_rows(entry):
    assert 2008<=entry['source_season']<=2018,'outside_year_scope'
    assert entry['annual_source']['filename']==f"torvik_{entry['source_season']}.csv.gz",'annual_path_scope'
    p=RAW/entry['annual_source']['filename'];assert sha(p)==entry['annual_source']['sha256'],'annual_source_changed'
    with gzip.open(p,'rt',newline='') as f:return parse_annual_records(csv.reader(f),entry['source_season'])

class GzipCSV:
    def __init__(self,path,columns):
        self.path=path;self.partial=path.with_name(path.name+'.partial');self.raw=self.partial.open('wb');self.gz=gzip.GzipFile(filename='',fileobj=self.raw,mode='wb',mtime=0,compresslevel=6);self.text=io.TextIOWrapper(self.gz,encoding='utf-8',newline='');self.writer=csv.DictWriter(self.text,fieldnames=columns);self.writer.writeheader()
    def row(self,x):self.writer.writerow(x)
    def close(self):
        self.text.close();self.raw.close();self.partial.replace(self.path)

def assess_group(k,records,annual,bad_reasons):
    reasons=set(bad_reasons)
    if not records:reasons.add('no_valid_game_records')
    if len(annual)!=1:reasons.add('missing_annual_row' if not annual else 'duplicate_annual_rows')
    total={name:sum(g[name] for g in records) for name in COUNTS.values()};gp=len(records)
    if records and len({g['name'] for g in records})!=1:reasons.add('inconsistent_game_name')
    if len(annual)==1:
        a=annual[0]
        if records and any(g['name']!=a['name'] for g in records):reasons.add('annual_game_name_disagreement')
        if gp!=a['gp']:reasons.add('gp_disagreement')
        for name in SIX:
            if total[name]!=a[name]:reasons.add(name+'_disagreement')
    return gp,total,sorted(reasons)

def apply_annual_issues(annual,issues,bad):
    subjects={hashed('subject',*key):key for key in annual};wide=False
    for issue in issues:
        subject=issue['source_subject_id']
        if subject in subjects:bad[subjects[subject]].add('invalid_annual_record')
        else:wide=True
    return wide

def group_records(parsed,bad=None):
    bad=collections.defaultdict(set) if bad is None else bad
    semantic=collections.Counter((k,g['date'],g['opponent']) for k,g in parsed)
    sourcekeys=collections.Counter((k,g['raw_game_id']) for k,g in parsed)
    # A source player-game may not appear under several teams on the same date.
    playerdates=collections.defaultdict(set)
    for k,g in parsed:playerdates[(k[0],k[1],g['date'])].add((g['team'],g['opponent']))
    records=collections.defaultdict(list);duplicate_rows=0
    for k,g in parsed:
        if semantic[(k,g['date'],g['opponent'])]!=1 or sourcekeys[(k,g['raw_game_id'])]!=1:
            bad[k].add('duplicate_player_game');duplicate_rows+=1
        if len(playerdates[(k[0],k[1],g['date'])])!=1:bad[k].add('player_date_multiple_teams_or_opponents')
        records[k].append(g)
    return records,bad,duplicate_rows

def build_year(entry):
    year=entry['source_season'];assert 2008<=year<=2018,'outside_year_scope'
    expected=R/'private'/f'games{year}.bin' if year<2018 else REF/'private/player_games2018_compressed.bin'
    path=R/entry['path'];assert path.resolve()==expected.resolve(),'game_path_scope'
    assert shutil.disk_usage(R).free>FLOOR,'free_space_floor'
    assert sha(path)==entry['sha256'],'game_source_changed'
    raw=json.loads(decode(path));assert isinstance(raw,list) and len(raw)==entry['rows'],'unexpected_row_count'
    annual,annual_invalid=annual_rows(entry)
    parsed=[];invalid=[];bad=collections.defaultdict(set);raw_groups=collections.Counter();year_wide_error=False
    annual_wide_error=apply_annual_issues(annual,annual_invalid,bad)
    for i,row in enumerate(raw):
        key=None
        try:key=key_for(row,year);raw_groups[key]+=1
        except (AssertionError,ValueError,TypeError,IndexError):pass
        try:
            k,g=parse(row,year);g['source_row_zero_based']=i;parsed.append((k,g))
        except (AssertionError,ValueError,TypeError,IndexError) as err:
            reason=str(err) or type(err).__name__;subject=hashed('subject',*key) if key else None
            invalid.append({'source_season':year,'source_row_zero_based':i,'source_subject_id':subject,'reason':reason,'source_sha256':entry['sha256']})
            if key:bad[key].add('invalid_game_record')
            else:year_wide_error=True
    del raw
    records,bad,duplicate_rows=group_records(parsed,bad)
    for key in set(raw_groups)|set(annual):
        if year_wide_error:bad[key].add('unassignable_invalid_source_row_in_season')
        if annual_wide_error:bad[key].add('unassignable_invalid_annual_row_in_season')
    base=['source_subject_id','source_team_id','source_season']
    projection_cols=[*base,'source_opponent_team_id','source_game_id','game_date','source_row_zero_based','source_sha256',*COUNTS.values()]
    projection=GzipCSV(R/'data'/f'games_{year}.csv.gz',projection_cols)
    for k,g in parsed:
        projection.row({'source_subject_id':hashed('subject',*k),'source_team_id':hashed('team',k[2]),'source_season':year,'source_opponent_team_id':hashed('team',g['opponent']),'source_game_id':hashed('game',year,g['raw_game_id']),'game_date':g['date'],'source_row_zero_based':g['source_row_zero_based'],'source_sha256':entry['sha256'],**{n:g[n] for n in COUNTS.values()}})
    projection.close()
    candidates=[];audits=[];crosswalk=[];reason_counts=collections.Counter();valid=0
    allkeys=sorted(set(raw_groups)|set(annual)|set(records))
    for k in allkeys:
        gs=records.get(k,[]);ar=annual.get(k,[]);gp,total,reasons=assess_group(k,gs,ar,bad[k]);okay=not reasons;valid+=okay;reason_counts.update(reasons)
        subject=hashed('subject',*k);common={'source_subject_id':subject,'source_team_id':hashed('team',k[2]),'source_season':year}
        cand={**common,'cgd_observed_gp':gp if okay else None,**{f'cgd_{n}_pg':total[n]/gp if okay else None for n in COUNTS.values()}}
        candidates.append(cand)
        audit={**common,'source_raw_game_rows':raw_groups.get(k,0),'valid_parsed_game_rows':gp,'annual_rows':len(ar),'annual_source_row_zero_based':ar[0]['source_row_zero_based'] if len(ar)==1 else None,'annual_gp':ar[0]['gp'] if len(ar)==1 else None,'source_consistent':okay,'model_eligible':False,'quarantine_reasons':reasons,'source_sha256':entry['sha256'],'annual_source_sha256':entry['annual_source']['sha256'],'game_date_min':min((g['date'] for g in gs),default=None),'game_date_max':max((g['date'] for g in gs),default=None),'direct_game_totals':total,'annual_six_counts':{n:ar[0][n] for n in SIX} if len(ar)==1 else None,'all_zero_basic_records':sum(all(g[n]==0 for n in COUNTS.values()) for g in gs)}
        audits.append(audit)
        crosswalk.append({**common,'raw_player_id':k[1],'source_team_name':k[2],'game_source_names':sorted({g['name'] for g in gs}),'annual_source_names':sorted({a['name'] for a in ar})})
    with (R/'data'/f'candidates_{year}.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(candidates[0]));w.writeheader();w.writerows(candidates)
    def json_gz(name,obj,private=False):
        p=(R/'private' if private else R/'data')/name
        with p.open('wb') as f:
            with gzip.GzipFile(filename='',fileobj=f,mode='wb',mtime=0,compresslevel=6) as z:z.write(json.dumps(obj,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode())
    json_gz(f'audit_{year}.json.gz',audits);json_gz(f'crosswalk_{year}.json.gz',crosswalk,private=True)
    json_gz(f'quarantine_games_{year}.json.gz',invalid)
    json_gz(f'invalid_annual_rows_{year}.json.gz',annual_invalid)
    return {'source_season':year,'source_rows':entry['rows'],'valid_parsed_game_rows':len(parsed),'invalid_game_rows':len(invalid),'duplicate_player_game_rows':duplicate_rows,'unassignable_invalid_game_row_blocks_season':year_wide_error,'unassignable_invalid_annual_row_blocks_season':annual_wide_error,'annual_source_rows':sum(map(len,annual.values()))+len(annual_invalid),'invalid_annual_rows':len(annual_invalid),'source_player_team_seasons':len(allkeys),'source_consistent_player_team_seasons':valid,'quarantined_player_team_seasons':len(allkeys)-valid,'quarantine_reason_counts':dict(reason_counts),'candidate_columns':15,'model_eligible':False,'all_zero_basic_game_rows':sum(all(g[n]==0 for n in COUNTS.values()) for _,g in parsed),'source_sha256':entry['sha256'],'annual_source_sha256':entry['annual_source']['sha256']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--years',type=int,nargs='*');a=p.parse_args()
    manifest=freeze_manifest();coverage_file=R/'coverage.json';existing=json.loads(coverage_file.read_text()) if coverage_file.exists() else []
    coverage={x['source_season']:x for x in existing}
    for e in manifest['sources']:
        year=e['source_season']
        if a.years is not None and year not in a.years:continue
        result=build_year(e);coverage[year]=result;coverage_file.write_text(json.dumps([coverage[y] for y in sorted(coverage)],indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':main()

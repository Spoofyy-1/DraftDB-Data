"""Bounded, source-first 2012–2014 selected-player registry. No WAR/NBA-ID reads."""
from __future__ import annotations
import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT=Path(__file__).resolve().parent
YEARS=(2012,2013,2014)
DRAFT_DATES={2012:'2012-06-28',2013:'2013-06-27',2014:'2014-06-26'}
HR_URLS={2012:'https://www.hoopsrumors.com/2012/06/2012-nba-draft-results.html',
         2013:'https://www.hoopsrumors.com/2013/06/2013-nba-draft-results.html',
         2014:'https://www.hoopsrumors.com/2014/06/2014-draft-results.html'}
HR_DATES={2012:'2012-06-29',2013:'2013-06-28',2014:'2014-06-27'}
AP_URLS={2012:'https://www.thespread.com/nba-news/sp-2041481404/',
         2013:'https://www.ctpost.com/sports/article/2013-nba-draft-selections-4632115.php',
         2014:'https://www.foxnews.com/sports/2014-nba-draft-team-by-team'}
AP_DATES={2012:'2012-06-29',2013:'2013-06-28',2014:'2014-06-27'}

def norm(value):
    text=unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]','',text)

def sha(value):
    return hashlib.sha256(value).hexdigest()

def dump(path,obj):
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')

def write_csv(path,rows,fields=None):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def candidate_id(year,name):
    # Names and year, never selection number, determine IDs.
    return f'prior_{year}_'+sha(f'{year}|{norm(name)}'.encode())[:20]

def validate_picks(rows,year):
    if year not in YEARS:
        raise ValueError('Pilot accepts only 2012–2014')
    if len(rows)!=60 or sorted(r['actual_pick'] for r in rows)!=list(range(1,61)):
        raise ValueError(f'Incomplete/duplicated source selection list for {year}')
    if len({norm(r['player_name']) for r in rows})!=60:
        raise ValueError('Duplicate normalized player name')

def parse_hr(text,year):
    rows=[]
    round_number=0
    for line_number,line in enumerate(text.splitlines(),1):
        if line.strip().startswith('Round One'):
            round_number=1
        elif line.strip().startswith('Round Two'):
            round_number=2
        m=re.match(r'^\s*(\d+)\.\s+(.+?):\s*(.+?)\s+\(([^,]+),\s*(.+?)\)',line)
        if not m:
            continue
        assert round_number in (1,2)
        ordinal=int(m[1])
        # 2013's source explicitly numbers the second round 1–30; other years use 31–60.
        pick=ordinal+30 if year==2013 and round_number==2 else ordinal
        assert (pick-1)//30+1==round_number
        rows.append(dict(actual_pick=pick,round_number=round_number,player_name=m[3].strip(),
                         affiliation_source=m[5].strip(),team_display_source=m[2].strip(),source_text_line=line_number))
    validate_picks(rows,year)
    return rows

def parse_ap(text,year):
    rows=[]
    for line_number,line in enumerate(text.splitlines(),1):
        if year==2013:
            m=re.match(r'^L(\d+): (\d+)\. (.+)$',line)
            if not m:
                continue
            source_line,pick=int(m[1]),int(m[2])
            # Team footnotes may contain commas, so the first team/player split
            # is the first comma followed by a space after the team expression.
            textrow=re.sub(r'^c,d-', '',m[3])
            _,rest=textrow.split(', ',1)
            name=re.split(r', [fgcr](?:,|\s*-)',rest,flags=re.I)[0]
            name=name.replace(', Jr.',' Jr.').strip()
        else:
            m=re.match(r'^([12]) \((\d+)\) (.+)$',line.strip())
            if not m:
                continue
            pick=int(m[2]);rest=m[3]
            if year==2012 and pick==23:
                assert rest.startswith('Atlanta, ')
                rest=rest.removeprefix('Atlanta, ')
            name=rest.split(', ',1)[0].strip()
            source_line=line_number
        rows.append(dict(actual_pick=pick,player_name=name,source_text_line=source_line))
    validate_picks(rows,year)
    return rows

def get_sources(private):
    hr={}
    for f in ('hr_2012_2013_indexed.txt','hr_2014_indexed.txt'):
        path=private/f
        for page in re.split(r'-{80}\n',path.read_text()):
            year=int(re.search(r'201[234]',page)[0])
            assert HR_URLS[year] in page.splitlines()[0]
            hr[year]=(path,page)
    ap={2012:(private/'ap_2012_indexed.txt',(private/'ap_2012_indexed.txt').read_text()),
        2014:(private/'ap_2014_indexed.txt',(private/'ap_2014_indexed.txt').read_text())}
    path=private/'contemporary_views.txt'
    page=next(p for p in re.split(r'-{80}\n',path.read_text()) if AP_URLS[2013] in p.splitlines()[0])
    ap[2013]=(path,page)
    sources=[];results={}
    for year in YEARS:
        hrrows=parse_hr(hr[year][1],year)
        aprows=parse_ap(ap[year][1],year)
        results[year]=(hrrows,{r['actual_pick']:r for r in aprows})
        for provider,record,urls,dates in [('hr',hr[year],HR_URLS,HR_DATES),('ap',ap[year],AP_URLS,AP_DATES)]:
            path,page=record
            stamp=dt.date.fromisoformat(dates[year]).strftime('%B %-d, %Y')
            assert stamp in page
            sources.append(dict(source_id=f'{provider}_{year}',url=urls[year],draft_year=year,
                claimed_publication_date=dates[year],later_update_date='2015-02-05' if provider=='ap' and year==2014 else None,
                independently_observed_at_utc=dt.datetime.fromtimestamp(path.stat().st_mtime,dt.timezone.utc).isoformat(),
                capture_sha256=sha(page.encode()),capture_representation='web_tool_page_view' if provider=='ap' and year==2013 else 'web_tool_indexed_source_text',
                raw_http_sha256=None,role='canonical_contemporary_roster' if provider=='hr' else 'independent_AP_membership_corroboration',
                parsed_selections=60,publication_body_public=False))
    return results,sources

def make_registry(results):
    registry=[];protected=[];aliases=[]
    for year in YEARS:
        main,ap=results[year]
        for record in main:
            other=ap[record['actual_pick']]
            cid=candidate_id(year,record['player_name'])
            names=list(dict.fromkeys([record['player_name'],other['player_name']]))
            same=norm(names[0])==norm(names[-1])
            registry.append(dict(candidate_id=cid,draft_year=year,player_name_source=record['player_name'],
                membership_basis='contemporary_complete_actual_draft_results',membership_available_date=HR_DATES[year],
                primary_source_id=f'hr_{year}',corroborating_source_id=f'ap_{year}',
                source_names_agree_normalized=same,global_identity_verified=False,cohort_selected_population_complete=True))
            protected.append(dict(candidate_id=cid,draft_year=year,actual_pick=record['actual_pick'],
                actual_round=record['round_number'],primary_source_text_line=record['source_text_line'],
                corroborating_source_text_line=other['source_text_line'],
                primary_source_url=HR_URLS[year],corroborating_source_url=AP_URLS[year]))
            for name in names:
                aliases.append(dict(candidate_id=cid,draft_year=year,player_name_source=name,name_normalized=norm(name),
                    source_role='canonical' if name==record['player_name'] else 'corroborating_variant_needs_review'))
    return sorted(registry,key=lambda r:r['candidate_id']),sorted(protected,key=lambda r:r['candidate_id']),sorted(aliases,key=lambda r:(r['candidate_id'],r['name_normalized']))

def identity_crosswalk(registry,aliases,key_rows,legacy_rows,train_ids):
    broad=collections.defaultdict(list);legacy=collections.defaultdict(list);names=collections.defaultdict(set)
    for row in key_rows:
        broad[norm(row['player_name'])].append(row)
    for row in legacy_rows:
        if int(row['draft_year']) in YEARS:
            legacy[(int(row['draft_year']),norm(row['player_name']))].append(row)
    for row in aliases:
        names[row['candidate_id']].add(row['name_normalized'])
    result=[]
    for row in registry:
        cid=row['candidate_id'];year=row['draft_year']
        # Variants from independent draft-result rows support a candidate search;
        # they are never silently certified as identity matches.
        legacy_matches={r['pid']:r for n in names[cid] for r in legacy.get((year,n),[])}
        broad_matches={r['pid']:r for n in names[cid] for r in broad.get(n,[])}
        pid=next(iter(legacy_matches)) if len(legacy_matches)==1 else (next(iter(broad_matches)) if not legacy_matches and len(broad_matches)==1 else None)
        method=('unique_legacy_cohort_name_suggestion' if len(legacy_matches)==1 else
                ('unique_broad_name_suggestion' if not legacy_matches and len(broad_matches)==1 else 'unresolved'))
        result.append(dict(candidate_id=cid,draft_year=year,legacy_same_cohort_name_match_count=len(legacy_matches),
            broad_key_name_match_count=len(broad_matches),suggested_pid=pid,crosswalk_method=method,
            identity_verified=False,matched_existing_training_pid=pid in train_ids if pid is not None else False,
            gap_status=('no_legacy_same_cohort_name_match' if not legacy_matches else
                        ('ambiguous_legacy_name_match' if len(legacy_matches)>1 else
                         ('legacy_candidate_absent_from_training' if pid not in train_ids else 'existing_training_candidate')))))
    return result

def model_row_index(registry,prediction_year,information_cutoff_date):
    """Identifier-only index; source order, source line, names and picks excluded."""
    dt.date.fromisoformat(information_cutoff_date)
    if any(r['draft_year'] not in YEARS for r in registry):
        raise ValueError('Out-of-pilot cohort rejected')
    rows=[dict(candidate_id=r['candidate_id'],draft_year=r['draft_year']) for r in registry
          if r['draft_year']<prediction_year and r['membership_available_date']<=information_cutoff_date]
    rows.sort(key=lambda r:r['candidate_id'])
    # A cutoff may exclude an entire cohort; it must never produce a partial class.
    for year in {r['draft_year'] for r in rows}:
        if sum(r['draft_year']==year for r in rows)!=60:
            raise ValueError('Partial selected cohort rejected')
    return rows

def main():
    import pandas as pd
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=ROOT/'data')
    parser.add_argument('--player-key',type=Path,default=Path('/Users/kennakao/nba/keys/player_key.parquet'))
    parser.add_argument('--legacy-identity',type=Path,default=Path('/Users/kennakao/nba/datarebuild/identity/tabular_names.csv'))
    parser.add_argument('--train-inputs',type=Path,default=ROOT.parent/'r8l'/'data'/'features.csv')
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True);(ROOT/'protected').mkdir(exist_ok=True)
    results,sources=get_sources(ROOT/'private')
    registry,protected,aliases=make_registry(results)
    keys=pd.read_parquet(args.player_key,columns=['pid','player_uid','player_name']).to_dict('records')
    # Crucially, actual_pick is never read from this mixed-year identity file.
    legacy=pd.read_csv(args.legacy_identity,usecols=['pid','draft_year','player_name']).to_dict('records')
    train=pd.read_csv(args.train_inputs,usecols=['pid','draft_year'])
    train_ids=set(train.loc[train.draft_year.isin(YEARS),'pid'])
    xwalk=identity_crosswalk(registry,aliases,keys,legacy,train_ids)
    index=model_row_index(registry,2015,'2014-12-31')
    write_csv(args.out/'membership_registry.csv',registry)
    write_csv(args.out/'source_name_variants.csv',aliases)
    write_csv(args.out/'identity_crosswalk_suggestions.csv',xwalk)
    write_csv(args.out/'model_row_index_2015.csv',index)
    lookup={r['candidate_id']:r for r in registry}
    gaps=[dict(**r,player_name_source=lookup[r['candidate_id']]['player_name_source']) for r in xwalk if r['gap_status']!='existing_training_candidate']
    write_csv(args.out/'training_population_gaps.csv',gaps)
    write_csv(ROOT/'protected'/'actual_draft_positions.csv',protected)
    (ROOT/'protected'/'actual_draft_positions.csv').chmod(0o600)
    coverage={str(y):dict(selected_source_rows=60,ap_corroborating_rows=60,
        normalized_source_name_agreement=sum(r['draft_year']==y and r['source_names_agree_normalized'] for r in registry),
        identity_status_counts=dict(collections.Counter(r['crosswalk_method'] for r in xwalk if r['draft_year']==y)),
        gap_status_counts=dict(collections.Counter(r['gap_status'] for r in xwalk if r['draft_year']==y))) for y in YEARS}
    manifest=dict(schema_version=1,years=list(YEARS),sources=sources,coverage=coverage,registry_rows=len(registry),
        source_draft_membership_complete=True,global_identities_resolved=False,model_ready=False,
        outcomes_read=False,nba_ids_read=False,actual_pick_from_legacy_identity_read=False,model_fits=0,test_scores=0,
        actual_positions_path_excluded_from_public='protected/actual_draft_positions.csv',
        inputs=[dict(path_basename=p.name,sha256=sha(p.read_bytes()),columns_read=cols) for p,cols in
                [(args.player_key,['pid','player_uid','player_name']),(args.legacy_identity,['pid','draft_year','player_name']),(args.train_inputs,['pid','draft_year'])]],
        conditions=['draft_year < prediction_year','membership_available_date <= separately configured information cutoff',
                    'all selected members retained, even with no identity, feature or label match','only identifier fields emitted to model row index'],
        omissions=['2007–2011 and 2015+ outside this bounded pilot','No individual NBA participation or WAR labels collected',
                   'Names-only suggestions require further identity evidence','Public datelines not independently timestamped archive snapshots',
                   '2014 AP source has a 2015 update; 2014 availability comes from the independent contemporaneous Hoops Rumors record',
                   'Primary live NBA history URLs unavailable; contemporary specialist reporting crosschecked with all 60 AP rows'],
        original_benchmark_unchanged=True)
    dump(args.out/'manifest.json',manifest)
    dump(args.out/'coverage.json',dict(coverage=coverage,registry_rows=len(registry),source_draft_membership_complete=True,model_ready=False))
    print(json.dumps(dict(coverage=coverage,registry_rows=len(registry)),indent=2))

if __name__=='__main__':
    main()

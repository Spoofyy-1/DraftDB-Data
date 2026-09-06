"""Offline, source-first NBA early-entry pilot; no outcomes or NBA IDs are read."""
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

ROOT = Path(__file__).resolve().parent
SEPARATOR = "\n" + "-" * 80 + "\n"
URLS = {
    "2012_final": "https://pr.nba.com/2012-nba-draft-early-entry-candidates/",
    "2013_final": "https://pr.nba.com/early-entry-candidates-withdraw-2013-nba-draft/",
    "2014_final": "https://pr.nba.com/2014-nba-draft-withdrawals/",
    "2012_initial": "https://pr.nba.com/entry-candidates-2012-nba-draft/",
    "2013_initial": "https://pr.nba.com/nba-early-entry-candidates-2013-nba-draft/",
    "2014_initial": "https://pr.nba.com/2014-nba-draft-early-entry-candidates/",
}
DATES = {"2012_final":"2012-06-19", "2013_final":"2013-06-18", "2014_final":"2014-06-17",
         "2012_initial":"2012-05-03", "2013_initial":"2013-05-01", "2014_initial":"2014-04-30"}
DRAFT_DATES = {2012:"2012-06-28", 2013:"2013-06-27", 2014:"2014-06-26"}
WITHDRAWAL_DEADLINES = {2012:"2012-06-18T17:00:00-04:00",2013:"2013-06-17T17:00:00-04:00",2014:"2014-06-16T17:00:00-04:00"}
# Audited source-view line ranges, expected row counts, status and source category.
RANGES = {
    "2012_final": [(21,21,1,"withdrawn","college"),(27,44,10,"withdrawn","international"),
                   (54,145,49,"eligible_final_early_entry","college"),(151,162,7,"eligible_final_early_entry","international")],
    "2013_final": [(32,34,2,"withdrawn","college"),(40,68,16,"withdrawn","international"),
                   (73,157,45,"eligible_final_early_entry","college"),(162,188,15,"eligible_final_early_entry","international")],
    "2014_final": [(21,21,1,"withdrawn","college"),(27,56,17,"withdrawn","international"),
                   (62,142,44,"eligible_final_early_entry","college"),(148,170,13,"eligible_final_early_entry","international")],
    "2012_initial": [],  # The release links an attachment; no individual entry date inferred.
    "2013_initial": [(21,100,46,"declared_unresolved","college"),(105,157,31,"declared_unresolved","international")],
    "2014_initial": [(20,64,45,"declared_unresolved","college"),(69,98,30,"declared_unresolved","international")],
}

def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", value)

def dump(path: Path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")

def write_csv(path: Path, rows: list[dict], fields=None):
    fields = fields or list(rows[0])
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def parse_lines(page: str) -> dict[int, str]:
    return {int(m[1]): m[2].strip() for m in re.finditer(r"L(\d+): (.*?)(?=(?:\n| )L\d+: |$)", page, re.S)}

def split_fact(row: str, source_id: str, line: int) -> tuple[str, str]:
    row = row.strip()
    # This source-view row has no column whitespace. Explicitly audited split only.
    if source_id == "2012_final" and line == 136:
        assert row == "Richard Townsend-Gant Vancouver Island University"
        return "Richard Townsend-Gant", "Vancouver Island University"
    parts = re.split(r"\s{2,}", row)
    if len(parts) < 2:
        raise ValueError(f"Unparseable factual row: {source_id} line {line}")
    name, affiliation = parts[:2]
    # Initial 2013 releases have extra height/status columns. Neither is imported.
    if source_id == "2013_initial":
        affiliation = re.sub(r"\s+[5-8]-\d{1,2}.*$", "", affiliation)
    if not name or not affiliation or len(name) > 65:
        raise ValueError(f"Bad factual cells: {source_id} line {line}")
    return name.strip(), affiliation.strip()

def source_candidate_id(year: int, name: str, category: str) -> str:
    # A source-local cohort ID, not a claim of globally resolved person identity.
    return f"elig_{year}_" + sha(f"{year}|{category}|{norm(name)}".encode())[:20]

def extract(private_dir: Path):
    events, sources = [], []
    for kind in ("initial", "final"):
        capture = private_dir / f"{kind}_web_response.txt"
        observed = dt.datetime.fromtimestamp(capture.stat().st_mtime, dt.timezone.utc).isoformat()
        for page in capture.read_text().split(SEPARATOR):
            year = int(re.search(r"201[234]", page)[0])
            source_id = f"{year}_{kind}"
            lines = parse_lines(page)
            expected_stamp = dt.date.fromisoformat(DATES[source_id]).strftime("%B %-d, %Y")
            assert expected_stamp in lines.values(), (source_id, "publication date changed")
            assert URLS[source_id] in page.splitlines()[0]
            assert DATES[source_id] < DRAFT_DATES[year], "Post-draft release rejected"
            if kind == "final":
                assert DATES[source_id] > WITHDRAWAL_DEADLINES[year][:10]
            src = dict(source_id=source_id, url=URLS[source_id], draft_year=year,
                       claimed_published_date=DATES[source_id], independently_observed_at_utc=observed,
                       capture_sha256=sha(page.encode()), capture_representation="web_tool_primary_page_text_view",
                       raw_http_sha256=None, date_confidence="publisher_historical_dateline_not_independent_archive_snapshot",
                       release_kind=kind, parsed_rows=0, early_entry_list_only=True,
                       source_file_private=capture.name, source_copyright_body_public=False)
            for start, stop, expected, status, category in RANGES[source_id]:
                group=[]
                for n in range(start, stop + 1):
                    row=lines.get(n, "")
                    if not row:
                        continue
                    name, affiliation = split_fact(row, source_id, n)
                    group.append(dict(event_id=f"nba_pr_{source_id}_L{n}",
                        candidate_id=source_candidate_id(year,name,category), draft_year=year,
                        player_name_source=name, name_normalized=norm(name), source_category=category,
                        affiliation_source=affiliation, status=status,
                        evidence_available_date=DATES[source_id], event_effective_date=None,
                        evidence_date_basis="publisher_release_date; exact player filing/withdrawal date unknown",
                        source_id=source_id, source_url=URLS[source_id], source_view_line=n,
                        source_capture_sha256=src["capture_sha256"]))
                assert len(group) == expected, (source_id,start,len(group),expected)
                assert len({r['candidate_id'] for r in group})==len(group)
                events.extend(group)
                src['parsed_rows'] += len(group)
            sources.append(src)
    return events, sources

def resolve_registry(events: list[dict], cutoff_dates: dict[int, str]):
    by_id = collections.defaultdict(list)
    for event in events:
        if event["evidence_available_date"] <= cutoff_dates[event["draft_year"]]:
            by_id[event["candidate_id"]].append(event)
    result=[]
    for cid, rows in sorted(by_id.items()):
        rows=sorted(rows,key=lambda r:(r['evidence_available_date'],r['event_id']))
        latest=rows[-1]
        same_date=[x['status'] for x in rows if x['evidence_available_date']==latest['evidence_available_date']]
        status=latest['status'] if len(set(same_date))==1 else 'conflict_unresolved'
        result.append(dict(candidate_id=cid,draft_year=latest['draft_year'],player_name_source=latest['player_name_source'],
            name_normalized=latest['name_normalized'],source_category=latest['source_category'],
            affiliation_source=latest['affiliation_source'],eligibility_status=status,
            positive_eligibility_evidence=status=='eligible_final_early_entry',
            registry_cutoff_date=cutoff_dates[latest['draft_year']],
            latest_evidence_available_date=latest['evidence_available_date'],
            first_observed_entry_evidence_date=next((r['evidence_available_date'] for r in rows if r['status']=='declared_unresolved'),None),
            event_ids='|'.join(r['event_id'] for r in rows), latest_source_id=latest['source_id'],
            global_person_identity_status='unresolved_source_local_id',
            complete_eligible_cohort=False))
    return result

def crosswalk_rows(registry: list[dict], keys: list[dict]):
    by_name=collections.defaultdict(list)
    for row in keys:
        by_name[norm(row['player_name'])].append(row)
    result=[]
    for row in registry:
        matches=by_name.get(row['name_normalized'],[])
        # Name equality alone is a crosswalk suggestion, never identity certification.
        unique=len(matches)==1
        result.append(dict(candidate_id=row['candidate_id'],draft_year=row['draft_year'],
            unique_name_crosswalk_suggestion=unique, match_count=len(matches),
            suggested_pid=matches[0]['pid'] if unique else None,
            suggested_player_uid=matches[0]['player_uid'] if unique else None,
            match_method='exact_normalized_name_only', identity_verified=False,
            crosswalk_status='unique_name_needs_identity_review' if unique else ('ambiguous' if matches else 'source_only_no_exact_match'),
            determines_eligibility=False))
    return result

def crosswalk(registry: list[dict], player_key: Path):
    import pandas as pd
    # Read only identity fields. NBA IDs and outcome/participation fields are excluded.
    keys=pd.read_parquet(player_key,columns=['pid','player_uid','player_name'])
    result=crosswalk_rows(registry,keys.to_dict('records'))
    return result, dict(path_basename=player_key.name,sha256=sha(player_key.read_bytes()),
                        columns_read=['pid','player_uid','player_name'],rows=len(keys),purpose='optional_crosswalk_only')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--player-key',type=Path,default=Path('/Users/kennakao/nba/keys/player_key.parquet'))
    parser.add_argument('--out',type=Path,default=ROOT/'data')
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    events,sources=extract(ROOT/'private')
    cutoffs={y:max(s['claimed_published_date'] for s in sources if s['draft_year']==y) for y in DRAFT_DATES}
    registry=resolve_registry(events,cutoffs)
    xwalk,key_meta=crosswalk(registry,args.player_key)
    write_csv(args.out/'entry_events.csv',events)
    write_csv(args.out/'eligibility_registry.csv',registry)
    write_csv(args.out/'identity_crosswalk_suggestions.csv',xwalk)
    # Explicit empty factual table: a mock alone never proves final eligibility.
    write_csv(args.out/'draft_discussed_only.csv',[],['candidate_id','draft_year','player_name_source','source_url','evidence_available_date','status'])
    coverage={}
    for year in DRAFT_DATES:
        rows=[r for r in registry if r['draft_year']==year]
        xr=[r for r in xwalk if r['draft_year']==year]
        coverage[str(year)]=dict(source_local_candidates=len(rows),
            eligibility_status_counts=dict(collections.Counter(r['eligibility_status'] for r in rows)),
            crosswalk_status_counts=dict(collections.Counter(r['crosswalk_status'] for r in xr)),
            automatic_eligibility_rows=0, full_cohort_complete=False)
    manifest=dict(schema_version=1, sources=sources, identity_source=key_meta,
        cutoff_rules={str(y):dict(draft_date=DRAFT_DATES[y],draft_date_source=f'{y}_final',
            withdrawal_deadline=WITHDRAWAL_DEADLINES[y],withdrawal_deadline_source=f'{y}_initial',
            registry_cutoff_date=cutoffs[y]) for y in DRAFT_DATES},
        years_requested=list(range(2007,2015)),years_with_pilot_facts=list(DRAFT_DATES),years_not_collected=list(range(2007,2012)),
        coverage=coverage,event_rows=len(events),registry_rows=len(registry),
        complete_predraft_universe=False,model_ready=False,models_fit=0,outcome_sources_read=[],
        limitations=['Only NBA early-entry candidates; seniors and other automatic entrants are not collected.',
            'Source-local IDs do not certify global person identity; do not fit until aliases/homonyms are resolved.',
            'Initial declarations missing a name-matched final decision remain unresolved; no absence-based eligibility inference.',
            'The 2012 initial attachment was not fetched; exact individual filing dates are not recovered.',
            '2012 initial aggregate is 66 while the final named lists total 67; no invented reconciliation.',
            '2013 initial aggregate is 77 while final lists total 78; changed name spellings remain unresolved separately.',
            'Public publisher datelines are historical evidence but no independently timestamped archive snapshot was recovered.',
            'No full copyrighted page bodies, height/birth-date columns or outcomes are exported.'],
        acquisition=dict(direct_http_attempts=1,direct_http_status=403,direct_http_retries=0,
            primary_page_access='web tool source text views',further_source_collection='bounded pilot stopped at three years'))
    dump(args.out/'manifest.json',manifest)
    dump(args.out/'coverage.json',dict(coverage=coverage,event_rows=len(events),registry_rows=len(registry),complete_predraft_universe=False,model_ready=False))
    print(json.dumps(dict(coverage=coverage,event_rows=len(events),registry_rows=len(registry)),indent=2))

if __name__=='__main__':
    main()

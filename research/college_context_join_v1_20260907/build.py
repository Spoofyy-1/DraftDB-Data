"""Quarantined candidate joins only. No network, labels, models or name matching."""
from pathlib import Path
import collections,csv,datetime as dt,gzip,hashlib,json,math
R=Path(__file__).resolve().parent;W=R.parent
GAME=W/'college_player_games_v1';TEAM=W/'team_context_v1'
POOL=W/'verified_inputs_v2/train_inputs.csv';LINEAGE=W/'fifty_audit/source_row_lineage.json'
COLLEGE41=W/'r8w/data/features.csv'
COUNTS=['two_m','two_a','three_m','three_a','ft_m','ft_a','points','orb','drb','ast','tov','stl','blk','pf']
GAME_COLS=['cgd_observed_gp']+['cgd_'+n+'_pg' for n in COUNTS]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def subject(season,tpid,team):return 'subject_'+digest((season,str(tpid),team))[:24]
def team_id(name):return 'team_'+hashlib.sha256(name.encode()).hexdigest()[:20]
def rows(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))
def keyed(data,key):
    out={}
    for x in data:
        k=key(x);assert k not in out,'duplicate_join_key';out[k]=x
    return out

def verify_inputs():
    pins={}
    def pin(p,expected=None):
        h=sha(p);assert expected is None or h==expected,'source_hash_changed: '+str(p);pins[str(p.relative_to(W))]=h
    pm=json.loads((W/'verified_inputs_v2/manifest.json').read_text());e=next(x for x in pm['files'] if x['file']=='train_inputs.csv');assert e['rows']==1458;pin(POOL,e['sha256']);pin(W/'verified_inputs_v2/manifest.json')
    sm=json.loads((W/'r8w/data/manifest.json').read_text());pin(COLLEGE41,sm['files']['features.csv'])
    for root,names in [(GAME,['source_manifest.json','schema_manifest.json']), (TEAM,['team_context_train_candidates.csv','provenance.csv','quarantine.csv','summary.json','feature_dictionary.json']), (W/'verified_mock_bio',['manifest.json']), (W/'verified_mock_bio_extension',['manifest.json'])]:
        allow=json.loads((root/'PUBLIC_ALLOWLIST.json').read_text());pin(root/'PUBLIC_ALLOWLIST.json')
        for name in names:pin(root/name,allow['files'][name]['sha256'])
    summary=json.loads((TEAM/'summary.json').read_text());pin(LINEAGE,summary['focal_lineage_sha256']);pin(W/'fifty_audit/lineage_audit.json');pin(W/'r8/context_manifest.json')
    audit=json.loads((W/'fifty_audit/lineage_audit.json').read_text());assert audit['same_team_player_duplicate_rows']==0 and audit['source_player_ids_with_multiple_model_pids']==0
    old=R/'input_pins.json'
    if old.exists():assert json.loads(old.read_text())==pins,'input_registration_changed'
    else:old.write_text(json.dumps(pins,indent=2))
    return pins

def dates():
    result={}
    for p,key in [(W/'verified_mock_bio/manifest.json','sources'),(W/'verified_mock_bio_extension/manifest.json','source_tables')]:
        for s in json.loads(p.read_text())[key]:
            year=int(s['draft_year'])
            if year>2018:continue
            day=dt.date.fromisoformat(s['draft_date']);assert day.year==year
            assert year not in result or result[year]==day,'inconsistent_registered_draft_date';result[year]=day
    return result

def source_date_status(season,year,mindate,maxdate,cutoffs):
    try:
        if not 2008<=season<=min(year,2018):return 'source_season_after_draft_or_outside_scope'
        if year not in cutoffs:return 'unverified_draft_cutoff'
        first=dt.date.fromisoformat(mindate);last=dt.date.fromisoformat(maxdate)
        if not dt.date(season-1,7,1)<=first<=last<=dt.date(season,5,31):return 'game_date_outside_source_season'
        if last>=cutoffs[year]:return 'game_not_strictly_before_draft'
        return None
    except (TypeError,ValueError):return 'invalid_or_missing_game_date'

def game_status(focal,year,audit,candidate,entry,cutoffs):
    if audit is None or candidate is None:return 'missing_player_game_source_group'
    season=int(focal['season'])
    if not audit['source_consistent'] or audit['quarantine_reasons']:return 'quarantined_player_game_source_group'
    if audit['model_eligible'] is not False:return 'unexpected_source_admission_flag'
    if int(audit['source_season'])!=season or int(candidate['source_season'])!=season:return 'source_identity_season_disagreement'
    if int(audit['annual_source_row_zero_based'])!=int(focal['source_row']):return 'annual_source_row_disagreement'
    if focal['source']!=entry['annual_source']['filename'] or audit['annual_source_sha256']!=entry['annual_source']['sha256'] or audit['source_sha256']!=entry['sha256']:return 'source_provenance_disagreement'
    reason=source_date_status(season,year,audit['game_date_min'],audit['game_date_max'],cutoffs)
    if reason:return reason
    gp=int(audit['valid_parsed_game_rows'])
    if gp<=0 or gp!=int(audit['annual_gp']) or float(candidate['cgd_observed_gp'])!=gp:return 'observed_gp_disagreement'
    for n in COUNTS:
        try:v=float(candidate['cgd_'+n+'_pg'])
        except (ValueError,TypeError):return 'missing_candidate_statistic'
        if not math.isfinite(v) or v!=audit['direct_game_totals'][n]/gp:return 'candidate_arithmetic_disagreement'
    return None

def load(max_season=2018):
    pins=verify_inputs();base=rows(POOL);assert len(base)==1458 and len(base[0])==539
    bypid=keyed(base,lambda r:r['pid']);assert all(2000<=int(r['draft_year'])<=2018 for r in base)
    lineage=[r for r in json.loads(LINEAGE.read_text()) if int(r['draft_year'])<=2018];ld=keyed(lineage,lambda r:r['pid'])
    assert len(lineage)==790 and sum(p in bypid for p in ld)==671
    cuts=dates();manifest=json.loads((GAME/'source_manifest.json').read_text());allow=json.loads((GAME/'PUBLIC_ALLOWLIST.json').read_text())
    context_hashes=json.loads((W/'r8/context_manifest.json').read_text())['source_hashes']
    audits={};candidates={};entries={};consumed={}
    for entry in manifest['sources']:
        y=entry['source_season']
        if y>max_season:continue
        assert y<=2018 and context_hashes[entry['annual_source']['filename']]==entry['annual_source']['sha256'],'college_source_version_disagreement'
        entries[y]=entry
        for name in [f'data/audit_{y}.json.gz',f'data/candidates_{y}.csv']:
            assert sha(GAME/name)==allow['files'][name]['sha256'],'game_artifact_hash_changed';consumed[name]=allow['files'][name]['sha256']
        ar=json.loads(gzip.decompress((GAME/f'data/audit_{y}.json.gz').read_bytes()));cr=rows(GAME/f'data/candidates_{y}.csv')
        for target,data in [(audits,ar),(candidates,cr)]:
            for item in data:
                k=(int(item['source_season']),item['source_subject_id']);assert k not in target;target[k]=item
    tr=[r for r in rows(TEAM/'team_context_train_candidates.csv') if int(r['source_season'])<=max_season]
    tc=keyed(tr,lambda r:r['pid']);tp=keyed([r for r in rows(TEAM/'provenance.csv') if int(r['source_season'])<=max_season],lambda r:r['pid']);tq=keyed(rows(TEAM/'quarantine.csv'),lambda r:r['pid'])
    tcols=sorted(json.loads((TEAM/'feature_dictionary.json').read_text()));assert len(tcols)==20
    return base,ld,cuts,audits,candidates,entries,tc,tp,tq,tcols,pins,consumed

def project(data,max_draft_year=None):
    base,ld,cuts,audits,candidates,entries,tc,tp,tq,tcols,pins,consumed=data
    output=[];provenance=[];coverage=collections.defaultdict(collections.Counter);reasons=collections.Counter()
    for index,b in enumerate(base):
        pid=b['pid'];year=int(b['draft_year'])
        if max_draft_year is not None and year>max_draft_year:continue
        row={'pid':pid,'draft_year':b['draft_year'],**{c:'' for c in GAME_COLS+tcols}}
        g_reason=t_reason='no_verified_focal_college_lineage';info=ld.get(pid);record={'pid':pid,'draft_year':year,'input_row_zero_based':index,'model_eligible':False}
        if info:
            f=info['focal'];season=int(f['season']);key=(season,subject(season,f['tpid'],f['team']))
            assert int(info['draft_year'])==year and not info['team_has_duplicate_tpid'],'focal_identity_disagreement'
            record.update(source_season=season,source_subject_id=key[1],focal_lineage_hash=digest(f),registered_draft_date=cuts[year].isoformat() if year in cuts else None)
            a=audits.get(key);g=candidates.get(key);entry=entries.get(season)
            g_reason='source_season_unavailable' if entry is None else game_status(f,year,a,g,entry,cuts)
            if g_reason is None:
                row.update({c:g[c] for c in GAME_COLS});record.update(player_game_min_date=a['game_date_min'],player_game_max_date=a['game_date_max'],player_game_source_sha256=a['source_sha256'],annual_source_sha256=a['annual_source_sha256'],annual_source_row_zero_based=a['annual_source_row_zero_based'])
            t=tc.get(pid);p=tp.get(pid)
            t_reason='quarantined_or_missing_team_context' if pid in tq or t is None or p is None else None
            if t_reason is None:
                if int(t['draft_year'])!=year or int(t['source_season'])!=season or int(p['draft_year'])!=year or int(p['source_season'])!=season or p['team_id']!=team_id(f['team']) or int(p['college_source_row'])!=int(f['source_row']) or p['college_allowed_values_hash']!=f['allowed_values_hash']:t_reason='team_context_focal_provenance_disagreement'
                else:t_reason=source_date_status(season,year,p['min_game_date'],p['max_game_date'],cuts)
                if t_reason is None and any(not t[c] or not math.isfinite(float(t[c])) for c in tcols):t_reason='incomplete_team_context_candidates'
                if t_reason is None:
                    row.update({c:t[c] for c in tcols});record.update(team_game_min_date=p['min_game_date'],team_game_max_date=p['max_game_date'],team_totals_source_sha256=p['source_totals_sha256'],team_cached_games=int(p['validated_games']))
            coverage[year]['has_focal_lineage']+=1
        coverage[year]['full_pool_rows']+=1;coverage[year]['game_candidates']+=g_reason is None;coverage[year]['team_candidates']+=t_reason is None;coverage[year]['both_families']+=g_reason is None and t_reason is None
        record.update(game_join_reason=g_reason,team_join_reason=t_reason)
        reasons['game:'+str(g_reason)]+=1;reasons['team:'+str(t_reason)]+=1
        output.append(row);provenance.append(record)
    return output,provenance,dict(coverage),dict(reasons)

def write_csv(path,rows):
    with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def overlap(candidate_rows):
    # Only metadata plus41 named source features are projected; draft-result metadata is ignored.
    with COLLEGE41.open(newline='') as f:
        reader=csv.reader(f);header=next(reader);cols=[c for c in header if c.startswith(('ctx_base_','ctx_skill_'))];assert len(cols)==41
        keep=['pid','draft_year']+cols;idx=[header.index(c) for c in keep];study=[dict(zip(keep,[r[i] for i in idx])) for r in reader]
    d=keyed(study,lambda r:r['pid']);results=[]
    mapping={'cgd_observed_gp':('ctx_base_gp',False),'cgd_two_m_pg':('ctx_base_fg2m',True),'cgd_two_a_pg':('ctx_base_fg2a',True),'cgd_three_m_pg':('ctx_base_fg3m',True),'cgd_three_a_pg':('ctx_base_fg3a',True),'cgd_ft_m_pg':('ctx_base_ftm',True),'cgd_ft_a_pg':('ctx_base_fta',True),'cgd_orb_pg':('ctx_base_oreb_pg',False),'cgd_drb_pg':('ctx_base_dreb_pg',False),'cgd_ast_pg':('ctx_base_ast_pg',False),'cgd_stl_pg':('ctx_base_stl_pg',False),'cgd_blk_pg':('ctx_base_blk_pg',False)}
    for feature,(column,divide) in mapping.items():
        n=exact=rounded=0;maxerr=0.
        for r in candidate_rows:
            b=d.get(r['pid'])
            if b is None or not r[feature] or not b[column] or not b['ctx_base_gp']:continue
            expected=float(b[column])/(float(b['ctx_base_gp']) if divide else 1);value=float(r[feature]);err=abs(value-expected)
            n+=1;exact+=err<=1e-12;rounded+=err<=.00005001;maxerr=max(maxerr,err)
        results.append({'candidate':feature,'existing_formula':column+('/ctx_base_gp' if divide else ''),'paired_observed_rows':n,'equal_within_1e_minus12':exact,'equal_within_4_decimal_rounding':rounded,'max_abs_difference':maxerr})
    n=match=0
    for r in candidate_rows:
        b=d.get(r['pid'])
        if b is None or not r['cgd_points_pg'] or any(not b[c] for c in ['ctx_base_gp','ctx_base_fg2m','ctx_base_fg3m','ctx_base_ftm']):continue
        expected=(2*float(b['ctx_base_fg2m'])+3*float(b['ctx_base_fg3m'])+float(b['ctx_base_ftm']))/float(b['ctx_base_gp']);n+=1;match+=abs(float(r['cgd_points_pg'])-expected)<=1e-12
    results.append({'candidate':'cgd_points_pg','existing_formula':'(2*ctx_base_fg2m+3*ctx_base_fg3m+ctx_base_ftm)/ctx_base_gp','paired_observed_rows':n,'equal_within_1e_minus12':match})
    return {'study_pool_rows':len(study),'source41_columns':cols,'study_rows_with_game_candidates':sum(r['pid'] in d and bool(r['cgd_observed_gp']) for r in candidate_rows),'study_rows_with_team_candidates':sum(r['pid'] in d and bool(r['tctx_points_pg']) for r in candidate_rows),'algebraic_or_direct_comparisons':results,'direct_event_new_fields':['cgd_tov_pg','cgd_pf_pg'],'interpretation':'GP and six shooting rates plus scoring rate are representations of existing GP/shooting totals on paired rows. Other player rates repair source-subset differences. TOV/PF use direct events where current41 uses rounded rates/ratios; no claim of predictive improvement. Team-context fields describe team/opponent events absent from the current41 player-only source columns.','outcomes_or_model_results_used':False}

def main():
    data=load();out,provenance,coverage,reasons=project(data);base=data[0]
    assert not set(GAME_COLS+data[9])&set(base[0]),'candidate_name_collision'
    assert [(r['pid'],r['draft_year']) for r in out]==[(r['pid'],r['draft_year']) for r in base]
    write_csv(R/'candidate_inputs.csv',out)
    augmented=[{**b,**{k:v for k,v in o.items() if k not in ['pid','draft_year']}} for b,o in zip(base,out)]
    assert all([r[k] for k in b]==list(b.values()) for r,b in zip(augmented,base));write_csv(R/'private/full_pool_with_candidates.csv',augmented)
    for name,obj in [('join_provenance.json',provenance),('coverage.json',coverage),('excluded_reasons.json',reasons),('overlap_with_source41.json',overlap(out)),('consumed_game_files.json',data[-1])]:
        (R/name).write_text(json.dumps(obj,indent=2))
    summary={'pool_rows':len(base),'original_columns_preserved':len(base[0]),'candidate_columns':35,'focal_lineage_intersections':sum(c['has_focal_lineage'] for c in coverage.values()),'lineages_outside_pool_not_appended':119,'game_candidates':sum(c['game_candidates'] for c in coverage.values()),'team_candidates':sum(c['team_candidates'] for c in coverage.values()),'both_families':sum(c['both_families'] for c in coverage.values()),'input_pid_order_hash':digest([r['pid'] for r in base]),'model_eligible':False,'network_requests':0,'models_labels_or_results_used':False}
    (R/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
if __name__=='__main__':main()

"""Publishable feature tables; every row passes historical source and review gates."""
from pathlib import Path
import csv,json,hashlib,collections,datetime,zoneinfo,re,unicodedata
R=Path(__file__).parent
P=json.load(open(R.parents[1]/'collectors/players.json'));byid={p['pid']:p for p in P}
def norm(s):return ''.join(c for c in unicodedata.normalize('NFKD',s).lower() if c.isalnum())
def unit(metric):
 if metric.endswith('_per1k'):return 'matched terms per 1000 section words'
 if metric.endswith('_ppp'):return 'points per possession'
 if metric.endswith('_pps'):return 'points per shot'
 if metric.endswith('_pct'):return 'percent (0..100); named event denominator'
 if metric.endswith('_poss_pg') or metric=='report_poss_pg':return 'possessions per game'
 if metric.endswith('_fga_pg'):return 'field-goal attempts per game'
 if metric.endswith('_total') or metric.endswith('_count') or metric.endswith('_words'):return 'count'
 return 'binary source-reported status'
def denominator(metric):
 if metric.endswith('_per1k'):return '1000 words in the validated player section or report'
 if metric.endswith('_ppp'):return 'possessions of the named play type; all possessions for overall'
 if metric.endswith('_pps'):return 'shot attempts of the named play type'
 if metric.endswith('_fg_pct'):return 'field-goal attempts of the named play type'
 if metric.endswith('_turnover_pct'):return 'possessions of the named play type; all possessions when unqualified'
 if metric.endswith('_shots_fouled_pct'):return 'source-defined shot opportunities in the named play context; not interchangeable with free_throw_poss_pct'
 if metric=='report_jump_shot_pct':return 'all field-goal attempts; numerator is jump-shot attempts'
 if metric.endswith('_poss_pct'):return 'all player possessions; numerator is the named play/event category'
 if metric.endswith('_pg'):return 'games in the season or sample described by the article'
 return 'not a rate'
meta={json.load(open(p))['source_id']:json.load(open(p)) for p in R.glob('dx*.json') if json.load(open(p)).get('feature_eligible')}
base=[]
for row in csv.DictReader(open(R.parent/'pilot_observations_eligible.csv')):
 row['value']=float(row['value']);row['draft_year']=int(row['draft_year'])
 capture=datetime.datetime.strptime(row['capture_timestamp'],'%Y%m%d%H%M%S').replace(tzinfo=datetime.timezone.utc).isoformat()
 base.append({'pid':row['pid'],'draft_year':row['draft_year'],'source_id':row['source_id'],'source_url':row['source_url'],'archive_url':row['archive_url'],'publication_date':row['published_date'],'capture_utc':capture,'metric':row['metric'],'value':row['value'],'unit':unit(row['metric']),'method':'earlier_manually_verified_archive_fact','evidence_sha256':row['source_sha256']})
for row in csv.DictReader(open(R/'observations_candidate.csv')):
 if not row['metric'].startswith('report_text_'):continue
 base.append({k:row[k] for k in ['pid','source_id','source_url','archive_url','publication_date','capture_utc','metric']}|{'draft_year':int(row['draft_year']),'value':float(row['value']),'unit':row['unit'],'method':'fixed_lexicon_count_in_unique_subject_archived_section','evidence_sha256':row['section_sha256']})
reviews={r['candidate_key']:r for r in json.load(open(R/'numeric_review.json'))}
unreviewed=[];rejected=[]
for row in json.load(open(R/'private/numeric_candidates.json')):
 key=hashlib.sha256((row['pid']+'|'+row['source_id']+'|'+row['private_context']+'|'+str(row['value'])).encode()).hexdigest();review=reviews.get(key)
 if not review:unreviewed.append({'candidate_key':key,'pid':row['pid'],'source_id':row['source_id'],'value':row['value']});continue
 if review['decision']!='approve':rejected.append(review);continue
 metric=review['metric']
 base.append({k:row[k] for k in ['pid','draft_year','source_id','source_url','archive_url','publication_date','capture_utc']}|{'metric':metric,'value':float(row['value']),'unit':unit(metric),'method':'rule_discovery_with_manual_fact_and_denominator_review','evidence_sha256':row['body_sha256']})
for f in R.glob('manual_20*.json'):
 x=json.load(open(f));d=meta[x['source_id']];body=(R/'private'/f"{x['source_id']}.body.txt").read_text()
 numbers={float(a) for a in re.findall(r'(?<!\w)(?:\d+\.?\d*|\.\d+)',body)}
 for name,fields in x['players'].items():
  matches=[p for p in P if p['draft_year']==d['draft_year'] and norm(p['name'])==norm(name)]
  if len(matches)!=1:continue
  p=matches[0];assert norm(name) in norm(body)
  for metric,v in fields.items():
   assert float(v) in numbers,(x['source_id'],name,metric,v)
   metric='report_'+metric
   base.append({'pid':p['pid'],'draft_year':p['draft_year'],'source_id':x['source_id'],'source_url':d['source']['original'],'archive_url':d['archive_url'],'publication_date':d['publication_date'],'capture_utc':d['capture_utc'],'metric':metric,'value':float(v),'unit':unit(metric),'method':'manual_explicit_fact_transcription_checked_against_archive','evidence_sha256':d['body_sha256']})
for row in base:
 p=byid[row['pid']];assert p['draft_year']==row['draft_year']
 cap=datetime.datetime.fromisoformat(row['capture_utc']);cut=datetime.datetime.fromisoformat(p['draft_date']).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York'))
 assert cap<cut,(row['source_id'],cap,cut)
 assert row['publication_date']<p['draft_date']
 assert row['metric'].startswith('report_')
groups=collections.defaultdict(list)
for r in base:groups[(r['pid'],r['metric'])].append(r)
rows=[];conflicts=[]
for key,items in groups.items():
 values={r['value'] for r in items}
 if len(values)>1:
  conflicts.append({'pid':key[0],'metric':key[1],'values':list(values),'source_ids':list(set(r['source_id'] for r in items))});continue
 rows.append(items[0])
wide={};numeric={};text={}
for r in rows:
 d=wide.setdefault(r['pid'],{'pid':r['pid'],'draft_year':r['draft_year']});d[r['metric']]=r['value']
 family=text if r['metric'].startswith('report_text_') else numeric
 d=family.setdefault(r['pid'],{'pid':r['pid'],'draft_year':r['draft_year']});d[r['metric']]=r['value']
for filename,data in [('features_eligible.csv',wide),('numeric_features_eligible.csv',numeric),('text_features_eligible.csv',text)]:
 columns=['pid','draft_year']+sorted({k for d in data.values() for k in d if k not in ['pid','draft_year']})
 with (R/filename).open('w') as f:
  w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(data.values())
with (R/'observations_eligible.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(R/'final_conflicts_quarantined.json').write_text(json.dumps(conflicts,indent=2))
(R/'numeric_pending_review.json').write_text(json.dumps(unreviewed,indent=2))
(R/'numeric_rejected.json').write_text(json.dumps(rejected,indent=2))
dictionary={r['metric']:{'unit':r['unit'],'denominator':denominator(r['metric']),'family':'fixed_lexicon_text' if r['metric'].startswith('report_text_') else 'reported_representation' if 'agent' in r['metric'] or 'listed_' in r['metric'] else 'camp_invitations' if 'invited' in r['metric'] else 'synergy_situational','missing_policy':'missing, never inferred zero for an unobserved player','interpretation':'literal term frequency is topic coverage, not sentiment or a scouting grade' if r['metric'].startswith('report_text_') else 'source-reported factual value; PPP and PPS remain distinct'} for r in rows}
(R/'metric_dictionary.json').write_text(json.dumps(dictionary,indent=2))
summary={'eligible_observations':len(rows),'eligible_players':len(wide),'eligible_metrics':len(dictionary),'numeric_players':len(numeric),'text_players':len(text),'per_year':{str(y):{'all':len([d for d in wide.values() if d['draft_year']==y]),'numeric':len([d for d in numeric.values() if d['draft_year']==y]),'text':len([d for d in text.values() if d['draft_year']==y])} for y in sorted({d['draft_year'] for d in wide.values()})},'numeric_unreviewed':len(unreviewed),'conflicting_features_quarantined':len(conflicts),'source_time_policy':'strictly before midnight America/New_York on each player draft date','training_or_test_scoring_performed':False,'next_step':'Separate numeric Synergy and fixed-lexicon text family ablations; use original folds, seeds, outcome calendar cutoffs and complete class denominator'}
(R/'summary_final.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))

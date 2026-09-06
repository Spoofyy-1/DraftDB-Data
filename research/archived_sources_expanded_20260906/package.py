"""Build source-only matrices and an explicit public allowlist; no labels loaded."""
from pathlib import Path
import csv,json,hashlib
R=Path(__file__).parent
dictionary=json.load(open(R/'metric_dictionary.json'))
rows=list(csv.DictReader(open(R/'observations_eligible.csv')))
numeric=[x for x in rows if dictionary[x['metric']]['family']=='synergy_situational']
text=[x for x in rows if dictionary[x['metric']]['family']=='fixed_lexicon_text']
wide={};controls={}
for x in numeric:wide.setdefault(x['pid'],{'pid':x['pid'],'draft_year':x['draft_year']})[x['metric']]=x['value']
with (R/'synergy_features_eligible.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=['pid','draft_year']+sorted({x['metric'] for x in numeric}));w.writeheader();w.writerows(wide.values())
for x in rows:
 q=controls.setdefault(x['pid'],{'pid':x['pid'],'draft_year':x['draft_year'],'control_numeric_observed_metrics':0,'control_text_observed_metrics':0})
 family=dictionary[x['metric']]['family']
 if family=='synergy_situational':q['control_numeric_observed_metrics']+=1
 if family=='fixed_lexicon_text':q['control_text_observed_metrics']+=1
for q in controls.values():
 q['control_numeric_available']=int(q['control_numeric_observed_metrics']>0)
 q['control_text_available']=int(q['control_text_observed_metrics']>0)
with (R/'coverage_controls.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(next(iter(controls.values()))));w.writeheader();w.writerows(controls.values())
def counts(rr):return {'players':len({x['pid'] for x in rr}),'observations':len(rr),'metrics':len({x['metric'] for x in rr})}
coverage={'scope':'exact pid identity matches in verified sources; coverage relative to model input matrix must be rechecked at integration','synergy_total':counts(numeric),'text_total':counts(text),'folds':[]}
for traincut,val in [(2010,2012),(2011,2013),(2012,2014)]:
 tr=[x for x in numeric if int(x['draft_year'])<=traincut];va=[x for x in numeric if int(x['draft_year'])==val]
 cols={x['metric'] for x in tr}
 coverage['folds'].append({'training_draft_year_at_most':traincut,'validation_draft_year':val,'numeric_training':counts(tr),'numeric_validation':counts(va),'numeric_validation_with_training_observed_column':counts([x for x in va if x['metric'] in cols]),'text_training':counts([x for x in text if int(x['draft_year'])<=traincut]),'text_validation':counts([x for x in text if int(x['draft_year'])==val])})
(R/'family_coverage.json').write_text(json.dumps(coverage,indent=2))
sources={}
old=json.load(open(R.parent/'validated_sources.json'))
validated=set(json.load(open(R.parent/'validation_summary.json'))['archive_sources_validated'])
for sid in validated:
 d=old[sid];a=d['archival_evidence']
 sources[sid]={'source_id':sid,'source_url':d['url'],'publication_date':d['published_date'],'archive_url':a['archive_url'],'capture_timestamp':a['capture_timestamp'],'html_sha256':a['sha256'],'feature_eligible':True,'validation_basis':'completed earlier pilot validate_pilot.py fact and historical-capture checks','body_boundary':d['body_section']}
for f in R.glob('dx*.json'):
 d=json.load(open(f));sources[d['source_id']]=d
for d in json.load(open(R/'nba_validation.json')):sources[f"nba{d['draft_year']}_pilot"]=d
(R/'source_manifest.json').write_text(json.dumps(sources,indent=2))
allow=[
 'README.md','summary_final.json','family_coverage.json','metric_dictionary.json','cutoff_overrides.json','extraction_rules.json',
 'features_eligible.csv','numeric_features_eligible.csv','synergy_features_eligible.csv','text_features_eligible.csv','observations_eligible.csv','coverage_controls.csv',
 'nba_text_features_eligible.csv','nba_observations_eligible.csv','nba_validation.json','source_manifest.json',
 'sections.json','manual_2011.json','manual_2012.json','numeric_review.json','numeric_rejected.json','final_conflicts_quarantined.json',
 'discover.py','collect.py','repair_bodies.py','extract.py','finalize.py','package.py','discover_nba.py','collect_nba_pilot.py','validate_nba.py','discover_nba_stats.py',
 'discovery.json','collection_state.json'
]
allow+=sorted(str(f.relative_to(R)) for f in (R/'nba_discovery').glob('*.json'))
manifest={'policy':'Only listed files may be published. Do not recursively copy this directory. Candidate, unreviewed, and private files are not model inputs.','publish_exclude':['private/','observations_candidate.csv','numeric_pending_review.json','unresolved_sections.json','numeric_conflicts.json'],'files':{}}
for relative in allow:
 p=R/relative;assert p.is_file();assert 'private' not in p.relative_to(R).parts
 raw=p.read_bytes();manifest['files'][relative]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
(R/'public_manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'publishable_files':len(manifest['files']),'synergy':counts(numeric),'text':counts(text),'inference_pilot_rows':len(list(csv.DictReader(open(R/'nba_text_features_eligible.csv'))))},indent=2))

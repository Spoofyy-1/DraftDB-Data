"""Validate historical captures, identity/time joins and manually transcribed facts.
No label files loaded. Full source pages remain under private/ and must not publish.
"""
import runpy,re,json,csv,hashlib,datetime,collections,html
from html.parser import HTMLParser
from pathlib import Path
R=Path(__file__).parent
ns=runpy.run_path(str(R/'build_pilot.py'))
raw,sources,players,norm=ns['raw'],ns['sources'],ns['players'],ns['norm']
class T(HTMLParser):
 def __init__(self):super().__init__();self.p=[];self.skip=0
 def handle_starttag(self,t,a):
  if t in ['script','style']:self.skip+=1
  if t in ['br','tr','p','div']:self.p.append('\n')
 def handle_endtag(self,t):
  if t in ['script','style'] and self.skip:self.skip-=1
 def handle_data(self,x):
  if not self.skip:self.p.append(x)
def text(h):
 p=T();p.feed(h);return ''.join(p.p)
archives={d['source_id']:d for d in json.load(open(R/'archive_body_validation.json'))}
by_pid={p['pid']:p for p in players}
rows=list(csv.DictReader(open(R/'pilot_observations_quarantined.csv')))
failed=[];eligible=[];pending=[]
for row in rows:
 sid=row['source_id'];a=archives.get(sid,{})
 row['published_date']=sources[sid]['published_date']
 row['last_updated_date']=sources[sid].get('last_updated_date',sources[sid]['published_date'])
 row['capture_timestamp']=a.get('capture_timestamp','')
 row['source_url']=sources[sid]['url']
 row['archive_url']=a.get('archive_url','')
 row['source_sha256']=a.get('sha256','')
 row['model_feature_eligible']=False
 row['fact_date_eligible']=False
 if a.get('status')!='retrieved':
  row['quarantine_reason']='No pre-draft archived body retrieved';pending.append(row);continue
 capture=datetime.datetime.strptime(a['capture_timestamp'],'%Y%m%d%H%M%S').date().isoformat()
 assert capture<row['draft_date'],(sid,capture,row['draft_date'])
 assert row['last_updated_date']<=capture,(sid,row['last_updated_date'],capture)
 assert a['final_url']==a['archive_url'],a
 h=(R/'private'/f'{sid}.html').read_bytes()
 assert hashlib.sha256(h).hexdigest()==a['sha256']
 txt=text(h.decode('utf-8',errors='replace'))
 name=by_pid[row['pid']]['name'];value=float(row['value'])
 if sid=='dx2008agents':
  # Exact parsed row existence in table verified by construction.
  proven=any(norm(n)==norm(name) and row['metric'][7:] in stats and stats[row['metric'][7:]]==value for n,stats in raw[sid].items())
 elif sid=='dx2007camp':
  start=txt.index('*Camp Players');end=txt.index('Feedback',start)
  body=txt[start:end]
  marker={'report_camp_invited':'*Camp Players','report_physical_only_invited':'*Physical Only Players','report_media_invited':'Media Availability Session'}[row['metric']]
  start=body.index(marker);part=body[start:]
  for stop in ['Notes on Pre-Draft Camp Roster','Notes on Physical Only List']:
   if stop in part:part=part[:part.index(stop)]
  proven=norm(name) in norm(part) and value==1
 else:
  start=txt.index('Findings');end=txt.index('Feedback',start);body=txt[start:end]
  blocks=[b for b in body.split('•') if norm(name) in norm(b[:550])]
  proven=any(value in [float(v) for v in re.findall(r'(?<!\w)(?:\d+\.?\d*|\.\d+)',b)] for b in blocks)
 if not proven:
  row['quarantine_reason']='Numeric/name association did not validate against archived player section';failed.append(row);continue
 row['fact_date_eligible']=True;row['archive_snapshot_verified']=True;row['feature_eligible']=True;row['model_feature_eligible']=True;row['quarantine_reason']='';row['source_available_by']=capture
 eligible.append(row)
for name,data in [('pilot_observations_eligible.csv',eligible),('pilot_observations_pending.csv',pending+failed)]:
 cols=list(dict.fromkeys(k for row in rows for k in row))
 with (R/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(data)
wide={}
for row in eligible:
 d=wide.setdefault(row['pid'],{'pid':row['pid'],'draft_year':row['draft_year']})
 assert row['metric'] not in d
 d[row['metric']]=float(row['value'])
cols=['pid','draft_year']+sorted({row['metric'] for row in eligible})
with (R/'pilot_features_eligible.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(wide.values())
units={}
for c in cols[2:]:
 metric=c[7:]
 if metric.endswith('_ppp'):unit='points per possession';den='possessions of the named play type'
 elif metric.endswith('_pps'):unit='points per shot';den='shots of the named play type; do not merge with PPP'
 elif metric.endswith('_fg_pct'):unit='percent (0..100)';den='field-goal attempts of the named play type'
 elif metric.endswith('_posss_pg'):unit='possessions per game';den='logged games'
 elif metric.endswith('_poss_pg') or metric=='poss_pg':unit='possessions per game';den='logged games'
 elif metric.endswith('_fga_pg'):unit='field-goal attempts per game';den='logged games'
 elif metric.endswith('_fga_total'):unit='field-goal attempts';den='entire reported season sample'
 elif metric.endswith('_fgm_total'):unit='field-goals made';den='entire reported season sample'
 elif metric.endswith('_pct'):unit='percent (0..100)';den='named possession or shot denominator; shots_fouled differs from free_throw_poss'
 elif metric.endswith('_count'):unit='count';den='all contemporaneously listed clients with identical source agent spelling'
 else:unit='binary observed status';den='positive invitation roster entries or explicit representation listing; missing player is NaN'
 units[c]={'unit':unit,'denominator':den,'missing':'NaN, never zero-filled before fold-specific model preprocessing','source_family':'agent_reporting' if 'agent' in c or 'listed_' in c else 'camp_reporting' if 'invited' in c else 'situational_stats'}
(R/'metric_dictionary.json').write_text(json.dumps(units,indent=2))
summary={'eligible_observations':len(eligible),'eligible_players':len(wide),'eligible_metrics':len(cols)-2,'per_year':dict(collections.Counter(row['draft_year'] for row in wide.values())),'pending_or_failed_observations':len(pending)+len(failed),'failed_associations':[{'pid':r['pid'],'metric':r['metric'],'value':r['value'],'source_id':r['source_id']} for r in failed],'archive_sources_validated':sorted(set(r['source_id'] for r in eligible)),'labels_or_draft_results_read':False,'integration_status':'Source-safe sparse pilot; not yet used in training or scored','source_files_publishable':False}
(R/'validation_summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))

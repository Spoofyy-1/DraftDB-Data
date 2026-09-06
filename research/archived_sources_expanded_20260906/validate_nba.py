"""Validate archived NBA draft profiles; only report text is allowed to features."""
from pathlib import Path
from html.parser import HTMLParser
import json,re,gzip,csv,hashlib,datetime,zoneinfo,unicodedata,collections
R=Path(__file__).parent;P=json.load(open(R.parents[1]/'collectors/players.json'));byid={p['pid']:p for p in P}
lexicons=json.load(open(R/'extraction_rules.json'))['lexicons']
def norm(s):return ''.join(c for c in unicodedata.normalize('NFKD',s).lower() if c.isalnum())
class Body(HTMLParser):
 def __init__(self):super().__init__();self.depth=0;self.p=[];self.found=False
 def handle_starttag(self,t,attrs):
  if t=='div':
   if self.depth:self.depth+=1
   elif not self.found and 'field-name-body' in dict(attrs).get('class','').split():self.depth=1;self.found=True
  if self.depth and t in ['br','p','li']:self.p.append('\n')
 def handle_endtag(self,t):
  if t=='div' and self.depth:self.depth-=1
 def handle_data(self,s):
  if self.depth:self.p.append(s)
records=[];states=[]
for f in sorted((R/'nba_discovery').glob('*_pilot.json')):
 d=json.load(open(f));y=d['draft_year'];p=byid[d['pid']];fp=R/'private'/f'nba{y}.html';state=dict(d)
 try:
  capture=datetime.datetime.strptime(d['source']['timestamp'],'%Y%m%d%H%M%S').replace(tzinfo=datetime.timezone.utc)
  draft_date='2026-06-23' if y==2026 else p['draft_date'];cutoff=datetime.datetime.fromisoformat(draft_date).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York'))
  assert capture<cutoff,'capture after pre-draft cutoff'
  raw=fp.read_bytes()
  if raw[:2]==b'\x1f\x8b':h=gzip.decompress(raw).decode('utf8')
  else:h=raw.decode('utf8')
  nxt=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',h,re.S)
  if nxt:
   obj=json.loads(nxt[1])['props']['pageProps']['prospect'];assert obj['season']==y;assert norm(obj['displayName'])==norm(p['name'])
   assert not any(k in obj.get('draftDetails',{}) for k in ['round','pick','draftedBy']),'assigned draft fields detected'
   txt=obj['contentText'];boundary='allowlisted Next.js prospect.contentText only; draftDetails checked then excluded; navigation and categoryPrimary excluded'
  else:
   parser=Body();parser.feed(h);assert parser.found;txt=''.join(parser.p);boundary='unique Drupal field-name-body div subtree; headers/navigation excluded'
   assert norm(p['name']) in norm(txt[:600]),'identity not in article opening'
  assert 800<len(txt)<25000
  assert not re.search(r'\b(?:selected|drafted)\s+(?:with|at|by|no\.)',txt,re.I),'selection claim requires manual review'
  plain=' '.join(txt.split());wc=len(re.findall(r'\b\w+\b',plain));bodysha=hashlib.sha256(plain.encode()).hexdigest()
  state['sha256_definition']='original HTTP response bytes; html decoding/decompression may change local html byte representation'
  state['local_html_file_sha256']=hashlib.sha256(raw).hexdigest()
  state.update({'status':'verified_predraft_body','feature_eligible':True,'draft_date':draft_date,'publication_date':None,'date_evidence':'original publication timestamp unavailable; historical archive capture proves availability before cutoff','source_available_by_utc':capture.isoformat(),'body_sha256':bodysha,'body_words':wc,'body_boundary':boundary,'text_source_credit':'Synergy Sports' if 'synergy' in plain.lower() else 'NBA-hosted draft profile; numeric Synergy attribution not claimed'})
  (R/'private'/f'nba{y}.body.txt').write_text(plain)
  common={'pid':p['pid'],'draft_year':y,'source_id':f'nba{y}_pilot','source_url':d['source']['original'],'archive_url':d['archive_url'],'publication_date':'','capture_utc':capture.isoformat(),'body_sha256':bodysha,'feature_eligible':True}
  records.append(common|{'metric':'report_text_words','value':wc,'unit':'count'})
  for key,pat in lexicons.items():records.append(common|{'metric':f'report_text_{key}_per1k','value':1000*len(re.findall(pat,plain,re.I))/wc,'unit':'literal matched terms per1000 words; not player grades'})
 except Exception as e:state.update({'status':'quarantined_validation','feature_eligible':False,'reason':str(e)})
 states.append(state)
(R/'nba_validation.json').write_text(json.dumps(states,indent=2))
with (R/'nba_observations_eligible.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
wide={}
for row in records:wide.setdefault(row['pid'],{'pid':row['pid'],'draft_year':row['draft_year']})[row['metric']]=row['value']
with (R/'nba_text_features_eligible.csv').open('w') as f:
 cols=['pid','draft_year']+sorted({r['metric'] for r in records});w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(wide.values())
print(json.dumps([{'year':d['draft_year'],'status':d['status'],'words':d.get('body_words'),'reason':d.get('reason')} for d in states],indent=2))

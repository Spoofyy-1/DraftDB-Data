from pathlib import Path
import json,urllib.parse,urllib.request,time,hashlib,unicodedata,re
R=Path(__file__).parent
P=json.load(open(R.parents[1]/'collectors/players.json'))
def norm(s):return ''.join(c for c in unicodedata.normalize('NFKD',s).lower() if c.isalnum())
for f in sorted((R/'nba_discovery').glob('*.json')):
 if not re.fullmatch(r'20\d\d\.json',f.name):continue
 d=json.load(open(f));y=d['draft_year'];out=R/'nba_discovery'/f'{y}_pilot.json'
 if out.exists():continue
 chosen=None
 for snap in d.get('snapshots',[]):
  if y==2026 and snap['timestamp']>='20260623040000':continue
  u=urllib.parse.urlsplit(snap['original']);slug=u.path.rstrip('/').split('/')[-1]
  if slug=='prospects' or '.' in slug or u.query:continue
  matches=[p for p in P if p['draft_year']==y and norm(p['name'])==norm(slug)]
  if len(matches)==1:chosen=(snap,matches[0]);break
 if not chosen:continue
 snap,p=chosen;url='https://web.archive.org/web/'+snap['timestamp']+'id_/'+snap['original']
 m={'draft_year':y,'pid':p['pid'],'source':snap,'archive_url':url,'feature_eligible':False,'status':'body_pending_validation','cutoff_utc':d['cutoff_utc']}
 if y==2026:m['cutoff_utc']='20260623040000'
 try:
  response=urllib.request.urlopen(url,timeout=35);raw=response.read();assert response.url==url
  m.update({'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'status':'downloaded_body_pending_validation'})
  (R/'private'/f'nba{y}.html').write_bytes(raw)
 except Exception as e:m['status']='unavailable';m['error']=str(e)
 out.write_text(json.dumps(m,indent=2));print(y,m['status'],m.get('bytes'),flush=True);time.sleep(.5)

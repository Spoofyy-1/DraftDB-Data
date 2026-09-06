from pathlib import Path
import json,urllib.parse,urllib.request,time
R=Path(__file__).parent
for y,to in [(2019,'20190620035959'),(2020,'20201118045959')]:
 q=[('url',f'stats.nba.com/articles/{y}-nba-draft-profile-'),('matchType','prefix'),('to',to),('output','json'),('filter','statuscode:200'),('filter','mimetype:text/html'),('collapse','urlkey'),('limit','150')]
 u='https://web.archive.org/cdx/search/cdx?'+urllib.parse.urlencode(q);d={'year':y,'query_url':u,'cutoff_utc':to,'feature_eligible':False,'status':'discovery_only'}
 try:
  j=json.load(urllib.request.urlopen(u,timeout=35));d['snapshots']=[dict(zip(j[0],x)) for x in j[1:]] if j else []
 except Exception as e:d['status']='unavailable';d['error']=str(e)
 (R/'nba_discovery'/f'{y}_stats_index.json').write_text(json.dumps(d,indent=2));print(y,d['status'],len(d.get('snapshots',[])),flush=True);time.sleep(.4)

from pathlib import Path
import urllib.request,urllib.parse,json,time,concurrent.futures,datetime,zoneinfo
R=Path(__file__).parent
(R/'nba_discovery').mkdir(exist_ok=True)
p=json.load(open(R.parents[1]/'collectors/players.json'));dates={a['draft_year']:a['draft_date'] for a in p}
for year,override in json.load(open(R/'cutoff_overrides.json')).items():dates[int(year)]=override['draft_date']
def one(y):
 f=R/'nba_discovery'/f'{y}.json'
 cutoff=datetime.datetime.fromisoformat(dates[y]).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York')).astimezone(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')
 if f.exists():
  cached=json.load(open(f))
  if cached['cutoff_utc']==cutoff:return cached
  # Preserve evidence of a previous cutoff, but narrow a cached index without
  # another network request when the corrected cutoff is earlier.
  if cutoff<cached['cutoff_utc']:
   cached['previous_cutoff_utc']=cached['cutoff_utc'];cached['cutoff_utc']=cutoff
   cached['snapshots']=[s for s in cached.get('snapshots',[]) if s['timestamp']<cutoff]
   cached['cutoff_correction_source']=json.load(open(R/'cutoff_overrides.json'))[str(y)]
   f.write_text(json.dumps(cached,indent=2));return cached
 q=[('url',f'www.nba.com/draft/{y}/prospects/'),('matchType','prefix'),('from',f'{y-1}0701'),('to',cutoff),('output','json'),('filter','statuscode:200'),('filter','mimetype:text/html'),('collapse','urlkey'),('limit','150')]
 u='https://web.archive.org/cdx/search/cdx?'+urllib.parse.urlencode(q)
 d={'draft_year':y,'query_url':u,'cutoff_utc':cutoff,'feature_eligible':False,'status':'discovery_only','retrieved_at':time.time()}
 try:
  j=json.load(urllib.request.urlopen(u,timeout=30));d['snapshots']=[dict(zip(j[0],x)) for x in j[1:]] if j else []
 except Exception as e:d['status']='unavailable';d['error']=str(e)
 f.write_text(json.dumps(d,indent=2));return d
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:d=list(pool.map(one,range(2019,2027)))
print(json.dumps([{'year':a['draft_year'],'status':a['status'],'snapshot_urls':len(a.get('snapshots',[]))} for a in d],indent=2))

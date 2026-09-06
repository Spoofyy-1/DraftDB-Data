from pathlib import Path
import concurrent.futures,urllib.request,json,time,hashlib
R=Path(__file__).parent
(R/'private').mkdir(exist_ok=True)
entries=json.load(open(R/'archive_index_validation.json'))
def one(d):
 sid=d['source_id'];r={'source_id':sid,'archive_body_verified':False}
 if not d.get('snapshots'):return r|{'status':'no_pre_draft_snapshot'}
 snap=d['snapshots'][0]
 url='https://web.archive.org/web/'+snap['timestamp']+'id_/'+snap['original']
 r.update({'archive_url':url,'capture_timestamp':snap['timestamp'],'original':snap['original'],'cdx_digest':snap['digest']})
 try:
  response=urllib.request.urlopen(url,timeout=35);raw=response.read();r['final_url']=response.url;r['sha256']=hashlib.sha256(raw).hexdigest();r['status']='retrieved';r['bytes']=len(raw);(R/'private'/f'{sid}.html').write_bytes(raw)
 except Exception as e:r['status']='unavailable';r['error']=str(e)
 return r
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(one,entries))
(R/'archive_body_validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

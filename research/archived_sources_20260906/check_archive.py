from pathlib import Path
import concurrent.futures,urllib.parse,urllib.request,json,time,hashlib
ROOT=Path(__file__).parent
sources=[('dx2007camp','http://www.draftexpress.com/viewarticle.php?a=2085','20070627'),('dx2008agents','http://www.draftexpress.com/article/2008-NBA-Draft-Prospects-Agent-Listings-2684/','20080625'),('dx2009guards','http://www.draftexpress.com/article/Situational-Statistics-This-Years-Point-Guard-Crop-3209/','20090624'),('dx2010sf','http://www.draftexpress.com/article/Situational-Statistics-This-Yearas-Small-Forward-Crop-3503/','20100623'),('dx2010pf','http://www.draftexpress.com/article/Situational-Statistics-This-Yearas-Power-Forward-Crop-3505/','20100623'),('dx2011fw','http://www.draftexpress.com/article/Situational-Statistics-the-2011-Forward-Crop-3762/','20110622')]
def one(x):
 sid,url,cutoff=x
 q={'url':url,'to':cutoff,'output':'json','filter':'statuscode:200','collapse':'digest','limit':'3','matchType':'exact'}
 req='https://web.archive.org/cdx/search/cdx?'+urllib.parse.urlencode(q)
 d={'source_id':sid,'source_url':url,'cutoff':cutoff,'query_url':req,'retrieved_at':time.time(),'archive_verified':False}
 try:
  r=urllib.request.urlopen(req,timeout=25);raw=r.read();rows=json.loads(raw);d['response_sha256']=hashlib.sha256(raw).hexdigest();d['snapshots']=[dict(zip(rows[0],a)) for a in rows[1:]] if rows else [];d['status']='ok'
 except Exception as e:d['status']='unavailable';d['error']=str(e)
 return d
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(one,sources))
(ROOT/'archive_index_validation.json').write_text(json.dumps(r,indent=2))
print(json.dumps([{k:d[k] for k in ('source_id','status') }|{'snapshots':len(d.get('snapshots',[]))} for d in r],indent=2))

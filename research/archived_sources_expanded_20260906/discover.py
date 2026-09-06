from pathlib import Path
import urllib.parse,urllib.request,json,time,hashlib
R=Path(__file__).parent
q=[('url','www.draftexpress.com/article/Situational-Statistics'),('matchType','prefix'),('from','20110101'),('to','20140625'),('output','json'),('filter','statuscode:200'),('filter','mimetype:text/html'),('collapse','urlkey'),('limit','150')]
u='https://web.archive.org/cdx/search/cdx?'+urllib.parse.urlencode(q)
try:
 r=urllib.request.urlopen(u,timeout=45);raw=r.read();j=json.loads(raw);data={'url':u,'retrieved_at':time.time(),'sha256':hashlib.sha256(raw).hexdigest(),'records':[dict(zip(j[0],x)) for x in j[1:]] if j else [],'status':'ok'}
except Exception as e:data={'url':u,'retrieved_at':time.time(),'status':'unavailable','error':str(e)}
(R/'discovery.json').write_text(json.dumps(data,indent=2));print(json.dumps(data,indent=2))

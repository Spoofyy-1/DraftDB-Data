from pathlib import Path
import concurrent.futures,datetime as dt,gzip,hashlib,json,requests,shutil
R=Path(__file__).resolve().parent
(R/'raw').mkdir(exist_ok=True)
def fetch(pair):
 y,kind=pair;url=f'https://barttorvik.com/{y}_all_advgames.json.gz' if kind=='player' else f'https://barttorvik.com/{y}_season.json'
 p=R/'raw'/f'{kind}_{y}.bin';cap=(25 if kind=='player' else 15)*1024**2
 assert shutil.disk_usage(R).free>1024**3
 if not p.exists():
  with requests.get(url,timeout=40,stream=True,allow_redirects=False,headers={'User-Agent':'DraftDB-historical-input-reconstruction/1.0'})as r:
   assert r.status_code==200,(url,r.status_code);n=0
   with p.with_suffix('.partial').open('wb')as f:
    while True:
     b=r.raw.read(1024**2,decode_content=False)
     if not b:break
     n+=len(b);assert n<=cap;f.write(b)
   p.with_suffix('.partial').rename(p)
 b=p.read_bytes();assert len(b)<=cap
 d=gzip.decompress(b)if b[:2]==b'\x1f\x8b'else b;assert len(d)<150*1024**2;v=json.loads(d);assert isinstance(v,list)
 e={'year':y,'kind':kind,'url':url,'path':str(p.relative_to(R)),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'rows':len(v),'retrieved_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'original_publication_vintage_verified':False}
 (R/'raw'/f'{kind}_{y}.json').write_text(json.dumps(e,indent=2));print(json.dumps(e),flush=True);return e
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:
  r=list(pool.map(fetch,[(y,k)for y in range(2019,2026)for k in ['player','team']]))
 assert len(r)==14
 (R/'source_downloads.json').write_text(json.dumps(r,indent=2));print('ALL14_FETCHED',flush=True)

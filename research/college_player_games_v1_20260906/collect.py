"""Ten-request historical-only collector preserving bounded compressed bytes."""
from pathlib import Path
import datetime as dt,gzip,hashlib,io,json,shutil,time
import requests
R=Path(__file__).resolve().parent
MAX_WIRE=25*1024**2;MAX_DECODED=150*1024**2;MAX_TOTAL=200*1024**2;FLOOR=1024**3
YEARS=list(range(2017,2007,-1))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def decode(path):
    data=path.read_bytes()
    assert len(data)<=MAX_WIRE,'wire_limit'
    if data[:2]==b'\x1f\x8b':
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:data=f.read(MAX_DECODED+1)
    assert len(data)<=MAX_DECODED,'decoded_limit'
    assert data[:1]==b'[','not_json_array'
    return data

def main():
    log=R/'network_ledger.json';ledger=json.loads(log.read_text()) if log.exists() else []
    existing={x['source_season'] for x in ledger};consecutive=0
    for x in reversed(ledger):
        if x.get('status') in [403,404]:consecutive+=1
        else:break
    deadline=dt.datetime.fromisoformat('2026-09-06T14:43:00+00:00')
    for year in YEARS:
        if year in existing:continue
        assert len(ledger)<10 and consecutive<3,'request_or_route_stop'
        assert dt.datetime.now(dt.timezone.utc)<deadline,'time_limit'
        assert shutil.disk_usage(R).free>FLOOR+MAX_WIRE,'free_space_floor'
        assert sum(x.get('bytes',0) for x in ledger)+MAX_WIRE<=MAX_TOTAL,'total_size_limit'
        row={'source_season':year,'url':f'https://barttorvik.com/{year}_all_advgames.json.gz','retrieved_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'original_publication_date':None,'model_eligible':False}
        path=R/'private'/f'games{year}.bin';partial=path.with_suffix('.partial')
        try:
            with requests.get(row['url'],stream=True,timeout=35,allow_redirects=False,headers={'User-Agent':'DraftDB-historical-source-audit/1.0'}) as resp:
                row.update(status=resp.status_code,content_type=resp.headers.get('Content-Type'),content_encoding=resp.headers.get('Content-Encoding'))
                n=0
                with partial.open('wb') as f:
                    while True:
                        chunk=resp.raw.read(1024**2,decode_content=False)
                        if not chunk:break
                        n+=len(chunk);assert n<=MAX_WIRE,'compressed_file_limit';assert shutil.disk_usage(R).free>FLOOR+len(chunk),'free_space_floor'
                        f.write(chunk)
                partial.rename(path);row.update(bytes=n,sha256=sha(path),private_file=str(path.relative_to(R)))
                if resp.status_code==200:
                    data=decode(path);obj=json.loads(data);assert isinstance(obj,list),'json_array'
                    row.update(decoded_bytes=len(data),rows=len(obj),row_width_counts=dict(__import__('collections').Counter(len(x) if isinstance(x,list) else 'not_array' for x in obj)),decoded_success=True)
        except Exception as e:
            row['error']=repr(e)
            if partial.exists():row['partial_file']=str(partial.relative_to(R));row['partial_bytes']=partial.stat().st_size
        ledger.append(row);log.write_text(json.dumps(ledger,indent=2));print(json.dumps(row),flush=True)
        consecutive=consecutive+1 if row.get('status') in [403,404] else 0
        if consecutive>=3 or 'free_space_floor' in row.get('error',''):break
        time.sleep(.5)
if __name__=='__main__':main()

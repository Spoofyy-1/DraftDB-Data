"""Bounded source collector. No current ratings or NBA information is parsed."""
from pathlib import Path
import argparse,datetime as dt,hashlib,json,shutil,time
import requests
R=Path(__file__).resolve().parent
URLS={**{f'season{year}': f'https://barttorvik.com/{year}_season.json' for year in range(2008,2019)}, 'kentucky2012':'https://barttorvik.com/getgamestats.php?year=2012&tvalue=Kentucky', 'espn_kentucky_marist_20111111':'https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event=313150096'}
def main():
 p=argparse.ArgumentParser();p.add_argument('keys',nargs='+',choices=URLS);a=p.parse_args()
 log=R/'network_ledger.json'; ledger=json.loads(log.read_text()) if log.exists() else []
 for key in a.keys:
  if any(r['key']==key for r in ledger):continue
  assert len(ledger)<13  # Seven method/discovery operations already consumed the remainder of the20-operation cap.
  assert shutil.disk_usage(R).free>500*1024**2
  url=URLS[key];started=dt.datetime.now(dt.timezone.utc).isoformat()
  try:
   resp=requests.get(url,timeout=30,headers={'User-Agent':'DraftDB-source-audit/1.0'},allow_redirects=False)
   data=resp.content
   assert len(data)<15*1024**2,'Stop unexpectedly large response'
   f=R/'private'/f'{key}.bin';f.write_bytes(data)
   try: obj=resp.json();kind=type(obj).__name__;shape=len(obj);preview=list(obj)[:3] if isinstance(obj,dict) else [type(x).__name__ for x in obj[:3]]
   except Exception:kind='not_json';shape=None;preview=None
   row={'key':key,'url':url,'retrieved_at_utc':started,'status':resp.status_code,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'json_kind':kind,'shape':shape,'schema_preview':preview,'eligible':False,'reason':'Requires numeric schema, historical dates and source dependencies verification'}
  except Exception as e:row={'key':key,'url':url,'retrieved_at_utc':started,'error':repr(e),'eligible':False}
  ledger.append(row);log.write_text(json.dumps(ledger,indent=2));print(json.dumps(row),flush=True)
  if row.get('status') in [403,429]:break
  time.sleep(1)
if __name__=='__main__':main()

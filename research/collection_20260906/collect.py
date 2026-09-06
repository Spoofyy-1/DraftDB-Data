"""Independent resumable source collection; output is not a training feature file.
No labels/picks are read. Published dates are discovery evidence, not certification.
"""
from pathlib import Path
import argparse,datetime as dt,email.utils,hashlib,json,re,time,urllib.parse
import xml.etree.ElementTree as ET
import requests

ROOT=Path(__file__).resolve().parent
UA={'User-Agent':'DraftDB historical pre-draft research/2.0'}
def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2,allow_nan=False));tmp.replace(path)
def get(url):
    r=requests.get(url,headers=UA,timeout=(10,35));r.raise_for_status();return r
def news(p,report_only=False):
    start=f"{p['draft_year']-1}-07-01";end=p['draft_date']
    query=f'"{p["name"]}" (draft OR scouting OR prospect OR basketball) after:{start} before:{end}'
    if report_only:query=f'"{p["name"]}" ("scouting report" OR "draft profile" OR "mock draft") after:{start} before:{end}'
    url='https://news.google.com/rss/search?'+urllib.parse.urlencode(dict(q=query,hl='en-US',gl='US',ceid='US:en'))
    r=get(url);root=ET.fromstring(r.content);items=[];excluded=0
    for it in root.findall('.//item'):
        try:date=email.utils.parsedate_to_datetime(it.findtext('pubDate')).date().isoformat()
        except Exception:excluded+=1;continue
        if not start<=date<end:excluded+=1;continue
        title=it.findtext('title') or '';low=title.lower()
        category='mock' if 'mock' in low else 'scouting' if any(w in low for w in ['scouting','strengths','weaknesses','draft profile']) else 'news'
        items.append(dict(title=title,url=it.findtext('link'),published_date=date,source=it.findtext('source'),kind=category,eligibility='quarantine: publication and identity need source verification'))
    return dict(status='ok' if items else 'empty',query=query,query_url=url,items=items,rejected_dates=excluded,response_sha256=hashlib.sha256(r.content).hexdigest(),feature_eligible=False)

def reports(p):return news(p,report_only=True)

def scouting(p):
    slug=re.sub(r'[^a-z0-9]+','-',p['name'].lower()).strip('-')
    url=f'https://www.nbadraft.net/players/{slug}/'
    r=get(url)
    # Keep links and source hashes, not a public copy of the copyrighted report.
    dates=sorted(set(re.findall(r'(?:19|20)\d{2}-\d{2}-\d{2}',r.text)))
    headings=re.findall(r'<h[1-3][^>]*>(.*?)</h[1-3]>',r.text,re.S|re.I)
    headings=[re.sub('<[^>]+>',' ',x).strip() for x in headings][:8]
    return dict(status='discovered',source_url=r.url,source_sha256=hashlib.sha256(r.content).hexdigest(),page_dates=dates,headings=headings,feature_eligible=False,eligibility='quarantine: current profile may include draft results; use dated archived report section only')

def trends(p):
    if p['draft_year']<2004:return dict(status='unavailable_before_2004',feature_eligible=False)
    from pytrends.request import TrendReq
    end=dt.date.fromisoformat(p['draft_date'])-dt.timedelta(days=1)
    start=dt.date(p['draft_year'],1,1)
    pt=TrendReq(hl='en-US',tz=0,timeout=(10,30))
    terms=[p['name'],'NBA draft']
    pt.build_payload(terms,timeframe=f'{start} {end}',geo='US')
    f=pt.interest_over_time()
    if f is None or f.empty:return dict(status='empty',feature_eligible=False,terms=terms,start=str(start),end=str(end))
    samples=[]
    for ix,row in f.iterrows():
        date=ix.date()
        if not start<=date<=end:raise ValueError('Returned date outside request')
        samples.append(dict(date=str(date),value=float(row[terms[0]]),anchor=float(row[terms[1]]),partial=bool(row.get('isPartial',False))))
    steps=[(dt.date.fromisoformat(b['date'])-dt.date.fromisoformat(a['date'])).days for a,b in zip(samples,samples[1:])]
    interval=max(steps) if steps else None
    # Conservatively exclude any bucket whose end could cross the pre-draft cutoff.
    valid=[v for v in samples if not v['partial'] and interval is not None and dt.date.fromisoformat(v['date'])+dt.timedelta(days=interval-1)<=end]
    def ratio(rows):
        a=sum(v['anchor'] for v in rows)
        return sum(v['value'] for v in rows)/a if a>0 else None
    last=[v for v in valid if dt.date.fromisoformat(v['date'])>=end-dt.timedelta(days=29)]
    early=[v for v in valid if dt.date.fromisoformat(v['date'])<start+dt.timedelta(days=90)]
    return dict(status='ok',terms=terms,start=str(start),end=str(end),geo='US',sampling='retrieved retrospectively; sampled and normalized by Google',interval_days=interval,samples=samples,valid_samples=len(valid),ratio=ratio(valid),last30_calendar_ratio=ratio(last),first90_calendar_ratio=ratio(early),feature_eligible=False,eligibility='pending name ambiguity and source-vintage review; zero is not proof of zero interest')

def mocks(year,players):
    p=next(p for p in players if p['draft_year']==year)
    end=(dt.date.fromisoformat(p['draft_date'])-dt.timedelta(days=1)).strftime('%Y%m%d')
    params=dict(url='nbadraft.net/nba-mock-drafts/',matchType='exact',output='json',filter='statuscode:200',collapse='digest',**{'from':f'{year-1}1001','to':end,'limit':100})
    r=get('https://web.archive.org/cdx/search/cdx?'+urllib.parse.urlencode(params))
    rows=r.json();out=[]
    if rows:
        for row in rows[1:]:
            item=dict(zip(rows[0],row));ts=item.get('timestamp','')
            if ts[:8]>end:raise ValueError('Post-cutoff snapshot')
            out.append(item)
    return dict(status='ok' if out else 'empty',draft_year=year,cutoff=end,snapshots=out,feature_eligible=False,eligibility='archive index only; parse and check captured mock table before use')

def main():
    a=argparse.ArgumentParser();a.add_argument('lane',choices=['news','scouting','trends','mocks','reports']);a.add_argument('--hours',type=float,default=8);a.add_argument('--limit',type=int,default=0);args=a.parse_args()
    players=json.loads((ROOT/'players.json').read_text());players.sort(key=lambda p:(p['draft_year'] not in [2012,2013,2014],p['draft_year']>=2019,p['draft_year'],p['pid']));out=ROOT/'records'/args.lane;out.mkdir(parents=True,exist_ok=True)
    jobs=sorted(set(p['draft_year'] for p in players)) if args.lane=='mocks' else players
    if args.limit:jobs=jobs[:args.limit]
    start=time.time();counts={};attempts=0;consecutive_errors=0
    for p in jobs:
        if time.time()-start>args.hours*3600:break
        key=str(p) if isinstance(p,int) else p['pid'];path=out/f'{key}.json'
        if path.exists():continue
        rec=dict(collected_at=dt.datetime.now(dt.timezone.utc).isoformat(),lane=args.lane)
        if isinstance(p,dict):rec.update(p)
        try:
            rec.update(mocks(p,players) if args.lane=='mocks' else globals()[args.lane](p));consecutive_errors=0
        except Exception as e:
            rec.update(status='error',error=str(e)[:250],feature_eligible=False);consecutive_errors+=1
        save(path,rec);attempts+=1;counts[rec['status']]=counts.get(rec['status'],0)+1
        save(ROOT/f'{args.lane}_state.json',dict(status='running',updated=time.time(),attempted=attempts,existing=len(list(out.glob('*.json'))),total=len(jobs),current=key,counts=counts))
        print(json.dumps(dict(key=key,status=rec['status'],items=len(rec.get('items',[])))),flush=True)
        if consecutive_errors>=5:break
        time.sleep(0 if rec['status']=='unavailable_before_2004' else 20 if args.lane=='trends' else 3)
    save(ROOT/f'{args.lane}_state.json',dict(status='backoff' if consecutive_errors>=5 else 'completed_or_time_limit',updated=time.time(),attempted=attempts,existing=len(list(out.glob('*.json'))),total=len(jobs),counts=counts))
if __name__=='__main__':main()

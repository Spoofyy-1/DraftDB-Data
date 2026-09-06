"""Resume a bounded archive-only DraftExpress collection. No NBA labels/results."""
from pathlib import Path
import urllib.request,urllib.parse,json,re,time,hashlib,datetime,zoneinfo
from html.parser import HTMLParser
R=Path(__file__).parent
D=json.load(open(R/'discovery.json'))
P=json.load(open(R.parents[1]/'collectors/players.json'))
dates={int(p['draft_year']):p['draft_date'] for p in P}
class TXT(HTMLParser):
 def __init__(self):super().__init__();self.chunks=[];self.skip=0
 def handle_starttag(self,t,a):
  if t in ['script','style']:self.skip+=1
  if t in ['br','tr','p']:self.chunks.append('\n')
 def handle_endtag(self,t):
  if t in ['script','style'] and self.skip:self.skip-=1
 def handle_data(self,s):
  if not self.skip:self.chunks.append(s)
def plain(h):p=TXT();p.feed(h);return ''.join(p.chunks)
for d in D['records']:
 m=re.search('the-(201[1-4])-',d['urlkey']);ident=re.search(r'-(\d+)$',d['urlkey'])
 if not m or not ident:continue
 sid='dx'+ident[1];year=int(m[1]);out=R/f'{sid}.json'
 if out.exists():continue
 capture=datetime.datetime.strptime(d['timestamp'],'%Y%m%d%H%M%S').replace(tzinfo=datetime.timezone.utc)
 cutoff=datetime.datetime.fromisoformat(dates[year]).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York'))
 meta={'source_id':sid,'draft_year':year,'draft_date':dates[year],'cutoff_policy':'capture strictly before midnight America/New_York on draft date; conservative, excludes all draft-day daytime captures','source':d,'capture_utc':capture.isoformat(),'cutoff_utc':cutoff.astimezone(datetime.timezone.utc).isoformat(),'archive_verified':False,'feature_eligible':False}
 if capture>=cutoff:
  meta['status']='quarantined_late_capture';out.write_text(json.dumps(meta,indent=2));continue
 u='https://web.archive.org/web/'+d['timestamp']+'id_/'+d['original'];meta['archive_url']=u
 try:
  req=urllib.request.urlopen(u,timeout=35);raw=req.read();assert req.url==u
  try:h=raw.decode('utf-8');encoding='utf-8'
  except UnicodeDecodeError:h=raw.decode('cp1252');encoding='cp1252'
  # Dated article heading, not a navigation or profile snippet.
  heading=re.search(r'<span class=red_heading_large>(.*?)</span>',h,re.S|re.I)
  assert heading, 'article heading missing'
  heading_text=plain(heading[1]).strip();assert str(year) in heading_text
  i=h.index(heading[0]);tail=h[i:]
  pub=re.search(r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+20\d\d)',plain(tail)[:1400])
  assert pub,'publication date missing'
  publication=None
  for fmt in ['%B %d, %Y','%b %d, %Y']:
   try:publication=datetime.datetime.strptime(pub[1],fmt).date();break
   except ValueError:pass
  assert publication and publication.isoformat()<dates[year] and publication.year==year
  # Balance nested font tags. A non-greedy regex truncates articles at image
  # captions, silently discarding the remaining player sections.
  start=re.search(r'<font\s+size="?2"?\s*>',tail,re.I);assert start,'article body opening missing'
  depth=1;end=None
  for tag in re.finditer(r'<(/?)font\b[^>]*>',tail[start.end():],re.I):
   depth+=-1 if tag[1] else 1
   if depth==0:end=start.end()+tag.start();break
  assert end is not None,'balanced article body closing missing'
  article=tail[start.end():end]
  article_text=plain(article)
  assert 1000<len(article_text)<45000,('body length',len(article_text))
  assert 'Read Next' not in article_text and 'Full Profile' not in article_text and 'Feedback' not in article_text,'sidebar boundary failed'
  meta.update({'status':'verified_archive','publication_date':publication.isoformat(),'title':heading_text,'archive_verified':True,'feature_eligible':True,'encoding':encoding,'html_sha256':hashlib.sha256(raw).hexdigest(),'body_sha256':hashlib.sha256(article_text.encode()).hexdigest(),'body_chars':len(article_text),'retrieved_at':time.time(),'body_boundary':'balanced outer article font tag following dated headline; nested font/image tables retained, Feedback and profile sidebars excluded'})
  (R/'private'/f'{sid}.html').write_bytes(raw);(R/'private'/f'{sid}.body.txt').write_text(article_text);(R/'private'/f'{sid}.body.html').write_text(article)
 except Exception as e:meta['status']='quarantined_retrieval_or_boundary';meta['error']=str(e)
 out.write_text(json.dumps(meta,indent=2));print(sid,meta['status'],meta.get('body_chars'),flush=True);time.sleep(.4)
allmeta=[json.load(open(p)) for p in R.glob('dx*.json')]
(R/'collection_state.json').write_text(json.dumps({'updated':time.time(),'attempted':len(allmeta),'counts':{s:len([d for d in allmeta if d['status']==s]) for s in sorted({d['status'] for d in allmeta})}},indent=2))

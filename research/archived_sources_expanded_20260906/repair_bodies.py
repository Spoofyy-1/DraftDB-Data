import runpy,json,re,hashlib
from pathlib import Path
from html.parser import HTMLParser
R=Path(__file__).parent
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
for p in R.glob('dx*.json'):
 d=json.load(open(p));fp=R/'private'/f'{p.stem}.html'
 if not fp.exists():continue
 raw=fp.read_bytes()
 try:h=raw.decode('utf-8');enc='utf-8'
 except UnicodeDecodeError:h=raw.decode('cp1252');enc='cp1252'
 heading=re.search(r'<span class=red_heading_large>(.*?)</span>',h,re.S|re.I);tail=h[h.index(heading[0]):]
 start=re.search(r'<font\s+size="?2"?\s*>',tail,re.I);assert start
 depth=1;end=None
 for tag in re.finditer(r'<(/?)font\b[^>]*>',tail[start.end():],re.I):
  depth+=-1 if tag[1] else 1
  if depth==0:end=start.end()+tag.start();break
 assert end is not None
 body=tail[start.end():end];txt=plain(body)
 assert 1000<len(txt)<45000
 assert 'Feedback' not in txt and 'Full Profile' not in txt and 'Read Next' not in txt
 (R/'private'/f'{p.stem}.body.txt').write_text(txt)
 (R/'private'/f'{p.stem}.body.html').write_text(body)
 d['encoding']=enc;d['body_chars']=len(txt);d['body_sha256']=hashlib.sha256(txt.encode()).hexdigest();d['body_boundary']='balanced outer article font tag following dated headline; nested font/image tables retained, Feedback and profile sidebars excluded'
 p.write_text(json.dumps(d,indent=2));print(p.stem,len(txt))

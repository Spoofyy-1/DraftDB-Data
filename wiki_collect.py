"""Wikipedia (CC-BY-SA, API, robots-allowed) career-stat tables for non-college prospects.
Runs where the names live (Mac). Output is pid-keyed with NO names. 1 req/sec, descriptive UA, cached."""
import json,os,re,time,csv,html,unicodedata,urllib.request,urllib.parse,collections
from html.parser import HTMLParser
UA={"User-Agent":"DraftDB-research/1.0 (mike@alphax.inc) python-urllib"}
API="https://en.wikipedia.org/w/api.php"
def get(params,fn):
    p=f"wiki_raw/{fn}"
    if os.path.exists(p): return json.load(open(p))
    time.sleep(1.0); url=API+"?"+urllib.parse.urlencode(dict(params,format="json"))
    with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=40) as r: d=json.load(r)
    json.dump(d,open(p,"w")); return d
def norm(s): return re.sub(r"[^a-z0-9 ]","",unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower())
class T(HTMLParser):
    def __init__(s): super().__init__(); s.tables=[]; s.cur=None; s.row=None; s.cell=None; s.h2=None; s.in_h=False; s.sections=[]
    def handle_starttag(s,tag,a):
        if tag=="table": s.cur=[]; s.cur_sec=s.h2
        elif tag=="tr" and s.cur is not None: s.row=[]
        elif tag in("td","th") and s.row is not None: s.cell=""
        elif tag in("h2","h3"): s.in_h=True; s.htxt=""
    def handle_endtag(s,tag):
        if tag in("td","th") and s.cell is not None: s.row.append(html.unescape(s.cell).strip()); s.cell=None
        elif tag=="tr" and s.row is not None: s.cur.append(s.row); s.row=None
        elif tag=="table" and s.cur is not None: s.tables.append((s.cur_sec,s.cur)); s.cur=None
        elif tag in("h2","h3") and s.in_h: s.h2=s.htxt; s.in_h=False
    def handle_data(s,d):
        if s.cell is not None: s.cell+=d
        if s.in_h: s.htxt+=d
NUM=["gp","gs","mpg","fg%","3p%","ft%","rpg","apg","spg","bpg","ppg","fga","3pa","fta"]
def parse_tables(htmltext):
    p=T(); p.feed(htmltext); out=[]
    for sec,tb in p.tables:
        if not tb: continue
        hdr=[norm(c).replace(" ","") for c in tb[0]]
        if not("ppg" in hdr and "gp" in hdr): continue
        col={h:i for i,h in enumerate(hdr)}
        for r in tb[1:]:
            if len(r)<len(hdr)-2 or not r: continue
            yr=r[col.get("year",col.get("season",0))] if col else r[0]
            m=re.search(r"(\d{4})\s*[–-]\s*(\d{2,4})",yr) or re.search(r"(\d{4})",yr)
            if not m: continue
            end=int(m.group(1))+1 if (m.lastindex==1 or len(m.group(2))<4 and int(m.group(2))!=int(m.group(1))%100) else (int(m.group(2)) if m.lastindex==2 and len(m.group(2))==4 else int(m.group(1))+1)
            row=dict(section=(sec or "").strip(),year=yr,end=end,team=r[col["team"]] if "team" in col else "",league=r[col["league"]] if "league" in col else "")
            for k in NUM:
                if k in col and col[k]<len(r):
                    v=re.sub(r"[^\d.]","",r[col[k]].replace("*","")); row[k]=float(v) if v not in("","." ) else None
            out.append(row)
    return out
targets=list(csv.DictReader(open("targets_LOCAL_names.csv")))
res={}; n=0
for t in targets:
    n+=1; q=t["name"]+" basketball"
    try:
        s=get(dict(action="query",list="search",srsearch=q,srlimit=3),f"search_{t['pid']}.json")
        hits=s.get("query",{}).get("search",[])
        if not hits: res[t["pid"]]=dict(status="no_page"); continue
        title=None
        for h_ in hits:
            if norm(t["name"].split()[-1]) in norm(h_["title"]): title=h_["title"]; break
        title=title or hits[0]["title"]
        pg=get(dict(action="parse",page=title,prop="text",redirects=1),f"page_{t['pid']}.json")
        rows=parse_tables(pg.get("parse",{}).get("text",{}).get("*",""))
        pre=[r for r in rows if r["end"]<=int(t["draft_year"]) and r.get("gp") and "nba" not in norm(r.get("league","")) and "nba" not in norm(r.get("section",""))]
        res[t["pid"]]=dict(status="ok" if pre else "no_prestats",title=title,rows=pre)
    except Exception as e: res[t["pid"]]=dict(status="err",err=repr(e)[:80])
    if n%25==0: print(f"{n}/{len(targets)} done",flush=True)
json.dump(res,open("wiki_raw/_matches.json","w"))
c=collections.Counter(v["status"] for v in res.values()); print("status:",dict(c))

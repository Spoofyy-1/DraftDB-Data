"""College team-season facts from Wikipedia (API, cached): head coach, final AP/coaches rank, NCAA tournament result and
seed, conference champion. Keyed by (team, season) from the Torvik player rows; no player names involved."""
import json,os,re,time,csv,glob,gzip,urllib.request,urllib.parse,unicodedata,collections
UA={"User-Agent":"DraftDB-research/1.0 (mike@alphax.inc) python-urllib"}; API="https://en.wikipedia.org/w/api.php"
H="/Users/kennakao/Downloads/nba_redraft_handoff"
def get(params,fn):
    p=f"wiki_raw/{fn}"
    if os.path.exists(p): return json.load(open(p))
    time.sleep(1.0); url=API+"?"+urllib.parse.urlencode(dict(params,format="json"))
    with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=40) as r: d=json.load(r)
    json.dump(d,open(p,"w")); return d
def norm(s): s=unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower(); s=re.sub(r"\b(jr|sr|ii|iii|iv)\b","",s); return re.sub(r"[^a-z ]","",s).strip()
def fl(v):
    try: return float(v)
    except: return None
COLS=["player_name","team","conf","GP","Min_per","ORtg","usg","eFG","TS_per","ORB_per","DRB_per","AST_per","TO_per","FTM","FTA","FT_per","twoPM","twoPA","twoP_per","TPM","TPA","TP_per","blk_per","stl_per","ftr","yr","ht","num","porpag","adjoe","pfr","year","tpid"]
# which (team, season) pairs matter: final college season of every prospect 2010-2026
ids=[r for r in csv.DictReader(open(f"{H}/identity_KEEP_SEPARATE/tabular_names.csv")) if 2010<=int(float(r["draft_year"]))<=2026]
rows=collections.defaultdict(list)
for fp in sorted(glob.glob("tracking_raw/torvik_*.csv.gz")):
    for r in csv.reader(gzip.open(fp,"rt",errors="ignore")):
        if len(r)<34: continue
        d=dict(zip(COLS,r[:33])); d["_year"]=int(fl(d.get("year")) or 0); rows[norm(d["player_name"])].append(d)
need=collections.Counter()
for t in ids:
    dy=int(float(t["draft_year"])); cand=[d for d in rows.get(norm(t["player_name"]),[]) if d["_year"]<=dy]
    if not cand: continue
    last=max(cand,key=lambda d:(d["_year"],fl(d.get("Min_per")) or 0))
    if dy-last["_year"]<=1: need[(last["team"].strip(),last["_year"])]+=1
print("team-seasons needed:",len(need),flush=True)
def season_str(y): return f"{y-1}–{str(y)[2:]}"
def parse_infobox(wt):
    out={}
    for k,pat in (("coach",r"\|\s*head_coach\s*=\s*(.+)"),("aprank",r"\|\s*(?:ap|AP)[_ ]?rank\s*=\s*(.+)"),("coachrank",r"\|\s*coach(?:es)?[_ ]?rank\s*=\s*(.+)"),("tourney",r"\|\s*(?:tourney|bowl)\s*=\s*(.+)"),("result",r"\|\s*(?:tourney_result|bowl_result)\s*=\s*(.+)"),("champion",r"\|\s*champion\s*=\s*(.+)"),("record",r"\|\s*record\s*=\s*(.+)"),("conf_record",r"\|\s*conf_record\s*=\s*(.+)")):
        m=re.search(pat,wt)
        if m: out[k]=re.sub(r"<ref.*?(/>|</ref>)|\[\[|\]\]|\{\{[^{}]*\}\}","",m.group(1)).strip()[:120]
    return out
res={}; c=collections.Counter(); n=0
for (team,y),cnt in sorted(need.items(),key=lambda x:-x[1]):
    key=f"{team}|{y}"; n+=1
    fn=f"team_{re.sub(r'[^A-Za-z0-9]','_',team)}_{y}.json"
    try:
        q=f"{season_str(y)} {team} men's basketball team"
        s=get(dict(action="query",list="search",srsearch=q,srlimit=3),"ts_search_"+fn)
        hits=[h["title"] for h in s.get("query",{}).get("search",[]) if "men's basketball team" in h["title"] and season_str(y)[:4] in h["title"]]
        if not hits: res[key]=dict(status="no_page"); c["no_page"]+=1; continue
        pg=get(dict(action="parse",page=hits[0],prop="wikitext",redirects=1),"ts_page_"+fn)
        wt=pg.get("parse",{}).get("wikitext",{}).get("*","")
        ib=parse_infobox(wt); ib.update(status="ok",title=hits[0]); res[key]=ib; c["ok"]+=1
    except Exception as e: res[key]=dict(status="err",err=repr(e)[:80]); c["err"]+=1
    if n%50==0: print(f"{n}/{len(need)} {dict(c)}",flush=True); json.dump(res,open("wiki_raw/_teamseasons.json","w"))
json.dump(res,open("wiki_raw/_teamseasons.json","w")); print("status:",dict(c),flush=True); print("TEAMSEASON_DONE")

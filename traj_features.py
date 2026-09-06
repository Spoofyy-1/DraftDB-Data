"""Improvement-over-time features from each player's per-season stat tables (parsed from Wikipedia wikitext saved by
wiki_attention.py). Pre-draft seasons only (season end <= draft year). pid-keyed output: traj_features.csv."""
import json,re,glob,csv,unicodedata,collections
def norm(s): return re.sub(r"[^a-z0-9 %.]","",unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower()).strip()
def clean_cell(c):
    c=c.strip(); c=re.sub(r'^(?:[a-zA-Z]+\s*=\s*"[^"]*"\s*)+\|','',c); c=re.sub(r'^(?:[a-zA-Z]+\s*=\s*[^\s|]+\s*)+\|','',c)
    c=re.sub(r"\{\{[Tt]ooltip\|([^|}]*)\|[^}]*\}\}",r"\1",c); c=re.sub(r"\{\{[Aa]bbr\|([^|}]*)\|[^}]*\}\}",r"\1",c)
    c=re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]",r"\1",c); c=re.sub(r"\{\{[^{}]*\}\}","",c); c=re.sub(r"<ref.*?(/>|</ref>)","",c,flags=re.S); c=re.sub(r"<[^>]+>","",c)
    return c.replace("'''","").replace("''","").strip()
HMAP={"year":"year","season":"year","team":"team","club":"team","league":"league","gp":"gp","g":"gp","gs":"gs","mpg":"mpg","min":"mpg","fg%":"fg%","fg":"fg%","3p%":"3p%","3pt%":"3p%","ft%":"ft%","rpg":"rpg","reb":"rpg","apg":"apg","ast":"apg","spg":"spg","stl":"spg","bpg":"bpg","blk":"bpg","ppg":"ppg","pts":"ppg"}
NUM=("gp","gs","mpg","fg%","3p%","ft%","rpg","apg","spg","bpg","ppg")
def fnum(v):
    v=re.sub(r"[†‡*%]","",v or "").replace(",",".").strip(); m=re.search(r"-?\d*\.?\d+",v); return float(m.group(0)) if m else None
def parse_year(y):
    y=re.sub(r"\[.*?\]|[†‡*]","",y or "").strip(); m=re.search(r"(\d{4})\s*[–\-−/]\s*(\d{2,4})",y)
    if m:
        a=int(m.group(1)); b=m.group(2); e=int(b) if len(b)==4 else a//100*100+int(b)
        if e<a: e+=100
        return e if e-a<=1 else a+1
    m=re.search(r"^(\d{4})$",y); return int(m.group(1)) if m else None
STD=["year","team","gp","gs","mpg","fg%","3p%","ft%","rpg","apg","spg","bpg","ppg"]
def year_of(cell):
    m=re.search(r"\{\{nbay\|(\d{4})",cell)
    if m: return int(m.group(1))+1
    return parse_year(clean_cell(cell))
def rows_from(wt):
    out=[]; head=""; intable=False; hdr=None; block=[]
    def flush():
        nonlocal block
        if not block: return
        cells=[]
        for l in block:
            l=l.strip()
            if l.startswith("!"): cells+=[("h",c) for c in re.split(r"!!",l[1:])]
            elif l.startswith("|") and not l.startswith("|}"): cells+=[("d",c) for c in re.split(r"\|\|",l[1:])]
        block=[]
        if not cells: return
        if all(t=="h" for t,_ in cells):
            keys=[HMAP.get(norm(clean_cell(c)).replace(" ",""),None) for _,c in cells]
            if "gp" in keys and "ppg" in keys: hdr[:]=[keys]
            return
        raw=[c for _,c in cells]
        if re.search(r"career|total",norm(clean_cell(raw[0]))) or any("sortbottom" in c for c in raw[:1]): return
        yr=year_of(raw[0])
        if yr is None: return
        r=dict(section=head,end=yr,team="",league="")
        keys=hdr[0] if hdr and hdr[0] else STD
        if keys is STD:
            nums=[fnum(clean_cell(c)) for c in raw[1:]]
            texts=[clean_cell(c) for c in raw[1:] if fnum(clean_cell(c)) is None or re.search(r"[A-Za-z]{3}",clean_cell(c))]
            r["team"]=texts[0] if texts else ""; vals=[v for c,v in zip(raw[1:],nums) if not re.search(r"[A-Za-z]{3}",clean_cell(c))]
            names=["gp","gs","mpg","fg%","3p%","ft%","rpg","apg","spg","bpg","ppg"] if len(vals)>=11 else ["gp","mpg","fg%","3p%","ft%","rpg","apg","spg","bpg","ppg"]
            for k,v in zip(names,vals): r[k]=v
        else:
            vals=[clean_cell(c) for c in raw]
            for k,i in {k:i for i,k in enumerate(keys) if k}.items():
                if i<len(vals):
                    if k in("team","league"): r[k]=vals[i]
                    elif k!="year": r[k]=fnum(vals[i])
        if r.get("gp"): out.append(r)
    for line in wt.split("\n"):
        s=line.strip()
        m=re.match(r"^(==+)\s*(.*?)\s*==+\s*$",s)
        if m: flush(); head=m.group(2); intable=False; hdr=None; continue
        if re.search(r"\{\{[^{}]*statistics start",s,re.I) or s.startswith("{|"):
            flush(); intable=True; hdr=[None]; continue
        if not intable: continue
        if s.startswith("{{S-end}}") or s.startswith("{{end}}") or s.startswith("|}"): flush(); intable=False; hdr=None; continue
        if s.startswith("|-"): flush(); continue
        block.append(line)
    flush(); return out
NBA=re.compile(r"\bnba\b(?!\s*g league)",re.I); COLLEGE=re.compile(r"college|ncaa|university",re.I); YOUTH=re.compile(r"u1[5-9]|u2[01]|junior|youth|national team|fiba|eurobasket|world cup|olympic",re.I)
def classify(r):
    blob=f"{r['section']} {r['league']} {r['team']}"
    if NBA.search(blob) and not re.search(r"g league|development",blob,re.I): return "nba"
    if COLLEGE.search(blob): return "college"
    if YOUTH.search(blob): return "youth"
    return "pro"
def p36(r,k): return r[k]/r["mpg"]*36 if r.get(k) is not None and r.get("mpg") else None
def slope(xs,ys):
    pts=[(x,y) for x,y in zip(xs,ys) if y is not None]
    if len(pts)<2: return None
    mx=sum(p[0] for p in pts)/len(pts); my=sum(p[1] for p in pts)/len(pts); den=sum((p[0]-mx)**2 for p in pts)
    return sum((p[0]-mx)*(p[1]-my) for p in pts)/den if den else None
def feats(rows,dy):
    rows=[r for r in rows if r["end"]<=dy and classify(r) in("college","pro") and r.get("mpg")]
    if not rows: return None
    path="college" if any(classify(r)=="college" for r in rows) else "pro"
    rows=[r for r in rows if classify(r)==path]
    # one line per season: combine same-season rows by minutes (e.g. regular season + playoffs, two competitions)
    by=collections.defaultdict(list); [by[r["end"]].append(r) for r in rows]; seasons=[]
    for e in sorted(by):
        rs=by[e]; m=sum(r["gp"]*r["mpg"] for r in rs); gp=sum(r["gp"] for r in rs)
        if m<=0: continue
        agg=dict(end=e,gp=gp,mpg=m/gp)
        for k in("ppg","rpg","apg","spg","bpg"): agg[k]=sum(r["gp"]*r[k] for r in rs if r.get(k) is not None)/gp if any(r.get(k) is not None for r in rs) else None
        for k in("fg%","3p%","ft%"):
            v=[(r["gp"]*r["mpg"],r[k]) for r in rs if r.get(k) is not None]; agg[k]=(sum(w*(x/100 if x>1.5 else x) for w,x in v)/sum(w for w,_ in v)) if v else None
        seasons.append(agg)
    if not seasons: return None
    L=seasons[-1]; P=seasons[-2] if len(seasons)>1 else None; xs=list(range(len(seasons)))
    pts=[p36(s,"ppg") for s in seasons]; mpg=[s["mpg"] for s in seasons]
    f=dict(traj_path=1 if path=="college" else 0,traj_n_seasons=len(seasons),traj_last_gp=L["gp"],traj_last_mpg=round(L["mpg"],2),traj_last_pts36=round(pts[-1],3) if pts[-1] is not None else None,
           traj_slope_pts36=round(slope(xs,pts),3) if slope(xs,pts) is not None else None,traj_slope_mpg=round(slope(xs,mpg),3) if slope(xs,mpg) is not None else None,
           traj_last_is_peak=int(pts[-1]==max(x for x in pts if x is not None)) if pts[-1] is not None else None,traj_mpg_growth=round(L["mpg"]-seasons[0]["mpg"],2),traj_years_span=L["end"]-seasons[0]["end"])
    if P:
        d=lambda k:(round(p36(L,k)-p36(P,k),3) if p36(L,k) is not None and p36(P,k) is not None else None)
        f.update(traj_d_pts36=d("ppg"),traj_d_reb36=d("rpg"),traj_d_ast36=d("apg"),traj_d_stl36=d("spg"),traj_d_blk36=d("bpg"),traj_d_mpg=round(L["mpg"]-P["mpg"],2),
                 traj_d_fg=round(L["fg%"]-P["fg%"],3) if L.get("fg%") is not None and P.get("fg%") is not None else None,
                 traj_d_fg3=round(L["3p%"]-P["3p%"],3) if L.get("3p%") is not None and P.get("3p%") is not None else None,
                 traj_d_ft=round(L["ft%"]-P["ft%"],3) if L.get("ft%") is not None and P.get("ft%") is not None else None)
    return f
if __name__=="__main__":
    out=[]; c=collections.Counter()
    for fp in glob.glob("wiki_raw/attn_*.json"):
        d=json.load(open(fp)); rows=d.get("career_rows") or (rows_from(d["wikitext"]) if d.get("wikitext") else None)
        if rows is None: c["no_text"]+=1; continue
        f=feats(rows,d["draft_year"])
        if f: f["pid"]=d["pid"]; out.append(f); c["ok"]+=1
        else: c["no_rows"]+=1
    cols=["pid"]+sorted({k for r in out for k in r if k!="pid"})
    with open("traj_features.csv","w",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=cols); w.writeheader(); [w.writerow(r) for r in out]
    print("trajectory features:",dict(c),"cols",len(cols))

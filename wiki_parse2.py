"""Rebuild the international block from cached Wikipedia career tables (+ EuroLeague API cache).
Rule: LATEST pre-draft pro season (all competitions in that season combined by minutes), plus a
minutes-weighted last-two-seasons block and league strength. Offline: uses wiki_raw/page_*.json.
Output pid-keyed, no names: intl2_features.csv"""
import json,os,re,csv,html,unicodedata,collections,statistics as st
D="/Users/kennakao/nba/datarebuild"
def norm(s): return re.sub(r"[^a-z0-9 %.-]","",unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower()).strip()
from html.parser import HTMLParser
class T(HTMLParser):
    def __init__(s): super().__init__(); s.tables=[]; s.cur=None; s.row=None; s.cell=None; s.h=None; s.in_h=False; s.htxt=""; s.pending={}; s.col=0; s.rs=1; s.sup=0; s.style=0; s.hs={"h2":"","h3":"","h4":""}; s.htag=None
    def _skip(s):
        while s.col in s.pending:
            v,n=s.pending[s.col]; s.row.append(v)
            if n<=1: del s.pending[s.col]
            else: s.pending[s.col]=(v,n-1)
            s.col+=1
    def handle_starttag(s,tag,a):
        a=dict(a)
        if tag=="table": s.cur=[]; s.cur_sec=s.h; s.pending={}
        elif tag=="tr" and s.cur is not None: s.row=[]; s.col=0; s._skip()
        elif tag in("td","th") and s.row is not None:
            s.cell=""; v=re.sub(r"\D","",a.get("rowspan") or "1"); s.rs=int(v) if v else 1
        elif tag in("h2","h3","h4"): s.in_h=True; s.htxt=""; s.htag=tag
        elif tag=="sup" and s.cell is not None: s.sup+=1
        elif tag=="style": s.style+=1
    def handle_endtag(s,tag):
        if tag=="style": s.style=max(0,s.style-1)
        elif tag=="sup" and s.cell is not None and s.sup>0: s.sup-=1
        elif tag in("td","th") and s.cell is not None:
            txt=html.unescape(s.cell).strip(); s.row.append(txt)
            if s.rs>1: s.pending[s.col]=(txt,s.rs-1)
            s.col+=1; s.cell=None; s.sup=0; s._skip()
        elif tag=="tr" and s.row is not None: s.cur.append(s.row); s.row=None
        elif tag=="table" and s.cur is not None: s.tables.append((s.cur_sec,s.cur)); s.cur=None
        elif tag in("h2","h3","h4") and s.in_h:
            txt=re.sub(r"\[.*?\]","",s.htxt).strip(); s.hs[s.htag]=txt
            if s.htag=="h2": s.hs["h3"]=""; s.hs["h4"]=""
            if s.htag=="h3": s.hs["h4"]=""
            s.h=" / ".join(x for x in(s.hs["h2"],s.hs["h3"],s.hs["h4"]) if x); s.in_h=False
    def handle_data(s,d):
        if s.style: return
        if s.cell is not None and s.sup==0: s.cell+=d
        if s.in_h: s.htxt+=d
HMAP={"year":"year","season":"year","team":"team","club":"team","league":"league","competition":"league","gp":"gp","g":"gp","gs":"gs","mpg":"mpg","min":"mpg","mins":"mpg","minutes":"mpg",
      "fg%":"fg%","fg":"fg%","3p%":"3p%","3pt%":"3p%","3fg%":"3p%","2p%":"2p%","ft%":"ft%","rpg":"rpg","reb":"rpg","apg":"apg","ast":"apg","spg":"spg","stl":"spg","bpg":"bpg","blk":"bpg","ppg":"ppg","pts":"ppg","pir":"pir","fga":"fga","3pa":"3pa","fta":"fta","tpg":"tov","to":"tov",
      "saison":"year","equipe":"team","championnat":"league","competition":"league","ligue":"league","mj":"gp","matchsjoues":"gp","matchs":"gp","mt":"gs","minutes":"mpg","min.":"mpg","tirs":"fg%","%tirs":"fg%","tirs%":"fg%","%reussite":"fg%","reussite":"fg%","2pts":"2p%","%2pts":"2p%","3pts":"3p%","%3pts":"3p%","3pts%":"3p%","lf":"ft%","%lf":"ft%","lf%":"ft%","reb":"rpg","rbds":"rpg","rebonds":"rpg","rbd":"rpg","pd":"apg","passes":"apg","pdec":"apg","passesdecisives":"apg","int":"spg","interceptions":"spg","ct":"bpg","contres":"bpg","pts":"ppg","points":"ppg","eval":"pir","evaluation":"pir","titul.":"gs","titul":"gs","min.m":"mpg","%tir":"fg%","tir":"fg%","rbds":"rpg","pass":"apg","ctr":"bpg","ptsm.":"ppg"}
def hkey(c):
    k=re.sub(r"^\.mw.*?(?=[a-z0-9%]+$)","",norm(c).replace(" ",""))
    for cand in (k,re.sub(r"(m\.|/m|m)$","",k),re.sub(r"^%","",k),re.sub(r"^%","",re.sub(r"(m\.|/m|m)$","",k))):
        if cand in HMAP: return HMAP[cand]
    return None
NUM=("gp","gs","mpg","fg%","3p%","2p%","ft%","rpg","apg","spg","bpg","ppg","pir","fga","3pa","fta","tov")
COUNTRIES=set(norm(x) for x in "Slovenia Serbia Croatia France Spain Germany Italy Greece Turkey Lithuania Latvia Israel Australia Canada Argentina Brazil China Japan Russia Ukraine Georgia Montenegro Bosnia and Herzegovina North Macedonia Czech Republic Poland Finland Sweden Denmark Netherlands Belgium Austria Switzerland Portugal Hungary Romania Bulgaria Estonia Nigeria Senegal Cameroon Angola Egypt Mali Congo DR Congo South Sudan Sudan Dominican Republic Puerto Rico Mexico Venezuela Uruguay Chile Colombia New Zealand Philippines South Korea Iran Lebanon Jordan Kazakhstan Belarus Cyprus Iceland Ireland Great Britain United States USA Cape Verde Guinea Ivory Coast Tunisia Bahamas Jamaica Haiti Saint Lucia Luxembourg Slovakia Norway Kosovo Albania Moldova Armenia Azerbaijan Uzbekistan Mongolia Taiwan Chinese Taipei Bahrain Qatar Syria India Indonesia Thailand Malaysia Rwanda Uganda Ghana Cote d'Ivoire Gabon Benin Togo Central African Republic Madagascar Mozambique Zimbabwe South Africa Ethiopia Kenya Tanzania Somalia Eritrea".split(" ") if len(x)>2) | {"south sudan","north macedonia","czech republic","dominican republic","puerto rico","new zealand","south korea","great britain","united states","bosnia and herzegovina","cape verde","ivory coast","chinese taipei","central african republic","south africa","dr congo"}
YOUTH=re.compile(r"espoirs|cadets|minimes|jeunes|\bu ?1[5-9]\b|\bu ?2[01]\b|under[- ]?1[5-9]|under[- ]?2[01]|junior|youth|cadet|nike hoop|basketball without borders|albert schweitzer|adidas next|eybl|hoop summit|world cup u|europe u|americas u|asia u|africa u",re.I)
NATIONAL=re.compile(r"national team|equipe de france|selection nationale|championnat d.europe|championnat du monde|jeux olympiques|eurobasket|world cup|olympic|americup|afrobasket|asia cup|qualif|friendl|world championship|fiba",re.I)
COLLEGE=re.compile(r"college|ncaa|universitaire|ncaa division|naia|juco|junior college|cccaa|njcaa|university|high school|prep|\bhs\b|academy",re.I)
def league_strength(txt):
    t=norm(txt)
    R=[("euroleague",1.0,4),("euroligue",1.0,4),("eurocoupe",0.85,3),("espoirs",0.3,3),("nm1",0.3,3),("nationale 1",0.3,3),("nationale masculine",0.3,3),("ligue des champions",0.75,3),("leaders cup",0.7,3),("coupe de france",0.6,3),("supercoupe",0.6,3),("a2",0.45,3),("second division",0.45,3),("2nd division",0.45,3),("b division",0.4,3),("eurocup",0.85,3),("uleb cup",0.8,3),("acb",0.9,3),("liga endesa",0.9,3),("vtb",0.8,3),("bsl",0.8,3),("tbl",0.8,3),("turkish",0.8,3),("turkiye",0.8,3),("super ligi",0.8,3),
       ("lega basket",0.78,3),("serie a2",0.5,3),("serie a",0.78,3),("lba",0.78,3),("lnb elite",0.75,3),("lnb pro a",0.75,3),("pro a",0.75,3),("betclic",0.75,3),("elite",0.75,3),("pro b",0.5,3),("lnb",0.72,3),
       ("bundesliga",0.72,3),("bbl",0.72,3),("proa",0.45,3),("prob",0.35,3),("adriatic",0.72,3),("aba league",0.72,3),("aba",0.72,3),("greek",0.72,3),("gbl",0.72,3),("hebl",0.72,3),("esake",0.72,3),("a1 ",0.7,3),
       ("ligat",0.7,3),("israel",0.7,3),("nbl1",0.35,3),("nbl (new zealand)",0.4,3),("nbl canada",0.35,3),("nbl",0.72,3),("champions league",0.75,3),("bcl",0.75,3),("fiba europe cup",0.6,3),("eurochallenge",0.55,3),
       ("lkl",0.65,3),("lithuan",0.65,3),("plk",0.55,3),("polish",0.55,3),("energa",0.55,3),("leb oro",0.55,3),("leb plata",0.4,3),("leb",0.5,3),("cba",0.55,3),("chinese",0.55,3),("china",0.55,3),("b.league",0.5,3),("b league",0.5,3),("kbl",0.5,3),("korean",0.5,3),
       ("nbb",0.45,3),("brazil",0.45,3),("liga nacional",0.45,3),("argentin",0.45,3),("g league",0.85,2),("nba g",0.85,2),("d-league",0.85,2),("development league",0.85,2),("overtime elite",0.35,3),("ote",0.35,3),
       ("bsn",0.4,3),("puerto",0.4,3),("venezuel",0.35,3),("lnbp",0.4,3),("mexic",0.4,3),("bnxt",0.55,3),("belgi",0.55,3),("dbl",0.4,3),("dutch",0.4,3),("austria",0.4,3),("swiss",0.35,3),("czech",0.45,3),("hungar",0.45,3),
       ("romania",0.4,3),("croatia",0.5,3),("premijer",0.5,3),("kls",0.5,3),("serbia",0.5,3),("sloven",0.45,3),("montenegr",0.45,3),("bosnia",0.4,3),("baltic",0.45,3),("latvia",0.45,3),("lbl",0.45,3),("eston",0.4,3),
       ("finn",0.4,3),("korisliiga",0.4,3),("swed",0.4,3),("basketligan",0.4,3),("denmark",0.35,3),("danish",0.35,3),("norw",0.3,3),("ukrain",0.5,3),("superleague",0.5,3),("russia",0.65,3),("pbl",0.65,3),("georgia",0.35,3),("kazakh",0.4,3),
       ("cyprus",0.35,3),("iceland",0.3,3),("portug",0.4,3),("lpb",0.4,3),("philippin",0.4,3),("pba",0.4,3),("japan",0.5,3),("iran",0.4,3),("lebanon",0.4,3),("egypt",0.4,3),("bal",0.45,3),("africa",0.4,3),("angola",0.4,3),
       ("nigeria",0.35,3),("senegal",0.35,3),("cebl",0.4,3),("canad",0.4,3),("new zealand",0.4,3),("uruguay",0.35,3),("chile",0.3,3),("colombia",0.3,3),("dominican",0.35,3),("lnb (dominican)",0.35,3),("bulgar",0.35,3),("slovak",0.35,3),("kosovo",0.3,3),("albania",0.3,3),("great britain",0.4,3),("bbl (uk)",0.4,3),("british",0.4,3),("ireland",0.25,3),("luxemb",0.25,3),("qatar",0.35,3),("bahrain",0.3,3),("australia",0.6,3)]
    for k,sv,lvl in R:
        if k in t: return sv,lvl,True
    return 0.45,3,False
def parse_year(y):
    y=re.sub(r"\[.*?\]|[†‡*]","",y or "").strip()
    m=re.search(r"(\d{4})\s*[–\-−/]\s*(\d{2,4})",y)
    if m:
        a=int(m.group(1)); b=m.group(2); e=int(b) if len(b)==4 else a//100*100+int(b)
        if e<a: e+=100
        return e if e-a<=1 else a+1
    m=re.search(r"^(\d{4})$",y)
    return int(m.group(1)) if m else None
def fnum(v):
    v=re.sub(r"\[.*?\]|[†‡*%]","",v or "").strip().replace(",",".")
    m=re.search(r"-?\d*\.?\d+",v); return float(m.group(0)) if m else None
def parse_page(htmltext):
    p=T(); p.feed(htmltext); out=[]
    for sec,tb in p.tables:
        if not tb: continue
        hdr=[hkey(c) for c in tb[0]]
        if "ppg" not in hdr or "gp" not in hdr: continue
        col={h:i for i,h in enumerate(hdr) if h}
        for r in tb[1:]:
            if len(r)<len(hdr)-1: continue
            yr=r[col["year"]] if "year" in col else r[0]; end=parse_year(yr)
            if end is None: continue
            team=r[col["team"]] if "team" in col and col["team"]<len(r) else ""; league=r[col["league"]] if "league" in col and col["league"]<len(r) else ""
            if norm(team) in("total","career","totals") or norm(yr) in("career","total"): continue
            row=dict(section=(sec or "").strip(),year=yr,end=end,team=team,league=league)
            for k in NUM:
                if k in col and col[k]<len(r): row[k]=fnum(r[col[k]])
            out.append(row)
    return out
def classify(row):
    s=row["section"]; l=row["league"]; t=row["team"]; blob=f"{s} {l} {t}"
    if re.search(r"\bnba\b",norm(blob)) and not re.search(r"g league|nba g|development",norm(blob)): return "nba"
    if COLLEGE.search(blob) and not re.search(r"euroleague|eurocup|acb|nbl|lnb",norm(blob)): return "college"
    if YOUTH.search(blob): return "youth"
    if NATIONAL.search(blob) or norm(t) in COUNTRIES or norm(s) in COUNTRIES: return "national"
    return "pro"
def wavg(rows,key,minkey="_min"):
    num=sum(r[minkey]*r[key] for r in rows if r.get(key) is not None and r[minkey]>0); den=sum(r[minkey] for r in rows if r.get(key) is not None and r[minkey]>0)
    return num/den if den>0 else None
def block(rows):
    rows=[dict(r) for r in rows if r.get("gp") and r.get("mpg") is not None]
    for r in rows: r["_min"]=r["gp"]*r["mpg"]
    rows=[r for r in rows if r["_min"]>0]
    if not rows: return None
    gp=sum(r["gp"] for r in rows); mins=sum(r["_min"] for r in rows)
    def p36(k):
        num=sum(r["gp"]*r[k] for r in rows if r.get(k) is not None); den=sum(r["_min"] for r in rows if r.get(k) is not None)
        return num/den*36 if den>0 else None
    b=dict(gp=gp,minutes=mins,mpg=mins/gp,pts36=p36("ppg"),reb36=p36("rpg"),ast36=p36("apg"),stl36=p36("spg"),blk36=p36("bpg"),tov36=p36("tov"),pir36=p36("pir"),
           fg_pct=wavg(rows,"fg%"),fg3_pct=wavg(rows,"3p%"),ft_pct=wavg(rows,"ft%"),strength=wavg(rows,"_str"),best_strength=max(r["_str"] for r in rows),level=max(r["_lvl"] for r in rows),
           known_league=any(r["_known"] for r in rows),leagues="|".join(sorted(set(r["_lgtxt"][-24:] for r in rows))))
    for k in("fg_pct","fg3_pct","ft_pct"):
        if b[k] is not None and b[k]>1.5: b[k]=b[k]/100.0
    return b
# EuroLeague API cache (per player-season, matched by normalized name)
EL=json.load(open(f"{D}/raw/el_player_seasons.json")); ELIDX=collections.defaultdict(list)
def pct(v):
    try: return float(str(v).replace("%",""))
    except: return None
for e in EL:
    last,first=(e["name"].split(",")+[""])[:2]; ELIDX[(norm(last).strip(),norm(first).strip()[:1])].append(e)
def el_lookup(title,end):
    parts=norm(title).replace("(basketball)","").split()
    if not parts: return None
    cands=[]
    for last in (parts[-1],"".join(parts[-2:]) if len(parts)>2 else parts[-1]):
        for e in ELIDX.get((last,parts[0][:1]),[]):
            if e["season"]+1==end: cands.append(e)
    if not cands: return None
    cands.sort(key=lambda e:-(e["gp"] or 0)); return cands[0]
def seasons_gp(pro):
    out=[]
    for e in sorted(set(r["end"] for r in pro),reverse=True):
        gps=[r["gp"] for r in pro if r["end"]==e]; out.append("%d:%.0f:%s"%(e,sum(gps),"/".join("%.0f"%g for g in gps)))
    return "|".join(out)
targets=list(csv.DictReader(open(f"{D}/targets_LOCAL_names.csv")))
out=[]; stats=collections.Counter(); report=[]
for t in targets:
    pid=t["pid"]; dy=int(t["draft_year"]); fp=f"{D}/wiki_raw/page_{pid}.json"
    if not os.path.exists(fp):
        if os.path.exists(f"{D}/wiki_raw/fr_page_{pid}.json"): pg=None
        else: stats["no_page"]+=1; continue
    pg=json.load(open(fp)) if os.path.exists(fp) else {"parse":{"title":"","text":{"*":""}}}; title=pg.get("parse",{}).get("title",""); rows=parse_page(pg.get("parse",{}).get("text",{}).get("*",""))
    fr=f"{D}/wiki_raw/fr_page_{pid}.json"
    if os.path.exists(fr):
        pgf=json.load(open(fr)); rowsf=parse_page(pgf.get("parse",{}).get("text",{}).get("*",""))
        for r in rowsf: r["_cls"]=classify(r)
        prof=[r for r in rowsf if r["_cls"]=="pro" and r["end"]<=dy and r.get("gp")]
        for r in rows: r["_cls"]=classify(r)
        proe=[r for r in rows if r["_cls"]=="pro" and r["end"]<=dy and r.get("gp")]
        if len(prof)>len(proe): rows=rowsf; stats["fr_used"]+=1
    for r in rows:
        r["_cls"]=classify(r); lg=r["league"] if r["league"] and not re.search(r"regular|playoff|cup|total|season|round|final|qualif",norm(r["league"])) else ""; r["_lgtxt"]=lg or r["section"]; r["_str"],r["_lvl"],r["_known"]=league_strength(r["_lgtxt"])
        if r["_cls"]=="youth": r["_lvl"]=1
    pro=[r for r in rows if r["_cls"]=="pro" and r["end"]<=dy and r.get("gp")]
    youth=[r for r in rows if r["_cls"]=="youth" and r["end"]<=dy and r.get("gp")]
    colrows=[r for r in rows if r["_cls"]=="college" and r["end"]<=dy and r.get("gp")]
    rec=dict(pid=pid,intl2_has_pro=int(bool(pro)),intl2_has_college_rows=int(bool(colrows)))
    if pro:
        L=max(r["end"] for r in pro); S=block([r for r in pro if r["end"]==L]); P=block([r for r in pro if r["end"]==L-1]); TWO=block([r for r in pro if r["end"] in(L,L-1)])
        stats["pro_ok"]+=1; stats[f"gap{min(dy-L,3)}"]+=1
        rec.update(intl2_seasons_gp=seasons_gp(pro),intl2_season_end=L,intl2_season_gap=dy-L,intl2_n_seasons=len(set(r["end"] for r in pro)),intl2_career_best_strength=max(r["_str"] for r in pro),intl2_career_best_level=max(r["_lvl"] for r in pro))
        if S:
            for k,v in S.items():
                if k in("leagues","known_league"): continue
                rec[f"intl2_{k}"]=round(v,4) if isinstance(v,float) else v
            rec["intl2_known_league"]=int(S["known_league"]); rec["intl2_adj_pts36"]=round(S["pts36"]*S["strength"],3) if S["pts36"] is not None else None
            age=None
            try: age=float(t["age"]) if t.get("age") else None
            except: age=None
            rec["intl2_age"]=round(age-(dy-L)-0.35,2) if age else None
        if P: rec.update(intl2_prev_pts36=round(P["pts36"],3) if P["pts36"] is not None else None,intl2_prev_minutes=round(P["minutes"],1),intl2_prev_mpg=round(P["mpg"],2))
        if TWO: rec.update(intl2_two_pts36=round(TWO["pts36"],3) if TWO["pts36"] is not None else None,intl2_two_reb36=round(TWO["reb36"],3) if TWO["reb36"] is not None else None,intl2_two_ast36=round(TWO["ast36"],3) if TWO["ast36"] is not None else None,intl2_two_minutes=round(TWO["minutes"],1),intl2_two_fg_pct=round(TWO["fg_pct"],4) if TWO["fg_pct"] is not None else None,intl2_two_strength=round(TWO["strength"],3) if TWO["strength"] is not None else None)
        e=el_lookup(title,L)
        if e and e.get("mpg"):
            rec.update(intl2_el_gp=e["gp"],intl2_el_mpg=round(e["mpg"],2),intl2_el_pts36=round(e["pts"]/e["mpg"]*36,3),intl2_el_ts=pct(e["ts"]),intl2_el_efg=pct(e["efg"]),intl2_el_ftr=(pct(e["ftr"])/100 if pct(e["ftr"]) is not None else None),intl2_el_p3ar=(pct(e["p3ar"])/100 if pct(e["p3ar"]) is not None else None),
                       intl2_el_orb_pct=pct(e["orb_pct"]),intl2_el_drb_pct=pct(e["drb_pct"]),intl2_el_ast_ratio=pct(e["ast_ratio"]),intl2_el_tov_ratio=pct(e["tov_ratio"]),intl2_el_pir36=round(e["pir"]/e["mpg"]*36,3),intl2_el_league=e["league"]); stats["el_matched"]+=1
        report.append((t["name"],dy,L,S and round(S["gp"]),S and round(S["mpg"],1),S and S["pts36"] and round(S["pts36"],1),S and round(S["strength"],2),S and S["leagues"][:40],"EL" if e else ""))
    else: stats["no_pro_rows"]+=1
    if colrows:
        CL=max(r["end"] for r in colrows); C=block([r for r in colrows if r["end"]==CL])
        if C: rec.update(colw_season_end=CL,colw_gp=C["gp"],colw_mpg=round(C["mpg"],2),colw_pts36=round(C["pts36"],3) if C["pts36"] is not None else None,colw_reb36=round(C["reb36"],3) if C["reb36"] is not None else None,colw_ast36=round(C["ast36"],3) if C["ast36"] is not None else None,colw_stl36=round(C["stl36"],3) if C["stl36"] is not None else None,colw_blk36=round(C["blk36"],3) if C["blk36"] is not None else None,colw_fg_pct=C["fg_pct"],colw_fg3_pct=C["fg3_pct"],colw_ft_pct=C["ft_pct"],colw_n_seasons=len(set(r["end"] for r in colrows)))
    if youth:
        Y=block(youth)
        if Y: rec.update(intl2_youth_pts36=round(Y["pts36"],3) if Y["pts36"] is not None else None,intl2_youth_n=len(youth),intl2_youth_minutes=round(Y["minutes"],1))
    out.append(rec)
cols=["pid"]+sorted({k for r in out for k in r if k!="pid"})
with open(f"{D}/intl2_features.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); [w.writerow(r) for r in out]
print("targets",len(targets),"stats",dict(stats)); print("rows written",len(out),"cols",len(cols))
with open(f"{D}/intl2_report_LOCAL.txt","w") as f:
    for r in sorted(report,key=lambda x:(-x[1],x[0])): f.write("\t".join(str(x) for x in r)+"\n")
for r in report:
    if r[0] in("Victor Wembanyama","Luka Doncic","Deni Avdija","Nikola Topić","Nikola Topic","Alex Sarr","Yang Hansen","Emmanuel Mudiay","Killian Hayes","Goga Bitadze","Josh Giddey","Alperen Sengun","Amen Thompson","Nikola Jokic","Giannis Antetokounmpo","Kristaps Porzingis","Clint Capela","Dario Saric","Jusuf Nurkic"): print(r)

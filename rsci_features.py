"""RSCI consensus recruiting rankings (1998-2026 final lists, top 100 per HS class) -> pid-keyed rsci_*/hs_* features.
Source: RSCI Google Site published sheets (recruit_raw/rsci_{year}.csv). Matching: normalized name + draft year within 0..6
years after the HS class (latest class <= draft year wins). Only ranked players appear; unranked => rsci_top100=0, rank NA.
All values are from lists published in spring of the HS graduation year, i.e. before any draft decision."""
import csv,re,glob,unicodedata,statistics as st,collections
H="/Users/kennakao/Downloads/nba_redraft_handoff"
def norm(s): return re.sub(r"\s+"," ",re.sub(r"[^a-z ]","",unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower().replace(".",""))).strip()
ALIAS={"mohamed":"mo","mohammed":"mo","cameron":"cam","michael":"mike","matthew":"matt","nicolas":"nick","nicholas":"nick","joshua":"josh","christopher":"chris","jonathan":"jon","kenneth":"kenny","william":"will","robert":"rob","daniel":"danny","zachary":"zach","benjamin":"ben","alexander":"alex","jacob":"jake","joseph":"joe","thomas":"tom","timothy":"tim","samuel":"sam","gregory":"greg","patrick":"pat","jeffrey":"jeff","frederick":"fred","raymond":"ray","theodore":"theo","charles":"charlie","edward":"ed","andrew":"drew","james":"jim","jamal":"jamal"}
def alias(full):
    p=full.split()
    if p and p[0] in ALIAS: p[0]=ALIAS[p[0]]
    return " ".join(p)
def keys(name):
    """match keys: full name; quoted nickname + last name; first initial + last name (fallback, only used when unique)"""
    full=alias(strip_suffix(norm(name))); out=[full]
    m=re.search(r'"([^"]+)"',name)
    if m: out.append(strip_suffix(norm(m.group(1)+" "+name.split()[-1])))
    parts=full.split()
    if len(parts)>=2: out.append("~"+parts[0][0]+" "+parts[-1])
    return out
def strip_suffix(n): return re.sub(r"\b(jr|sr|ii|iii|iv)\b","",n).replace("  "," ").strip()
def fl(v):
    try: return float(str(v).replace("+",""))
    except: return None
def height_in(h):
    m=re.search(r"(\d)\D+(\d{1,2})",h or "")
    return int(m.group(1))*12+int(m.group(2)) if m else None
POS={"pg":1,"1":1,"g":1.5,"cg":1.5,"sg":2,"wg":2,"2g":2,"2":2,"w":2.5,"gf":2.5,"sf":3,"wf":3,"3":3,"f":3.5,"pf":4,"4":4,"fc":4.5,"c":5,"5":5}
ids=list(csv.DictReader(open("identity/tabular_names.csv")))
by_name=collections.defaultdict(list)
for r in ids:
    for k in keys(r["player_name"]): by_name[k].append((int(float(r["draft_year"])),r["pid"]))
rows=[]
for fp in sorted(glob.glob("recruit_raw/rsci_*.csv")):
    yr=int(re.search(r"rsci_(\d{4})",fp).group(1)); lines=list(csv.reader(open(fp,encoding="utf-8",errors="ignore")))
    hi=next(i for i,l in enumerate(lines) if "RSCI" in [c.strip() for c in l] and "Total" in [c.strip() for c in l]); hdr=[c.strip() for c in lines[hi]]
    ri=hdr.index("RSCI")
    tot=hdr.index("Total"); ht=hdr.index("Ht") if "Ht" in hdr else None; pos=hdr.index("Pos") if "Pos" in hdr else None; col=hdr.index("College") if "College" in hdr else None
    chg=hdr.index("Chg") if "Chg" in hdr else None; avg=hdr.index("Avg") if "Avg" in hdr else None; dev=hdr.index("Dev") if "Dev" in hdr else None
    data=[l for l in lines[hi+1:] if len(l)>ri and re.fullmatch(r"\d+",l[ri].strip() or "")]
    # name column: first column after RSCI whose header is blank and whose values are mostly alphabetic
    cand=[i for i in range(ri+1,tot) if hdr[i] not in("Chg","Avg","Dev","Prev") and sum(bool(re.search(r"[A-Za-z]{3}",l[i])) for l in data[:20] if i<len(l))>=15]
    if not cand: print("NO NAME COLUMN",yr,hdr[:12]); continue
    ni=cand[0]; svc=[i for i in range(ni+1,tot) if hdr[i] and hdr[i] not in("Avg","Dev","Chg")]
    maxtot=max(fl(l[tot]) or 0 for l in data)
    for l in data:
        l=l+[""]*(len(hdr)-len(l)); ranks=[fl(l[i]) for i in svc]; rk=[x for x in ranks if x is not None and x>0]
        rows.append(dict(hs_class=yr,name=l[ni].replace("*","").strip(),rsci_rank=int(l[ri]),rsci_n_ranked=len(rk),rsci_n_services=len(svc),
            rsci_frac_ranked=round(len(rk)/len(svc),3) if svc else None,rsci_best=min(rk) if rk else None,rsci_worst=max(rk) if rk else None,
            rsci_range=(max(rk)-min(rk)) if rk else None,rsci_std=round(st.pstdev(rk),2) if len(rk)>1 else None,
            rsci_total_norm=round((fl(l[tot]) or 0)/maxtot,4) if maxtot else None,rsci_chg=(fl(l[chg]) or 0.0) if chg is not None else None,
            rsci_avg=fl(l[avg]) if avg is not None else None,rsci_dev=fl(l[dev]) if dev is not None else None,
            rsci_hs_height_in=height_in(l[ht]) if ht is not None else None,rsci_hs_pos=POS.get((l[pos] or "").lower().strip()) if pos is not None else None,
            rsci_hs_to_pro=int(bool(re.search(r"NBA|G League|Ignite|Overtime|NBL|Europe",l[col] or "",re.I))) if col is not None else None,rsci_prep_5th=int("*" in l[ni])))
print("rsci rows:",len(rows),"years:",len(set(r["hs_class"] for r in rows)))
# match to pids: same normalized name, draft_year in [class, class+6]; latest class <= draft year wins
best={}
for r in rows:
    ks=keys(r["name"]); hits=[]
    for k in ks[:-1]: hits+=by_name.get(k,[])
    if not hits and len(by_name.get(ks[-1],[]))==1: hits=by_name[ks[-1]]   # initial+last fallback only when unambiguous
    for dy,pid in hits:
        if r["hs_class"]<=dy<=r["hs_class"]+6:
            if pid not in best or r["hs_class"]>best[pid]["hs_class"]: best[pid]=dict(r,draft_year=dy)
out=[]
for pid,r in best.items():
    o={"pid":pid,"rsci_top100":1,"rsci_years_to_draft":r["draft_year"]-r["hs_class"]}
    for k,v in r.items():
        if k.startswith("rsci_") and v is not None: o[k]=v
    out.append(o)
cols=["pid","rsci_top100","rsci_rank","rsci_n_ranked","rsci_n_services","rsci_frac_ranked","rsci_best","rsci_worst","rsci_range","rsci_std","rsci_total_norm","rsci_chg","rsci_avg","rsci_dev","rsci_hs_height_in","rsci_hs_pos","rsci_hs_to_pro","rsci_prep_5th","rsci_years_to_draft"]
w=csv.DictWriter(open("rsci_features.csv","w"),fieldnames=cols); w.writeheader(); [w.writerow(o) for o in out]
print("matched pids:",len(out))
byy=collections.Counter(); tot=collections.Counter()
for r in ids:
    dy=int(float(r["draft_year"]))
    if r.get("actual_pick") not in("","nan",None) and 2005<=dy<=2025: tot[dy]+=1; byy[dy]+=r["pid"] in best
print("coverage of drafted players by draft year:"," ".join(f"{y}:{byy[y]}/{tot[y]}" for y in sorted(tot)))
un=[r["name"] for r in rows if r["hs_class"] in(2016,2017) and r["rsci_rank"]<=30 and r["name"] not in {rr["name"] for rr in rows if any(k in by_name for k in keys(rr["name"])[:-1])}]
print("top-30 recruits 2016-17 with no identity match (sanity):",un[:15])

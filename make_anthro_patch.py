"""Merge the research agents' anthro_result_*.json into pid-keyed patches (no names, no URLs leave the Mac).
Only accepts plausible numeric values; records the measurement context as bio_measure_src (2 pro day / 3 team / 4 reported / 5 later)."""
import json,glob,csv,re,collections
S="/private/tmp/claude-501/-Users-kennakao-nba/6b23c15b-6018-47b3-9476-45353eadffc2/scratchpad"; H="/Users/kennakao/Downloads/nba_redraft_handoff"; D="/Users/kennakao/nba/datarebuild"
SRC={"combine":1,"pro day":2,"proday":2,"pro-day":2,"team measurement":3,"team":3,"reported":4,"later":5}
split={}
for r in csv.DictReader(open(f"{H}/data/train_2000_2018.csv")): split[r["pid"]]="train"
for fp in glob.glob(f"{H}/data/tests/test_*_inputs.csv"):
    for r in csv.DictReader(open(fp)): split[r["pid"]]="test"
def num(v,lo,hi):
    try: x=float(v); return x if lo<=x<=hi else None
    except: return None
rows=[]; stats=collections.Counter(); log=[]
for fp in sorted(glob.glob(f"{S}/anthro_result_*.json")):
    try: L=json.load(open(fp))
    except Exception as e: log.append(f"{fp}: unreadable {e}"); continue
    for x in L:
        pid=x.get("pid"); 
        if pid not in split: stats["unknown_pid"]+=1; continue
        ws=num(x.get("wingspan_in"),70,100); rc=num(x.get("reach_in"),85,125); ht=num(x.get("height_noshoes_in"),66,92); wt=num(x.get("weight_lb"),140,330)
        ctx=str(x.get("context") or "").lower().strip(); src=next((v for k,v in SRC.items() if k in ctx),4 if (ws or rc) else None)
        if not any(v is not None for v in(ws,rc,ht,wt)): stats["none_found"]+=1; continue
        rec={"pid":pid}
        if ws is not None: rec["bio_combine_wingspan_in"]=ws
        if rc is not None: rec["bio_combine_reach_in"]=rc
        if ht is not None: rec["bio_combine_height_in"]=ht
        if wt is not None: rec["bio_combine_weight_lb"]=wt
        rec["bio_measure_src"]=src; rows.append((split[pid],rec)); stats[f"{split[pid]}_filled"]+=1; stats[f"src{src}"]+=1
        if ws is not None: stats["wingspan"]+=1
        if rc is not None: stats["reach"]+=1
for sp in("train","test"):
    R=[r for s,r in rows if s==sp]; cols=["pid","bio_combine_wingspan_in","bio_combine_reach_in","bio_combine_height_in","bio_combine_weight_lb","bio_measure_src"]
    with open(f"{D}/anthro_patch_{sp}.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); [w.writerow({c:r.get(c,"") for c in cols}) for r in R]
print("stats:",dict(stats)); print("\n".join(log))

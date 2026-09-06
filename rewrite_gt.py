p="gtrends_collect.py"; s=open(p).read()
if '2004:"2004-06-24"' not in s:
    s=s.replace('DRAFT={2010:','DRAFT={2004:"2004-06-24",2005:"2005-06-28",2006:"2006-06-28",2007:"2007-06-28",2008:"2008-06-26",2009:"2009-06-25",2010:')
    old=s[s.index('ids=[r for r in csv.DictReader'):s.index('pt=TrendReq')]
    new='''import glob,re
split={}
for r in csv.DictReader(open(f"{H}/data/train_2000_2018.csv")):
    if 2004<=int(float(r["draft_year"]))<=2018: split[r["pid"]]="train"
for fp in glob.glob(f"{H}/data/tests/test_*_inputs.csv"):
    for r in csv.DictReader(open(fp)): split[r["pid"]]="test"
ids=[r for r in csv.DictReader(open(f"{H}/identity_KEEP_SEPARATE/tabular_names.csv")) if r["pid"] in split and int(float(r["draft_year"])) in DRAFT]
ids.sort(key=lambda r:(split[r["pid"]]!="test",-int(float(r["draft_year"]))))   # test classes first, then newest train years
'''
    s=s.replace(old,new)
    old2=s[s.index('            try:\n                sug=pt.suggestions'):s.index('            time.sleep(1.5+random.random())')]
    s=s.replace(old2,'').replace('            time.sleep(1.5+random.random())\n','')
    open(p,"w").write(s); print("collector rewritten")
import ast; ast.parse(open(p).read()); print("syntax ok")

"""Minimal source-only order audit bundle; query/append outcome labels excluded."""
from pathlib import Path
import csv
import hashlib
import json
import shutil
import pandas as pd
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'r8r'
DATA=ROOT/'data'
plan=json.loads((SOURCE/'plan.json').read_text())
manifest=json.loads((SOURCE/'data/manifest.json').read_text())
for name in ['features.csv','labels.csv','incumbent.json']:
    assert hashlib.sha256((SOURCE/'data'/name).read_bytes()).hexdigest()==manifest['files'][name]
cols=plan['base_columns'];assert len(cols)==41
x=pd.read_csv(SOURCE/'data/features.csv',usecols=['pid','draft_year','was_drafted']+cols)
assert (x.draft_year<=2018).all() and x.pid.is_unique
tr=x[x.draft_year.between(2007,2010)].copy()
query=x[(x.draft_year==2012)&x.was_drafted.eq(1)].copy()
added=x[x.draft_year.eq(2011)].sort_values('pid').head(32).copy()
assert len(tr)==251 and len(query)==55 and len(added)==32
assert not set(tr.pid)&set(query.pid) and not set(tr.pid)&set(added.pid)
for name,frame in [('train_inputs.csv',tr),('query_inputs.csv',query),('append_inputs.csv',added)]:
    frame[['pid','draft_year']+cols].to_csv(DATA/name,index=False)
# Filter before any label values are used: no query or append labels enter bundle.
with (SOURCE/'data/labels.csv').open() as source,(DATA/'train_labels.csv').open('w') as dest:
    reader=csv.DictReader(source);writer=csv.DictWriter(dest,fieldnames=reader.fieldnames);writer.writeheader()
    for row in reader:
        if row['pid'] in set(tr.pid) and int(float(row['season_end']))<=2011:
            writer.writerow(row)
shutil.copyfile(SOURCE/'data/incumbent.json',DATA/'incumbent.json')
shutil.copyfile(SOURCE/'legacy_kernel.py',ROOT/'legacy_kernel.py')
bundle={'training_label_cutoff':2011,'query_cohort':2012,'training_cohorts':[2007,2010],
        'base_columns':cols,'backbone':plan['backbone'],'fit_seed':0,'maximum_predictions':10,
        'random_query_seeds':[7319,19847,55201],'composition_seed':88127,
        'material_numeric_delta':1e-5,'material_rank_gap':1e-5,
        'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DATA.iterdir()) if p.name!='manifest.json'},
        'origin_source_files':{n:manifest['files'][n] for n in ['features.csv','labels.csv','incumbent.json']},
        'query_and_append_labels_present':False,'actual_pick_or_order_feature_present':False,
        'purpose':'Numerical query-order/composition invariance audit only; no WAR scoring or model selection.'}
(DATA/'manifest.json').write_text(json.dumps(bundle,indent=2))
print(json.dumps({'train_rows':len(tr),'query_rows':len(query),'append_rows':len(added),'features':len(cols),'max_predict_calls':10}))

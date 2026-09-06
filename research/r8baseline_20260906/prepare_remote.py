"""Prepare frozen inference inputs only; never load test outcomes."""
import json,hashlib,time
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parent;DATA=ROOT/'data';HOME=ROOT.parent
manifest=json.loads((DATA/'manifest.json').read_text())
frames=[]
for year in range(2019,2027):
    raw=pd.read_csv(HOME/f'data/tests/test_{year}_inputs.csv')
    raw=raw[pd.to_numeric(raw.was_drafted,errors='coerce')==1].copy()
    cols=['pid']+[c for c in manifest['legacy_features'] if c in raw and c!='draft_year']
    assert not any(c.startswith('y_') or c in ('actual_pick','actual_round','player_name') for c in cols)
    frame=raw[cols].copy();frame['draft_year']=year;frames.append(frame)
pd.concat(frames,ignore_index=True).to_csv(DATA/'inference_inputs.csv',index=False)
cfg=dict(protocol='strict_2018_calendar_baseline',selection='Fixed R8b incumbent without scout values; not selected from new test results',weights={'rich':[0,.75,.25],'thin':[.5,0,.5]},training_season_cutoff=2018,training_cohort_max=2017,horizons={str(y):min(5,2026-y) for y in range(2019,2026)},created=time.time(),feature_provenance='Inherited features remain uncertified; test benchmark previously reused',files={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in DATA.glob('*.csv')})
(ROOT/'frozen_protocol.json').write_text(json.dumps(cfg,indent=2))
print(json.dumps({'prepared_rows':len(pd.concat(frames)), 'years':list(range(2019,2027)), 'outcomes_read':False}))

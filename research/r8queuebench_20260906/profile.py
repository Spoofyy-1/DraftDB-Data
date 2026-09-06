"""Measure existing final-state serialization and audit overhead without fitting."""
from pathlib import Path
import sys,json,time,hashlib,statistics
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'model'))
from worker import summarize_matched
raw=(ROOT/'reference_state.json').read_bytes()
start=time.perf_counter();state=json.loads(raw);load_s=time.perf_counter()-start
measurements=[]
for _ in range(3):
 start=time.perf_counter();summary=summarize_matched(state['candidates']);summary_s=time.perf_counter()-start
 assert summary==state['matched_summary']
 start=time.perf_counter();encoded=json.dumps(state,indent=2,allow_nan=False);encode_s=time.perf_counter()-start
 assert encoded.encode()==raw
 measurements.append({'summary_seconds':summary_s,'json_encode_seconds':encode_s,'two_calls_each_per_loop_seconds':2*(summary_s+encode_s)})
out={'models_fitted':0,'tasks':len(state['candidates']),'state_bytes':len(raw),'state_sha256':hashlib.sha256(raw).hexdigest(),'load_seconds':load_s,'measurements':measurements,'median_two_calls_each_per_loop_seconds':statistics.median(r['two_calls_each_per_loop_seconds'] for r in measurements)}
(ROOT/'results/profile.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

"""Reopen and independently validate six private exports; no model or query access."""
from pathlib import Path
import json,hashlib,sys,stat
import numpy as np
import pandas as pd
from scipy.special import ndtri
from scipy.stats import rankdata
R=Path(sys.argv[1])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def vh(a):
 a=np.asarray(a,dtype=np.float64);a=np.where(a==0.,0.,a);m=np.isnan(a);a=np.where(m,0.,a)
 return hashlib.sha256(canon(list(a.shape))+m.tobytes()+a.tobytes()).hexdigest()
m=json.loads((R/'manifest.json').read_text());assert len(m['exports'])==6;proof=[]
for e in m['exports']:
 d=R/e['policy']/str(e['year']);p=json.loads((d/'manifest.json').read_text());assert sha(d/'manifest.json')==e['manifest_sha256']
 assert sha(d/'training.npz')==e['training_npz_sha256']==p['training_npz_sha256']
 assert sha(d/'eligible_label_facts.csv')==p['private_facts_file_sha256']
 with np.load(d/'training.npz',allow_pickle=False) as z:
  assert set(z.files)=={'pid','draft_year','label_value','y','prefix_length'};a={k:z[k] for k in z.files}
 assert len(set(a['pid']))==len(a['pid']) and len(a['pid'])==e['rows']
 f=pd.read_csv(d/'eligible_label_facts.csv',float_precision='round_trip');assert not f.duplicated(['pid','ordinal']).any() and f.season_end.le(e['year']-1).all()
 assert hashlib.sha256(canon(f[['pid','draft_year','ordinal','season_end','war']].to_dict(orient='records'))).hexdigest()==p['source_fact_hash']
 assert set(f.pid)==set(a['pid']);groups={pid:g.sort_values('ordinal') for pid,g in f.groupby('pid')}
 values=[]
 for pid,year,length in zip(a['pid'],a['draft_year'],a['prefix_length']):
  g=groups[pid];assert g.ordinal.tolist()==list(range(1,int(length)+1));assert g.draft_year.eq(year).all()
  if e['policy'].startswith('h_'):values.append(float(g.war.sum()))
  else:values.append(sum(.85**(int(r.ordinal)-1)*float(r.war) for r in g.itertuples()))
 assert np.array_equal(np.asarray(values),a['label_value'])
 expected=np.empty(len(values));clipped=np.clip(a['label_value'],-40,40)
 for year in np.unique(a['draft_year']):
  mask=a['draft_year']==year;n=int(mask.sum());assert n>=5
  expected[mask]=ndtri(np.clip((rankdata(clipped[mask],method='average')-.5)/n,.01,.99))
 assert np.array_equal(expected,a['y'])
 for field in ['label_value','y','draft_year','prefix_length']:assert vh(a[field])==p[field+'_hash']
 assert hashlib.sha256(canon(a['pid'].tolist())).hexdigest()==p['pid_hash']
 assert p['all_labels_finite_observed'] and not p['missing_training_labels_zero_filled'] and not p['query_truth_exported'] and not p['X_exported']
 proof.append({'policy':e['policy'],'year':e['year'],'rows':e['rows'],'all_facts_contiguous_and_cutoff_eligible':True,'independent_discount_cumulative_and_scipy_rankdata_replay_exact':True,'array_and_fact_hashes_exact':True,'known_zero_season_facts':int(f.war.eq(0).sum()),'zero_raw_target_rows':int((a['label_value']==0).sum())})
for p,h in m['source_hashes'].items():assert sha(Path(p))==h
for p in [R]+list(R.rglob('*')):assert stat.S_IMODE(p.stat().st_mode)==(0o700 if p.is_dir() else 0o600)
result={'passed':True,'exports_verified':6,'models_run':0,'source_hashes_unchanged':True,'all_permissions_private':True,'NPZ_keys_exact_and_no_X_or_query_truth':True,'verification_code_sha256':sha(Path(__file__)),'export_root_manifest_sha256':sha(R/'manifest.json'),'records':proof}
out=R/'verification.json';out.write_text(json.dumps(result,indent=2)+'\n');out.chmod(0o600);print(json.dumps(result,indent=2))

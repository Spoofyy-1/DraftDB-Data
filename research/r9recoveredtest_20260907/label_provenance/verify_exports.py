"""Independent arithmetic/structure replay of private recovered-stack exports; no models."""
from pathlib import Path
import hashlib,json,stat,sys
import numpy as np
import pandas as pd
from scipy.special import ndtri
from scipy.stats import rankdata
R=Path(sys.argv[1])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(x):return hashlib.sha256(x).hexdigest()
def vh(a):
 a=np.asarray(a,dtype=np.float64);a=np.where(a==0.,0.,a);m=np.isnan(a);a=np.where(m,0.,a)
 return digest(canon(list(a.shape))+m.tobytes()+a.tobytes())
m=json.loads((R/'manifest.json').read_text());assert len(m['exports'])==7
proof=[];cache={}
for e in m['exports']:
 d=R/e['relative_path'];p=json.loads((d/'manifest.json').read_text());assert sha(d/'manifest.json')==e['manifest_sha256']
 assert sha(d/'training.npz')==e['training_npz_sha256']==p['training_npz_sha256']
 assert sha(d/'eligible_label_facts.csv')==p['private_facts_file_sha256']
 with np.load(d/'training.npz',allow_pickle=False) as z:
  assert set(z.files)=={'pid','draft_year','label_value','y','prefix_length','season_end_max'};a={k:z[k] for k in z.files}
 assert all(v.dtype.kind!='O' for v in a.values()) and len(set(a['pid']))==len(a['pid'])==e['rows']
 assert a['draft_year'].min()>=2007 and a['draft_year'].max()<e['year']
 assert a['pid'].tolist()==sorted(a['pid'],key=lambda x:(digest(x.encode()),x))
 qpath=R/'queries'/f"{e['year']}.npz";assert sha(qpath)==m['query_metadata'][str(e['year'])]['query_npz_sha256']
 with np.load(qpath,allow_pickle=False) as q:
  assert set(q.files)=={'pid','draft_year'} and not set(q['pid'])&set(a['pid'])
  assert digest(canon(q['pid'].tolist()))==p['query_pid_hash'] and np.all(q['draft_year']==e['year'])
 f=pd.read_csv(d/'eligible_label_facts.csv',float_precision='round_trip')
 assert not f.duplicated(['pid','ordinal']).any() and f.season_end.le(e['year']-1).all() and np.isfinite(f.war).all()
 assert digest(canon(f[['pid','draft_year','ordinal','season_end','war']].to_dict(orient='records')))==p['source_fact_hash']
 groups={pid:g.sort_values('ordinal') for pid,g in f.groupby('pid')};assert set(groups)==set(a['pid'])
 values=[];maxima=[]
 for pid,year,length in zip(a['pid'],a['draft_year'],a['prefix_length']):
  g=groups[pid];assert g.ordinal.tolist()==list(range(1,int(length)+1)) and int(length)<=p['cap']
  assert g.draft_year.eq(year).all() and g.season_end.gt(year).all()
  assert g.season_end.tolist()==sorted(set(g.season_end));maxima.append(g.season_end.max())
  values.append(sum(.85**(int(r.ordinal)-1)*float(r.war) for r in g.itertuples()))
 assert np.array_equal(values,a['label_value']) and np.array_equal(maxima,a['season_end_max'])
 clipped=np.clip(a['label_value'],-40,40);expected=np.empty(len(values))
 for year in np.unique(a['draft_year']):
  mask=a['draft_year']==year;n=int(mask.sum());assert n>=5
  expected[mask]=ndtri(np.clip((rankdata(clipped[mask],method='average')-.5)/n,.01,.99))
 assert np.array_equal(expected,a['y'])
 for field,expectedhash in p['array_hashes'].items():assert vh(a[field])==expectedhash
 assert digest(canon(a['pid'].tolist()))==p['pid_hash']
 assert p['all_labels_finite_observed'] and not p['missing_training_labels_zero_filled'] and not p['query_truth_exported'] and not p['X_exported']
 cache[e['mode'],e['year']]=a
 proof.append({'mode':e['mode'],'year':e['year'],'rows':e['rows'],'facts_contiguous_and_actual_cutoff_eligible':True,'independent_discount_and_scipy_rankdata_replay_exact':True,'array_and_fact_hashes_exact':True})
for p,h in m['source_hashes'].items():assert sha(Path(p))==h
for p in [R]+list(R.rglob('*')):assert stat.S_IMODE(p.stat().st_mode)==(0o700 if p.is_dir() else 0o600)
out={'passed':True,'exports_verified':7,'query_metadata_files_verified':7,'models_run':0,'predictions_scored':0,'source_hashes_unchanged':True,'private_permissions_exact':True,'replay2019':m['replay2019'],'calendar_audits':m['calendar_audits'],'records':proof,'query_outcomes_or_vault_opened':False,'export_root_manifest_sha256':sha(R/'manifest.json'),'verification_code_sha256':sha(Path(__file__))}
target=R/'verification.json';target.write_text(json.dumps(out,indent=2)+'\n');target.chmod(0o600)
print(json.dumps(out,indent=2))

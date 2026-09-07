"""Input-only panel joins plus exact H h1 labels; no model fitting or score reading."""
from pathlib import Path
import os,json,hashlib
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parent;H=ROOT.parent/'r9h';K=ROOT.parent/'r9k';L=ROOT.parent/'r9k_label_exports'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(p,x):
 with p.open('x')as f:f.write(json.dumps(x,indent=2,allow_nan=False)+'\n')
def ah(a):
 a=np.asarray(a,dtype=np.float64);a=np.where(a==0,0.,a);m=np.isnan(a)
 return hashlib.sha256(json.dumps(list(a.shape),separators=(',',':')).encode()+m.tobytes()+np.where(m,0.,a).tobytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def main():
 os.umask(0o077);assert not(ROOT/'inputs').exists();(ROOT/'inputs').mkdir();(ROOT/'scoring').mkdir()
 protocol=read(ROOT/'code/protocol.json');hp=read(H/'plan.json');hf=read(H/'frozen.json');assert sha(H/'frozen.json')=='22e68b8bee7902d65ed0f1c7a2d04bde3fc6521f5f872339faead15416c24d0e'
 assert sha(H/'plan.json')==hf['files']['plan.json']
 pm=read(K/'panels/panel_manifest.json');assert sha(K/'panels/panel_manifest.json')==protocol['source_panel_manifest_sha256']
 path=K/'panels/panel174.csv';assert sha(path)==pm['outputs']['panel174.csv']['sha256'];panel=pd.read_csv(path,float_precision='round_trip').set_index('pid');assert len(panel)==1428 and panel.index.is_unique and panel.draft_year.le(2018).all()
 hpolicy=next(x for x in hp['canonical_payloads']if x['id']=='s2008_gap1_all_h1');tasks=[];scoring={};source_labels={}
 for year in protocol['outer_years']:
  audit=next(a for a in hpolicy['folds']if a['year']==year);train_path=H/'data'/f's2008_gap1_all_h1_{year}.npz';query_path=H/'data'/f'query_{year}.npz'
  for path in [train_path,query_path]:assert sha(path)==hf['files'][str(path.relative_to(H))]
  with np.load(train_path,allow_pickle=False)as z:tr={k:z[k]for k in z.files}
  with np.load(query_path,allow_pickle=False)as z:q={k:z[k]for k in z.files}
  assert ah(tr['y'])==audit['target_hash']and ah(tr['source_cumulative_WAR'])==audit['cumulative_WAR_hash']
  assert np.array_equal(panel.loc[tr['pid'],pm['columns44']].to_numpy(float),tr['X'],equal_nan=True)
  assert np.array_equal(panel.loc[q['pid'],pm['columns44']].to_numpy(float),q['X'],equal_nan=True)
  src=L/'prefix_s2007_gap1_all_d085'/str(year);m=read(src/'manifest.json');assert sha(src/'eligible_label_facts.csv')==m['private_facts_file_sha256']
  facts=pd.read_csv(src/'eligible_label_facts.csv',float_precision='round_trip');facts=facts[facts.ordinal.eq(1)&facts.pid.isin(tr['pid'])].sort_values(['pid','ordinal']).reset_index(drop=True)
  assert len(facts)==len(tr['pid']) and facts.pid.is_unique and facts.season_end.le(year-1).all()and facts.draft_year.lt(year).all()
  assert np.array_equal(facts.set_index('pid').loc[tr['pid'],'war'].to_numpy(float),tr['source_cumulative_WAR'])
  assert digest(facts[['pid','draft_year','ordinal','season_end','war']].to_dict(orient='records'))==audit['source_fact_hash']
  source_labels[str(year)]={'H_training_npz_sha256':sha(train_path),'cutoff_broker_prefix_manifest_sha256':sha(src/'manifest.json'),'all_H_first_season_facts_reverified':True,'rows':len(tr['pid']),'max_actual_label_season':int(facts.season_end.max())}
  dest=ROOT/'scoring'/f'{year}.npz';np.savez_compressed(dest,pid=q['pid'],legacy_truth=q['legacy_truth'],observed_truth_mask=q['observed_truth_mask']);scoring[str(year)]={'sha256':sha(dest),'source_sha256':sha(query_path),'not_mounted_in_model_worker':True}
  for spec in protocol['panels']:
   cols=spec['columns'];tid=f"{spec['id']}_y{year}";out=ROOT/'inputs'/tid;out.mkdir()
   np.savez_compressed(out/'training.npz',X=panel.loc[tr['pid'],cols].to_numpy(float),pid=tr['pid'],draft_year=tr['draft_year'],label_value=tr['source_cumulative_WAR'],y=tr['y'],prefix_length=np.ones(len(tr['pid']),dtype=np.int64))
   np.savez_compressed(out/'inference.npz',X=panel.loc[q['pid'],cols].to_numpy(float),pid=q['pid'])
   la={'outer_year':year,'max_actual_label_season':int(facts.season_end.max()),'all_labels_finite_observed':True,'missing_training_labels_zero_filled':False,'training_pid_hash':audit['pid_hash'],'label_value_hash':audit['cumulative_WAR_hash'],'target_hash':audit['target_hash'],'source_fact_hash':audit['source_fact_hash'],'source_fact_rows':len(facts),'cutoff_broker_reverified':True}
   manifest={'task_id':tid,'panel_id':spec['id'],'policy_id':protocol['policy_id'],'outer_year':year,'columns':cols,'protocol_sha256':sha(ROOT/'code/protocol.json'),'files':{n:{'sha256':sha(out/n)}for n in ['training.npz','inference.npz']},'label_audit':la};save(out/'manifest.json',manifest)
   tasks.append({'id':tid,'panel_id':spec['id'],'policy_id':protocol['policy_id'],'outer_year':year,'input_manifest_sha256':sha(out/'manifest.json'),'training_rows':len(tr['pid']),'query_rows':len(q['pid'])})
 assert len(tasks)==24
 j=ROOT.parent/'r9j';assert sha(j/'frozen.json')=='05bf210e7dda4fa78aa0add4b9b1501f4194071f5395ac6dceb04824602a1432'
 logged={e['task_id']:e for e in [json.loads(line)for line in (j/'results/completed.jsonl').read_text().splitlines()]}
 reference={str(y):{'query_pids':hp['queries'][str(y)]['query_pids'],'members':{}}for y in protocol['outer_years']}
 for family in ['tabicl','ridge_a30','ridge_a300','ridge_a3000']:
  for seed in [0,101,202]:
   tid=f'href_s2008_gap1_all_h1_B_tabicl32_seed{seed}'if family=='tabicl'else f's2008_gap1_all_h1__{family}_seed0'
   path=j/'results/tasks'/f'{tid}.json';assert sha(path)==logged[tid]['sha256'];record=read(path)
   for row in record['rows']:
    preds=row['predictions']if family=='tabicl'else row['checkpoints'][0]['predictions'];year=str(row['season'])
    assert [v['pid']for v in preds]==reference[year]['query_pids']
    reference[year]['members'].setdefault(family,{})[str(seed)]={'raw':[v['raw_score']for v in preds],'canonical':[v['score']for v in preds],'source_task_sha256':sha(path)}
 save(ROOT/'scoring/reference_vectors.json',reference)
 plan={'study':'R9L feature-family additions to verified TabICL-Ridge stack','target_percent':55,'tasks':tasks,'task_count':24,'model_fits':216,'workers':4,'outer_years':[2012,2013,2014],'seeds':[0,101,202],'protocol_sha256':sha(ROOT/'code/protocol.json'),'scoring':scoring,'source_labels':source_labels,'architectures':protocol['architectures'],'full_pool_primary':True,'subset_secondary':True,'fitted_weights':False,'reference_gate':'Exact44 J TabICL/Ridge allfold/seed vectors and50/50 recipe must replay before interpretation','no_2019plus_scoring':True,'no_automatic_promotion':True}
 plan['reference_vectors_sha256']=sha(ROOT/'scoring/reference_vectors.json')
 save(ROOT/'plan.json',plan);print(json.dumps({'tasks':24,'fits':216,'plan_sha256':sha(ROOT/'plan.json'),'label_reverification':source_labels}))
if __name__=='__main__':main()

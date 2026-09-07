"""Development scoring outside model namespaces; exact old-stack gate first."""
from pathlib import Path
import json,hashlib
import numpy as np
import reuse_controls
import cross_panel
from scipy.stats import rankdata
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def rho(a,b):
 a=rankdata(a);b=rankdata(b)
 return float(np.corrcoef(a,b)[0,1])if np.ptp(a)>0 and np.ptp(b)>0 else 0.
def reference_gate(records,root):
 source,gate=reuse_controls.verify(root);byid={r['task_id']:r for r in records}
 for r in source:
  assert r['task_id']in byid and r==byid[r['task_id']], 'Reused control record changed'
 return gate
def summarize(records,root):
 root=Path(root);p=read(root/'plan.json');recipes={r['id']:r for r in p['architectures']};detail=[];groups={};gate=reference_gate(records,root)
 for r in records:
  year=r['outer_year'];path=root/'scoring'/f'{year}.npz';assert sha(path)==p['scoring'][str(year)]['sha256']
  with np.load(path,allow_pickle=False)as q:
   assert r['query_pids']==q['pid'].tolist();truth=q['legacy_truth'];mask=q['observed_truth_mask']
  modes=r['seed_results']+[{'seed':'fixed_three_seed_family_rank_average',**r['fixed_three_seed_family_rank_average']}]
  for mode in modes:
   vectors=dict(mode['architectures'])
   for family,v in mode['members'].items():vectors['control_'+family]=v['canonical_predictions']if isinstance(v,dict)else v
   for name,v in vectors.items():
    v=np.asarray(v,dtype=float);assert v.shape==truth.shape and np.isfinite(v).all()
    row={'panel_id':r['panel_id'],'architecture':name,'year':year,'seed':mode['seed'],'query_pids':r['query_pids'],'prediction':v.tolist(),'full':rho(v,truth),'observed':rho(v[mask],truth[mask])};detail.append(row);groups.setdefault((r['panel_id'],name),[]).append(row)
 summaries=[]
 for (panel,name),rows in groups.items():
  if {r['year']for r in rows}!={2012,2013,2014}:continue
  direct=[r for r in rows if isinstance(r['seed'],int)];fixed=[r for r in rows if isinstance(r['seed'],str)];assert len(direct)==9 and len(fixed)==3
  recipe=recipes.get(name);multi=bool(recipe and len(recipe['members'])>=2)
  item={'panel_id':panel,'policy_id':'h_s2008_gap1_all_h1','architecture':name,'recipe':recipe,'member_control':name.startswith('control_')or not multi,'multi_family_every_fold_seed':multi,'diagnostic_only':True,'no_automatic_promotion':True}
  for metric in ['full','observed']:
   item[metric]={'mean_score':float(np.mean([r[metric]for r in direct])),'fold_scores':{str(y):float(np.mean([r[metric]for r in direct if r['year']==y]))for y in p['outer_years']},'seed_scores':{str(s):float(np.mean([r[metric]for r in direct if r['seed']==s]))for s in p['seeds']},'fixed_three_seed_family_rank_average':float(np.mean([r[metric]for r in fixed]))}
  summaries.append(item)
 bykey={(r['panel_id'],r['architecture']):r for r in summaries};comparisons=[]
 for s in summaries:
  baseline=bykey.get(('base44',s['architecture']))
  if s['panel_id']!='base44' and baseline:
   s['full_gain_vs_same_recipe44']=s['full']['mean_score']-baseline['full']['mean_score'];s['full_fold_gains_vs44']={y:s['full']['fold_scores'][y]-baseline['full']['fold_scores'][y]for y in s['full']['fold_scores']};s['full_seed_gains_vs44']={y:s['full']['seed_scores'][y]-baseline['full']['seed_scores'][y]for y in s['full']['seed_scores']};s['all_fold_and_seed_means_improved']=all(x>0 for x in list(s['full_fold_gains_vs44'].values())+list(s['full_seed_gains_vs44'].values()));comparisons.append(s)
 summaries.sort(key=lambda s:(-s['full']['mean_score'],s['panel_id'],s['architecture']));stacks=[s for s in summaries if s['multi_family_every_fold_seed']];controls=[s for s in summaries if s['member_control']]
 result={'reference_gate':gate,'stack_summaries_oof':stacks if gate['passed']else[],'control_summaries_oof':controls if gate['passed']else[],'best_actual_multifamily_stack':stacks[0]if stacks and gate['passed']else None,'best_member_control':controls[0]if controls and gate['passed']else None,'paired_panel_comparisons':comparisons if gate['passed']else[],'prediction_details':detail,'scored_prediction_records':len(detail),'full_pool_primary':True,'subset_secondary':True,'interpretation_allowed':gate['passed'],'no2019plus_access':True}

 if len(records)==24:
  protocol=read(root/'code/protocol.json');cross=cross_panel.assemble(records,protocol,gate);cross_groups={};cross_details=[]
  query_cache={}
  for year in p['outer_years']:
   path=root/'scoring'/f'{year}.npz';assert sha(path)==p['scoring'][str(year)]['sha256']
   with np.load(path,allow_pickle=False)as q:query_cache[year]=(q['pid'].tolist(),q['legacy_truth'].copy(),q['observed_truth_mask'].copy())
  for row in cross['cross_panel_prediction_records']:
   year=row['year'];pids,truth,mask=query_cache[year];assert row['query_pids']==pids
   v=np.asarray(row['prediction']);scored={**row,'full':rho(v,truth),'observed':rho(v[mask],truth[mask])};cross_details.append(scored);cross_groups.setdefault(row['architecture'],[]).append(scored)
  cross_summaries=[]
  for recipe in protocol['cross_panel_stacks']['recipes']:
   rows=cross_groups[recipe['id']];direct=[r for r in rows if isinstance(r['seed'],int)];fixed=[r for r in rows if isinstance(r['seed'],str)];assert len(direct)==9 and len(fixed)==3
   multi=all(r['multi_family_stack']for r in rows);item={'panel_id':'cross_panel','policy_id':protocol['policy_id'],'architecture':recipe['id'],'recipe':recipe,'member_control':not multi,'multi_family_every_fold_seed':multi,'diagnostic_only':True,'no_automatic_promotion':True}
   for metric in ['full','observed']:
    item[metric]={'mean_score':float(np.mean([r[metric]for r in direct])),'fold_scores':{str(y):float(np.mean([r[metric]for r in direct if r['year']==y]))for y in p['outer_years']},'seed_scores':{str(s):float(np.mean([r[metric]for r in direct if r['seed']==s]))for s in p['seeds']},'fixed_three_seed_family_rank_average':float(np.mean([r[metric]for r in fixed]))}
   same=recipe['design_aliases'][0]['same_panel_recipe']
   for panel,suffix in [('base44','44'),('add_f50','f50')]:
    ref=bykey[(panel,same)];item[f'full_gain_vs_same_recipe_{suffix}']=item['full']['mean_score']-ref['full']['mean_score'];item[f'full_fold_gains_vs_{suffix}']={y:item['full']['fold_scores'][y]-ref['full']['fold_scores'][y]for y in item['full']['fold_scores']};item[f'full_seed_gains_vs_{suffix}']={s:item['full']['seed_scores'][s]-ref['full']['seed_scores'][s]for s in item['full']['seed_scores']}
   cross_summaries.append(item)
  cross_summaries.sort(key=lambda s:(-s['full']['mean_score'],s['architecture']));result.update(cross_panel_summaries=cross_summaries,cross_panel_prediction_details=cross_details,cross_panel_scored_prediction_records=len(cross_details),best_cross_panel_actual_stack=next((s for s in cross_summaries if s['multi_family_every_fold_seed']),None),best_cross_panel_standalone_control=next((s for s in cross_summaries if s['member_control']),None))
 return result

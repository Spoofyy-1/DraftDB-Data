"""All frozen stack recipes from saved predictions; no fit/optimization."""
from pathlib import Path
import json,gzip,hashlib
import numpy as np
import worker as W
from stack_math import blend,family_seed_average
def sha(b):return hashlib.sha256(b).hexdigest()
def save(path,value):
 raw=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode();tmp=path.with_suffix('.tmp');tmp.write_bytes(raw);tmp.replace(path)
def process(records,out):
 p=W.plan();assert len(records)==48 and W.summarize(records)['reference_replays_passed']==12
 tasks={(e['config']['id'],e['seed']):e for e in records};out=Path(out);dest=out/'stack_diagnostics';dest.mkdir(exist_ok=True);summaries=[];chunks=[];total=0
 for payload in p['payloads']:
  pid=payload['id'];anchor=payload['matched_anchor_variant'];queries={};vectors={}
  for year in p['folds']:
   _,ate,_,te,_,_=W.H.payload(pid,year);queries[year]=(ate,te)
   for seed in p['seeds']:
    ar=next(r for r in tasks[('href_'+anchor,seed)]['rows']if r['season']==year)
    vectors[('matched_H_anchor',None,seed,year)]=np.array([r['score']for r in ar['predictions']])
   for s in p['settings']:
    for seed in s['seeds']:
     row=next(r for r in tasks[(pid+'__'+s['id'],seed)]['rows']if r['season']==year)
     for cp in row['checkpoints']:vectors[(s['id'],cp['checkpoint'],seed,year)]=np.array([r['score']for r in cp['predictions']])
   member_keys={key[:2]for key in vectors if key[3]==year}
   for setting,cp in member_keys:
    if setting.startswith('ridge_'):
     for seed in [101,202,None]:vectors[(setting,cp,seed,year)]=vectors[(setting,cp,0,year)]
    else:vectors[(setting,cp,None,year)]=family_seed_average([vectors[(setting,cp,s,year)]for s in p['seeds']])
  per_recipe={r['id']:[]for r in p['stacks']['recipes']}
  for seed in p['seeds']+[None]:
   mode='fixed_three_seed_family_rank_average'if seed is None else f'seed_{seed}';path=dest/f'{pid}__{mode}.jsonl.gz';tmp=path.with_suffix('.tmp');lines=[];unc=hashlib.sha256();size=0
   with tmp.open('wb')as file:
    with gzip.GzipFile(filename='',mode='wb',fileobj=file,mtime=0,compresslevel=6)as stream:
     for recipe in p['stacks']['recipes']:
      rows=[]
      for year in p['folds']:
       ate,te=queries[year];vs=[vectors[(m['setting'],m['checkpoint'],seed,year)]for m in recipe['members']];z=blend(vs,recipe,ate);base=vectors[('matched_H_anchor',None,seed,year)];truth=te['legacy_truth'];mask=te['observed_truth_mask'];seen={}
       for key,value in zip(W.B._exact_vector_keys(ate),z):
        if key in seen:assert seen[key]==value
        else:seen[key]=value
       row={'season':year,'predictions':[{'pid':pid,'score':float(x)}for pid,x in zip(te['pid'],z)],'exact_input_vector_ties_preserved':True,'source_prediction_hashes':[W.H.values_hash(x)for x in vs]}
       for metric,keep in [('legacy',np.ones(len(z),dtype=bool)),('observed',mask)]:
        value=W.B.rho(z[keep],truth[keep]);baseline=W.B.rho(base[keep],truth[keep]);row[metric+'_score']=value;row[metric+'_delta']=value-baseline
       rows.append(row)
      result={'payload_id':pid,'recipe_id':recipe['id'],'recipe':recipe,'mode':mode,'seed':seed,'rows':rows}
      for metric in ['legacy','observed']:result[metric]={'mean_score':float(np.mean([r[metric+'_score']for r in rows])),'mean_delta':float(np.mean([r[metric+'_delta']for r in rows])),'fold_deltas':{str(r['season']):r[metric+'_delta']for r in rows}}
      per_recipe[recipe['id']].append(result);raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();line=raw+b'\n';stream.write(line);unc.update(line);size+=len(line);lines.append({'line_1based':len(lines)+1,'sha256':sha(raw),'bytes':len(raw)});total+=1
   assert tmp.stat().st_size<40_000_000
   if path.exists():assert tmp.read_bytes()==path.read_bytes();tmp.unlink()
   else:tmp.replace(path)
   restored=hashlib.sha256()
   with gzip.open(path,'rb')as stream:
    for item in lines:
     line=stream.readline();assert line.endswith(b'\n')and sha(line[:-1])==item['sha256']and len(line)-1==item['bytes'];restored.update(line)
    assert not stream.read()
   assert restored.hexdigest()==unc.hexdigest();chunks.append({'file':str(path.relative_to(out)),'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size,'uncompressed_sha256':unc.hexdigest(),'uncompressed_bytes':size,'recipes':lines,'all_roundtrips_exact':True})
  for recipe in p['stacks']['recipes']:
   results=per_recipe[recipe['id']];group=[x for x in results if x['seed']is not None];fixed=next(x for x in results if x['seed']is None);result={'payload_id':pid,'recipe_id':recipe['id'],'recipe':recipe,'primary_ranking_mode':'mean_all_three_seed_correlations','fixed_three_seed_family_rank_average':{m:fixed[m]for m in ['legacy','observed']}}
   for metric in ['legacy','observed']:
    deltas={str(y):float(np.mean([r[metric+'_delta']for e in group for r in e['rows']if r['season']==y]))for y in p['folds']};seed_deltas={str(e['seed']):e[metric]['mean_delta']for e in group};result[metric]={'mean_score':float(np.mean([e[metric]['mean_score']for e in group])),'mean_delta':float(np.mean([e[metric]['mean_delta']for e in group])),'fold_deltas':deltas,'seed_deltas':seed_deltas,'positive_every_fold_and_seed_mean':all(x>0 for x in list(deltas.values())+list(seed_deltas.values()))}
   summaries.append(result)
 assert total==p['stacks']['recipe_records_expected']==2244 and len(chunks)==12
 save(out/'stack_manifest.json',{'recipes':total,'chunks':chunks,'all_roundtrips_exact':True,'registered_method':p['stacks'],'both_metrics':True,'no_weight_fitting':True})
 save(out/'stack_summary.json',{'diagnostic_only':True,'no_automatic_promotion':True,'selection_criterion':p['stacks']['selection_rule'],'summaries':summaries})
 # Display is explicitly selected by primary full-pool development mean, never subset score.
 ranked=sorted(summaries,key=lambda x:(-x['legacy']['mean_score'],x['payload_id'],x['recipe_id']))
 def compact(x):return {**x,'primary_metric':'full_pool_mean_three_seed_Spearman','secondary_metric':'complete_target_subset','diagnostic_only':True,'no_automatic_promotion':True}
 leaders=[compact(next(x for x in ranked if x['payload_id']==v['id']))for v in p['payloads']]
 return {'recipes':total,'chunks':len(chunks),'configurations':len(summaries),'both_metrics':True,'no_weight_fitting':True,'all_roundtrips_exact':True,'best_stack':compact(ranked[0]),'stack_summaries':[compact(x)for x in ranked[:10]],'best_stack_each_payload':leaders,'equal_weight_references':[compact(x)for x in summaries if x['recipe_id']in[p['stacks']['equal_three_family_reference'],p['stacks']['equal_four_family_reference']]],'architecture_references':[compact(x)for x in summaries if x['recipe']['kind']=='adapted_coverage_control']}

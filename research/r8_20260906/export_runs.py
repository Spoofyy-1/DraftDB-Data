import json,pathlib,hashlib
root=pathlib.Path('/home/ubuntu/nba/handoff')
allowed={'gen','mut','mutation','delta','accepted','passed','name','style','wf','fit','fitness','gain',
         'folds','fold_fit','mf','cf','secs','time','ts','t','genome','champ','weights','wts','kind','metric',
         'fitmetric','improved','base','candidate','config','desc','label','status','win','mean','n_wins'}
out={'files':[]}
for folder in ['r3','r4','r5','r6','r7']:
 for p in sorted((root/folder).rglob('*')):
  if not p.is_file():continue
  if not any(s in p.name for s in ['runs','lineage']):continue
  if not ('.json' in p.name):continue
  try:
   raw=p.read_text()
   if '.jsonl' in p.name: records=[json.loads(x) for x in raw.splitlines() if x.strip()]
   else:
    data=json.loads(raw)
    records=data.get('history',data.get('runs',[data])) if isinstance(data,dict) else data
   if not isinstance(records,list):records=[records]
   cleaned=[]
   for r in records:
    if isinstance(r,dict):cleaned.append({k:v for k,v in r.items() if k in allowed})
   out['files'].append({'path':str(p.relative_to(root)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                         'keys':sorted(set(k for r in records if isinstance(r,dict) for k in r)),
                         'records':cleaned})
  except Exception as e:out['files'].append({'path':str(p.relative_to(root)),'error':str(e)})
out['policy']='Configuration and development metrics only; blind scores and per-player outcomes omitted.'
print(json.dumps(out,indent=1))

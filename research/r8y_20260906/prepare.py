from pathlib import Path
import json,shutil,hashlib
R=Path(__file__).resolve().parent;X=R.parent/'r8x'
for n in ['worker.py','plan.json','source_manifest.json','queue_runtime.py','w_reference.json']:shutil.copyfile(X/n,R/'x_reference'/n)
shutil.copytree(X/'base',R/'x_reference/base',dirs_exist_ok=True)
shutil.copyfile(X/'queue_runtime.py',R/'queue_runtime.py')
xplan=json.loads((X/'plan.json').read_text());p={'study':'R8y ensemble-size diagnostic','diagnostic_only':True,'no_confirmation_or_test_scoring':True,'folds':xplan['folds'],'seeds':xplan['seeds'],'sizes':[16,32,64,128,256],'contexts':['baseline','pair06_RR'],'model_constructor':xplan['model_constructor'],'variants':[],'execution':{'task_count':30,'workers':4,'runtime_seconds':7200,'memory':'140G','cpu_quota':'2200%'}}
for size in [32,16,64,128,256]:
 for context in p['contexts']:p['variants'].append({'id':f'{context}_n{size}','context':context,'n_estimators':size})
p['reference_gate']='All six n32 tasks must exactly match X raw/canonical predictions, scores and full fold audits before interpretation.'
p['capacity_note']='Record effective ensemble count and feature count; feature-permutation caps can make64/128/256 identical. No architecture, checkpoint, normalization or precision change.'
p['selection']='Fixed W baseline and completed X pair06 RR (usage career slope + posterior rim), selected on pre2019 development only; no promotion.'
(R/'plan.json').write_text(json.dumps(p,indent=2)+'\n')
refs=[json.loads((X/'results/tasks'/f'{context}_seed{seed}.json').read_text()) for context in p['contexts'] for seed in p['seeds']]
(R/'references.json').write_text(json.dumps({'records':refs,'source_completion_sha256':hashlib.sha256((X/'results/completion.json').read_bytes()).hexdigest()},indent=2)+'\n')
files={str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in (R/'x_reference').rglob('*') if f.is_file() and '__pycache__'not in f.parts}
(R/'source_manifest.json').write_text(json.dumps({'files':files},indent=2)+'\n')

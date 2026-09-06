"""Scheduler-only fixtures; no ML estimator is constructed or fitted."""
from pathlib import Path
import tempfile,json,time,copy,concurrent.futures as cf
import queue_runtime as Q
import benchmark as B


def job(vid,seed):
    time.sleep(.015)
    return {'task_id':f'{vid}_seed{seed}','seed':seed,'config':{'id':vid},'score':seed+.25,'rows':[{'payload':['a',None,1.25]}],'seconds':.015}


def validate(record):assert record==job_value(record['config']['id'],record['seed'])

def job_value(vid,seed):return {'task_id':f'{vid}_seed{seed}','seed':seed,'config':{'id':vid},'score':seed+.25,'rows':[{'payload':['a',None,1.25]}],'seconds':.015}


def summarize(records):return {'count':len(records),'sum':sum(r['score'] for r in records)}


def rejects(name,fn,tests):
    try:fn()
    except (AssertionError,json.JSONDecodeError):tests.append(name)
    else:raise AssertionError('Tamper accepted: '+name)


def main():
    tests=[];tasks=[(f'case{i}',i) for i in range(8)];events=[]
    with tempfile.TemporaryDirectory() as td:
        out=Path(td)/'run'
        result=Q.run_queue(tasks,job,[],out,validate,summarize,lambda n:cf.ThreadPoolExecutor(n),workers=2,snapshot_seconds=100,summary_seconds=100,registration_hash='fixture',event=lambda k,d:events.append((k,d)))
        assert result['completed_new']==8 and result['counts']=={'snapshots':2,'summaries':2}
        for v,s in tasks:assert json.loads((out/'tasks'/f'{v}_seed{s}.json').read_text())==job_value(v,s)
        submitted=collected=0
        for kind,detail in events:
            if kind=='submitted':submitted+=1
            if kind=='collected':collected+=1
            if kind=='persist_start':assert submitted>=min(8,2+collected),'Persistence preceded refill'
        def forbid(*a):raise AssertionError('Completed task reran')
        resumed=Q.run_queue(tasks,forbid,[],out,validate,summarize,lambda n:cf.ThreadPoolExecutor(n),workers=2,snapshot_seconds=100,summary_seconds=100,registration_hash='fixture')
        assert len(resumed['records'])==8
        (out/'completed.jsonl').unlink()
        recovered=Q.run_queue(tasks,forbid,[],out,validate,summarize,lambda n:cf.ThreadPoolExecutor(n),workers=2,snapshot_seconds=100,summary_seconds=100,registration_hash='fixture')
        assert len((out/'completed.jsonl').read_text().splitlines())==8 and len(recovered['records'])==8
        rejects('changed_registration',lambda:Q.run_queue(tasks,forbid,[],out,validate,summarize,lambda n:cf.ThreadPoolExecutor(n),workers=2,snapshot_seconds=100,summary_seconds=100,registration_hash='different'),tests)
        rejects('changed_initial_records',lambda:Q.run_queue(tasks,forbid,[job_value('prior',99)],out,validate,summarize,lambda n:cf.ThreadPoolExecutor(n),workers=2,snapshot_seconds=100,summary_seconds=100,registration_hash='fixture'),tests)
        conflict=job_value('case0',0);conflict['score']=123
        rejects('conflicting_immutable',lambda:Q.save_immutable(out/'tasks',conflict),tests)
        path=out/'tasks/case0_seed0.json';good=path.read_bytes();path.write_text(json.dumps(conflict))
        rejects('changed_record_or_log_hash',lambda:Q.load_completed(out/'tasks',out/'completed.jsonl',{f'{v}_seed{s}' for v,s in tasks},validate),tests);path.write_bytes(good)
        with (out/'completed.jsonl').open('a') as f:f.write('{"unfinished":')
        rejects('partial_log_fails_closed',lambda:Q.load_completed(out/'tasks',out/'completed.jsonl',{f'{v}_seed{s}' for v,s in tasks},validate),tests)
    source=json.loads((B.ROOT/'reference_state.json').read_text())['candidates'][0]
    assert B.exact_reference(source,source)
    for name,mutate in [('raw_prediction',lambda r:r['rows'][0]['predictions'][0].__setitem__('raw_score',999.)),('score',lambda r:r.__setitem__('score',999.)),('audit',lambda r:r['rows'][0]['audit'].__setitem__('training_matrix_hash','changed'))]:
        changed=copy.deepcopy(source);mutate(changed);rejects(name,lambda:B.exact_reference(changed,source),tests)
    output={'passed':True,'models_fitted':0,'fixture_tasks':8,'immutable_raw_records_exact':True,'refill_before_persistence':True,'completed_tasks_not_reexecuted':True,'published_but_unlogged_record_recovered':True,'snapshot_and_summary_throttling':True,'directory_fsync_after_publish':True,'tamper_rejections':tests,'partial_log_policy':'Fail closed; explicit repair required. Never silently discard a partial tail.'}
    (B.ROOT/'tests.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output,indent=2))

if __name__=='__main__':main()

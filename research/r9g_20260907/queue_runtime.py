"""Immediate-refill queue with immutable outputs and throttled compact progress.

This module controls scheduling/persistence only; it never prepares model inputs.
"""
import concurrent.futures as cf
import hashlib,json,os,re,time,uuid
from pathlib import Path


def digest(raw):return hashlib.sha256(raw).hexdigest()

def sync_directory(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def atomic_json(path,value):
    raw=json.dumps(value,indent=2,allow_nan=False).encode()
    tmp=path.with_name('.'+path.name+'.tmp')
    with tmp.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    tmp.replace(path);sync_directory(path.parent)


def save_immutable(directory,record):
    tid=record['task_id'];assert re.fullmatch(r'[A-Za-z0-9_]+',tid)
    raw=json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    final=directory/(tid+'.json')
    if final.exists():
        assert final.read_bytes()==raw,'Conflicting immutable result: '+tid
        return final,digest(raw)
    tmp=directory/('.'+tid+'.'+uuid.uuid4().hex+'.tmp')
    with tmp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    try:os.link(tmp,final) # Atomic publish, no overwrite.
    except FileExistsError:assert final.read_bytes()==raw,'Conflicting immutable result: '+tid
    finally:tmp.unlink()
    sync_directory(directory)
    return final,digest(raw)


def append_record(log,tid,path,sha,recovered=False):
    payload={'task_id':tid,'file':path.name,'sha256':sha,'recovered_after_publish':recovered}
    with log.open('a') as f:
        f.write(json.dumps(payload,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())


def load_completed(directory,log,allowed,validate):
    logged={}
    if log.exists():
        lines=log.read_text().splitlines()
        for line in lines:
            try:item=json.loads(line)
            except json.JSONDecodeError:raise AssertionError('Incomplete/corrupt append log; fail closed')
            assert item['task_id'] not in logged and item['file']==item['task_id']+'.json'
            logged[item['task_id']]=item
    records={}
    for path in sorted(directory.glob('*.json')):
        raw=path.read_bytes();record=json.loads(raw);tid=record['task_id']
        assert path.name==tid+'.json' and tid in allowed and tid not in records
        validate(record)
        if tid in logged:assert digest(raw)==logged[tid]['sha256']
        else:append_record(log,tid,path,digest(raw),recovered=True)
        records[tid]=record
    assert set(logged)<=set(records),'Logged immutable output missing'
    return records


def run_queue(tasks,run_one,initial_records,out,validate,summarize,executor_factory,*,
              workers=4,snapshot_seconds=3.,summary_seconds=20.,registration_hash='',event=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);directory=out/'tasks';directory.mkdir(exist_ok=True)
    ids=[f'{v}_seed{s}' for v,s in tasks];assert len(ids)==len(set(ids))
    assert not set(ids)&{r['task_id'] for r in initial_records}
    initial_hash=digest(json.dumps(initial_records,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
    registration={'registration_hash':registration_hash,'initial_records_sha256':initial_hash,'task_ids':ids,'workers':workers,
                  'snapshot_seconds':snapshot_seconds,'summary_seconds':summary_seconds}
    path=out/'queue_registration.json'
    if path.exists():assert json.loads(path.read_text())==registration
    else:atomic_json(path,registration)
    completed=load_completed(directory,out/'completed.jsonl',set(ids),validate)
    records=list(initial_records)+list(completed.values());todo=[t for t in tasks if f'{t[0]}_seed{t[1]}' not in completed]
    started=time.perf_counter();last_snapshot=last_summary=float('-inf');summary=None;pending={};counts={'snapshots':0,'summaries':0}
    def observe(kind,**kwargs):
        if event:event(kind,kwargs)
    def snapshot(final=False):
        nonlocal last_snapshot,last_summary,summary
        now=time.perf_counter()
        if final or now-last_summary>=summary_seconds:
            observe('summary_start');summary=summarize(records);last_summary=time.perf_counter();counts['summaries']+=1;observe('summary_end')
        if final or time.perf_counter()-last_snapshot>=snapshot_seconds:
            compact={'status':'completed' if final else 'running','completed':len(records),'total':len(initial_records)+len(tasks),
                     'new_completed':len(completed),'new_total':len(tasks),'workers':workers,'elapsed_seconds':time.perf_counter()-started,
                     'current':[f'{v}_seed{s}' for v,s in pending.values()],
                     'candidates':[{k:r[k] for k in ['task_id','seed','config','score','seconds','error'] if k in r} for r in records],
                     'matched_summary':summary,'raw_output_location':'tasks/*.json; initial records remain in the frozen reference artifact',
                     'registration_hash':registration_hash}
            observe('snapshot_start');atomic_json(out/'state.json',compact);last_snapshot=time.perf_counter();counts['snapshots']+=1;observe('snapshot_end')
    with executor_factory(workers) as pool:
        def refill():
            while todo and len(pending)<workers:
                task=todo.pop(0);pending[pool.submit(run_one,*task)]=task;observe('submitted',task=f'{task[0]}_seed{task[1]}')
        refill();snapshot()
        while pending:
            ready,_=cf.wait(pending,timeout=min(snapshot_seconds,1.),return_when=cf.FIRST_COMPLETED)
            collected=[]
            for future in ready:
                task=pending.pop(future);record=future.result();assert record['task_id']==f'{task[0]}_seed{task[1]}'
                collected.append(record);observe('collected',task=record['task_id'])
            # Refill before validation, serialization, disk writes or summary.
            refill()
            for record in collected:
                validate(record);tid=record['task_id'];assert tid not in completed
                observe('persist_start',task=tid);path,sha=save_immutable(directory,record);append_record(out/'completed.jsonl',tid,path,sha)
                completed[tid]=record;records.append(record);observe('persist_end',task=tid)
            snapshot()
    snapshot(final=True)
    return {'elapsed_seconds':time.perf_counter()-started,'completed_new':len(completed),'records':records,'counts':counts}

"""Post-run, model-free verification and lossless immutable task backup."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import hashlib, json, gzip, math, time
import worker as X
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'results'; ARCHIVE=OUT/'task_archives'
EXPECTED_FROZEN='a4189ca0c01786d5af1e2263e20224e311a96449edae27ae8e077bb5f67d97de'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def write_json(path,data):
    raw=(json.dumps(data,indent=2,allow_nan=False)+'\n').encode();tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_bytes(raw);tmp.replace(path)
def file_info(path):return {'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size}
def main():
    start=time.perf_counter();frozen_raw=(ROOT/'frozen.json').read_bytes();assert sha(frozen_raw)==EXPECTED_FROZEN
    frozen=json.loads(frozen_raw);assert len(frozen['files'])==55
    for name,digest in frozen['files'].items():assert sha((ROOT/name).read_bytes())==digest,name
    plan=X.load_plan();expected=[f"{v['id']}_seed{s}" for v in plan['variants'] for s in plan['seeds']]
    assert len(expected)==len(set(expected))==171 and len(plan['variants'])==57 and len(plan['settings_by_id'])==60
    for name,info in X.capacity()['sources'].items():assert sha(Path(name).read_bytes())==info['sha256']
    # Read-only historical-fold replay; prohibit checkpoint inference during verification.
    from tabicl import TabICLRegressor
    def no_inference(*args,**kwargs):raise AssertionError('No model inference permitted in verification')
    TabICLRegressor.fit=no_inference;TabICLRegressor.predict=no_inference
    _,_,_,folds=X.B._prepared();fold_by_year={f['year']:f for f in folds}
    for fold in folds:X.design(fold)
    registration=json.loads((OUT/'preregistered_plan.json').read_text())
    assert registration=={'plan':plan,'plan_sha256':sha((ROOT/'plan.json').read_bytes()),'files':frozen['files']}
    queue=json.loads((OUT/'queue_registration.json').read_text())
    assert queue['task_ids']==expected and queue['registration_hash']==EXPECTED_FROZEN and queue['initial_records_sha256']==sha(b'[]') and queue['workers']==4
    completion=json.loads((OUT/'completion.json').read_text());assert completion['status']=='completed' and completion['tasks']==171 and completion['no_model_promotion']
    state=json.loads((OUT/'state.json').read_text());assert state['status']=='completed' and state['completed']==state['total']==171 and state['active_workers']==0 and not state.get('error')
    assert not state.get('test_result') and not state.get('confirmation')
    paths={p.stem:p for p in (OUT/'tasks').glob('*.json')};assert set(paths)==set(expected)
    log={}
    for line in (OUT/'completed.jsonl').read_text().splitlines():
        item=json.loads(line);tid=item['task_id'];assert tid not in log and item['file']==tid+'.json';log[tid]=item
    assert set(log)==set(expected)
    records=[];record_info=[];refs={(e['config']['id'],seed):e for seed,e in X.references().items()};ref_count=0
    for tid in expected:
        p=paths[tid];assert p.is_file() and not p.is_symlink();raw=p.read_bytes();entry=json.loads(raw)
        assert b'\n' not in raw and sha(raw)==log[tid]['sha256'] and entry['task_id']==tid
        assert raw==json.dumps(entry,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        X.validate_entry(entry,plan)
        assert math.isfinite(entry['score']) and math.isclose(entry['score'],math.fsum(r['stack'] for r in entry['rows'])/3,rel_tol=0,abs_tol=1e-15)
        for row in entry['rows']:
            assert row['season'] in [2012,2013,2014] and row['cutoff']==row['season']-1 and row['max_label_season']<=row['cutoff']
            assert row['audit']['training_max_draft_year']<=row['season']-2
            assert len(row['predictions'])==row['n'] and len({v['pid'] for v in row['predictions']})==row['n']
            assert all(math.isfinite(v['score']) and math.isfinite(v['raw_score']) for v in row['predictions'])
            fold=fold_by_year[row['season']];assert [v['pid'] for v in row['predictions']]==fold['te'].pid.tolist()
            assert X.B.rho([v['score'] for v in row['predictions']],fold['truth'])==row['stack']
        key=(entry['config']['id'],entry['seed'])
        if key in refs:
            ref=refs[key];assert all(entry[k]==ref[k] for k in ['config','seed','score'])
            for row,old in zip(entry['rows'],ref['rows']):
                for key in ['season','stack','predictions','audit']:assert row[key]==old[key]
            ref_count+=1
        records.append(entry);record_info.append({'task_id':tid,'file':'tasks/'+tid+'.json','sha256':sha(raw),'bytes':len(raw)})
    assert ref_count==3
    summary=X.summarize_matched(records);assert summary==state['matched_summary']
    assert summary['interpretation_allowed'] and summary['reference_replays_passed']==3 and not summary['reference_replays_pending'] and len(summary['configurations'])==57
    ensembles=X.seed_average(records);assert ensembles==json.loads((OUT/'seed_ensembles.json').read_text())
    assert state['seed_averaged_diagnostic']==[{k:v for k,v in e.items() if k!='rows'} for e in ensembles['configurations']]
    assert ensembles['no_favorable_seed_selection'] and len(ensembles['configurations'])==57
    candidates={e['task_id']:e for e in state['candidates']};assert len(candidates)==171 and set(candidates)==set(expected)
    for record in records:
        c=candidates[record['task_id']]
        assert all(c[k]==record[k] for k in ['config','seed','score','seconds'])
        assert c['rows']==[{'season':r['season'],'stack':r['stack']} for r in record['rows']]
    print('Verified 171 records, 3 exact references, 55 frozen files and exact complete summary.',flush=True)
    write_json(OUT/'matched_summary.json',summary)
    # Fixed plan order and 32 MB uncompressed chunks guarantee generous room below 40 MB gzip limit.
    ARCHIVE.mkdir(exist_ok=True);groups=[];group=[];size=0
    for info in record_info:
        if group and size+info['bytes']+1>32_000_000:groups.append(group);group=[];size=0
        group.append(info);size+=info['bytes']+1
    if group:groups.append(group)
    chunks=[]
    for index,group in enumerate(groups):
        name=f'tasks_{index:03d}.jsonl.gz';path=ARCHIVE/name;tmp=path.with_suffix('.tmp');uncompressed=hashlib.sha256();nbytes=0
        with tmp.open('wb') as file:
            with gzip.GzipFile(filename='',mode='wb',fileobj=file,mtime=0,compresslevel=6) as stream:
                for info in group:
                    raw=(OUT/info['file']).read_bytes();assert sha(raw)==info['sha256'];line=raw+b'\n';stream.write(line);uncompressed.update(line);nbytes+=len(line)
        assert tmp.stat().st_size<40_000_000
        if path.exists():assert file_info(path)==file_info(tmp);tmp.unlink()
        else:tmp.replace(path)
        restored_hash=hashlib.sha256();restored_bytes=0;count=0
        with gzip.open(path,'rb') as stream:
            for info in group:
                line=stream.readline();assert line.endswith(b'\n');raw=line[:-1]
                assert len(raw)==info['bytes'] and sha(raw)==info['sha256'] and raw==(OUT/info['file']).read_bytes()
                restored_hash.update(line);restored_bytes+=len(line);count+=1
            assert stream.read()==b''
        assert restored_hash.hexdigest()==uncompressed.hexdigest() and restored_bytes==nbytes and count==len(group)
        for line,info in enumerate(group):info.update(chunk=name,line_1based=line+1)
        chunks.append({'file':'task_archives/'+name,**file_info(path),'records':count,'uncompressed_bytes':nbytes,'uncompressed_sha256':uncompressed.hexdigest(),'roundtrip_exact':True})
    assert {p.name for p in ARCHIVE.glob('*.gz')}=={Path(c['file']).name for c in chunks}
    archive={'format':'gzip of exact original task JSON bytes, each followed by one LF; recover each original file by removing exactly that terminal LF','ordering':'frozen plan variant order, then registered model seed order','gzip':{'mtime':0,'filename':'','compresslevel':6},'chunk_compressed_limit_bytes':40_000_000,'chunk_uncompressed_target_bytes':32_000_000,'frozen_manifest_sha256':EXPECTED_FROZEN,'record_count':len(record_info),'original_bytes':sum(i['bytes'] for i in record_info),'compressed_bytes':sum(c['bytes'] for c in chunks),'all_roundtrips_exact':True,'chunks':chunks,'records':record_info}
    write_json(OUT/'task_archive_manifest.json',archive)
    proof={'passed':True,'models_fitted':0,'records':171,'reference_replays_exact':3,'frozen_files_unchanged':55,'frozen_manifest_sha256':EXPECTED_FROZEN,'preregistration_exact':True,'queue_registration_exact':True,'append_log_all_hashes_exact':True,'complete_summary_recomputed_exact':True,'compact_candidates_exact':True,'requested_configurations':60,'distinct_configurations':57,'effective_generator_designs_exact':True,'all_saved_fold_scores_recomputed_exact':True,'seed_averaged_diagnostics_recomputed_exact':True,'installed_source_hashes_exact':True,'seed_ensembles':file_info(OUT/'seed_ensembles.json'),'all_pre2019_development_only':True,'no_model_promotion':True,'task_archive_manifest':file_info(OUT/'task_archive_manifest.json'),'chunks':len(chunks),'original_bytes':archive['original_bytes'],'compressed_bytes':archive['compressed_bytes'],'max_chunk_bytes':max(c['bytes'] for c in chunks),'all_record_roundtrips_byte_exact':True,'elapsed_seconds':completion['elapsed_seconds'],'trials_per_minute':171*60/completion['elapsed_seconds'],'verification_seconds':time.perf_counter()-start,'verification_code_sha256':sha(Path(__file__).read_bytes()),'summary':file_info(OUT/'matched_summary.json')}
    write_json(OUT/'run_verification.json',proof)
    report=f"R9d verification passed: 171/171 immutable task records, all 3 full reference replays, all 55 frozen file hashes and the complete recomputed summary match. No TabICL fit, prediction or held-out evaluation was run during verification.\n\nThe queue completed in {completion['elapsed_seconds']:.3f} seconds ({proof['trials_per_minute']:.2f} tasks/minute), with no errors. It covers 57 distinct TabICL settings from 60 requested configurations after CPU-only effective-design deduplication. All 513 saved fold scores and all 57 fixed equal-weight three-seed prediction ensembles were recomputed exactly. It remains a pre-2019 development diagnostic, with no model promotion. The retrospective source and reused-development selection limitations remain.\n\nAll original task files remain on the server. {len(chunks)} deterministic gzip chunks preserve their exact bytes ({archive['original_bytes']:,} original bytes; {archive['compressed_bytes']:,} compressed bytes); every record passed round-trip comparison. Each chunk is below 40 MB. task_archive_manifest.json records original file, task ID, byte length, SHA-256, chunk and line, plus compressed and uncompressed chunk hashes. To restore, decompress a chunk and remove exactly one final LF from each record line.\n\nThe 44-predictor B baseline and all input, calendar and ordering policies were unchanged. No source certification or held-out claim follows this study; disabled clipping was serialized safely and requested64 estimators had44 effective members. Full numerical diagnostics are in matched_summary.json. Verification deliberately performs no selection for the next study.\n"
    (OUT/'report.md').write_text(report)
    public_names=set(frozen['files'])|{'frozen.json','verify_and_archive.py','run_verify_sandbox.sh'}
    public_names|={'results/'+name for name in ['preregistered_plan.json','queue_registration.json','preparation.json','completion.json','state.json','completed.jsonl','launch_verification.json','matched_summary.json','seed_ensembles.json','task_archive_manifest.json','run_verification.json','report.md']}
    public_names|={'results/'+c['file'] for c in chunks}
    public={'study':'r9d','files':{name:file_info(ROOT/name) for name in sorted(public_names)},'raw_task_files_preserved_remote':True,'all_raw_tasks_losslessly_included_in_chunks':True,'record_count':171,'no_heldout_inputs_or_outcomes':True}
    public['total_bytes']=sum(x['bytes'] for x in public['files'].values());write_json(OUT/'PUBLIC_ALLOWLIST.json',public)
    print(json.dumps(proof),flush=True)
    print(json.dumps({'public_allowlist':file_info(OUT/'PUBLIC_ALLOWLIST.json'),'public_files':len(public['files']),'public_bytes':public['total_bytes']}),flush=True)
if __name__=='__main__':main()

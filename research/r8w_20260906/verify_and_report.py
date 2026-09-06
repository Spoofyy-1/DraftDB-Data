"""Post-run integrity verification and descriptive reporting; never fits a model."""
from pathlib import Path
import hashlib,json
import worker as W
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results'
state=json.loads((OUT/'state.json').read_text())
plan=json.loads((ROOT/'plan.json').read_text())
frozen=json.loads((ROOT/'prototype_manifest.json').read_text())
registration=json.loads((OUT/'preregistered_plan.json').read_text())
assert state['status']=='completed' and state['completed']==state['total']==603
assert all('error' not in e for e in state['candidates'])
expected={f"{v['id']}_seed{s}" for v in plan['variants'] for s in plan['seeds']}
assert len(state['candidates'])==len(expected)==len({e['task_id'] for e in state['candidates']}) and {e['task_id'] for e in state['candidates']}==expected
for name,digest in frozen['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
assert registration['code_and_bundle_hashes']==frozen['files']
assert registration['sha256']==hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest()
for name,digest in json.loads((ROOT/'data/manifest.json').read_text())['files'].items():assert hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()==digest,name
summary=W.summarize_matched(state['candidates'])
assert summary==state['matched_summary'] and summary['interpretation_allowed'] and not summary['pending']
assert len(summary['baseline_replay_checks'])==3 and len(summary['statistics'])==50
vstate=json.loads((ROOT.parent/'r8v/results/state.json').read_text())
assert vstate['status']=='completed'
vrefs={e['seed']:e for e in vstate['candidates'] if e['config']['id']=='college_consensus_tabicl32'}
uentries={e['seed']:e for e in state['candidates'] if e['config']['id']=='baseline'}
assert set(vrefs)==set(uentries)==set(plan['seeds'])
for seed,current in uentries.items():
 ref=vrefs[seed];assert current['score']==ref['score']
 assert all(a['season']==b['season'] and a['stack']==b['stack'] and a['predictions']==b['predictions'] for a,b in zip(current['rows'],ref['rows']))
stats=sorted(summary['statistics'],key=lambda r:r['paired_mean_gain'],reverse=True)
baseline=summary['baseline_score_context_only']
positive=[r for r in stats if r['paired_mean_gain']>0]
both=[r for r in positive if r['real_minus_baseline_context_only']>0]
consistent=[r for r in both if min(r['fold_gains'].values())>0 and min(r['seed_gains'].values())>0]
widths=sorted({r['audit']['raw_feature_count'] for e in state['candidates'] for r in e['rows']})
assert widths==[45,46]
launch=json.loads((OUT/'launch_verification.json').read_text())
verification={'status':'completed_verified','unit':launch['unit'],'invocation_id':launch['invocation_id'],'tasks':603,'errors':0,
              'elapsed_seconds':state['elapsed_seconds'],'tasks_per_minute':state['experiments_per_minute'],
              'frozen_files_unchanged':len(frozen['files']),'summary_recomputed_exact':True,
              'baseline_replays':summary['baseline_replay_checks'],'direct_R8v_tabicl32_raw_canonical_score_replays':sorted(vrefs),'widths':widths,
              'live_unit_limits_observed':launch['live_unit_limits_observed'],
              'heldout_or_confirmation_scoring':False,'no_promotion_or_combinations':True,
              'metric':'Pre2019 mean-fold Spearman, displayed times100; not classification accuracy',
              'matched_positive_fields':len(positive),'matched_and_baseline_positive_fields':len(both),
              'matched_and_baseline_positive_all_fold_and_seed_gains_positive':[r['id'] for r in consistent],
              'report_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(OUT/'run_verification.json').write_text(json.dumps(verification,indent=2)+'\n')
rows=['R8w completed all 603 registered trials with zero errors. All three baseline seeds reproduced the saved R8u raw and canonical predictions and scores exactly. The baseline mean-fold Spearman is %.6f (%.3f displayed points).'%(baseline,100*baseline),
      'This is an exploratory pre-2019 screen of 50 additional statistics conditional on the fixed college41 + dated consensus4 background. It has no 2019–2026 result, independent confirmation, combinations or automatic promotion.',
      '%d fields had a positive mean real-minus-shuffle effect; %d also exceeded the 45-column baseline. %d had positive matched effects in every fold and model seed while exceeding baseline. These are descriptive counts, not statistical discoveries.'%(len(positive),len(both),len(consistent)),
      'The primary comparison keeps real/control width at46 with a single common extra slot and exactly preserved cohort/missingness patterns. The separate real-minus-baseline comparison changes width45→46; a matched advantage alone is not baseline improvement.',
      '| Statistic | Real score ×100 | Shuffled score ×100 | Matched change (points) | Real−baseline (points) | Fold changes 2012 / 2013 / 2014 |',
      '|---|---:|---:|---:|---:|---|']
for r in stats:
 rows.append('| %s | %.3f | %.3f | %+.3f | %+.3f | %s |'%(r['id'],100*r['real_mean'],100*r['control_mean'],100*r['paired_mean_gain'],100*r['real_minus_baseline_context_only'],' / '.join('%+.3f'%(100*r['fold_gains'][str(y)] )for y in plan['folds'])))
rows.extend(['', 'All 15 frozen model/protocol/test/reference files and all22 mounted data hashes were unchanged; the saved summary was recomputed exactly. The run used four workers with the registered two-hour,140 GiB and22-CPU-equivalent limits.',
            'Source limitations remain: historical Torvik vintages and the original prospect universe are not fully certified; an independent basic-count audit found disagreements in some count/per-game denominators. Three model seeds and three shuffle seeds are dependent exploratory checks, not nine independent observations or a significance test. Different added fields may break associations with existing predictors; the matched test measures their usability conditional on this particular model and background. R8r used the earlier ordering policy and lacked consensus, so differences from R8r alone cannot isolate an interaction with consensus.'])
(OUT/'report.md').write_text('\n\n'.join(rows[:4])+'\n\n'+'\n'.join(rows[4:])+'\n')
print(json.dumps({'verification':verification,'top_matched':stats[:10],'top_absolute':sorted(stats,key=lambda r:r['real_mean'],reverse=True)[:5],'bottom_matched':stats[-5:]},indent=2))

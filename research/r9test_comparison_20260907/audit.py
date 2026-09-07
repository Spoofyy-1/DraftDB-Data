"""Read-only metric/mapping audit: saved aggregates and input values, no answers/fits."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

WORK = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SITE = Path('/Users/kennakao/nba/site/model/CURRENT_MODEL.json')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def obj(p): return json.loads(p.read_text())

def main():
    old = obj(SITE); new = obj(WORK/'r9test/results/test_result.json')
    recipe = obj(WORK/'r9test/recipe.json'); source = obj(WORK/'r9test_inputs/manifest.json')
    spec = importlib.util.spec_from_file_location('mapping_audit_core', WORK/'r9test/model_core.py')
    core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
    assert recipe['columns'] == source['columns']
    assert recipe['physical_source_fields'] == source['physical_source_fields']
    assert len(set(recipe['columns'])) == len(set(recipe['physical_source_fields'])) == 44
    mapping = []
    for year in range(2019, 2026):
        xp = WORK/f'r9test_inputs/inputs_{year}.csv'
        mp = WORK/f'r9test_inputs/metadata_{year}.csv'
        assert sha(xp) == source['output_files'][xp.name]['sha256']
        assert sha(mp) == source['output_files'][mp.name]['sha256']
        x = pd.read_csv(xp, dtype={'pid':str}, float_precision='round_trip')
        meta = pd.read_csv(mp, dtype={'pid':str}, float_precision='round_trip')
        assert x[['pid','draft_year']].equals(meta[['pid','draft_year']])
        q = core.canonical_rows(x[meta.was_drafted.eq(1)])
        manifest = obj(WORK/f'r9test/bundle_manifests/{year}.json')
        pred = obj(WORK/f'r9test/results/{year}/predictions.json')
        h = core.values_hash(q[recipe['columns']])
        assert h == manifest['prepared_payload_audit']['query_matrix_hash'] == pred['audit']['query_matrix_hash']
        assert q.pid.tolist() == manifest['canonical_query_PIDs']
        assert q.pid.tolist() == [v['pid'] for v in pred['fixed_rank_average']]
        mapping.append({'year':year,'rows':len(q),'query_matrix_hash':h,
                        'all_44_columns_order_values_and_PID_join_exact':True})

    # Execute only extracted pure calculation functions, never import legacy vault.py.
    vault_ast = ast.parse((WORK/'audit/vault.py').read_text())
    old_fn = next(n for n in vault_ast.body if isinstance(n,ast.FunctionDef) and n.name=='score')
    stop = next(i for i,n in enumerate(old_fn.body) if isinstance(n,ast.Import) and any(a.name=='fcntl' for a in n.names))
    old_fn.body = old_fn.body[:stop] + [ast.Return(ast.Tuple([ast.Name('ic',ast.Load()),ast.Name('dic',ast.Load())],ast.Load()))]
    scorer_ast = ast.parse((WORK/'r9test/score_frozen.py').read_text())
    new_fn = next(n for n in scorer_ast.body if isinstance(n,ast.FunctionDef) and n.name=='correlation')
    ns = {'np':np,'pd':pd,'spearmanr':spearmanr,'S':[f'y_s{i}_war' for i in range(1,6)]}
    module = ast.fix_missing_locations(ast.Module(body=[old_fn,new_fn],type_ignores=[]))
    exec(compile(module,'extracted_pure_metric_functions','exec'),ns)
    fixture_checks=[]
    rng=np.random.default_rng(240917)
    for k in range(1,6):
        a=pd.DataFrame({'pid':[f'fixture_{i}' for i in range(24)],'actual_pick':np.arange(1,25)})
        values=rng.integers(-3,5,size=(24,5)).astype(float);values[::4,:]=np.nan;values[1::6,0]=0
        for j,c in enumerate(ns['S']): a[c]=values[:,j]
        ns['_ANS']={2000:a}; predictions=dict(zip(a.pid,rng.integers(-4,5,size=24).astype(float)))
        legacy,draft=ns['score'](predictions,2000,k,'fixture','fixture')
        truth=np.nan_to_num(values[:,:k],nan=0).sum(axis=1)
        current=ns['correlation'](np.array([predictions[p] for p in a.pid]),truth,3)
        comparator=ns['correlation'](-a.actual_pick.to_numpy(),truth,3)
        assert current==legacy and comparator==draft
        fixture_checks.append({'k':k,'negative_zero_missing_tied_values_exact':True})

    aggregates={}
    for start in [2019,2020]:
        rows=[r for r in new['rows'] if r['season']>=start]
        aggregates[f'{start}_2025']={metric:{m:statistics.mean(r[metric][m] for r in rows)
            for m in ['score','mean_seed_score','draft']}
            for metric in ['full_legacy','complete_target_subset']}
    original={m:{c:statistics.mean(r[c] for r in old['metrics'][m]['per_class']) for c in ['stack','draft']}
              for m in ['strict','expanding']}
    comparators=[]
    for row in new['rows']:
        prior=next(x for x in old['metrics']['strict']['per_class'] if x['season']==row['season'])
        assert row['k']==prior['k'] and round(row['full_legacy']['draft'],3)==prior['draft']
        comparators.append({'year':row['season'],'k':row['k'],'draft_new':row['full_legacy']['draft'],
                            'draft_published_old':prior['draft'],'same_at_published_precision':True})
    for metric in ['full_legacy','complete_target_subset']:
        for key,value in aggregates['2019_2025'][metric].items():
            assert abs(value-new['aggregate'][metric][key])<1e-15
    proof={'passed':True,'no_new_answers_opened':True,'model_fits':0,'new_scoring_calls':0,
           'mapping':mapping,'pure_metric_fixtures':fixture_checks,'draft_comparators':comparators,
           'recomputed_current_aggregates':aggregates,'original_means_from_rounded_published_rows':original,
           'same_year_gap_rho':original['expanding']['stack']-aggregates['2020_2025']['full_legacy']['score'],
           'source_sha256':{str(p):sha(p)for p in [SITE,WORK/'r9test/results/test_result.json',WORK/'r9test/recipe.json',WORK/'audit/vault.py',WORK/'r9test/score_frozen.py']}}
    (HERE/'verification.json').write_text(json.dumps(proof,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'passed':True,'mapped_cohorts':7,'metric_fixtures':5,'matched_2020_2025':aggregates['2020_2025'],
                      'original':original,'same_year_gap_points':100*proof['same_year_gap_rho']}))

if __name__=='__main__': main()

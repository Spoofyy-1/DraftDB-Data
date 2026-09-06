"""Register the full F50 source-only rescreen using pre-2019 inputs only."""
from pathlib import Path
import hashlib
import json
import shutil
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'r8n'
FIFTY = ROOT.parent / 'fifty'
DATA = ROOT / 'data'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    DATA.mkdir(exist_ok=True)
    prior_plan = json.loads((BASE / 'plan.json').read_text())
    prior_manifest = json.loads((BASE / 'data/manifest.json').read_text())
    variant = next(v for v in prior_plan['variants'] if v['id'] == 'dated_raw_college_source_control')
    base_columns = list(variant['context_features'])
    assert len(base_columns) == 41 and all(c.startswith(('ctx_base_', 'ctx_skill_')) for c in base_columns)
    assert not any(c in ['ctx_base_age', 'ctx_base_height'] for c in base_columns)
    for name, expected in prior_manifest['files'].items():
        assert Path(name).name == name and sha(BASE / 'data' / name) == expected
    x = pd.read_csv(BASE / 'data/features.csv')
    assert x.pid.is_unique and (x.draft_year <= 2018).all()
    features = [c for c in prior_manifest['context_features'] if c.startswith('f50_')]
    assert len(features) == len(set(features)) == 50
    # Materialize only the allowed 41 baseline values and four necessary metadata
    # fields: legacy bio/medical/consensus values never enter this bundle.
    metadata_columns = ['pid', 'draft_year', 'was_drafted', 'actual_pick']
    x[metadata_columns + base_columns].to_csv(DATA / 'features.csv', index=False)
    x[['pid', 'draft_year'] + features].to_csv(DATA / 'source_features.csv', index=False)
    for name in ['labels.csv', 'incumbent.json']:
        shutil.copyfile(BASE / 'data' / name, DATA / name)
    shutil.copyfile(BASE / 'legacy_kernel.py', ROOT / 'legacy_kernel.py')
    raw_features = pd.read_csv(FIFTY / 'fifty_train.csv')
    assert raw_features.pid.is_unique and (raw_features.draft_year <= 2018).all()
    joined = x[['pid', 'draft_year']].merge(raw_features, on=['pid', 'draft_year'], how='left', validate='one_to_one', sort=False)
    pd.testing.assert_frame_equal(x[features], joined[features], check_exact=False, rtol=1e-12, atol=1e-12)
    original_catalog = json.loads((FIFTY / 'catalog.json').read_text())
    dictionary = {r['name']: {k: r[k] for k in ['name', 'group', 'formula', 'source']} for r in original_catalog}
    assert set(dictionary) == set(features)
    (DATA / 'source_dictionary.json').write_text(json.dumps(dictionary, indent=2))
    source_manifest = json.loads((FIFTY / 'manifest.json').read_text())
    provenance = [r for r in source_manifest['provenance'] if r['draft_year'] <= 2018 and r['pid'] in set(x.pid)]
    assert len({r['pid'] for r in provenance}) == len(provenance)
    for r in provenance:
        assert r['source_season'] <= r['draft_year'] <= 2018
        assert r['history_seasons'] and max(r['history_seasons']) == r['source_season']
    assert set(x.loc[x[features].notna().any(axis=1), 'pid']) <= {r['pid'] for r in provenance}
    (DATA / 'source_provenance.json').write_text(json.dumps(provenance, indent=2))
    source_metadata = {'source_fields': source_manifest['source_fields'],
                       'source_hashes': {k: v for k, v in source_manifest['source_hashes'].items() if int(k.split('_')[1].split('.')[0]) <= 2018},
                       'limitation': source_manifest['limitation'], 'fifty_train_sha256': sha(FIFTY / 'fifty_train.csv'),
                       'builder_sha256': sha(ROOT.parent / 'collectors/build_fifty.py')}
    assert '45' not in source_metadata['source_fields']
    (DATA / 'source_metadata.json').write_text(json.dumps(source_metadata, indent=2))
    eligibility = {}
    for year in prior_plan['folds']:
        tr = x[(x.draft_year >= prior_plan['backbone']['window']) & (x.draft_year <= year - 2)]
        rows = []
        for feature in features:
            values = tr[feature]
            observed, unique = int(values.notna().sum()), int(values.nunique())
            movable = sum(int(group[feature].notna().sum()) for _, group in tr.groupby('draft_year') if group[feature].nunique() > 1)
            rows.append({'feature': feature, 'training_observed': observed, 'training_unique': unique,
                         'eligible': observed >= 5 and unique >= 2, 'swappable_training_observed': movable})
        eligibility[str(year)] = rows
    active, excluded = [], {}
    for feature in features:
        rows = {year: next(r for r in values if r['feature'] == feature) for year, values in eligibility.items()}
        if any(r['eligible'] and r['swappable_training_observed'] > 0 for r in rows.values()):
            active.append(feature)
        else:
            excluded[feature] = {'status': 'untestable_from_training_values', 'folds': rows,
                                 'reason': 'No fold has >=5 observed, >=2 unique training values with any within-cohort value variation; excluded before scoring.'}
    permutations = [9317, 18739, 28657]
    variants = [{'id': 'baseline', 'backbone': 'source_college', 'family': 'baseline', 'arm': 'baseline', 'permutation_seed': None}]
    for feature in active:
        variants.append({'id': feature + '_real', 'backbone': 'source_college', 'family': feature, 'arm': 'real', 'permutation_seed': None})
        variants.extend({'id': f'{feature}_shuffle{seed}', 'backbone': 'source_college', 'family': feature, 'arm': 'permuted', 'permutation_seed': seed} for seed in permutations)
    task_count = len(variants) * len(prior_plan['seeds'])
    assert task_count == 3 + 12 * len(active) <= 603
    plan = {'study': 'R8r full F50 source-only matched rescreen', 'diagnostic_only': True,
            'purpose': 'Rescreen every F50 hypothesis on the fixed raw college source-only R8n backbone; prior inherited-baseline results do not select this queue.',
            'baseline': 'baseline', 'baselines': {'source_college': 'baseline'}, 'baseline_variants': {'source_college': variant},
            'backbone': prior_plan['backbone'], 'base_columns': base_columns, 'metadata_columns': metadata_columns,
            'candidate_features': features, 'families': {c: [c] for c in features}, 'active_families': active,
            'excluded_families': excluded, 'training_eligibility': eligibility,
            'folds': prior_plan['folds'], 'seeds': prior_plan['seeds'], 'permutation_seeds': permutations,
            'variants': variants, 'slot_mapping': {feature: 'slot_0' for feature in features},
            'source_filter': {'min_training_observed': 5, 'min_training_unique': 2, 'validation_coverage_used': False},
            'selection': {'base_topk': 60, 'selector_seed': 11, 'scope': 'Only the same41 source columns, once per fold; all retained in fixed training-only importance order.',
                          'source_scope': 'Per-fold training values only. Exclude wholly untestable features from queue before scoring. No old scores, validation coverage or labels choose source eligibility.'},
            'controls': {'shuffle': 'Per feature, permute only observed values within draft cohort and train/validation role, stable pid order, fixed SHA256 seed stream.',
                         'dimensions': 'Same41 selected columns plus identical slot_0 for real/three controls wherever training eligibility passes; exact masks and cohort marginals.',
                         'unused_folds': 'A feature ineligible in one fold supplies no slot for any arm in that fold; no fake imputation or validation-based resurrection.'},
            'calendar_policy': prior_plan['calendar_policy'], 'confirmation_note': prior_plan['confirmation_note'],
            'no_confirmation_or_test_scoring': True,
            'summary': {'comparison': 'Pair real minus mean of three same-mask shuffles for each model seed/fold; report fold/seed/permutation differences.',
                        'baseline_difference': 'Context only: dimensions differ; baseline gains do not establish information.',
                        'multiplicity': 'All50 exploratory hypotheses; no p-values, independent-seed claims or automatic promotion.',
                        'combinations': 'No combination tasks registered. Review all completed singles before separately preregistering combinations.',
                        'automatic_promotion': False},
            'execution': {'workers': 4, 'xgboost_selector': 'cpu', 'predictor': 'Unchanged GPU TabICL only; no weight reuse',
                          'task_count': task_count, 'maximum_tasks': 603, 'gpu_launch_performed': False}}
    (ROOT / 'plan.json').write_text(json.dumps(plan, indent=2))
    manifest = {'base_columns': base_columns, 'metadata_columns': metadata_columns, 'source_features': features,
                'baseline_variants': plan['baseline_variants'], 'base_data_origin_hashes': dict(prior_manifest['files']),
                'source_package_hashes': {'fifty_train.csv': sha(FIFTY / 'fifty_train.csv'), 'build_fifty.py': sha(ROOT.parent / 'collectors/build_fifty.py')},
                'label_policy': prior_manifest['label_policy'],
                'limitations': ['Original historical publication vintages unavailable.', 'Inherited prospect universe is retained; no fully certified clean-test claim.',
                                'Only pre-2019 source values, date metadata and NBA labels enter this bundle.'],
                'files': {p.name: sha(p) for p in sorted(DATA.iterdir()) if p.is_file() and p.name != 'manifest.json'}}
    (DATA / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'tasks': task_count, 'active_features': len(active), 'excluded_features': excluded,
                      'players': len(x), 'baseline_columns': len(base_columns), 'observed_F50_cells': int(x[features].notna().sum().sum())}, indent=2))


if __name__ == '__main__':
    main()

"""Build R8q's pre-2019-only combine bundle; no source mutation or model runs."""
from pathlib import Path
import hashlib
import json
import shutil
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'r8n'
SOURCE = ROOT.parent / 'verified_combine' / 'data'
DATA = ROOT / 'data'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    DATA.mkdir(exist_ok=True)
    base_plan = json.loads((BASE / 'plan.json').read_text())
    base_manifest = json.loads((BASE / 'data/manifest.json').read_text())
    wanted = {'source_college': 'dated_raw_college_source_control',
              'quarantined_legacy': 'quarantine_bio_med_consensus_college_derived'}
    backbones = {key: next(v for v in base_plan['variants'] if v['id'] == vid) for key, vid in wanted.items()}
    for filename, expected in base_manifest['files'].items():
        assert Path(filename).name == filename and sha(BASE / 'data' / filename) == expected
        shutil.copyfile(BASE / 'data' / filename, DATA / filename)
    shutil.copyfile(BASE / 'legacy_kernel.py', ROOT / 'legacy_kernel.py')
    x = pd.read_csv(DATA / 'features.csv')
    assert x.pid.is_unique and (x.draft_year <= 2018).all()
    dictionary = json.loads((SOURCE / 'feature_dictionary.json').read_text())
    source_manifest = json.loads((SOURCE / 'manifest.json').read_text())
    assert sha(SOURCE / 'train_inputs.csv') == source_manifest['output_files']['train_inputs.csv']
    columns = list(dictionary)
    assert columns == source_manifest['features'] and len(columns) == 37
    athletics = ['vcmb_standing_vertical_in', 'vcmb_max_vertical_in', 'vcmb_lane_agility_s',
                 'vcmb_modified_lane_agility_s', 'vcmb_three_quarter_sprint_s', 'vcmb_bench_press_reps']
    shooting = [c for c in columns if dictionary[c]['kind'] == 'official combine shooting drill']
    anthropometry = [c for c in columns if c not in athletics + shooting]
    assert (len(anthropometry), len(athletics), len(shooting)) == (10, 6, 21)
    families = {'anthropometry': anthropometry, 'athletics': athletics, 'shooting': shooting}
    registered = anthropometry + athletics + shooting
    families['all'] = registered
    assert len(set(registered)) == 37 and all(c.startswith('vcmb_') for c in registered)
    for family in ['anthropometry', 'athletics', 'shooting']:
        for c in families[family]:
            dictionary[c]['experiment_family'] = family
    source = pd.read_csv(SOURCE / 'train_inputs.csv')
    assert source.pid.is_unique and (source.draft_year <= 2018).all()
    assert list(source) == ['pid', 'draft_year'] + columns
    assert not set(registered) & set(x)
    joined = x[['pid', 'draft_year']].merge(source, on=['pid', 'draft_year'], how='left', validate='one_to_one', sort=False)
    assert joined.pid.tolist() == x.pid.tolist()
    assert np.isfinite(joined[registered].stack().dropna().to_numpy()).all()
    joined[['pid', 'draft_year'] + registered].to_csv(DATA / 'source_features.csv', index=False)
    # Provenance has no outcomes. Only pre-2019 rows in the fixed model universe
    # enter the sandbox; inference feature files are never opened or copied.
    provenance = pd.read_csv(SOURCE / 'row_provenance.csv')
    provenance = provenance[(provenance.draft_year <= 2018) & provenance.pid.isin(x.pid)].copy()
    assert provenance.pid.is_unique and (provenance.source_year == provenance.draft_year).all()
    assert provenance.draft_year.equals(provenance.pid.map(x.set_index('pid').draft_year))
    assert set(joined.loc[joined[registered].notna().any(axis=1), 'pid']) <= set(provenance.pid)
    provenance.to_csv(DATA / 'source_provenance.csv', index=False)
    source_metadata = {k: source_manifest[k] for k in ['protocol', 'identity_sha256', 'builder_sha256', 'policy']}
    source_metadata['source_files'] = [r for r in source_manifest['source_files'] if r['source_year'] <= 2018]
    source_metadata['train_inputs_sha256'] = sha(SOURCE / 'train_inputs.csv')
    source_metadata['dictionary_sha256'] = sha(SOURCE / 'feature_dictionary.json')
    for r in source_metadata['source_files']:
        year = r['source_year']
        assert r['all_row_seasons_verified'] and r['parameters']['SeasonYear'] == f'{year}-{str(year+1)[2:]}'
    (DATA / 'source_metadata.json').write_text(json.dumps(source_metadata, indent=2))
    (DATA / 'source_dictionary.json').write_text(json.dumps(dictionary, indent=2))
    manifest = dict(base_manifest)
    manifest.update({'source_features': registered, 'source_families': families, 'baseline_variants': backbones,
                     'base_data_hashes': dict(base_manifest['files']),
                     'source_package_hashes': {name: sha(SOURCE / name) for name in ['train_inputs.csv', 'feature_dictionary.json', 'row_provenance.csv', 'manifest.json']},
                     'unmatched_source_identities_excluded': source.loc[~source.pid.isin(x.pid), ['pid', 'draft_year']].to_dict('records'),
                     'limitations': ['No certified clean-test claim: inherited prospect universe and publication vintages remain unresolved.',
                                     'Only independently reconstructed same-draft-year official combine values are added.',
                                     'Independent per-column shuffles break family algebra/covariance as well as player-value association.']})
    manifest['files'] = {p.name: sha(p) for p in sorted(DATA.iterdir()) if p.is_file() and p.name != 'manifest.json'}
    (DATA / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    # Freeze this omission from training coverage before any model is scored.
    shooting_eligibility = {}
    for year in base_plan['folds']:
        training = joined[(joined.draft_year >= base_plan['backbone']['window']) & (joined.draft_year <= year - 2)]
        eligible = [c for c in shooting if training[c].notna().sum() >= 5 and training[c].nunique() >= 2]
        shooting_eligibility[str(year)] = eligible
    assert all(not columns for columns in shooting_eligibility.values())
    active_families = ['anthropometry', 'athletics', 'all']
    permutation_seeds = [9317, 18739, 28657]
    variants = []
    baselines = {}
    for backbone in backbones:
        base_id = f'{backbone}__baseline'
        baselines[backbone] = base_id
        variants.append({'id': base_id, 'backbone': backbone, 'family': 'baseline', 'arm': 'baseline', 'permutation_seed': None})
        for family in active_families:
            variants.append({'id': f'{backbone}__{family}_real', 'backbone': backbone, 'family': family, 'arm': 'real', 'permutation_seed': None})
            for seed in permutation_seeds:
                variants.append({'id': f'{backbone}__{family}_shuffle{seed}', 'backbone': backbone, 'family': family, 'arm': 'permuted', 'permutation_seed': seed})
    plan = {'study': 'R8q verified-combine matched family diagnostics', 'diagnostic_only': True,
            'purpose': 'Assess verified combine families against identical-shape controls on two fixed R8n backbones; no clean-test certification or automatic promotion.',
            'baseline': baselines['quarantined_legacy'], 'baselines': baselines, 'baseline_variants': backbones,
            'backbone': base_plan['backbone'], 'folds': base_plan['folds'], 'seeds': base_plan['seeds'],
            'permutation_seeds': permutation_seeds, 'variants': variants, 'families': families,
            'active_families': active_families,
            'excluded_families': {'shooting': {'status': 'untestable_no_training_eligible_columns',
                                              'eligibility_by_fold': shooting_eligibility, 'omitted_tasks': 24,
                                              'decision_basis': 'Training feature availability only, before any scoring; source fields remain in the bundle.'}},
            'source_filter': {'min_training_observed': 5, 'min_training_unique': 2, 'validation_coverage_used': False},
            'slot_mapping': {c: f'slot_{i:03d}' for i, c in enumerate(registered)},
            'selection': {'base_topk': 60, 'selector_seed': 11,
                          'scope': 'Base columns only, independently per registered backbone/fold; fixed across all families, controls and model seeds.',
                          'source_filter_scope': 'Training values only, no labels or validation coverage. Each family keeps a fixed eligible column order across arms; all is their ordered union.'},
            'controls': {'shuffle': 'Per feature, independently permute observed values within draft cohort and train/validation role, preserving exact NaN positions.',
                         'seed_stream': 'SHA256(feature, permutation seed, role, cohort), stable pid order; no outcomes.',
                         'dimensions': 'Exact same selected base, slot names/order, masks and within-cohort per-column distributions for real/shuffled arms.',
                         'limitation': 'Independent-column controls break BMI/drill algebra and cross-feature covariance. Gain includes usable family joint structure, not unique per-feature causal information.'},
            'calendar_policy': base_plan['calendar_policy'], 'confirmation_note': base_plan['confirmation_note'],
            'no_confirmation_or_test_scoring': True,
            'summary': {'comparison': 'Within backbone/family, pair each model seed/fold real score with mean of three shuffles; report fold, seed and individual-shuffle differences.',
                        'baseline_difference': 'Context only; different model dimensions cannot establish information gain.',
                        'automatic_promotion': False, 'multiplicity': 'Exploratory six active backbone/family comparisons; no p-values or significance gates. Seeds are not independent datasets.',
                        'all_interpretation': 'Joint family effect, not a factorial interaction or proven complementarity.'},
            'execution': {'workers': 4, 'xgboost_selector': 'cpu', 'predictor': 'GPU TabICL only', 'task_count': 78, 'gpu_launch_performed': False}}
    assert len(variants) * len(plan['seeds']) == 78
    (ROOT / 'plan.json').write_text(json.dumps(plan, indent=2))
    print(json.dumps({'tasks': 78, 'players': len(x), 'source_players': int(joined[registered].notna().any(axis=1).sum()),
                      'source_observations': int(joined[registered].notna().sum().sum()), 'family_sizes': {k: len(v) for k, v in families.items()}}, indent=2))


if __name__ == '__main__':
    main()

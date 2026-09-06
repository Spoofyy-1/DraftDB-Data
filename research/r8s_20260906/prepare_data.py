"""Freeze an independent pre-2019 factorial bundle; never mutate source packages."""
from pathlib import Path
import hashlib
import json
import shutil
import csv
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
Q = ROOT.parent / 'r8q'
CONSENSUS = ROOT.parent / 'verified_consensus'
DATA = ROOT / 'data'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    DATA.mkdir(exist_ok=True)
    qplan = json.loads((Q / 'plan.json').read_text())
    qm = json.loads((Q / 'data/manifest.json').read_text())
    for name, expected in qm['files'].items():
        assert Path(name).name == name and sha(Q / 'data' / name) == expected
    base = qplan['baseline_variants']['source_college']
    baseline = {k: base[k] for k in ['id', 'input_source', 'context_features']}
    assert baseline['input_source'] == 'context' and len(baseline['context_features']) == 41
    mapping = {name: name for name in qm['base_data_hashes']}
    mapping.update({'source_features.csv': 'combine_features.csv', 'source_provenance.csv': 'combine_provenance.csv',
                    'source_dictionary.json': 'combine_dictionary.json', 'source_metadata.json': 'combine_metadata.json'})
    for old, new in mapping.items():
        shutil.copyfile(Q / 'data' / old, DATA / new)
    # Physically exclude inherited predictors, preserving allowed numeric text.
    projected = ['pid', 'draft_year', 'was_drafted', 'actual_pick'] + baseline['context_features']
    with (Q / 'data/features.csv').open(newline='') as source:
        rows = list(csv.DictReader(source))
    with (DATA / 'features.csv').open('w', newline='') as target:
        writer = csv.DictWriter(target, fieldnames=projected, lineterminator='\n', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    shutil.copyfile(Q / 'legacy_kernel.py', ROOT / 'legacy_kernel.py')
    x = pd.read_csv(DATA / 'features.csv', usecols=['pid', 'draft_year'])
    assert x.pid.is_unique and (x.draft_year <= 2018).all()
    public = json.loads((CONSENSUS / 'public_manifest.json').read_text())
    cons_names = ['features_eligible.csv', 'rank_observations.csv', 'metric_dictionary.json', 'validated_sources.json']
    before = {name: sha(CONSENSUS / name) for name in cons_names}
    assert all(before[name] == public['files'][name]['sha256'] for name in cons_names)
    cons = pd.read_csv(CONSENSUS / 'features_eligible.csv')
    assert cons.pid.is_unique and cons.draft_year.between(2007, 2014).all()
    cons_columns = list(cons.columns[2:])
    assert cons_columns == ['vcons_mock_mean_rank', 'vcons_mock_best_rank', 'vcons_mock_rank_range', 'vcons_mock_n_sources']
    joined = x.merge(cons, on=['pid', 'draft_year'], how='left', validate='one_to_one', sort=False)
    assert joined[['pid', 'draft_year']].equals(x)
    joined.to_csv(DATA / 'consensus_features.csv', index=False)
    provenance = pd.read_csv(CONSENSUS / 'rank_observations.csv')
    provenance = provenance[provenance.pid.isin(x.pid)].copy()
    assert provenance.draft_year.equals(provenance.pid.map(x.set_index('pid').draft_year))
    provenance.to_csv(DATA / 'consensus_provenance.csv', index=False)
    sources = [s for s in json.loads((CONSENSUS / 'validated_sources.json').read_text()) if s['feature_eligible']]
    assert all(s['draft_year'] <= 2014 for s in sources)
    (DATA / 'consensus_sources.json').write_text(json.dumps(sources, indent=2))
    dictionary = json.loads((CONSENSUS / 'metric_dictionary.json').read_text())
    (DATA / 'consensus_dictionary.json').write_text(json.dumps({c: dictionary[c] for c in cons_columns}, indent=2))
    families = {'combine': list(qplan['families']['all']), 'consensus': cons_columns}
    assert len(families['combine']) == 37 and not set(families['combine']) & set(cons_columns)
    combined = pd.read_csv(DATA / 'combine_features.csv').merge(joined, on=['pid', 'draft_year'], validate='one_to_one', sort=False)
    eligibility = {}
    for year in qplan['folds']:
        tr = combined[(combined.draft_year >= qplan['backbone']['window']) & (combined.draft_year <= year - 2)]
        eligibility[str(year)] = {family: [c for c in columns if tr[c].notna().sum() >= 5 and tr[c].nunique() >= 2] for family, columns in families.items()}
        assert len(eligibility[str(year)]['combine']) == 15 and len(eligibility[str(year)]['consensus']) == 4
    permutation_seeds = [9317, 18739, 28657]
    variants = [{'id': 'baseline', 'scope': 'baseline', 'arms': {}, 'permutation_seed': None}]
    for family in ['combine', 'consensus']:
        variants.append({'id': family + '_real', 'scope': family, 'arms': {family: 'real'}, 'permutation_seed': None})
        variants += [{'id': f'{family}_shuffle{seed}', 'scope': family, 'arms': {family: 'permuted'}, 'permutation_seed': seed} for seed in permutation_seeds]
    variants.append({'id': 'joint_RR', 'scope': 'joint', 'arms': {'combine': 'real', 'consensus': 'real'}, 'permutation_seed': None})
    for code, arms in [('RP', {'combine': 'real', 'consensus': 'permuted'}),
                       ('PR', {'combine': 'permuted', 'consensus': 'real'}),
                       ('PP', {'combine': 'permuted', 'consensus': 'permuted'})]:
        variants += [{'id': f'joint_{code}_shuffle{seed}', 'scope': 'joint', 'arms': arms, 'permutation_seed': seed} for seed in permutation_seeds]
    plan = {'study': 'R8s combine and consensus factorial diagnostics', 'diagnostic_only': True,
            'purpose': 'Test incremental combine/consensus information and conditional additions with family-vector controls that preserve masks and internal algebra.',
            'baseline': 'baseline', 'baseline_source_variant': baseline,
            'backbone': qplan['backbone'], 'folds': qplan['folds'], 'seeds': qplan['seeds'],
            'permutation_seeds': permutation_seeds, 'families': families, 'variants': variants,
            'source_filter': {'min_training_observed': 5, 'min_training_unique': 2, 'validation_coverage_used': False},
            'training_eligibility_registration': eligibility,
            'slot_mapping': {c: f'slot_{i:03d}' for i, c in enumerate(families['combine'] + cons_columns)},
            'selection': {'base_features': 41, 'selector_seed': 11, 'scope': 'The same 41 source-only R8n columns, ordered by the fixed CPU selector once per fold/process. No legacy engineering/coverage/shrinkage. Source slots appended afterward.'},
            'controls': {'shuffle': 'Permute whole family row vectors only within draft cohort AND exact selected-column missingness-pattern strata, with stable PID ordering.',
                         'seed_stream': 'SHA256(family, permutation seed, train-or-validation role, cohort, mask pattern); independent family streams, reused across solo and factorial arms.',
                         'preserved': 'Every player/column NaN mask and all within-family row-vector distributions, algebra and covariance.',
                         'limitations': 'Singleton/constant-vector strata are immovable. Report effective swappable observed rows and changed values; strata constrain the tested population.'},
            'calendar_policy': qplan['calendar_policy'], 'confirmation_note': qplan['confirmation_note'],
            'no_confirmation_or_test_scoring': True,
            'summary': {'solo': 'Pair real with mean of three family-vector shuffles at each fit seed/fold.',
                        'factorial': 'RR-RP is consensus given real combine; RR-PR is combine given real consensus; interaction RR-RP-PR+PP uses paired permutation replicates and model seeds.',
                        'conditional_controls': 'Joint comparisons always have identical selected base and source slot shapes. Solo versus joint raw-score differences are not complementarity evidence.',
                        'automatic_promotion': False, 'inference': 'Exploratory development contrasts, not significance tests or independent data replications.'},
            'registration_basis': 'Fixed source packages and training coverage only. No R8q scores or test outcomes inspected for plan construction.',
            'execution': {'workers': 4, 'task_count': 57, 'xgboost_selector': 'cpu', 'predictor': 'GPU TabICL only', 'gpu_launch_performed': False}}
    assert len(variants) * len(plan['seeds']) == 57
    (ROOT / 'plan.json').write_text(json.dumps(plan, indent=2))
    manifest = {'files': {p.name: sha(p) for p in sorted(DATA.iterdir()) if p.is_file() and p.name != 'manifest.json'},
                'base_data_hashes': {name: sha(DATA / name) for name in qm['base_data_hashes']},
                'unprojected_source_hashes': qm['base_data_hashes'], 'source_families': families,
                'baseline_source_variant': baseline, 'source_package_hashes': {'combine_bundle': {name: qm['files'][name] for name in mapping if name.startswith('source_')}, 'consensus': before},
                'q_plan_reference_sha256': sha(Q / 'plan.json'), 'consensus_unmatched_model_identities': cons.loc[~cons.pid.isin(x.pid), ['pid', 'draft_year']].to_dict('records'),
                'limitations': ['Prospect-universe completeness and original retrospective college/combine release vintages remain unresolved.',
                                'Consensus snapshots are verified pre-draft, but some earlier years have stale vintages and only two publishers.',
                                'No clean test or automatic promotion claim is authorized by this diagnostic study.']}
    (DATA / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    assert before == {name: sha(CONSENSUS / name) for name in cons_names}, 'Published consensus source mutated'
    print(json.dumps({'tasks': 57, 'players': len(x), 'eligible_columns_per_fold': {year: {f: len(c) for f, c in parts.items()} for year, parts in eligibility.items()}}, indent=2))


if __name__ == '__main__':
    main()

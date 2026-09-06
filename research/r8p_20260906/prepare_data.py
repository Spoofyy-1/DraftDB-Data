"""Prepare a local R8p input bundle without changing the published source package."""
from pathlib import Path
import csv
import hashlib
import json
import shutil
import datetime
import zoneinfo
import pandas as pd

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'r8n'
SOURCE = ROOT.parent / 'source_validation' / 'expansion'
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


base_plan = json.loads((BASE / 'plan.json').read_text())
base_variant = next(v for v in base_plan['variants'] if v['id'] == 'quarantine_bio_med_consensus_college_derived')
base_manifest = json.loads((BASE / 'data/manifest.json').read_text())
for filename, expected in base_manifest['files'].items():
    assert Path(filename).name == filename and sha(BASE / 'data' / filename) == expected
    shutil.copyfile(BASE / 'data' / filename, DATA / filename)
shutil.copyfile(BASE / 'legacy_kernel.py', ROOT / 'legacy_kernel.py')

x = pd.read_csv(DATA / 'features.csv')
assert x.pid.is_unique and (x.draft_year < 2019).all()
dictionary = json.loads((SOURCE / 'metric_dictionary.json').read_text())
families = {
    'numeric': sorted(k for k, v in dictionary.items() if v['family'] == 'synergy_situational'),
    'text': sorted(k for k, v in dictionary.items() if v['family'] == 'fixed_lexicon_text'),
}
assert len(families['numeric']) == 74 and len(families['text']) == 19
assert not set(families['numeric']) & set(families['text'])
registered = families['numeric'] + families['text']
assert not any('agent' in c or 'invited' in c or 'listed_' in c for c in registered)
public = json.loads((SOURCE / 'public_manifest.json').read_text())
assert sha(SOURCE / 'observations_eligible.csv') == public['files']['observations_eligible.csv']['sha256']
assert sha(SOURCE / 'metric_dictionary.json') == public['files']['metric_dictionary.json']['sha256']
observations = pd.read_csv(SOURCE / 'observations_eligible.csv')
observations = observations[observations.metric.isin(registered)].copy()
assert (observations.draft_year <= 2014).all()
assert not observations.duplicated(['pid', 'metric']).any()
players = {p['pid']: p for p in json.loads((ROOT.parent / 'collectors/players.json').read_text())}
observations['draft_date'] = observations.pid.map(lambda p: players[p]['draft_date'])
for row in observations.itertuples():
    assert players[row.pid]['draft_year'] == row.draft_year
    assert row.publication_date < row.draft_date
    cutoff = datetime.datetime.fromisoformat(row.draft_date).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York'))
    assert datetime.datetime.fromisoformat(row.capture_utc) < cutoff
eligible = observations[observations.pid.isin(x.pid)].copy()
unmatched = observations[~observations.pid.isin(x.pid)][['pid', 'draft_year']].drop_duplicates().to_dict('records')
# The model universe stays fixed. Source-only identities are recorded, never
# matched approximately or appended as unlabeled extra training rows.
source_wide = eligible.pivot(index=['pid', 'draft_year'], columns='metric', values='value').reset_index()
source_wide.columns.name = None
joined = x[['pid', 'draft_year']].merge(source_wide, on=['pid', 'draft_year'], how='left', validate='one_to_one', sort=False)
assert joined.pid.tolist() == x.pid.tolist() and len(joined) == len(x)
assert int(joined[registered].notna().sum().sum()) == len(eligible)
joined[['pid', 'draft_year'] + registered].to_csv(DATA / 'source_features.csv', index=False)
eligible.to_csv(DATA / 'source_provenance.csv', index=False)
(DATA / 'source_dictionary.json').write_text(json.dumps({c: dictionary[c] for c in registered}, indent=2))
manifest = dict(base_manifest)
manifest['source_families'] = families
manifest['source_features'] = registered
manifest['source_package_hashes'] = {name: public['files'][name]['sha256'] for name in ['observations_eligible.csv', 'metric_dictionary.json']}
manifest['baseline_variant'] = base_variant
manifest['unmatched_source_identities_excluded'] = unmatched
manifest['base_data_hashes'] = dict(base_manifest['files'])
manifest['files'] = {p.name: sha(p) for p in sorted(DATA.iterdir()) if p.is_file() and p.name != 'manifest.json'}
manifest['limitations'] = ['Diagnostic study: remaining legacy source provenance is not fully certified.',
                          'Only archived pre-draft numerical Synergy and fixed-lexicon text values are added.',
                          'No camp, agent or NBA 2019–2026 pilot rows are included in the source bundle.']
(DATA / 'manifest.json').write_text(json.dumps(manifest, indent=2))

variants = [{'id': 'baseline', 'family': 'baseline', 'arm': 'baseline', 'permutation_seed': None}]
permutation_seeds = [9317, 18739, 28657]
for family in ['numeric', 'text', 'joint']:
    variants.append({'id': family + '_real', 'family': family, 'arm': 'real', 'permutation_seed': None})
    for seed in permutation_seeds:
        variants.append({'id': f'{family}_shuffle{seed}', 'family': family, 'arm': 'permuted', 'permutation_seed': seed})
plan = {
    'study': 'R8p archived-report family diagnostics',
    'diagnostic_only': True,
    'purpose': 'Estimate numerical, text and joint effects against identical-shape within-cohort controls on a fixed quarantined baseline. Remaining legacy inputs are not certified.',
    'baseline': 'baseline', 'baseline_source_variant': base_variant,
    'backbone': base_plan['backbone'], 'folds': base_plan['folds'], 'seeds': base_plan['seeds'],
    'permutation_seeds': permutation_seeds, 'variants': variants,
    'families': families,
    'source_filter': {'min_training_observed': 5, 'min_training_unique': 2, 'validation_coverage_used': False},
    'slot_mapping': {c: f'slot_{i:03d}' for i, c in enumerate(registered)},
    'selection': {'base_topk': 60, 'selector_seed': 11, 'scope': 'Legacy base only; once per fold/process and identical audit hashes across tasks.',
                  'source_filter_scope': 'Training values only; fixed eligible column order across real/control arms and model seeds.'},
    'controls': {'shuffle': 'Independently permute observed values for each feature within each draft cohort, preserving every player/column NaN mask.',
                 'seed_stream': 'SHA256(feature, permutation seed, train-or-validation role, cohort); stable pid order; no outcomes.',
                 'dimensions': 'Same base, fixed slot names/order, masks, cardinalities and column sets for a family real/control comparison.'},
    'calendar_policy': base_plan['calendar_policy'],
    'confirmation_note': base_plan['confirmation_note'],
    'no_confirmation_or_test_scoring': True,
    'summary': {'comparison': 'Per model seed and fold: real minus the mean of its three matched shuffles. Mean equally across seeds and folds.',
                'baseline_difference': 'Context only; shape differs from added-family models and cannot establish information gain.',
                'automatic_promotion': False, 'joint_interpretation': 'Joint family effect, not a factorial interaction or proven complementarity.'},
    'execution': {'workers': 4, 'xgboost_selector': 'cpu', 'predictor': 'GPU TabICL only', 'task_count': 39, 'gpu_launch_performed': False}
}
assert len(variants) * len(plan['seeds']) == 39
(ROOT / 'plan.json').write_text(json.dumps(plan, indent=2))
print(json.dumps({'tasks': 39, 'base_players': len(x), 'source_players': len(source_wide), 'source_observations': len(eligible), 'source_columns': len(registered)}, indent=2))

"""Aggregate dated publisher ranks without labels, actual picks or outcomes."""
from pathlib import Path
import csv
import hashlib
import json
import math
import statistics
import collections
import pandas as pd

ROOT = Path(__file__).parent
observations = list(csv.DictReader((ROOT / 'rank_observations.csv').open()))
sources = {f"{d['publisher']}_{d['draft_year']}": d for d in json.loads((ROOT / 'validated_sources.json').read_text())}
groups = collections.defaultdict(list)
keys = set()
for row in observations:
    row['draft_year'], row['mock_rank'], row['listed_count'] = int(row['draft_year']), int(row['mock_rank']), int(row['listed_count'])
    assert 2007 <= row['draft_year'] <= 2014 and 1 <= row['mock_rank'] <= row['listed_count']
    assert sources[row['source_id']]['feature_eligible']
    key = row['pid'], row['publisher']
    assert key not in keys, 'One vote per publisher per player required'
    keys.add(key)
    groups[(row['pid'], row['draft_year'])].append(row)
wide = []
for (pid, year), entries in sorted(groups.items(), key=lambda pair: (pair[0][1], pair[0][0])):
    ranks = [r['mock_rank'] for r in entries]
    wide.append({'pid': pid, 'draft_year': year, 'vcons_mock_mean_rank': statistics.mean(ranks),
                 'vcons_mock_best_rank': min(ranks), 'vcons_mock_rank_range': max(ranks) - min(ranks) if len(ranks) >= 2 else '',
                 'vcons_mock_n_sources': len(entries)})
with (ROOT / 'features_eligible.csv').open('w') as f:
    writer = csv.DictWriter(f, fieldnames=list(wide[0])); writer.writeheader(); writer.writerows(wide)
with (ROOT / 'publisher_ranks_eligible.csv').open('w') as f:
    columns = ['pid', 'draft_year', 'vcons_dx_rank', 'vcons_nbadraft_rank', 'vcons_walter_rank']
    writer = csv.DictWriter(f, fieldnames=columns); writer.writeheader()
    for (pid, year), entries in sorted(groups.items(), key=lambda pair: (pair[0][1], pair[0][0])):
        writer.writerow({'pid': pid, 'draft_year': year, **{f"vcons_{r['publisher']}_rank": r['mock_rank'] for r in entries}})
dictionary = {
    'vcons_mock_mean_rank': {'unit': 'mock rank positions', 'definition': 'Arithmetic mean over one verified snapshot per observed publisher'},
    'vcons_mock_best_rank': {'unit': 'mock rank positions', 'definition': 'Smallest numerical mock rank among observed publishers'},
    'vcons_mock_rank_range': {'unit': 'mock rank positions', 'definition': 'Largest minus smallest observed publisher rank; missing unless at least two publishers list this player'},
    'vcons_mock_n_sources': {'unit': 'publisher count', 'definition': 'Number of distinct verified publishers listing this exact player in this draft cohort'},
}
for publisher in ['dx', 'nbadraft', 'walter']:
    dictionary[f'vcons_{publisher}_rank'] = {'unit': 'mock rank position', 'definition': 'Literal pre-draft prediction rank from the verified publisher snapshot; not actual draft selection'}
for value in dictionary.values():
    value['missing_policy'] = 'Unlisted or unmatched players stay missing; never impute actual pick, rank61 or rank0'
(ROOT / 'metric_dictionary.json').write_text(json.dumps(dictionary, indent=2))
# Read only identities/years from the current model universe. No pick or target
# columns are read, and no prediction/scoring work occurs in this package.
model = pd.read_csv(ROOT.parent / 'r8n/data/features.csv', usecols=['pid', 'draft_year']).to_dict('records')
model_ids = {row['pid'] for row in model}
model_years = {row['pid']: row['draft_year'] for row in model}
assert len(model_years) == len(model)
assert all(row['draft_year'] == model_years[row['pid']] for row in wide if row['pid'] in model_ids), 'Same pid has different cohort in model universe'
coverage = {'rank_observations': len(observations), 'eligible_players': len(wide),
            'players_with_two_publishers': sum(row['vcons_mock_n_sources'] == 2 for row in wide),
            'verified_sources': sum(s['feature_eligible'] for s in sources.values()),
            'actual_pick_or_outcome_columns_used': False, 'training_or_scoring_performed': False,
            'per_year': {}, 'fold_training_coverage': []}
for year in range(2007, 2015):
    listed = [r for r in wide if r['draft_year'] == year]
    universe = [r for r in model if r['draft_year'] == year]
    coverage['per_year'][str(year)] = {'eligible_players': len(listed), 'two_publishers': sum(r['vcons_mock_n_sources'] == 2 for r in listed),
                                     'model_universe_players': len(universe), 'model_players_with_rank': sum(r['pid'] in model_ids for r in listed),
                                     'sources': [{'publisher': d['publisher'], 'listed_count': d['listed_count'], 'matched_players': d['matched_players'],
                                                  'last_updated': d['source_last_updated_date'], 'capture_utc': d['source_available_by_utc']}
                                                 for d in sources.values() if d['draft_year'] == year and d['feature_eligible']]}
for cutoff in [2010, 2011, 2012]:
    relevant = [r for r in wide if 2007 <= r['draft_year'] <= cutoff and r['pid'] in model_ids]
    coverage['fold_training_coverage'].append({'training_draft_year_at_most': cutoff, 'players_with_rank': len(relevant),
                                               'players_with_two_publishers': sum(r['vcons_mock_n_sources'] == 2 for r in relevant)})
(ROOT / 'coverage.json').write_text(json.dumps(coverage, indent=2))
print(json.dumps({k: v for k, v in coverage.items() if k != 'per_year'}, indent=2))
print(json.dumps({year: {k: v for k, v in d.items() if k != 'sources'} for year, d in coverage['per_year'].items()}, indent=2))

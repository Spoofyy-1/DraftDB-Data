"""Factual rank aggregation and full identity-only left joins; no outcomes."""
from pathlib import Path
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parent
ORIGINAL = Path('/Users/kennakao/Downloads/nba_redraft_handoff/data')
MIRROR = Path('/Users/kennakao/nba/site/data')
COLUMNS = ['vcons_mock_mean_rank', 'vcons_mock_best_rank', 'vcons_mock_rank_range', 'vcons_mock_n_sources']


def main():
    obs = pd.read_csv(ROOT / 'rank_observations.csv')
    states = json.loads((ROOT / 'validated_sources.json').read_text())
    sources = {s['source_id']: s for s in states}
    assert obs.draft_year.between(2015, 2026).all()
    assert not obs.duplicated(['pid', 'publisher']).any()
    assert all(sources[sid]['feature_eligible'] for sid in obs.source_id)
    frame = obs.groupby(['pid', 'draft_year']).agg(vcons_mock_mean_rank=('mock_rank', 'mean'),
             vcons_mock_best_rank=('mock_rank', 'min'), vcons_mock_rank_range=('mock_rank', lambda x: x.max() - x.min() if len(x) >= 2 else float('nan')),
             vcons_mock_n_sources=('publisher', 'nunique')).reset_index().sort_values(['draft_year', 'pid']).reset_index(drop=True)
    assert frame.pid.is_unique
    frame[frame.draft_year <= 2018].to_csv(ROOT / 'features_training_2015_2018.csv', index=False)
    frame[frame.draft_year >= 2019].to_csv(ROOT / 'features_inference_2019_2026.csv', index=False)
    publisher = obs.pivot(index=['pid', 'draft_year'], columns='publisher', values='mock_rank').reset_index()
    publisher = publisher.rename(columns={c: f'vcons_{c}_rank' for c in publisher if c not in ['pid', 'draft_year']})
    publisher.to_csv(ROOT / 'publisher_ranks_eligible.csv', index=False)
    dictionary = json.loads((ROOT.parent / 'verified_consensus/metric_dictionary.json').read_text())
    dictionary = {c: dictionary[c] for c in COLUMNS}
    for c in dictionary:
        dictionary[c]['extension_policy'] = 'Same four aggregations. First15 serious Walter mocks are explicitly partial; others list60 ordinal slots. Never replace unlisted players with15/60/61 or use actual selection.'
    (ROOT / 'metric_dictionary.json').write_text(json.dumps(dictionary, indent=2))
    sidecars = ROOT / 'sidecars'
    sidecars.mkdir(exist_ok=True)
    coverage = {'rank_observations': len(obs), 'verified_sources': sum(s['feature_eligible'] for s in states),
                'training_eligible_players': int((frame.draft_year <= 2018).sum()),
                'inference_eligible_players': int((frame.draft_year >= 2019).sum()),
                'only_identity_columns_read_from_original_datasets': ['pid', 'draft_year'],
                'training_or_scoring_performed': False, 'per_year': {}, 'full_left_joins': {}}
    all_universes = []
    train = pd.read_csv(ORIGINAL / 'train_2000_2018.csv', usecols=['pid', 'draft_year'])
    assert train.pid.is_unique and train.draft_year.between(2000, 2018).all()
    train_extension = frame[frame.draft_year <= 2018]
    joined = train.merge(train_extension, on=['pid', 'draft_year'], how='left', validate='one_to_one', sort=False)
    assert joined[['pid', 'draft_year']].equals(train)
    joined.to_csv(sidecars / 'consensus_extension_train_2000_2018.csv', index=False)
    coverage['full_left_joins']['training'] = {'rows': len(train), 'ranked': int(joined.vcons_mock_mean_rank.notna().sum()),
                                             'identity_order_sha256': hashlib.sha256(train.to_csv(index=False).encode()).hexdigest()}
    all_universes.append(train)
    for year in range(2019, 2027):
        name = f'test_{year}_inputs.csv'
        identities = pd.read_csv(ORIGINAL / 'tests' / name, usecols=['pid', 'draft_year'])
        mirror = pd.read_csv(MIRROR / 'tests' / name, usecols=['pid', 'draft_year'])
        assert identities.equals(mirror), 'Original and public-site test identity/order differ'
        assert identities.pid.is_unique and (identities.draft_year == year).all()
        joined = identities.merge(frame[frame.draft_year == year], on=['pid', 'draft_year'], how='left', validate='one_to_one', sort=False)
        assert joined[['pid', 'draft_year']].equals(identities)
        assert len(joined) == len(identities)
        missing = joined.vcons_mock_mean_rank.isna()
        assert joined.loc[missing, COLUMNS].isna().all().all()
        joined.to_csv(sidecars / f'consensus_extension_test_{year}_inputs.csv', index=False)
        coverage['full_left_joins'][str(year)] = {'rows': len(joined), 'ranked': int((~missing).sum()), 'missing': int(missing.sum()),
                                                'two_publishers': int((joined.vcons_mock_n_sources >= 2).sum()),
                                                'identity_order_sha256': hashlib.sha256(identities.to_csv(index=False).encode()).hexdigest(),
                                                'original_and_site_identity_copies_match': True}
        all_universes.append(identities)
    universe = pd.concat(all_universes, ignore_index=True)
    assert universe.pid.is_unique
    model = pd.read_csv(ROOT.parent / 'r8n/data/features.csv', usecols=['pid', 'draft_year'])
    for year in range(2015, 2027):
        subset, o = frame[frame.draft_year == year], obs[obs.draft_year == year]
        coverage['per_year'][str(year)] = {'observations': len(o), 'eligible_players': len(subset),
                                          'two_publishers': int((subset.vcons_mock_n_sources >= 2).sum()),
                                          'source_ids': sorted(o.source_id.unique().tolist()),
                                          'model_universe_intersection': int(subset.pid.isin(model.pid).sum()) if year <= 2018 else None,
                                          'original_universe_intersection': int(subset.pid.isin(universe.pid).sum())}
    unmatched = frame[~frame.pid.isin(universe.pid)][['pid', 'draft_year']]
    coverage['eligible_source_identities_outside_original_universe'] = unmatched.to_dict('records')
    (ROOT / 'coverage.json').write_text(json.dumps(coverage, indent=2))
    print(json.dumps({k: v for k, v in coverage.items() if k not in ['eligible_source_identities_outside_original_universe']}, indent=2))


if __name__ == '__main__':
    main()

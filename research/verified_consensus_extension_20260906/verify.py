"""Replay source facts and adversarial boundaries without training or scoring."""
from pathlib import Path
import collections
import copy
import datetime as dt
import hashlib
import json
import zoneinfo
import pandas as pd
import parse as P

ROOT = Path(__file__).resolve().parent


def main():
    states = json.loads((ROOT / 'validated_sources.json').read_text())
    observations = pd.read_csv(ROOT / 'rank_observations.csv')
    obs = {(r.source_id, r.pid): r for r in observations.itertuples()}
    replayed, trees = [], {}
    for state in states:
        if not state['feature_eligible']:
            continue
        raw, tree, encoding = P.read_tree(ROOT / 'private' / f"{state['source_id']}.html")
        assert hashlib.sha256(raw).hexdigest() == state['html_sha256']
        parser = {'dx': P.dx, 'nbadraft': P.nbadraft, 'walter_serious': P.walter_serious}[state['publisher']]
        ranks, updated, text, boundary, evidence = parser(tree, state['draft_year'])
        assert updated == state['source_last_updated_date'] < state['draft_date']
        cutoff = dt.datetime.fromisoformat(state['draft_date']).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York'))
        capture = dt.datetime.fromisoformat(state['source_available_by_utc'])
        assert capture < cutoff and updated <= capture.date().isoformat()
        if state['draft_year'] == 2026:
            assert state['draft_date'] == '2026-06-23' and capture.date() == dt.date(2026, 5, 8)
        assert hashlib.sha256(evidence).hexdigest() == state['table_sha256']
        assert hashlib.sha256(json.dumps(ranks, sort_keys=True).encode()).hexdigest() == state['rank_facts_sha256']
        placeholders = state['nonplayer_placeholder_rows']
        assert len(ranks) == state['listed_count'] == (15 if state['publisher'] == 'walter_serious' else 60)
        for row in ranks:
            if row['source_name'] in ['Forfeited Pick', 'Pick Forfeited']:
                assert {'rank': row['rank'], 'text': row['source_name']} in placeholders
                continue
            identities = [p for p in P.PLAYERS if p['draft_year'] == state['draft_year'] and P.norm(p['name']) == P.norm(row['source_name'])]
            if len(identities) != 1:
                continue
            identity = identities[0]
            key = state['source_id'], identity['pid']
            r = obs[key]
            assert r.draft_year == identity['draft_year'] and r.mock_rank == row['rank']
            assert r.publisher == state['publisher'] and r.match_method == 'unique_exact_normalized_same_cohort_name'
            assert r.rank_facts_sha256 == state['rank_facts_sha256'] and r.table_sha256 == state['table_sha256']
            assert r.capture_utc == state['source_available_by_utc'] and r.draft_date == state['draft_date']
            replayed.append(key)
        trees[state['source_id']] = tree
    assert len(replayed) == len(set(replayed)) == len(obs) == len(observations)
    tests = []
    def reject(name, source, mutate, parser, year):
        tree = copy.deepcopy(trees[source])
        mutate(tree)
        try:
            parser(tree, year)
        except (AssertionError, ValueError):
            tests.append(name)
        else:
            raise AssertionError('Malformed boundary accepted: ' + name)

    reject('nb_round_truncated', 'nbadraft_2015', lambda t: t.xpath('//table[@id="nba_mock_consensus_table2"]/tbody/tr|//table[@id="nba_mock_consensus_table2"]/tr')[-1].drop_tree(), P.nbadraft, 2015)
    reject('nb_wrong_year_heading', 'nbadraft_2021', lambda t: setattr(t.xpath('//h1')[0], 'text', '2022 Mock Draft'), P.nbadraft, 2021)
    reject('nb_ambiguous_player_link', 'nbadraft_2021', lambda t: t.xpath('//table[@id="nba_mock_consensus_table"]//td[@class="player"]')[0].append(copy.deepcopy(t.xpath('//table[@id="nba_mock_consensus_table"]//td[@class="player"]/a')[0])), P.nbadraft, 2021)
    reject('nb_conflicting_sticky_rank', 'nbadraft_2022', lambda t: setattr(t.xpath('//table[@id="nba_mock_consensus_table"]')[1].xpath('./tbody/tr/td|./tr/td')[0], 'text', '2'), P.nbadraft, 2022)
    reject('dx2016_missing_item', 'dx_2016', lambda t: P.classes(t, 'div', 'ranking-item')[-1].drop_tree(), P.dx, 2016)
    reject('dx2017_changed_header', 'dx_2017', lambda t: setattr([tb for tb in P.classes(t, 'table', 'sorttable') if 'averages' in tb.get('class', '').split()][0].xpath('./thead/tr[last()]/th')[3], 'text', 'Team'), P.dx, 2017)
    reject('walter_partial_list_truncated', 'walter_serious_2018', lambda t: t.xpath('//ol/li')[-1].drop_tree(), P.walter_serious, 2018)
    reject('walter_wrong_author', 'walter_serious_2019', lambda t: [setattr(n, 'text', n.text.replace('David Kay', 'Other Writer')) for n in t.iter() if n.text and 'David Kay' in n.text], P.walter_serious, 2019)
    latest = next(s for s in states if s['source_id'] == 'nbadraft_2026')
    assert not latest['feature_eligible'] and latest['reason'] == 'Page update not strictly pre-draft'
    assert all(not s['feature_eligible'] for s in states if s['source_id'] in ['walter_2018', 'walter_2019'])
    calls = [json.loads(line) for line in (ROOT / 'network_attempts.jsonl').read_text().splitlines()]
    assert len(calls) == 42 <= 45 and [r['attempt'] for r in calls] == list(range(1, 43))
    assert sum(s['feature_eligible'] for s in states) <= 30
    public = ROOT.parent / 'verified_consensus'
    old_manifest = json.loads((public / 'public_manifest.json').read_text())
    assert all(hashlib.sha256((public / name).read_bytes()).hexdigest() == r['sha256'] for name, r in old_manifest['files'].items())
    s_root = ROOT.parent / 'r8s'
    s_manifest = json.loads((s_root / 'prototype_manifest.json').read_text())
    r8s_unchanged = all(hashlib.sha256((s_root / name).read_bytes()).hexdigest() == value for name, value in s_manifest['files'].items())
    report = {'status': 'passed_without_model_execution', 'replayed_rank_observations': len(replayed),
              'verified_sources': len(trees), 'adversarial_parser_tests_passed': tests,
              'ambiguous_2026_update_quarantined': True, 'satirical_walter_pages_quarantined': True,
              'network_attempts': len(calls), 'network_limit': 45, 'collector_stopped': True,
              'original_consensus_public_files_unchanged': len(old_manifest['files']),
              'r8s_original_files_unchanged': r8s_unchanged,
              'training_or_scoring_performed': False}
    (ROOT / 'verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

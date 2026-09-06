"""Source/identity and adversarial table-parser checks. No models or labels."""
from pathlib import Path
import copy
import csv
import datetime
import hashlib
import json
import parse as P

ROOT = Path(__file__).parent
sources = {f"{s['publisher']}_{s['draft_year']}": s for s in json.loads((ROOT / 'validated_sources.json').read_text())}
players = {p['pid']: p for p in P.PLAYERS}
observations = list(csv.DictReader((ROOT / 'rank_observations.csv').open()))
facts = {}
for source_id, source in sources.items():
    if not source['feature_eligible']:
        continue
    raw, tree, _ = P.source_tree(ROOT / 'private' / f'{source_id}.html')
    assert hashlib.sha256(raw).hexdigest() == source['html_sha256']
    if source['publisher'] == 'walter':
        rows, updated, _, _, table = P.parse_walter(tree, source['draft_year'], raw)
    else:
        parser = P.parse_dx if source['publisher'] == 'dx' else P.parse_nbadraft
        rows, updated, _, _, table = parser(tree, source['draft_year'])
    assert hashlib.sha256(table).hexdigest() == source['table_sha256']
    assert hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest() == source['rank_facts_sha256']
    assert updated == source['source_last_updated_date'] < source['draft_date']
    assert datetime.datetime.fromisoformat(source['source_available_by_utc']) < datetime.datetime.fromisoformat(source['cutoff_utc'])
    facts[source_id] = {row['rank']: row for row in rows}
seen = set()
for row in observations:
    key = row['pid'], row['publisher']
    assert key not in seen
    seen.add(key)
    player = players[row['pid']]
    assert player['draft_year'] == int(row['draft_year']) and player['draft_date'] == row['draft_date']
    fact = facts[row['source_id']][int(row['mock_rank'])]
    assert P.norm(fact['source_name']) == P.norm(player['name'])

rejected = []
def must_reject(name, operation):
    try:
        operation()
    except AssertionError:
        rejected.append(name)
    else:
        raise AssertionError('Unsafe parser input accepted: ' + name)

_, dx, _ = P.source_tree(ROOT / 'private/dx_2011.html')
missing = copy.deepcopy(dx)
table = missing.xpath('//table[@class="lotto2"]')[1]
table.remove(table.xpath('./tr')[-1])
must_reject('DX truncated second round', lambda: P.parse_dx(missing, 2011))
ambiguous = copy.deepcopy(dx)
cell = ambiguous.xpath('//table[@class="lotto2"]')[0].xpath('./tr')[1].xpath('./td')[2]
cell.append(copy.deepcopy(cell.xpath('./a')[0]))
must_reject('DX two subject links in player cell', lambda: P.parse_dx(ambiguous, 2011))
_, nd, _ = P.source_tree(ROOT / 'private/nbadraft_2012.html')
must_reject('NBADraft wrong cohort header', lambda: P.parse_nbadraft(nd, 2013))
truncated = copy.deepcopy(nd)
table = truncated.xpath('//table[@id="nba_mock_consensus_table"]')[0]
last_row = table.xpath('./tbody')[0].xpath('./tr')[-1]
last_row.getparent().remove(last_row)
must_reject('NBADraft missing player row', lambda: P.parse_nbadraft(truncated, 2012))
raw, walter, _ = P.source_tree(ROOT / 'private/walter_2008.html')
must_reject('Walter missing OL boundary', lambda: P.parse_walter(walter, 2008, raw.replace(b'<ol>', b'<div>', 1)))
report = {'status': 'passed', 'verified_mock_tables': len(facts), 'rank_observations_verified': len(observations),
          'identity_policy': 'Exact normalized name plus exact draft cohort; no aliases, fuzzy joins or outcome-assisted identity resolution',
          'adversarial_cases_rejected': rejected, 'model_or_test_scoring_performed': False}
(ROOT / 'verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

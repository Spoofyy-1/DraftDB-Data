"""Strict archive-only rank extraction; historical bio availability inventory."""
from pathlib import Path
import collections
import csv
import datetime as dt
import hashlib
import json
import re
import unicodedata
from lxml import html

ROOT = Path(__file__).resolve().parent
PLAYERS = json.loads((ROOT.parent / 'collectors/players.json').read_text())


def norm(name):
    return ''.join(c for c in unicodedata.normalize('NFKD', name).lower() if c.isalnum())


def txt(node):
    return ' '.join(node.text_content().split())


def read_tree(path):
    raw = path.read_bytes()
    try:
        text, encoding = raw.decode('utf8'), 'utf8'
    except UnicodeDecodeError:
        text, encoding = raw.decode('cp1252'), 'cp1252'
    tree = html.fromstring(text)
    for node in tree.xpath('//script|//style'):
        node.drop_tree()
    return raw, tree, encoding


def classes(tree, tag, cls):
    return tree.xpath('.//' + tag + '[contains(concat(" ",normalize-space(@class)," "),$cls)]', cls=' ' + cls + ' ')


def dx(tree, year):
    if year == 2017:
        assert len([h for h in tree.xpath('//h1') if txt(h) == f'{year} Mock Draft']) == 1, 'Unique target-year H1 missing'
    else:
        assert len([s for s in tree.xpath('//text()') if re.fullmatch(rf'\s*{year}\s+(?:DraftExpress NBA )?Mock Draft\s*', s)]) == 1, 'Unique target-year heading missing'
    if year < 2017:
        update = re.search(r'Updated on ((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+[A-Z][a-z]+\s+\d{1,2})(?:st|nd|rd|th)\s+at\s+(\d{2}:\d{2}:\d{2}\s+[AP]M)', txt(tree))
        assert update
        date = dt.datetime.strptime(f'{year} {update[1]}', '%Y %a %b %d').date()
        assert date.strftime('%a') == update[1][:3]
    else:
        update = re.search(r'Last updated\s*:\s*([A-Z][a-z]+\s+\d{1,2},\s+\d{4})\s+at\s+(\d{1,2}:\d{2}\s+[ap]m)', txt(tree))
        assert update
        date = dt.datetime.strptime(update[1], '%B %d, %Y').date()
        assert date.year == year
    rows, evidence = [], []
    if year == 2015:
        candidates = []
        for table in tree.xpath('//table'):
            found = [r for r in table.xpath('./tr|./tbody/tr') if r.xpath('./td') and re.fullmatch(r'\d+\.', txt(r.xpath('./td')[0]))]
            if len(found) >= 30:
                candidates.append((table, found))
        assert len(candidates) == 1
        table, found = candidates[0]
        for row in found:
            cells = row.xpath('./td')
            links = cells[2].xpath('.//a[contains(@href,"/profile/")]')
            assert len(links) == 1
            # Inventory only the player cell before its embedded college stats.
            cell = html.fromstring(html.tostring(cells[2]))
            for nested in cell.xpath('.//table'):
                nested.drop_tree()
            bio = txt(cell)
            fields = [f for f, pattern in [('age', r'\d+\.\d+ years old'), ('height', r"\d+'\d+\""), ('weight', r'\d+ lbs'), ('class', r' - (Freshman|Sophomore|Junior|Senior|International)\)'), ('position', r'\b(?:PG|SG|SF|PF|C)(?:/(?:PG|SG|SF|PF|C))? \(')] if re.search(pattern, bio)]
            rows.append({'rank': int(txt(cells[0])[:-1]), 'source_name': txt(links[0]), 'profile_href': links[0].get('href'), 'bio_fields_present': fields})
        evidence = [html.tostring(table)]
        boundary = 'Unique extended mock table; exactly60 direct ordinal rows, unique profile link in player cell; inventory ends before nested statistics table'
    elif year == 2016:
        containers = classes(tree, 'div', 'rankings')
        assert len(containers) == 1
        items = containers[0].xpath('./div[contains(concat(" ",normalize-space(@class)," ")," ranking-item ")]')
        assert len(items) == 60
        for item in items:
            num, cell = classes(item, 'div', 'numero'), classes(item, 'div', 'item')
            assert len(num) == len(cell) == 1 and re.fullmatch(r'\d+\.', txt(num[0]))
            links = cell[0].xpath('.//a[contains(@href,"/profile/")]')
            assert len(links) == 1
            bio = txt(cell[0])
            fields = [f for f, pattern in [('age', r'\d+\.\d+ years old'), ('height', r"\d+'\d+\""), ('weight', r'\d+ lbs'), ('class', r' - (Freshman|Sophomore|Junior|Senior|International)\)'), ('position', r'\b(?:PG|SG|SF|PF|C)(?:/(?:PG|SG|SF|PF|C))? \(')] if re.search(pattern, bio)]
            rows.append({'rank': int(txt(num[0])[:-1]), 'source_name': txt(links[0]), 'profile_href': links[0].get('href'), 'bio_fields_present': fields})
        evidence = [html.tostring(containers[0])]
        boundary = 'Unique rankings container,60 direct ranking-item blocks; unique numero and item child with profile link; stats/video siblings excluded from bio inventory'
    elif year == 2017:
        tables = [table for table in classes(tree, 'table', 'sorttable') if 'averages' in table.get('class', '').split()]
        assert len(tables) == 1, 'Unique extended averages mock table missing'
        table = tables[0]
        heads = [txt(n) for n in table.xpath('./thead/tr[last()]/th')]
        assert heads == ['#', '+/-', '', 'Player', 'CO', 'Pos', 'Age', 'HT', 'WT', 'WS', 'Pts', 'Reb', 'Ast', 'PER', 'Team', 'League'], 'Unexpected DX2017 columns'
        for row in table.xpath('./tr|./tbody/tr'):
            cells = row.xpath('./td')
            assert len(cells) == 16 and re.fullmatch(r'\d+', txt(cells[0]))
            links = cells[3].xpath('./a[contains(@href,"/profile/")]')
            assert len(links) == 1
            fields = [f for f, index in [('position', 5), ('age', 6), ('height', 7), ('weight', 8), ('wingspan', 9)] if txt(cells[index]) not in ['', '-', 'N/A']]
            rows.append({'rank': int(txt(cells[0])), 'source_name': txt(links[0]), 'profile_href': links[0].get('href'), 'bio_fields_present': fields})
        evidence = [html.tostring(table)]
        boundary = 'Unique sorttable with16 documented header columns and60 direct ordinal rows; unique profile link in column3; rank movement/team/statistics columns excluded'
    else:
        raise AssertionError('Unsupported DX year')
    assert [r['rank'] for r in rows] == list(range(1, 61))
    return rows, date.isoformat(), update[0], boundary, b'\n'.join(evidence)


def nbadraft(tree, year):
    assert len([h for h in tree.xpath('//h1') if txt(h) == f'{year} Mock Draft']) == 1
    text = txt(tree)
    update = re.search(r'Updated:\s*(\d{1,2}/\d{1,2}/\d{2})\s+(\d{1,2}:\d{2}\s+[ap]m)', text) if year <= 2019 else re.search(r'Updated:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})', text)
    assert update
    date = dt.datetime.strptime(update[1], '%m/%d/%y' if year <= 2019 else '%Y-%m-%d').date()
    assert date.year == year
    rows, evidence = [], []
    for ident, expected in [('nba_mock_consensus_table', list(range(1, 31))), ('nba_mock_consensus_table2', list(range(31, 61)))]:
        tables = tree.xpath('//table[@id=$ident]', ident=ident)
        assert 1 <= len(tables) <= 2
        clones = []
        for table in tables:
            assert [txt(n) for n in table.xpath('./thead/tr/th')] == ['#', 'Team', 'Player', 'H', 'W', 'P', 'School', 'C']
            found = []
            for row in table.xpath('./tr|./tbody/tr'):
                cells = row.xpath('./td')
                assert len(cells) == 8 and re.fullmatch(r'\d+', txt(cells[0]))
                links = cells[2].xpath('./a')
                assert len(links) == 1 and '/players/' in links[0].get('href', '')
                fields = [f for f, i in [('height', 3), ('weight', 4), ('position', 5), ('class', 7)] if txt(cells[i]) not in ['', '-', 'N/A']]
                found.append({'rank': int(txt(cells[0])), 'source_name': txt(links[0]), 'profile_href': links[0].get('href'), 'bio_fields_present': fields})
            assert [r['rank'] for r in found] == expected
            clones.append(found)
        assert all(c == clones[0] for c in clones), 'Conflicting duplicate sticky mock table'
        rows.extend(clones[0])
        evidence.append(html.tostring(tables[0]))
    return rows, date.isoformat(), update[0], 'Exact two round table IDs with eight checked headings and60 ordinal rows; duplicate sticky first-round tables must reproduce all rank/name/profile/field-presence facts exactly; unique player link and only historical table-cell bio availability', b'\n'.join(evidence)


def walter_serious(tree, year):
    assert len([h for h in tree.xpath('//h1') if txt(h) == f'{year} NBA Mock Draft']) == 1
    text = txt(tree)
    assert not re.search(r'(?:fake|not this Web site.s real)\s+(?:\d{4} NBA )?Mock Draft', text, re.I), 'Satirical mock excluded'
    assert 'Written by David Kay' in text, 'Expected serious mock author missing'
    updates = list(re.finditer(rf'This {year} NBA Mock Draft was updated:\s*([A-Z][a-z]+\.?\s+\d{{1,2}},\s+\d{{4}})', text))
    assert len(updates) == 1
    value = updates[0][1].replace('Sept.', 'Sep').replace('.', '')
    try:
        date = dt.datetime.strptime(value, '%B %d, %Y').date()
    except ValueError:
        date = dt.datetime.strptime(value, '%b %d, %Y').date()
    assert year - 1 <= date.year <= year
    lists = tree.xpath('//ol')
    assert len(lists) == 1 and lists[0].get('start') in [None, '1']
    items = lists[0].xpath('./li')
    assert len(items) == 15 and f'{year} NBA Mock Draft: Round 1 - Picks 16-30' in text, 'Explicit partial first15 boundary missing'
    rows = []
    for rank, item in enumerate(items, 1):
        headings = item.xpath('./b|./strong')
        assert len(headings) == 1
        heading = txt(headings[0])
        assert ':' in heading and ',' in heading
        name = heading.split(':', 1)[1].split(',', 1)[0].strip()
        assert len(name.split()) >= 2
        fields = [f for f, pattern in [('height', r'\b[5-8]-\d{1,2}\b'), ('class', r'\b(?:Fr|Soph|So|Jr|Sr)\.'), ('position', r',\s*(?:PG|SG|SF|PF|C|F|G)(?:/(?:PG|SG|SF|PF|C|F|G))?,') ] if re.search(pattern, heading)]
        rows.append({'rank': rank, 'source_name': name, 'profile_href': '', 'bio_fields_present': fields})
    return rows, date.isoformat(), updates[0][0], 'Unique ordered list with15 direct LI items and explicit navigation to Round1 Picks16-30; known partial top15 list, not missing bottom rows; only first bold player headings supply identities/bio inventory; narrative excluded', html.tostring(lists[0])


def main():
    observations, unmatched, states, inventory = [], [], [], []
    for metadata in sorted((ROOT / 'sources').glob('*.json')):
        state = json.loads(metadata.read_text())
        source_id, year = metadata.stem, state['draft_year']
        file = ROOT / 'private' / f'{source_id}.html'
        if not file.exists():
            states.append(state)
            continue
        try:
            raw, tree, encoding = read_tree(file)
            assert hashlib.sha256(raw).hexdigest() == state['html_sha256']
            capture = dt.datetime.strptime(state['source']['timestamp'], '%Y%m%d%H%M%S').replace(tzinfo=dt.timezone.utc)
            assert capture < dt.datetime.fromisoformat(state['cutoff_utc'])
            assert state['publisher'] != 'walter', 'Canonical Walt page explicitly labels itself fake; serious author route required'
            parser = {'dx': dx, 'nbadraft': nbadraft, 'walter_serious': walter_serious}[state['publisher']]
            ranks, updated, update_text, boundary, evidence = parser(tree, year)
            assert updated < state['draft_date'] and updated <= capture.date().isoformat(), 'Page update not strictly pre-draft'
            placeholders = [r for r in ranks if r['source_name'] in ['Forfeited Pick', 'Pick Forfeited']]
            assert all(r['profile_href'].rstrip('/').endswith(('/players/forfeited-pick', '/players/pick-forfeited')) and not r['bio_fields_present'] for r in placeholders)
            player_rows = [r for r in ranks if r not in placeholders]
            assert len({norm(r['source_name']) for r in player_rows}) == len(player_rows), 'Duplicate player names in mock boundary'
            rank_hash = hashlib.sha256(json.dumps(ranks, sort_keys=True).encode()).hexdigest()
            table_hash = hashlib.sha256(evidence).hexdigest()
            state.update(status='verified_predraft_mock', feature_eligible=True, publication_date=None, encoding=encoding,
                         source_last_updated_date=updated, source_update_text=update_text, source_available_by_utc=capture.isoformat(),
                         update_timezone='not specified; strict calendar date and archive UTC checks both required',
                         rank_facts_sha256=rank_hash, table_sha256=table_hash, listed_count=len(ranks), body_boundary=boundary,
                         nonplayer_placeholder_rows=[{'rank': r['rank'], 'text': r['source_name']} for r in placeholders],
                         rank_policy='Literal mock ordinal retained; nonplayer forfeited slots are excluded from identities and ranks are never compressed')
            (ROOT / 'private' / f'{source_id}.table.html').write_bytes(evidence)
            matches = []
            for rank in player_rows:
                candidates = [p for p in PLAYERS if p['draft_year'] == year and norm(p['name']) == norm(rank['source_name'])]
                if len(candidates) != 1:
                    unmatched.append({'source_id': source_id, 'draft_year': year, 'rank': rank['rank'], 'source_name': rank['source_name'], 'reason': 'No unique exact normalized same-cohort identity'})
                    continue
                p = candidates[0]
                assert p['draft_date'] == state['draft_date']
                matches.append(rank)
                observations.append({'pid': p['pid'], 'draft_year': year, 'source_id': source_id, 'publisher': state['publisher'],
                                     'mock_rank': rank['rank'], 'listed_count': len(ranks), 'source_url': state['source']['original'], 'archive_url': state['archive_url'],
                                     'source_last_updated_date': updated, 'capture_utc': capture.isoformat(), 'draft_date': state['draft_date'],
                                     'rank_facts_sha256': rank_hash, 'table_sha256': table_hash, 'match_method': 'unique_exact_normalized_same_cohort_name'})
            state['matched_players'] = len(matches)
            inventory.append({'source_id': source_id, 'draft_year': year, 'matched_players': len(matches),
                              'historical_cell_fields_matched_counts': dict(collections.Counter(f for r in matches for f in r['bio_fields_present'])),
                              'table_sha256': table_hash, 'archive_url': state['archive_url'], 'available_by_utc': capture.isoformat(),
                              'inventory_only': True, 'bio_features_extracted_or_modeled': False})
        except Exception as error:
            state.update(status='quarantined_validation', feature_eligible=False, reason=str(error))
        states.append(state)
    # A fallback snapshot replaces a failed/quarantined source, never adds a
    # second vote for the same publisher/year.
    assert len({(s['publisher'], s['draft_year']) for s in states if s['feature_eligible']}) == sum(s['feature_eligible'] for s in states)
    assert len({(r['pid'], r['publisher']) for r in observations}) == len(observations)
    fields = ['pid', 'draft_year', 'source_id', 'publisher', 'mock_rank', 'listed_count', 'source_url', 'archive_url', 'source_last_updated_date', 'capture_utc', 'draft_date', 'rank_facts_sha256', 'table_sha256', 'match_method']
    with (ROOT / 'rank_observations.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(observations)
    for name, value in [('validated_sources', states), ('unmatched_identities', unmatched), ('historical_bio_inventory', inventory)]:
        (ROOT / f'{name}.json').write_text(json.dumps(value, indent=2))
    print(json.dumps([{'id': s['source_id'], 'status': s['status'], 'matched': s.get('matched_players'), 'reason': s.get('reason')} for s in states], indent=2))


if __name__ == '__main__':
    main()

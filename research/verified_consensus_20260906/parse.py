"""Extract only rank/name facts from verified historical mock table boundaries."""
from pathlib import Path
import csv
import datetime
import hashlib
import json
import re
import unicodedata
import urllib.parse
from lxml import html

ROOT = Path(__file__).parent
PLAYERS = json.loads((ROOT.parent / 'collectors/players.json').read_text())


def norm(name):
    return ''.join(c for c in unicodedata.normalize('NFKD', name).lower() if c.isalnum())


def txt(node):
    return ' '.join(node.text_content().split())


def source_tree(path):
    raw = path.read_bytes()
    try:
        content, encoding = raw.decode('utf8'), 'utf8'
    except UnicodeDecodeError:
        content, encoding = raw.decode('cp1252'), 'cp1252'
    root = html.fromstring(content)
    for node in root.xpath('//script|//style'):
        node.drop_tree()
    return raw, root, encoding


def parse_dx(tree, year):
    # The old heading is a BR tail text node, not an element's .text.
    heads = [text for text in tree.xpath('//text()') if re.fullmatch(rf'\s*{year}\s+(?:DraftExpress NBA )?Mock Draft\s*', text)]
    assert len(heads) == 1, 'Unique target-year mock heading missing'
    text = txt(tree)
    updated = re.search(r'(?:This Mock was last updated|Updated) on ((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+[A-Z][a-z]+\s+\d{1,2})(?:st|nd|rd|th)\s+at\s+(\d{2}:\d{2}:\d{2}\s+[AP]M)', text)
    assert updated, 'Mock update date missing'
    date = datetime.datetime.strptime(f'{year} {updated[1]}', '%Y %a %b %d').date()
    assert date.strftime('%a') == updated[1][:3], 'Weekday/year inconsistency'
    tables = tree.xpath('//table[contains(concat(" ",normalize-space(@class)," ")," lotto ") or contains(concat(" ",normalize-space(@class)," ")," lotto2 ")]')
    output, evidence = [], []
    if tables:
        assert len(tables) == 2
        for table, heading, offset in zip(tables, ['First Round', 'Second Round'], [0, 30]):
            rows = table.xpath('./tr|./tbody/tr')
            assert txt(rows[0]) == heading
            found = []
            for row in rows[1:]:
                cells = row.xpath('./td')
                assert len(cells) == 3 and re.fullmatch(r'\d+', txt(cells[0]))
                links = [a for a in cells[2].xpath('.//a') if '/profile/' in a.get('href', '') or 'viewprofile.php?' in a.get('href', '')]
                assert len(links) == 1
                rank = int(txt(cells[0]))
                found.append(rank)
                output.append({'rank': rank + offset, 'source_name': txt(links[0]), 'profile_href': links[0].get('href')})
            assert found == list(range(1, 31)), 'Incomplete or reordered round table'
            evidence.append(html.tostring(table))
        boundary = 'Two exact lotto/lotto2 tables titled First Round and Second Round; only ordinal and unique profile-link text used; second round offset +30'
    else:
        assert year == 2014, 'Unsupported DraftExpress layout'
        candidates = []
        for table in tree.xpath('//table'):
            found = []
            for row in table.xpath('./tr|./tbody/tr'):
                cells = row.xpath('./td')
                if len(cells) < 3 or not re.fullmatch(r'\d+\.', txt(cells[0])):
                    continue
                links = [a for a in cells[2].xpath('.//a') if '/profile/' in a.get('href', '')]
                if len(links) != 1:
                    continue
                found.append({'rank': int(txt(cells[0])[:-1]), 'source_name': txt(links[0]), 'profile_href': links[0].get('href')})
            if len(found) >= 30:
                candidates.append((table, found))
        assert len(candidates) == 1
        table, output = candidates[0]
        evidence = [html.tostring(table)]
        boundary = 'Unique 2014 extended mock table with 60 direct ordinal/profile rows; biography, statistics and video cells ignored'
    assert [row['rank'] for row in output] == list(range(1, 61))
    return output, date.isoformat(), updated[0], boundary, b'\n'.join(evidence)


def parse_nbadraft(tree, year):
    heads = tree.xpath('//h1')
    assert len([h for h in heads if txt(h) == f'{year} Mock Draft']) == 1
    text = txt(tree)
    updated = re.search(r'Updated:\s*(\d{1,2}/\d{1,2}/\d{2})\s+(\d{1,2}:\d{2}\s+[ap]m)', text)
    assert updated, 'Mock update date missing'
    date = datetime.datetime.strptime(updated[1], '%m/%d/%y').date()
    assert date.year == year
    output, evidence = [], []
    for ident, expected in [('nba_mock_consensus_table', list(range(1, 31))), ('nba_mock_consensus_table2', list(range(31, 61)))]:
        matches = tree.xpath('//table[@id=$ident]', ident=ident)
        assert len(matches) == 1
        table = matches[0]
        rows = table.xpath('./tr|./tbody/tr')
        found = []
        for row in rows:
            cells = row.xpath('./td')
            assert len(cells) == 8 and re.fullmatch(r'\d+', txt(cells[0]))
            links = cells[2].xpath('./a')
            assert len(links) == 1 and '/players/' in links[0].get('href', '')
            rank = int(txt(cells[0]))
            found.append(rank)
            output.append({'rank': rank, 'source_name': txt(links[0]), 'profile_href': links[0].get('href')})
        assert found == expected, 'Incomplete or reordered mock table'
        evidence.append(html.tostring(table))
    boundary = 'Exact nba_mock_consensus_table and nba_mock_consensus_table2 IDs; only ordinal and player-link text used; team, size and trade notes ignored'
    return output, date.isoformat(), updated[0], boundary, b'\n'.join(evidence)


def parse_walter(tree, year, raw):
    assert f'{year} NBA Mock Draft' in tree.xpath('string(//title)')
    updates = re.findall(rf'{year} NBA Mock Draft\s*\(Updated\s*(\d{{1,2}}/\d{{1,2}})\)', txt(tree))
    assert len(set(updates)) == 1, 'No unique target-year update date'
    date = datetime.datetime.strptime(f'{year}/{updates[0]}', '%Y/%m/%d').date()
    # Preserve the original ordered-list boundary before HTML repair moves
    # invalid font/div children outside OL. Only LI bold heading facts are read.
    starts = list(re.finditer(rb'<ol\s*>', raw, re.I))
    assert len(starts) == 1, 'Unique ordered mock list missing'
    tail = raw[starts[0].end():]
    # Both archived pages omit </ol>. The next repeated Draft Links heading
    # explicitly starts the footer; all 30 mock items precede that boundary.
    footer = re.search(rb'(?:NBA )?Draft Links:', tail, re.I)
    assert footer, 'End-of-mock footer boundary missing'
    body = tail[:footer.start()]
    chunks = re.split(rb'<li\s*>', body, flags=re.I)[1:]
    assert len(chunks) == 30, 'Expected complete 30-position ordered mock list'
    output = []
    for rank, chunk in enumerate(chunks, 1):
        bold = re.search(rb'<b\s*>(.*?)</b\s*>', chunk, re.S | re.I)
        assert bold, 'Player heading missing'
        heading = txt(html.fromstring(b'<span>' + bold[1] + b'</span>'))
        assert ':' in heading and ',' in heading
        name = heading.split(':', 1)[1].split(',', 1)[0].strip()
        assert len(name.split()) >= 2
        output.append({'rank': rank, 'source_name': name, 'profile_href': ''})
    return output, date.isoformat(), f'{year} NBA Mock Draft (Updated {updates[0]})', 'Unique original OL through repeated Draft Links footer heading (source omits closing OL); exactly 30 LI ordinal positions and bold player-name headings only; all commentary excluded', body


def main():
    observations, states, unmatched = [], [], []
    for metadata in sorted((ROOT / 'sources').glob('*.json')):
        state = json.loads(metadata.read_text())
        if state['publisher'] not in ['dx', 'nbadraft', 'walter']:
            continue
        path = ROOT / 'private' / f'{metadata.stem}.html'
        if not path.exists():
            states.append(state)
            continue
        year = state['draft_year']
        try:
            raw, tree, encoding = source_tree(path)
            assert hashlib.sha256(raw).hexdigest() == state['html_sha256']
            capture = datetime.datetime.strptime(state['source']['timestamp'], '%Y%m%d%H%M%S').replace(tzinfo=datetime.timezone.utc)
            assert capture < datetime.datetime.fromisoformat(state['cutoff_utc'])
            if state['publisher'] == 'walter':
                ranks, updated, update_text, boundary, evidence = parse_walter(tree, year, raw)
            else:
                parser = parse_dx if state['publisher'] == 'dx' else parse_nbadraft
                ranks, updated, update_text, boundary, evidence = parser(tree, year)
            assert updated < state['draft_date'] and updated <= capture.date().isoformat()
            assert len({norm(row['source_name']) for row in ranks}) == len(ranks)
            fact_hash = hashlib.sha256(json.dumps(ranks, sort_keys=True).encode()).hexdigest()
            state.update(status='verified_predraft_mock', feature_eligible=True, publication_date=None,
                         source_last_updated_date=updated, source_update_text=update_text, update_timezone='not specified by source; calendar-date check only',
                         source_available_by_utc=capture.isoformat(), body_boundary=boundary, encoding=encoding,
                         table_sha256=hashlib.sha256(evidence).hexdigest(), rank_facts_sha256=fact_hash, listed_count=len(ranks))
            (ROOT / 'private' / f'{metadata.stem}.table.html').write_bytes(evidence)
            matched = 0
            for row in ranks:
                candidates = [p for p in PLAYERS if p['draft_year'] == year and norm(p['name']) == norm(row['source_name'])]
                if len(candidates) != 1:
                    unmatched.append({'source_id': metadata.stem, 'draft_year': year, **row, 'reason': 'No unique exact normalized same-cohort identity'})
                    continue
                p = candidates[0]
                assert p['draft_date'] == state['draft_date']
                observations.append({'pid': p['pid'], 'draft_year': year, 'source_id': metadata.stem, 'publisher': state['publisher'],
                                     'mock_rank': row['rank'], 'listed_count': len(ranks), 'source_url': state['source']['original'],
                                     'archive_url': state['archive_url'], 'source_last_updated_date': updated,
                                     'capture_utc': capture.isoformat(), 'draft_date': state['draft_date'],
                                     'rank_facts_sha256': fact_hash, 'table_sha256': state['table_sha256'],
                                     'match_method': 'unique_exact_normalized_same_cohort_name'})
                matched += 1
            state['matched_players'] = matched
        except Exception as error:
            state.update(status='quarantined_validation', feature_eligible=False, reason=str(error))
        states.append(state)
    (ROOT / 'validated_sources.json').write_text(json.dumps(states, indent=2))
    (ROOT / 'unmatched_identities.json').write_text(json.dumps(unmatched, indent=2))
    with (ROOT / 'rank_observations.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(observations[0])); writer.writeheader(); writer.writerows(observations)
    print(json.dumps([{'source': d['publisher'], 'year': d['draft_year'], 'status': d['status'], 'matched': d.get('matched_players'), 'reason': d.get('reason')} for d in states], indent=2))


if __name__ == "__main__":
    main()

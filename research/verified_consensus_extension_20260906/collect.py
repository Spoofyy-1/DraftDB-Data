"""Bounded, resumable archived mock discovery/fetch. No ranks eligible yet."""
from pathlib import Path
import datetime as dt
import gzip
import hashlib
import json
import subprocess
import shutil
import time
import urllib.parse
import urllib.request
import urllib.error
import zoneinfo

ROOT = Path(__file__).resolve().parent
PLAYERS = json.loads((ROOT.parent / 'collectors/players.json').read_text())
DATES = {p['draft_year']: p['draft_date'] for p in PLAYERS}
assert DATES[2026] == '2026-06-23'
LEDGER = ROOT / 'network_attempts.jsonl'
LIMIT = 45


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)


def decode_response(raw):
    if raw[:2] == b'\x1f\x8b':
        return gzip.decompress(raw)
    if raw[:4] == bytes.fromhex('28b52ffd'):
        node = '/Users/kennakao/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
        return subprocess.run([node, '-e', 'process.stdout.write(require("node:zlib").zstdDecompressSync(require("node:fs").readFileSync(0)))'], input=raw, capture_output=True, check=True).stdout
    return raw


def request(url, purpose, route):
    assert not (ROOT / 'collection_complete.json').exists(), 'This bounded collection is frozen; use a separately authorized extension'
    assert shutil.disk_usage(ROOT).free >= 500 * 1024 * 1024, 'Disk guard: fewer than500MiB free'
    previous = [json.loads(s) for s in LEDGER.read_text().splitlines()] if LEDGER.exists() else []
    assert len(previous) < LIMIT, 'Bounded network budget exhausted'
    assert not any(r['route'] == route and r.get('http_status') in [403, 429] for r in previous), 'Blocked route stopped'
    record = {'attempt': len(previous) + 1, 'url': url, 'purpose': purpose, 'route': route,
              'requested_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'status': 'requested'}
    with LEDGER.open('a') as f:
        f.write(json.dumps(record) + '\n')
    try:
        response = urllib.request.urlopen(url, timeout=30)
        raw = response.read()
        record.update(status='fetched', response_url=response.url, http_status=response.status,
                      response_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        assert response.url == url, 'Response redirected; not exact requested capture'
        return decode_response(raw)
    except Exception as error:
        record.update(status='failed', error=str(error))
        if isinstance(error, urllib.error.HTTPError):
            record['http_status'] = error.code
        raise
    finally:
        temporary = LEDGER.with_suffix('.tmp')
        temporary.write_text('\n'.join(json.dumps(r) for r in previous + [record]) + '\n')
        temporary.replace(LEDGER)
        time.sleep(.35)


def cutoff(year):
    return dt.datetime.fromisoformat(DATES[year]).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York')).astimezone(dt.timezone.utc)


def collect(publisher, year, target, reuse=False, source_id=None):
    source_id = source_id or f'{publisher}_{year}'
    index_path, source_path = ROOT / 'indexes' / f'{source_id}.json', ROOT / 'sources' / f'{source_id}.json'
    if source_path.exists():
        return json.loads(source_path.read_text())
    state = {'publisher': publisher, 'draft_year': year, 'draft_date': DATES[year], 'cutoff_utc': cutoff(year).isoformat(),
             'target_url': target, 'feature_eligible': False, 'status': 'discovery_only', 'source_id': source_id}
    if index_path.exists():
        index = json.loads(index_path.read_text())
    else:
        index = dict(state)
        existing = ROOT.parent / 'collectors/records/mocks' / f'{year}.json'
        cached = json.loads(existing.read_text()) if reuse and existing.exists() else {}
        if cached.get('snapshots'):
            index.update(records=cached['snapshots'], reused_index_path=str(existing.relative_to(ROOT.parent)),
                         reused_index_sha256=hashlib.sha256(existing.read_bytes()).hexdigest())
        else:
            query = [('url', target), ('matchType', 'exact'), ('from', f'{year}0101'),
                     ('to', (cutoff(year) - dt.timedelta(seconds=1)).strftime('%Y%m%d%H%M%S')),
                     ('output', 'json'), ('filter', 'statuscode:200'), ('filter', 'mimetype:text/html'),
                     ('collapse', 'digest'), ('limit', '250')]
            url = 'https://web.archive.org/cdx/search/cdx?' + urllib.parse.urlencode(query)
            index['query_url'] = url
            try:
                data = json.loads(request(url, 'archive_index', publisher + '_index'))
                index['records'] = [dict(zip(data[0], r)) for r in data[1:]] if data else []
            except Exception as error:
                index.update(records=[], status='unavailable_index', error=str(error))
        index['records'] = [r for r in index.get('records', [])
                            if dt.datetime.strptime(r['timestamp'], '%Y%m%d%H%M%S').replace(tzinfo=dt.timezone.utc) < cutoff(year)]
        atomic_json(index_path, index)
    if not index.get('records'):
        state.update(status='unavailable_index', error=index.get('error'), captures=0)
    else:
        source = max(index['records'], key=lambda r: r['timestamp'])
        url = f"https://web.archive.org/web/{source['timestamp']}id_/{source['original']}"
        state.update(source=source, archive_url=url, captures=len(index['records']))
        try:
            raw = request(url, 'archive_body', publisher + '_body')
            (ROOT / 'private' / f'{source_id}.html').write_bytes(raw)
            state.update(status='pending_body_validation', html_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        except Exception as error:
            state.update(status='unavailable_body', error=str(error))
    atomic_json(source_path, state)
    print(source_id, state['status'], state.get('captures'), state.get('bytes'), flush=True)
    return state


if __name__ == '__main__':
    jobs = [('dx', y, f'www.draftexpress.com/nba-mock-draft/{y}/', False) for y in range(2015, 2018)]
    jobs += [('nbadraft', y, f'www.nbadraft.net/{y}mock_draft', False) for y in range(2015, 2020)]
    jobs += [('nbadraft', y, 'nbadraft.net/nba-mock-drafts/', True) for y in range(2020, 2027)]
    for job in jobs:
        collect(*job)

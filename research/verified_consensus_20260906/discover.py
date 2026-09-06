"""Bounded historical mock discovery. Index records are not eligible features."""
from pathlib import Path
import concurrent.futures
import datetime
import json
import time
import urllib.parse
import urllib.request
import zoneinfo

ROOT = Path(__file__).parent
(ROOT / 'indexes').mkdir(exist_ok=True)
(ROOT / 'private').mkdir(exist_ok=True)
players = json.loads((ROOT.parent / 'collectors/players.json').read_text())
dates = {p['draft_year']: p['draft_date'] for p in players}


def one(job):
    publisher, year = job
    output = ROOT / 'indexes' / f'{publisher}_{year}.json'
    if output.exists():
        return json.loads(output.read_text())
    cutoff = datetime.datetime.fromisoformat(dates[year]).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York')).astimezone(datetime.timezone.utc)
    if publisher == 'dx':
        target = f'www.draftexpress.com/nba-mock-draft/{year}/' if year > 2007 else 'www.draftexpress.com/mymock.php?page=official&year=2007'
        match = 'exact'
    elif publisher == 'nbadraft':
        target, match = f'www.nbadraft.net/{year}mock_draft', 'prefix'
    elif publisher == 'walter':
        target, match = f'www.walterfootball.com/nbadraft{year}.php', 'exact'
    elif publisher == 'dx_prefix':
        target, match = f'www.draftexpress.com/nba-mock-draft/{year}', 'prefix'
    else:
        raise ValueError(publisher)
    query = [('url', target), ('matchType', match), ('from', f'{year}0101'),
             ('to', (cutoff - datetime.timedelta(seconds=1)).strftime('%Y%m%d%H%M%S')),
             ('output', 'json'), ('filter', 'statuscode:200'), ('filter', 'mimetype:text/html'),
             ('collapse', 'digest'), ('limit', '250')]
    url = 'https://web.archive.org/cdx/search/cdx?' + urllib.parse.urlencode(query)
    state = {'publisher': publisher, 'draft_year': year, 'draft_date': dates[year],
             'cutoff_utc': cutoff.isoformat(), 'query_url': url, 'feature_eligible': False,
             'status': 'discovery_only', 'retrieved_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        data = json.load(urllib.request.urlopen(url, timeout=35))
        state['records'] = [dict(zip(data[0], row)) for row in data[1:]] if data else []
        assert all(datetime.datetime.strptime(row['timestamp'], '%Y%m%d%H%M%S').replace(tzinfo=datetime.timezone.utc) < cutoff for row in state['records'])
    except Exception as error:
        state.update(status='unavailable', error=str(error), records=[])
    output.write_text(json.dumps(state, indent=2))
    print(publisher, year, state['status'], len(state['records']), flush=True)
    time.sleep(.5)
    return state


jobs = [(p, y) for y in range(2007, 2015) for p in ['dx', 'nbadraft']]
jobs += [('walter', 2007), ('walter', 2008), ('dx_prefix', 2008), ('dx_prefix', 2009)]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    states = list(pool.map(one, jobs))
(ROOT / 'discovery_summary.json').write_text(json.dumps([{'publisher': d['publisher'], 'draft_year': d['draft_year'], 'status': d['status'], 'captures': len(d['records'])} for d in states], indent=2))

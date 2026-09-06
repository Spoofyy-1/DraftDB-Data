"""Fetch at most one last verified-index snapshot per publisher/year."""
from pathlib import Path
import concurrent.futures
import datetime
import gzip
import hashlib
import json
import time
import urllib.request

ROOT = Path(__file__).parent
(ROOT / 'sources').mkdir(exist_ok=True)


def one(index):
    d = json.loads(index.read_text())
    out = ROOT / 'sources' / index.name
    if out.exists():
        return json.loads(out.read_text())
    state = {k: d[k] for k in ['publisher', 'draft_year', 'draft_date', 'cutoff_utc']}
    state.update(feature_eligible=False, status='pending_body_validation')
    if not d.get('records'):
        state['status'] = 'unavailable_index'
        out.write_text(json.dumps(state, indent=2))
        return state
    source = max(d['records'], key=lambda r: r['timestamp'])
    url = f"https://web.archive.org/web/{source['timestamp']}id_/{source['original']}"
    state.update(source=source, archive_url=url)
    try:
        response = urllib.request.urlopen(url, timeout=35)
        raw = response.read()
        assert response.url == url, 'Archive snapshot redirected'
        state['response_sha256'] = hashlib.sha256(raw).hexdigest()
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        state['html_sha256'] = hashlib.sha256(raw).hexdigest()
        (ROOT / 'private' / f'{index.stem}.html').write_bytes(raw)
        state['bytes'] = len(raw)
        state['retrieved_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    except Exception as error:
        state.update(status='unavailable_body', error=str(error))
    out.write_text(json.dumps(state, indent=2))
    print(index.stem, state['status'], state.get('bytes'), flush=True)
    time.sleep(.5)
    return state


with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    # Prefix probes exposed malformed relative navigation subpaths, not newer
    # canonical mocks. Keep that discovery metadata without fetching them.
    files = [p for p in sorted((ROOT / 'indexes').glob('*.json')) if not p.stem.startswith('dx_prefix_')]
    list(pool.map(one, files))

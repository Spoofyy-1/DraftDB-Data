"""Explicit publication allowlist; never publish archived HTML or full text."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).parent
allow = ['README.md', 'features_eligible.csv', 'publisher_ranks_eligible.csv', 'rank_observations.csv',
         'metric_dictionary.json', 'coverage.json', 'verification.json', 'validated_sources.json',
         'unmatched_identities.json', 'discovery_summary.json', 'discover.py', 'fetch.py', 'parse.py',
         'build.py', 'verify.py', 'package.py']
allow += sorted(str(p.relative_to(ROOT)) for folder in ['indexes', 'sources'] for p in (ROOT / folder).glob('*.json'))
manifest = {'policy': 'Publish only the listed factual/provenance files. Do not recursively copy this directory.',
            'publish_exclude': ['private/', '__pycache__/'], 'files': {}}
for name in allow:
    path = ROOT / name
    assert path.is_file() and not name.startswith('private/')
    raw = path.read_bytes()
    manifest['files'][name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
(ROOT / 'public_manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps({'publishable_files': len(allow), 'full_source_bodies_publishable': False}, indent=2))

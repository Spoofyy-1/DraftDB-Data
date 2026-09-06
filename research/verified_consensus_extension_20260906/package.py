"""Explicit factual-data publication allowlist; no full source bodies."""
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path(__file__).resolve().parent


def main():
    verification = json.loads((ROOT / 'verification.json').read_text())
    assert verification['status'] == 'passed_without_model_execution'
    summary = {'status': 'complete_frozen_no_more_network', 'network_attempts': 42, 'network_limit': 45,
               'verified_sources': 18, 'verified_rank_observations': 764,
               'training_or_scoring_performed': False,
               'remaining_routes': 'Serious Walter2021–23 returned no records; no further routes attempted after bounded pilot completion'}
    (ROOT / 'collection_complete.json').write_text(json.dumps(summary, indent=2))
    names = ['README.md', 'collect.py', 'parse.py', 'build.py', 'verify.py', 'package.py',
             'rank_observations.csv', 'features_training_2015_2018.csv', 'features_inference_2019_2026.csv',
             'publisher_ranks_eligible.csv', 'metric_dictionary.json', 'validated_sources.json',
             'unmatched_identities.json', 'historical_bio_inventory.json', 'coverage.json',
             'verification.json', 'network_attempts.jsonl', 'recovery.json', 'collection_complete.json']
    names += [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'sidecars').glob('*.csv'))]
    names += [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'indexes').glob('*.json'))]
    names += [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'sources').glob('*.json'))]
    assert len(names) == len(set(names))
    assert all('private' not in Path(name).parts and Path(name).suffix not in ['.html', '.zst'] for name in names)
    records = {}
    for name in names:
        file = ROOT / name
        raw = file.read_bytes()
        if file.suffix == '.py':
            ast.parse(raw)
        records[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    manifest = {'publication_policy': 'Publish only the exact files enumerated here. Full source bodies/table markup remain private; never recursively sync the package directory.',
                'source_package': 'verified_consensus_extension', 'files': records,
                'private_excluded': ['private/', '__pycache__/'],
                'model_use': 'Not attached to any model. Training and inference inputs separated; no scoring performed.'}
    (ROOT / 'public_manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'public_files': len(records), 'public_bytes': sum(r['bytes'] for r in records.values()), **summary}, indent=2))


if __name__ == '__main__':
    main()

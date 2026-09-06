"""Explicit publication allowlist for factual bio extension outputs only."""
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path(__file__).resolve().parent
verification = json.loads((ROOT / 'verification.json').read_text())
assert verification['status'] == 'passed_no_models_or_network' and verification['network_calls'] == 0
names = ['README.md', 'build.py', 'test_build.py', 'package.py', 'source_observations.csv', 'row_provenance.csv',
         'selected_sources.csv', 'features_training_2015_2018.csv', 'features_inference_2019_2026.csv',
         'metric_dictionary.json', 'coverage.json', 'missing_field_reasons.json', 'manifest.json', 'verification.json']
names += [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'sidecars').glob('*.csv'))]
assert len(names) == len(set(names)) == 23
files = {}
for name in names:
    raw = (ROOT / name).read_bytes()
    if name.endswith('.py'):
        ast.parse(raw)
    files[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
public = {'policy': 'Publish only these exact factual/provenance/code files. Do not copy archived bodies or recursively copy source directories.',
          'exclude': ['__pycache__/', '../verified_consensus_extension/private/'], 'files': files,
          'definitions': 'Reviewed10vmb only; no additional feature definitions or model integration.',
          'no_network_or_model_execution': True}
(ROOT / 'PUBLIC_ALLOWLIST.json').write_text(json.dumps(public, indent=2))
print(json.dumps({'public_files': len(files), 'bytes': sum(v['bytes'] for v in files.values()), 'verified': True}))

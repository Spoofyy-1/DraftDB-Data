"""Join independently reviewed candidate feature sidecars onto all eight members."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
KEY = ['candidate_id', 'draft_year']

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def assemble(index, left, right):
    assert list(index) == KEY and len(index) == 8
    assert not index.duplicated(KEY).any()
    expected = set(map(tuple, index[KEY].to_numpy()))
    for frame in [left, right]:
        assert set(KEY) <= set(frame)
        assert not frame.duplicated(KEY).any()
        assert set(map(tuple, frame[KEY].to_numpy())) == expected
        for field in frame.columns.difference(KEY):
            assert not re.search(r'(^y_|war|actual_|nba_id|player_name|legacy_pid|broad_pid|source_|draft_pick)', field, re.I), field
            assert pd.api.types.is_numeric_dtype(frame[field]), field
            assert np.isfinite(frame[field].dropna().to_numpy()).all(), field
    overlap = (set(left) & set(right)) - set(KEY)
    assert not overlap, f'Overlapping candidate predictors: {overlap}'
    result = index.merge(left, on=KEY, how='left', validate='one_to_one', sort=False)
    result = result.merge(right, on=KEY, how='left', validate='one_to_one', sort=False)
    assert result[KEY].equals(index[KEY]) and len(result) == 8
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--feature-file', type=Path, required=True)
    args = p.parse_args()
    args.feature_file = args.feature_file.resolve()
    ip = ROOT / 'data/pilot_member_index.csv'
    cp = ROOT / 'data/combine_feature_candidates.csv'
    index = pd.read_csv(ip)
    combine, other = pd.read_csv(cp), pd.read_csv(args.feature_file)
    result = assemble(index, combine, other)
    output = ROOT / 'data/combined_feature_candidates.csv'
    result.to_csv(output, index=False)
    numeric = result.drop(columns=KEY)
    manifest = dict(rows=8, candidate_predictors=len(numeric.columns), combine_predictors=len(combine.columns)-2,
        independently_reviewed_other_predictors=len(other.columns)-2, observed_cells=int(numeric.notna().sum().sum()),
        all_members_preserved=True, imputation_performed=False, model_ready=False, labels_merged=False,
        inputs=[dict(path=str(path.relative_to(ROOT)), sha256=digest(path)) for path in [ip, cp, args.feature_file]],
        output=dict(path=str(output.relative_to(ROOT)), sha256=digest(output)),
        candidate_features=list(numeric), note='Source candidate features only; labels and private crosswalks are not merged. Every input sidecar must already pass its own dated provenance review.')
    (ROOT / 'data/combined_feature_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    coverage_path = ROOT / 'data/coverage.json'
    coverage = json.loads(coverage_path.read_text())
    family_columns = {
        'official_combine': [c for c in numeric if c.startswith('vcmb_')],
        'college_context': [c for c in numeric if c.startswith('ctx_')],
        'mock_ranks': [c for c in numeric if c.startswith('vcons_')],
        'mock_profile': [c for c in numeric if c.startswith('vmb_')],
        'synergy': [c for c in numeric if c.startswith('report_') and not c.startswith('report_text_')],
        'report_lexicon': [c for c in numeric if c.startswith('report_text_')],
    }
    coverage.update(combined_candidate_predictors=len(numeric.columns), combined_observed_cells=manifest['observed_cells'],
        feature_family_coverage={family: int(numeric[fields].notna().any(axis=1).sum()) for family, fields in family_columns.items()})
    coverage_path.write_text(json.dumps(coverage, indent=2)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ['candidate_features','inputs','output']}, indent=2))

if __name__ == '__main__':
    main()

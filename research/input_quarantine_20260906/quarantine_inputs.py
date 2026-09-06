"""Create reversible predictor-only snapshots with unsafe/undated fields masked."""
from pathlib import Path
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'fifty/merged_inputs'
OUT = ROOT / 'quarantined_inputs'
PREFIXES = ('bio_', 'med_', 'cons_', 'scout_')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    records = []
    for source in sorted(SOURCE.glob('*_inputs.csv')):
        frame = pd.read_csv(source)
        assert frame.pid.is_unique
        assert not any(c.startswith('y_') or c in ['actual_pick', 'actual_round'] for c in frame)
        columns = [c for c in frame if c.startswith(PREFIXES)]
        before = frame.pid.tolist()
        cells = int(frame[columns].notna().sum().sum())
        frame[columns] = float('nan')
        assert frame.pid.tolist() == before and frame[columns].isna().all().all()
        frame.to_csv(OUT / source.name, index=False)
        records.append({'file': source.name, 'rows': len(frame), 'masked_nonmissing_cells': cells,
                        'masked_columns': columns, 'source_sha256': sha(source),
                        'sha256': sha(OUT / source.name)})
    manifest = {
        'version': 'input_quarantine_20260906', 'status': 'partially audited; not certified clean',
        'purpose': 'Mask confirmed contaminated bio descendants and quarantine undated medical, consensus, and scouting values pending source verification. Preserve every original predictor row.',
        'masked_prefixes': list(PREFIXES), 'files': records,
        'reasons': {
            'bio_': 'Current NBA measurement fallback, train-plus-test imputation, and a documented post-draft research fill. Official-source replacements must come from a separate verified sidecar.',
            'med_': 'Original collectors/dates unavailable; implausible injury timing found.',
            'cons_': 'Original dated mock/big-board evidence unavailable in the handoff; quarantine until recovered.',
            'scout_': 'Original grades and date/source validation not independently certified.'},
        'limitations': ['Remaining inherited predictors still require source provenance review.',
                       'No training labels, draft picks, or held-out answers are stored in these snapshots.',
                       'This snapshot is data preparation only; it does not retroactively change or certify past scores.',
                       'All 50 newly built raw-statistic columns are retained with their separate source/date manifests.'],
    }
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'files': len(records), 'rows': sum(r['rows'] for r in records),
                      'masked_cells': sum(r['masked_nonmissing_cells'] for r in records)}))


if __name__ == '__main__':
    main()

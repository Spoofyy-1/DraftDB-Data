"""Export only dated earlier-cohort labels from existing verified broker bundles.

Run outside model namespaces. No target-year answers or scores are opened.
Each model receives only its own output-year directory.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil

import numpy as np
import pandas as pd

ROOT = Path('/home/ubuntu/nba/handoff')
SOURCE = ROOT / 'calendar_broker_prototype/bundles'
OUTPUT = ROOT / 'r9test_label_exports'
H_DATA = ROOT / 'r9g/d_reference/b_reference/a_reference/x_reference/base/data'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.umask(0o077)
    assert not OUTPUT.exists(), 'Never overwrite a prior export'
    OUTPUT.mkdir()
    old = pd.read_csv(H_DATA / 'labels.csv')
    old = old[old.ordinal.isin([1, 2])]
    assert old.season_end.le(2018).all()
    reports = []
    for year in range(2019, 2026):
        src = SOURCE / str(year)
        manifest = json.loads((src / 'manifest.json').read_text())
        assert manifest['predicted_draft_year'] == year
        assert manifest['actual_label_max'] <= year - 1
        for name, expected in manifest['files'].items():
            assert sha(src / name) == expected, (year, name)
        labels = pd.read_csv(src / 'training_labels.csv')
        assert labels.pid.notna().all()
        assert labels.draft_year.lt(year).all()
        assert labels.season_end.le(year - 1).all()
        assert labels.season_end.ge(labels.draft_year + labels.ordinal).all()
        assert not labels.duplicated(['pid', 'ordinal']).any()
        assert np.isfinite(labels.war).all()
        labels = labels[labels.ordinal.isin([1, 2])].copy()
        query = pd.read_csv(ROOT / f'data/tests/test_{year}_inputs.csv', usecols=['pid'])
        assert query.pid.is_unique and not set(query.pid) & set(labels.pid)
        common = old.merge(labels, on=['pid', 'ordinal'], suffixes=('_H', '_broker'))
        assert common.draft_year_H.eq(common.draft_year_broker).all()
        assert common.season_end_H.eq(common.season_end_broker).all()
        assert np.allclose(common.war_H, common.war_broker, rtol=0, atol=1e-5)
        labels = labels.sort_values(['pid', 'ordinal']).reset_index(drop=True)
        dst = OUTPUT / str(year)
        dst.mkdir()
        labels.to_csv(dst / 'training_labels.csv', index=False)
        counts = labels.groupby('pid').ordinal.nunique()
        report = {
            'predicted_year': year,
            'permitted_season_end': year - 1,
            'actual_label_max': int(labels.season_end.max()),
            'partial_calendar': manifest['partial_calendar'],
            'missing_calendar_seasons': manifest['missing_calendar_seasons'],
            'source_manifest_sha256': sha(src / 'manifest.json'),
            'source_labels_sha256': manifest['files']['training_labels.csv'],
            'export_labels_sha256': sha(dst / 'training_labels.csv'),
            'rows': len(labels),
            'players': int(labels.pid.nunique()),
            'players_with_both_ordinals_before_feature_membership_filter': int((counts == 2).sum()),
            'common_H_facts_calendar_and_WAR_verified': len(common),
            'H_facts_absent_from_verified_broker': len(old) - len(common),
            'no_query_or_future_cohort_labels': True,
            'no_missing_labels_zero_filled': True,
            'test_answer_files_opened_by_this_exporter': False,
            'source_eligible_label_mismatch_players': manifest['label_verification']['eligible_label_mismatch_players'],
            'scope': 'Observed ordinal1+2 labels only; drafted membership and feature joins occur separately',
        }
        (dst / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
        reports.append(report)
    (OUTPUT / 'aggregate_audit.json').write_text(json.dumps(reports, indent=2) + '\n')
    print(json.dumps(reports))


if __name__ == '__main__':
    main()

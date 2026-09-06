"""Preserve input populations and append separately dated profile/mock facts."""
from pathlib import Path
import hashlib
import json
import csv
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'verified_inputs_v2'
EXPECTED_COLUMNS = {
    'vcons_': ['vcons_mock_mean_rank', 'vcons_mock_best_rank', 'vcons_mock_rank_range', 'vcons_mock_n_sources'],
    'vmb_': ['vmb_age_reported_years', 'vmb_listed_height_in', 'vmb_listed_weight_lb', 'vmb_listed_bmi',
             'vmb_college_class_year', 'vmb_position_pg', 'vmb_position_sg', 'vmb_position_sf', 'vmb_position_pf', 'vmb_position_c'],
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_file(package, manifest_name, filename):
    root = ROOT / package
    manifest = json.loads((root / manifest_name).read_text())
    expected = manifest['files'][filename]['sha256']
    path = root / filename
    assert sha(path) == expected, (package, filename)
    frame = pd.read_csv(path)
    assert frame.pid.is_unique and list(frame)[:2] == ['pid', 'draft_year']
    with path.open(newline='') as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == list(frame)
        tokens = list(reader)
    assert len(tokens) == len(frame)
    return frame, dict(package=package, file=filename, sha256=expected,
                      publication_manifest_sha256=sha(root / manifest_name)), tokens


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--source-cutoff', type=int, default=2026)
    args = parser.parse_args()
    output = args.output
    output.mkdir(exist_ok=True)
    sources, families, source_tokens = [], {}, {}
    for family, old, new, manifest in [
        ('vcons_', 'verified_consensus', 'verified_consensus_extension', 'public_manifest.json'),
        ('vmb_', 'verified_mock_bio', 'verified_mock_bio_extension', 'PUBLIC_ALLOWLIST.json'),
    ]:
        parts = []
        tokens_by_identity = {}
        for package, filename, start, end in [
            (old, 'features_eligible.csv', 2007, 2014),
            (new, 'features_training_2015_2018.csv', 2015, 2018),
            (new, 'features_inference_2019_2026.csv', 2019, 2026),
        ]:
            if start > args.source_cutoff:
                continue
            frame, provenance, tokens = verified_file(package, manifest, filename)
            assert frame.draft_year.between(start, end).all()
            frame = frame[frame.draft_year <= args.source_cutoff].copy()
            assert list(frame.columns[2:]) == EXPECTED_COLUMNS[family]
            assert not parts or list(frame) == list(parts[0])
            parts.append(frame)
            sources.append(provenance)
            for record in tokens:
                key = (record['pid'], int(record['draft_year']))
                if key[1] > args.source_cutoff:
                    continue
                assert key not in tokens_by_identity
                tokens_by_identity[key] = [record[column] for column in EXPECTED_COLUMNS[family]]
        union = pd.concat(parts, ignore_index=True)
        assert union.pid.is_unique
        families[family] = union
        source_tokens[family] = tokens_by_identity
    records = []
    base_root = ROOT / 'verified_inputs_v1'
    base_manifest = json.loads((base_root / 'manifest.json').read_text())
    registered = {entry['file']: entry for entry in base_manifest['files']}
    paths = sorted(base_root.glob('*_inputs.csv'))
    assert {p.name for p in paths} == set(registered) == {'train_inputs.csv'} | {f'{y}_inputs.csv' for y in range(2019, 2027)}
    for source in paths:
        assert sha(source) == registered[source.name]['sha256']
        base = pd.read_csv(source)
        assert base.pid.is_unique and len(base) == registered[source.name]['rows']
        assert base.draft_year.between(2000, 2018).all() if source.name == 'train_inputs.csv' else (base.draft_year == int(source.name[:4])).all()
        merged = base.copy()
        coverage = {}
        for family, facts in families.items():
            columns = list(facts.columns[2:])
            assert len(columns) == (4 if family == 'vcons_' else 10)
            assert not set(columns) & set(merged)
            merged = merged.merge(facts, on=['pid', 'draft_year'], how='left',
                                  validate='one_to_one', sort=False)
            coverage[family] = int(merged[columns].notna().any(axis=1).sum())
        pd.testing.assert_frame_equal(merged[base.columns], base)
        assert merged[['pid', 'draft_year']].equals(base[['pid', 'draft_year']])
        assert not any(c.startswith('y_') or c in ['actual_pick', 'actual_round'] for c in merged)
        assert merged[[c for c in merged if c.startswith(('bio_', 'med_', 'cons_', 'scout_'))]].isna().all().all()
        # Append raw numeric text: never reserialize or round existing cells.
        with source.open(newline='') as handle:
            reader = csv.DictReader(handle)
            base_columns = reader.fieldnames
            base_tokens = list(reader)
        extra_columns = [column for family in families for column in EXPECTED_COLUMNS[family]]
        with (output / source.name).open('w', newline='') as handle:
            writer = csv.writer(handle, lineterminator='\n')
            writer.writerow(base_columns + extra_columns)
            for record in base_tokens:
                key = (record['pid'], int(record['draft_year']))
                extras = [value for family in families for value in source_tokens[family].get(key, [''] * len(EXPECTED_COLUMNS[family]))]
                writer.writerow([record[column] for column in base_columns] + extras)
        with (output / source.name).open(newline='') as handle:
            written = list(csv.DictReader(handle))
        assert [{column: record[column] for column in base_columns} for record in written] == base_tokens
        records.append(dict(file=source.name, rows=len(merged), coverage=coverage,
                            base_sha256=sha(source), sha256=sha(output / source.name)))
    assert len(records) == 9 and sum(r['rows'] for r in records) == 2419
    manifest = dict(version='verified_inputs_v2_20260906', files=records, sources=sources, source_cutoff=args.source_cutoff,
                    base_manifest_sha256=sha(base_root / 'manifest.json'), existing_cells_preserved_as_exact_text=True,
                    newly_appended_columns=[c for frame in families.values() for c in frame.columns[2:]],
                    new_research_feature_count=101,
                    status='Partially audited inputs; not an approved model matrix or clean benchmark certification',
                    policy='Left joins preserve all original identities, row order, existing values and missingness. No outcomes, actual draft picks, imputation, model fitting or scoring.',
                    limitations=['Original population selection and remaining inherited columns are uncertified.',
                                 'Dated listed profiles are distinct from official combine measurements.',
                                 'Reported snapshot age is missing in the later source tables; no birth dates inferred.',
                                 'Mock rank lists may be partial or stale; this is not complete market consensus.'])
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(dict(files=9, rows=2419, added=14, coverage=records), indent=2))


if __name__ == '__main__':
    main()

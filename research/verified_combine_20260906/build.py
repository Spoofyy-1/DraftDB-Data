"""Rebuild pre-draft combine features from cached official JSON only.

No network, legacy collector import, WAR fields, biographies, research fills,
cross-cohort imputation, or contemporary NBA measurements are used.
"""
import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


MEASUREMENTS = [
    ("height_without_shoes_in", "HEIGHT_WO_SHOES", "inches", True),
    ("height_with_shoes_in", "HEIGHT_W_SHOES", "inches", True),
    ("weight_lb", "WEIGHT", "pounds", True),
    ("wingspan_in", "WINGSPAN", "inches", True),
    ("standing_reach_in", "STANDING_REACH", "inches", True),
    ("body_fat_pct", "BODY_FAT_PCT", "percentage points", False),
    ("hand_length_in", "HAND_LENGTH", "inches", True),
    ("hand_width_in", "HAND_WIDTH", "inches", True),
    ("standing_vertical_in", "STANDING_VERTICAL_LEAP", "inches", False),
    ("max_vertical_in", "MAX_VERTICAL_LEAP", "inches", False),
    ("lane_agility_s", "LANE_AGILITY_TIME", "seconds", True),
    ("modified_lane_agility_s", "MODIFIED_LANE_AGILITY_TIME", "seconds", True),
    ("three_quarter_sprint_s", "THREE_QUARTER_SPRINT", "seconds", True),
    ("bench_press_reps", "BENCH_PRESS", "repetitions", False),
]
ZONES = ["CORNER_LEFT", "BREAK_LEFT", "TOP_KEY", "BREAK_RIGHT", "CORNER_RIGHT"]
DRILLS = {
    "spot_15ft": ["SPOT_FIFTEEN_" + z for z in ZONES],
    "spot_college3": ["SPOT_COLLEGE_" + z for z in ZONES],
    "spot_nba3": ["SPOT_NBA_" + z for z in ZONES],
    "off_dribble_15ft": ["OFF_DRIB_FIFTEEN_" + z for z in ZONES[1:4]],
    "off_dribble_college3": ["OFF_DRIB_COLLEGE_" + z for z in ZONES[1:4]],
    "on_move_15ft": ["ON_MOVE_FIFTEEN"],
    "on_move_college3": ["ON_MOVE_COLLEGE"],
}


def norm(value):
    return re.sub("[^a-z0-9]", "", unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def numeric(value, positive=False):
    if value is None or (isinstance(value, str) and not value.strip()):
        return np.nan
    try:
        result = float(value)
    except (TypeError, ValueError):
        return np.nan
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        return np.nan
    return result


def nba_id(value):
    number = numeric(value, positive=True)
    return int(number) if math.isfinite(number) and number.is_integer() else None


def shots(value):
    if value is None:
        return None
    match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", str(value))
    if not match:
        return None
    made, attempted = map(int, match.groups())
    return (made, attempted) if 0 <= made <= attempted else None


def feature_dictionary():
    result = {}
    for short, source, unit, positive in MEASUREMENTS:
        result["vcmb_" + short] = dict(kind="official combine measurement", source_fields=[source], unit=unit,
                                      transform="numeric parse only; no imputation", positive_required=positive)
    result["vcmb_bmi_kg_m2"] = dict(kind="within-row derived measurement", source_fields=["WEIGHT", "HEIGHT_WO_SHOES"],
                                    unit="kg/m^2", transform="(weight_lb * 0.45359237) / (height_without_shoes_in * 0.0254)^2; both required")
    result["vcmb_wingspan_minus_height_in"] = dict(kind="within-row derived measurement", source_fields=["WINGSPAN", "HEIGHT_WO_SHOES"],
                                                 unit="inches", transform="wingspan minus height without shoes; both required")
    for group, fields in DRILLS.items():
        for metric, unit in [("made", "shots made"), ("attempted", "shots attempted"), ("pct", "fraction 0 to 1")]:
            result[f"vcmb_{group}_{metric}"] = dict(kind="official combine shooting drill", source_fields=fields, unit=unit,
                                                     transform=f"All {len(fields)} named source stations must parse as made-attempted; sum {metric} or total made / total attempted",
                                                     missing_rule="Any missing/malformed station makes the aggregate NaN; zero attempts yield NaN percentage")
    return result


FEATURES = list(feature_dictionary())


def transform(row):
    out = {c: np.nan for c in FEATURES}
    for short, source, _, positive in MEASUREMENTS:
        out["vcmb_" + short] = numeric(row.get(source), positive)
    height, weight, span = [out[c] for c in ["vcmb_height_without_shoes_in", "vcmb_weight_lb", "vcmb_wingspan_in"]]
    if math.isfinite(height) and math.isfinite(weight):
        out["vcmb_bmi_kg_m2"] = weight * 0.45359237 / (height * 0.0254)**2
    if math.isfinite(height) and math.isfinite(span):
        out["vcmb_wingspan_minus_height_in"] = span - height
    for group, fields in DRILLS.items():
        attempts = [shots(row.get(c)) for c in fields]
        if any(x is None for x in attempts):
            continue
        made, total = [sum(x[i] for x in attempts) for i in [0, 1]]
        out[f"vcmb_{group}_made"] = made
        out[f"vcmb_{group}_attempted"] = total
        if total > 0:
            out[f"vcmb_{group}_pct"] = made / total
    return out


def read_source(path, year):
    value = json.loads(path.read_text())
    params = value["parameters"]
    expected_season = f"{year}-{str(year+1)[-2:]}"
    assert params["SeasonYear"] == expected_season, "Request parameter year differs from cache filename"
    assert str(params["LeagueID"]) == "00", "Unexpected league"
    results = [x for x in value["resultSets"] if x["name"] == "DraftCombineStats"]
    assert len(results) == 1
    result = results[0]
    headers = result["headers"]
    assert len(headers) == len(set(headers))
    assert {"SEASON", "PLAYER_ID", "PLAYER_NAME"} <= set(headers)
    rows = []
    for position, values in enumerate(result["rowSet"]):
        assert len(values) == len(headers)
        row = dict(zip(headers, values))
        assert int(row["SEASON"]) == year and str(row["SEASON"]) == str(year), "A source row has another SEASON"
        row["_source_position"] = position
        row["_id"] = nba_id(row["PLAYER_ID"])
        row["_name"] = norm(row["PLAYER_NAME"])
        rows.append(row)
    return rows, dict(filename=path.name, sha256=sha(path), source_year=year, parameters=params,
                      all_row_seasons_verified=True, rows=len(rows),
                      source_url=f"https://stats.gleague.nba.com/stats/draftcombinestats?LeagueID=00&SeasonYear={expected_season}")


def match_row(identity, source, identities):
    current = nba_id(identity.nba_id)
    if current is not None:
        id_matches = [r for r in source if r["_id"] == current]
        # A future identity row must not alter an earlier cohort's join decision.
        eligible_identities = identities[identities.draft_year.le(identity.draft_year)]
        project_id_count = int(eligible_identities["_id"].eq(current).sum())
        if len(id_matches) == 1 and project_id_count == 1:
            return id_matches[0], "unique_nba_id"
        if len(id_matches) > 1 or project_id_count > 1:
            return None, "ambiguous_nba_id"
    key = norm(identity.player_name)
    same_cohort = identities[identities.draft_year.eq(identity.draft_year)]
    name_matches = [r for r in source if r["_name"] == key]
    if len(name_matches) != 1 or int(same_cohort["_name"].eq(key).sum()) != 1:
        return None, "no_unique_same_cohort_name"
    found = name_matches[0]
    if current is not None and found["_id"] is not None and current != found["_id"]:
        return None, "conflicting_nba_ids"
    return found, "unique_exact_same_cohort_name"


def build(args):
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    identities = pd.read_csv(args.identity, usecols=["pid", "draft_year", "player_name", "nba_id"])
    assert identities.pid.is_unique and identities.draft_year.between(2000, 2026).all()
    identities["_id"] = identities.nba_id.map(nba_id)
    identities["_name"] = identities.player_name.map(norm)
    sources, source_audit, rejected = {}, [], []
    for year in range(2000, 2027):
        path = args.raw / f"combine_{year}.json"
        if not path.exists() or (args.source_cutoff is not None and year > args.source_cutoff):
            continue
        try:
            rows, provenance = read_source(path, year)
        except Exception as error:
            rejected.append(dict(filename=path.name, sha256=sha(path), reason=f"{type(error).__name__}: {error}"))
            continue
        sources[year] = rows
        source_audit.append(provenance)
    audits, provenance, output_files = [], [], []
    for cohort in ["train"] + list(range(2019, 2027)):
        filename = "train_inputs.csv" if cohort == "train" else f"{cohort}_inputs.csv"
        path = args.pools / filename
        pool = pd.read_csv(path, usecols=["pid", "draft_year"])
        assert pool.pid.is_unique
        assert pool.draft_year.between(2000, 2018).all() if cohort == "train" else pool.draft_year.eq(cohort).all()
        joined = pool.merge(identities, how="left", on=["pid", "draft_year"], validate="one_to_one")
        assert len(joined) == len(pool) and joined.pid.tolist() == pool.pid.tolist()
        result, status = [], Counter()
        for identity in joined.itertuples():
            year = int(identity.draft_year)
            source = sources.get(year)
            values = {"pid": identity.pid, "draft_year": year, **{c: np.nan for c in FEATURES}}
            if source is None:
                status["no_verified_same_year_cache"] += 1
            elif pd.isna(identity.player_name):
                status["missing_identity"] += 1
            else:
                row, method = match_row(identity, source, identities)
                status[method] += 1
                if row is not None:
                    assert int(row["SEASON"]) == year
                    values.update(transform(row))
                    provenance.append(dict(pid=identity.pid, draft_year=year, source_year=year,
                                           source_filename=f"combine_{year}.json", source_row=row["_source_position"], match_method=method))
            result.append(values)
        frame = pd.DataFrame(result, columns=["pid", "draft_year"] + FEATURES)
        assert frame.pid.tolist() == pool.pid.tolist()
        assert not np.isinf(frame[FEATURES].to_numpy(dtype=float)).any()
        destination = output / ("train_inputs.csv" if cohort == "train" else f"{cohort}_inputs.csv")
        frame.to_csv(destination, index=False)
        output_files.append(destination)
        audits.append(dict(cohort=cohort, rows=len(frame), matched_players=int(frame[FEATURES].notna().any(axis=1).sum()),
                           identity_match_counts=dict(status), column_coverage=frame[FEATURES].notna().sum().to_dict(),
                           source_pool_filename=path.name, source_pool_sha256=sha(path), output_sha256=sha(destination)))
    pd.DataFrame(provenance).to_csv(output / "row_provenance.csv", index=False)
    (output / "feature_dictionary.json").write_text(json.dumps(feature_dictionary(), indent=2))
    manifest = dict(protocol="vcmb_official_same_cohort_cache_v1", features=FEATURES, feature_count=len(FEATURES),
                    source_files=source_audit, rejected_source_files=rejected, datasets=audits,
                    identity_sha256=sha(args.identity), builder_sha256=sha(Path(__file__)), source_cutoff=args.source_cutoff,
                    output_files={p.name: sha(p) for p in output_files},
                    policy={"source_year": "Strict equality to draft cohort (stronger than <= draft-year cutoff)",
                            "join": "Unique NBA ID preferred; exact unique normalized same-cohort name only without conflicting NBA IDs",
                            "imputation": "None; missing source fields and unmatched players remain NaN",
                            "BMI": "Actual combine weight and height without shoes from the same row; no alternate-height or NBA-bio fallback",
                            "drills": "Each aggregate requires every expected source station; zero attempts are not 0% shooting",
                            "source_absent_2026": "All features NaN unless a verified same-year cache is supplied",
                            "forbidden": "No age, current NBA bio, biomedical/research fills, legacy collector import, network or WAR"})
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"feature_count": len(FEATURES), "verified_cache_files": len(source_audit), "rejected_cache_files": len(rejected),
                      "datasets": [{k: a[k] for k in ["cohort", "rows", "matched_players", "identity_match_counts"]} for a in audits]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ["raw", "identity", "pools", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-cutoff", type=int)
    build(parser.parse_args())

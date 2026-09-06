"""Prepare calendar-correct expanding bundles outside every model namespace.

This program is an authority-separated data broker, not a model or scorer. It
opens only earlier-cohort answer files that have verified eligible source dates.
The model must receive ONE output-year directory, never this broker's inputs or
the directory containing all output years. No fitting or test scoring occurs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE_URL = "https://raw.githubusercontent.com/fivethirtyeight/data/master/nba-raptor/historical_RAPTOR_by_player.csv"
TARGETS = [f"y_s{i}_war" for i in range(1, 6)]
FORBIDDEN = {"actual_pick", "actual_round", "player_name", "nba_id", "was_drafted", "pid", "draft_year"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm(value):
    return re.sub("[^a-z0-9]", "", unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower())


def eligible_calendar(source, identities, year):
    """Assign ordinal using *recorded* NBA seasons, then enforce the cutoff.

    Filtering source years first also ensures later source identity/name changes
    cannot affect an earlier-year match. Historical RAPTOR starts in 1977, before
    the first NBA season of every player in this project's 2000+ cohort universe.
    """
    cutoff = year - 1
    source = source[source.season <= cutoff].copy()
    source["name_key"] = source.player_name.map(norm)
    identities = identities[identities.draft_year < year].copy()
    identities["name_key"] = identities.player_name.map(norm)
    # Duplicate project identities are not merged or resolved from outcomes.
    unique_project = ~identities.name_key.duplicated(keep=False)
    groups = {k: g.sort_values("season") for k, g in source.groupby("name_key")}
    rows, reasons = [], {}
    for row in identities[unique_project].itertuples():
        seasons = groups.get(row.name_key)
        if seasons is None:
            reasons["no_recorded_source_identity_by_cutoff"] = reasons.get("no_recorded_source_identity_by_cutoff", 0) + 1
            continue
        if seasons.player_id.nunique() != 1 or seasons.season.duplicated().any():
            reasons["ambiguous_source_identity_or_season"] = reasons.get("ambiguous_source_identity_or_season", 0) + 1
            continue
        seasons = seasons[seasons.season > row.draft_year]
        if not len(seasons):
            reasons["no_nba_season_after_draft_by_cutoff"] = reasons.get("no_nba_season_after_draft_by_cutoff", 0) + 1
        for ordinal, season in enumerate(seasons.head(5).itertuples(), 1):
            rows.append(dict(pid=row.pid, draft_year=int(row.draft_year), ordinal=ordinal,
                             season_end=int(season.season), reference_war=float(season.war_total)))
    reasons["ambiguous_project_name"] = int((~unique_project).sum())
    result = pd.DataFrame(rows, columns=["pid", "draft_year", "ordinal", "season_end", "reference_war"])
    assert result.empty or (result.season_end.le(cutoff).all() and result.draft_year.lt(year).all())
    return result, reasons


def verify_eligible_labels(calendar, source_rows):
    """Compare only labels with a source-recorded season on/before the cutoff.

    An eligible mismatch excludes that player's labels. Future ordinal values
    are never inspected, compared, zero-filled, or used to choose an identity.
    """
    by_pid = source_rows.set_index("pid")
    accepted, mismatch, missing = [], set(), set()
    for r in calendar.itertuples():
        if r.pid not in by_pid.index:
            missing.add(r.pid)
            continue
        value = pd.to_numeric(by_pid.at[r.pid, f"y_s{r.ordinal}_war"], errors="coerce")
        if not np.isfinite(value) or not np.isclose(value, r.reference_war, rtol=0, atol=1e-5):
            mismatch.add(r.pid)
            continue
        accepted.append(dict(pid=r.pid, draft_year=r.draft_year, ordinal=r.ordinal,
                             season_end=r.season_end, war=float(value)))
    result = pd.DataFrame(accepted, columns=["pid", "draft_year", "ordinal", "season_end", "war"])
    result = result[~result.pid.isin(mismatch)]
    return result, {"eligible_label_mismatch_players": len(mismatch), "missing_project_label_players": len(missing)}


def build(args):
    year, cutoff = args.year, args.year - 1
    assert 2019 <= year <= 2026
    source = pd.read_csv(args.source, usecols=["player_name", "player_id", "season", "war_total"])
    assert source.season.min() <= 1977
    source_max = int(source.season.max())
    if cutoff > source_max and not args.allow_partial_calendar:
        raise ValueError(f"Calendar ends in {source_max}; cutoff {cutoff} requires --allow-partial-calendar or a verified newer source")
    identities = pd.read_csv(args.identity, usecols=["pid", "draft_year", "player_name"])
    assert identities.pid.is_unique
    calendar, reasons = eligible_calendar(source, identities, year)
    config = json.loads(Path(args.feature_manifest).read_text())
    features = list(config["legacy_features"])
    assert len(features) == len(set(features))
    assert not any(c in FORBIDDEN or c.startswith("y_") for c in features)
    root, vault = Path(args.project), Path(args.vault)
    old_path = root / "data/train_2000_2018.csv"
    # Old training table contains later labels, but only eligible label cells are
    # accessed by verify_eligible_labels. The raw table never leaves the broker.
    old = pd.read_csv(old_path)
    assert old.pid.is_unique and old.draft_year.between(2000, 2018).all()
    all_features = [old[["pid", "draft_year"] + features]]
    all_labels = [old[["pid"] + TARGETS]]
    opened = [{"kind": "old_training_snapshot", "sha256": sha(old_path)}]
    eligible_years = sorted(int(x) for x in calendar.draft_year.unique() if x >= 2019)
    assert all(y < year for y in eligible_years)
    for cohort in eligible_years:
        # No held-out Y/future answer file is opened even for a schema/hash check.
        answer_path = vault / f"answers_{cohort}.csv"
        feature_path = root / f"data/tests/test_{cohort}_inputs.csv"
        label_rows = pd.read_csv(answer_path, usecols=["pid", "draft_year"] + TARGETS)
        input_rows = pd.read_csv(feature_path)
        assert label_rows.pid.is_unique and label_rows.draft_year.eq(cohort).all()
        assert input_rows.pid.is_unique
        if "draft_year" in input_rows:
            assert input_rows.draft_year.eq(cohort).all()
        input_rows["draft_year"] = cohort
        all_features.append(input_rows.reindex(columns=["pid", "draft_year"] + features))
        all_labels.append(label_rows[["pid"] + TARGETS])
        opened.append({"cohort": cohort, "kind": "earlier_cohort_only", "answers_sha256": sha(answer_path), "inputs_sha256": sha(feature_path)})
    project_labels = pd.concat(all_labels, ignore_index=True)
    assert project_labels.pid.is_unique
    labels, verification = verify_eligible_labels(calendar, project_labels)
    training = pd.concat(all_features, ignore_index=True)
    training = training[training.pid.isin(labels.pid)].copy()
    assert training.pid.is_unique
    assert training.draft_year.lt(year).all()
    assert labels.season_end.le(cutoff).all()
    declared_years = identities.set_index("pid").draft_year
    assert training.pid.map(declared_years).eq(training.draft_year).all()
    inference_path = root / f"data/tests/test_{year}_inputs.csv"
    raw_inference = pd.read_csv(inference_path)
    if "draft_year" in raw_inference:
        assert raw_inference.draft_year.eq(year).all()
    inference = raw_inference.reindex(columns=["pid"] + features).copy()
    inference["draft_year"] = year
    assert inference.pid.is_unique and not set(inference.pid).intersection(training.pid)
    # Keep every provided test input row. Benchmark cohort selection belongs to
    # the scoring authority after a prediction freeze, not to this broker.
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    training.to_csv(out / "training_inputs.csv", index=False)
    labels.to_csv(out / "training_labels.csv", index=False)
    inference.to_csv(out / "inference_inputs.csv", index=False)
    label_coverage = labels.groupby("draft_year").agg(players=("pid", "nunique"), labels=("ordinal", "size")).to_dict("index")
    result = dict(protocol="calendar_expanding_broker_prototype_v1", predicted_draft_year=year,
                  permitted_season_end=cutoff, calendar_source_max=source_max,
                  actual_label_max=int(labels.season_end.max()), partial_calendar=source_max < cutoff,
                  missing_calendar_seasons=list(range(source_max + 1, cutoff + 1)),
                  training_players=len(training), training_labels=len(labels), inference_rows=len(inference),
                  label_coverage_by_cohort=label_coverage, identity_exclusions=reasons, label_verification=verification,
                  source={"url": SOURCE_URL, "sha256": sha(args.source)}, identity_sha256=sha(args.identity),
                  eligible_answer_cohorts_opened=eligible_years, inputs=opened,
                  features=features, files={p.name: sha(p) for p in out.glob("*.csv")},
                  outcome_definition="Unchanged existing reconstructed WAR; matched within 1e-5 to source-recorded eligible seasons",
                  limitations=["Calendar coverage beyond source_max is incomplete; no guessed dates or future values fill omissions",
                               "Only unique normalized exact identities with matching eligible WAR are used for training",
                               "Players with no verified NBA season by cutoff are excluded, not assigned future-informed zero targets",
                               "Inherited predictor provenance remains uncertified; this broker certifies only label timing",
                               "Mount only this single-year bundle in a fresh worker; never mount the broker or all-year output root",
                               "This is data preparation only; no model was fit and no test score was read"])
    (out / "manifest.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ["predicted_draft_year", "training_players", "training_labels", "inference_rows", "actual_label_max", "partial_calendar", "missing_calendar_seasons", "eligible_answer_cohorts_opened", "label_verification"]}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for option in ["source", "identity", "feature-manifest", "project", "vault", "output"]:
        p.add_argument("--" + option, type=Path, required=True)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--allow-partial-calendar", action="store_true")
    build(p.parse_args())

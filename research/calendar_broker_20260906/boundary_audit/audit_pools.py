"""Audit only identity pools and drafted-status missingness, never WAR/scores."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd


def pool_hash(values):
    return hashlib.sha256(json.dumps(sorted(map(str, values)), separators=(",", ":")).encode()).hexdigest()


def main(args):
    results = []
    for year in range(2019, 2027):
        original = pd.read_csv(args.project / f"data/tests/test_{year}_inputs.csv", usecols=["pid", "draft_year", "was_drafted"])
        bundle = pd.read_csv(args.bundles / str(year) / "inference_inputs.csv", usecols=["pid", "draft_year"])
        # actual_pick is used only to identify the scorer's fixed complete pool;
        # its numeric values are never returned, sorted, or used by a model.
        answers = pd.read_csv(args.project / f"vault/answers_{year}.csv", usecols=["pid", "actual_pick"])
        assert original.pid.is_unique and bundle.pid.is_unique and answers.pid.is_unique
        assert original.draft_year.eq(year).all() and bundle.draft_year.eq(year).all()
        assert original.pid.tolist() == bundle.pid.tolist(), f"Original inference order/pool changed for {year}"
        benchmark = answers.loc[answers.actual_pick.notna(), "pid"]
        declared = original.loc[pd.to_numeric(original.was_drafted, errors="raise").eq(1), "pid"]
        assert set(benchmark) == set(declared), f"Input drafted status and scorer benchmark differ for {year}"
        assert set(benchmark) <= set(bundle.pid)
        results.append(dict(year=year, original_input_rows=len(original), bundle_rows=len(bundle),
                            benchmark_rows=len(benchmark), extra_original_prospects=len(bundle)-len(benchmark),
                            full_original_pool_preserved=True, complete_benchmark_covered=True,
                            original_pid_set_sha256=pool_hash(original.pid), benchmark_pid_set_sha256=pool_hash(benchmark),
                            scoreboard_eligible=year <= 2025))
    result = dict(status="passed", no_WAR_columns_read=True, no_prediction_scores_read=True, no_model_fits=True,
                  years=results, benchmark_rows_2019_2025=sum(x["benchmark_rows"] for x in results if x["year"] <= 2025))
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--bundles", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    main(p.parse_args())

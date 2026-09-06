"""Suggested scorer-side identity contract. Contains no metric or vault loader."""
import pandas as pd


def align_original_benchmark(original_inputs, answers, predictions, year):
    """Allow extra *original* inference prospects without narrowing the benchmark.

    Pass frames already read by the independent scorer after prediction freeze.
    Its answer frame may include targets, but this helper only uses actual_pick
    missingness to select the original drafted population.
    """
    assert original_inputs.pid.is_unique and answers.pid.is_unique and predictions.pid.is_unique
    assert original_inputs.pid.notna().all() and answers.pid.notna().all() and predictions.pid.notna().all()
    assert predictions.season.eq(year).all()
    assert set(predictions.pid) == set(original_inputs.pid), "Missing or unexpected original inference prospect"
    benchmark = answers.loc[answers.actual_pick.notna()].copy()
    assert len(benchmark) and set(benchmark.pid) <= set(predictions.pid), "Incomplete original drafted benchmark"
    joined = benchmark.merge(predictions[["pid", "score"]], on="pid", how="left", validate="one_to_one")
    assert len(joined) == len(benchmark) and joined.score.notna().all()
    return joined


def self_test():
    # Synthetic fixtures exercise identity coverage; they are never model data.
    original = pd.DataFrame({"pid": ["a", "b", "extra"]})
    answers = pd.DataFrame({"pid": ["a", "b", "extra"], "actual_pick": [1, 2, None]})
    predictions = pd.DataFrame({"pid": ["extra", "b", "a"], "season": [2020]*3, "score": [.1, .2, .3]})
    joined = align_original_benchmark(original, answers, predictions, 2020)
    assert joined.pid.tolist() == ["a", "b"]
    for bad in [predictions[predictions.pid != "a"], predictions[predictions.pid != "extra"],
                pd.concat([predictions, predictions.iloc[[0]]]), predictions.assign(season=2021)]:
        try:
            align_original_benchmark(original, answers, bad, 2020)
        except AssertionError:
            pass
        else:
            raise AssertionError("Invalid prediction pool accepted")
    print("PASS: extra original prospects accepted; missing benchmark, missing input, duplicate and wrong-year rows rejected")


if __name__ == "__main__":
    self_test()

"""Boundary and missing-data checks for official combine reconstruction."""
import argparse
import json
import math
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from build import DRILLS, match_row, norm, numeric, read_source, transform


def main(args):
    sample = args.raw / "combine_2010.json"
    value = json.loads(sample.read_text())
    rows, _ = read_source(sample, 2010)
    assert rows
    with tempfile.TemporaryDirectory(prefix="combine_check_", dir=Path(__file__).resolve().parent) as temp:
        path = Path(temp) / "combine_2010.json"
        wrong_parameter = json.loads(json.dumps(value))
        wrong_parameter["parameters"]["SeasonYear"] = "2025-26"
        wrong_row = json.loads(json.dumps(value))
        result = next(x for x in wrong_row["resultSets"] if x["name"] == "DraftCombineStats")
        result["rowSet"][0][result["headers"].index("SEASON")] = 2025
        for bad in [wrong_parameter, wrong_row]:
            path.write_text(json.dumps(bad))
            try:
                read_source(path, 2010)
            except AssertionError:
                pass
            else:
                raise AssertionError("Wrong source year was accepted")
    out = transform({"WEIGHT": "200", "HEIGHT_WO_SHOES": None, "HEIGHT_W_SHOES": 80, "WINGSPAN": 84})
    assert math.isnan(out["vcmb_bmi_kg_m2"])
    assert math.isnan(out["vcmb_wingspan_minus_height_in"])
    assert out["vcmb_height_with_shoes_in"] == 80
    zero_shots = {field: "0-0" for field in DRILLS["spot_15ft"]}
    zero = transform(zero_shots)
    assert zero["vcmb_spot_15ft_attempted"] == 0
    assert math.isnan(zero["vcmb_spot_15ft_pct"])
    missing_station = {field: "2-5" for field in DRILLS["spot_15ft"]}
    missing_station[DRILLS["spot_15ft"][0]] = None
    assert math.isnan(transform(missing_station)["vcmb_spot_15ft_made"])
    identity = SimpleNamespace(nba_id=100, player_name="Example Player", draft_year=2010)
    known = pd.DataFrame([{"pid": "old", "nba_id": 100, "draft_year": 2010, "player_name": "Example Player"},
                          {"pid": "future", "nba_id": 100, "draft_year": 2026, "player_name": "Future Identity"}])
    known["_id"] = known.nba_id
    known["_name"] = known.player_name.map(norm)
    source = [{"_id": 100, "_name": norm("Example Player")}]
    assert match_row(identity, source, known)[1] == "unique_nba_id"
    assert match_row(identity, source, known.iloc[:1])[1] == "unique_nba_id"
    conflict = [{"_id": 101, "_name": norm("Example Player")}]
    assert match_row(identity, conflict, known)[1] == "conflicting_nba_ids"
    assert math.isnan(numeric(None)) and math.isnan(numeric(float("inf")))
    print("PASS: request and row year mismatch rejection; missing-height BMI; missing drill station; zero attempts; future identity invariance; conflicting-ID rejection")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, required=True)
    main(p.parse_args())

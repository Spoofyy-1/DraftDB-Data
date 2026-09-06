"""Offline parser checks using cached source responses; no network requests."""
import copy
import json
from pathlib import Path
from collect_calendar import parse_participation


def main():
    root = Path(__file__).resolve().parent
    raw = json.loads((root / "private/espn_athlete_stats_1966.json").read_text())
    regular, status = parse_participation(raw, 2)
    assert {2023, 2024, 2025} <= regular
    assert status == "explicit_played_season_rows"
    # Unrelated scoring stats must not affect the extracted calendar.
    changed = copy.deepcopy(raw)
    category = next(x for x in changed["categories"] if "gamesPlayed" in x["names"])
    point_index = category["names"].index("avgPoints")
    for row in category["statistics"]:
        row["stats"][point_index] = "9999999"
    assert parse_participation(changed, 2) == (regular, status)
    postseason = json.loads((root / "private/espn_athlete_stats_1966_postseason.json").read_text())
    post, status = parse_participation(postseason, 3)
    assert status == "explicit_played_season_rows"
    assert {2023, 2024, 2025} <= post
    # A source response that ignores a supported requested season type is an
    # error, rather than fabricated playoff participation.
    try:
        parse_participation(raw, 3)
        raise RuntimeError("ignored season type was accepted")
    except AssertionError:
        pass
    # Explicit absence of a postseason table is distinguished from a table of
    # postseason appearances. No regular-season rows leak through that fallback.
    absent = copy.deepcopy(raw)
    next(x for x in absent["filters"] if x["name"] == "seasontype")["options"] = [{"value": "2"}]
    assert parse_participation(absent, 3) == (set(), "source_has_no_postseason_table")
    print("PASS: explicit season years, games-played extraction, RS/PO separation, ignored-filter rejection, missing-PO fallback, unrelated-stat invariance")


if __name__ == "__main__":
    main()

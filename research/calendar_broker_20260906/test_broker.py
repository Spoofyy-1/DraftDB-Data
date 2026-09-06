"""Adversarial boundary checks; synthetic fixtures never enter model datasets."""
import pandas as pd
from pandas.testing import assert_frame_equal
from broker import eligible_calendar, verify_eligible_labels


def main():
    ids = pd.DataFrame([dict(pid="old", draft_year=2017, player_name="Delayed Debut"),
                        dict(pid="heldout", draft_year=2020, player_name="Held Out")])
    source = pd.DataFrame([
        dict(player_name="Delayed Debut", player_id="old01", season=2019, war_total=1.25),
        dict(player_name="Delayed Debut", player_id="old01", season=2021, war_total=2.5),
        dict(player_name="Held Out", player_id="held01", season=2021, war_total=3.0),
    ])
    labels = pd.DataFrame([dict(pid="old", y_s1_war=1.25, y_s2_war=2.5)])
    calendar, _ = eligible_calendar(source, ids, 2020)
    assert calendar.season_end.tolist() == [2019]
    assert calendar.ordinal.tolist() == [1]
    result, _ = verify_eligible_labels(calendar, labels)
    assert result.war.tolist() == [1.25]
    # Change future source WAR, append a future-season name collision, and change
    # the future ordinal target. The earlier bundle must remain byte-equivalent.
    changed = source.copy()
    changed.loc[changed.season > 2019, "war_total"] = 9999999
    changed = pd.concat([changed, pd.DataFrame([dict(player_name="Delayed Debut", player_id="collision", season=2025, war_total=-100)])], ignore_index=True)
    later_labels = labels.copy()
    later_labels["y_s2_war"] = -9999999
    calendar2, _ = eligible_calendar(changed, ids, 2020)
    result2, _ = verify_eligible_labels(calendar2, later_labels)
    assert_frame_equal(calendar, calendar2)
    assert_frame_equal(result, result2)
    # A gap preserves the original NBA-season ordinal; it is not draft+ordinal.
    calendar3, _ = eligible_calendar(source, ids, 2022)
    old = calendar3[calendar3.pid == "old"]
    assert old.season_end.tolist() == [2019, 2021]
    assert old.ordinal.tolist() == [1, 2]
    # A mismatch in an eligible label rejects all labels of that player.
    corrupted = labels.copy()
    corrupted["y_s1_war"] = 8
    rejected, audit = verify_eligible_labels(calendar, corrupted)
    assert rejected.empty and audit["eligible_label_mismatch_players"] == 1
    print("PASS: cutoff, delayed debut, gap, future perturbation, current-cohort exclusion, eligible mismatch rejection")


if __name__ == "__main__":
    main()

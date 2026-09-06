# Historical Oliver reconstruction: dependency pilot

The current caches are **insufficient for clean player ORtg, DRtg or Stops reconstruction**. This task collected the missing bulk team/opponent game data for every season from 2008 through 2018, audited those inputs, and retained explicit missing dependencies. No current Torvik impact numbers were imported and no player impact features, outcomes, model runs or study joins were produced.

The source is the public `YEAR_season.json` endpoint documented by Bart Torvik. All eleven requests succeeded. The additional team endpoint reproduced 40 Kentucky 2012 raw game arrays exactly, providing a format cross-check; both endpoints share upstream data, so this is not independent official validation. Current team-results CSVs had adjusted ratings and conference summaries, not the required full box-score totals. [Author's data documentation](https://adamcwisports.blogspot.com/p/data.html).

The new files contain 63,038 source game rows. Conservative date, count, rebound, scoring and cross-team checks passed 62,480 and quarantined 558. Among them, 418 rows in the 2015 source have `1/0/00` dates. No date was guessed. Aggregation produced 5,741 team-season candidates, including non-Division-I opponents. Every candidate remains `model_eligible=False` and `publication_vintage_verified=False`; teams with rejected games also have explicitly incomplete cached totals. Schedule completeness and historical publication vintage remain unproved.

`team_season_totals_candidate.csv` holds numeric team/opponent totals with hashed team keys. `team_game_lineage.csv.gz` links every summed contribution to its source row/hash. `team_game_numeric_pilot.csv` contains the first 80 validated team-game rows for review, selected by source order. `coverage.json`, `quarantine.json` and `player_dependency_inventory.json` document coverage and failures. Raw responses and the team-name crosswalk remain private.

## Dependencies and why player features remain missing

The original Oliver methods are dated to his 2004 book. They use player/team/opponent box scores and fixed historical constants, not a later NBA-fitted BPM model. ORtg needs exact player turnovers and assists, rebounds, shooting totals, points and minutes; DRtg/Stops additionally need exact fouls, steals, blocks, defensive rebounds, team/opponent totals and a pinned possession definition. [Oliver methods](https://www.basketball-reference.com/about/ratings.html).

The player cache exposes exact shooting counts, but several other statistics are rounded averages or ratios. Multiplying those averages by the listed GP does not consistently reproduce the cache's shooting-derived point total: 10,662 rows fail the rounding-interval check across the eleven seasons. This is evidence of incompatible denominators, inclusion rules or source revisions, not proof of which mechanism caused it. No alternate denominator was inferred. Direct exact player turnover, foul and minute totals are missing from the selected schema. Inverting rounded foul or assist/turnover rates would add assumptions and is not approved.

The new team arrays use two 15-field basic-stat blocks, tested against scoring/rebound identities. Their inferred field map and minute convention still require an independent official box-score check before promotion. The source's existing possession/efficiency estimates are excluded. An Oliver possession formula and its free-throw convention must be separately pinned; no modern or unexplained coefficient should be substituted.

## Precise next collection step

Obtain official NCAA or school cumulative season tables that contain exact player MP, AST, TOV, PF, ORB, DRB, STL and BLK, together with shooting totals and the same game's inclusion scope. Start with a single 2012 team and reconcile its team/opponent totals against the new game arrays. Preserve team rebounds, team turnovers, overtime minutes, missed games and non-Division-I inclusions explicitly. Then extend only after identities, dates, completeness and algebra reconcile.

The UK Athletics April 3, 2012 report supplied a dated route to its final box score, but that legacy box-score link returned 404. Its current archives page did not expose a 2012 cumulative table. An ESPN game-summary fallback returned 403; no blocked endpoint was retried. These routes are recorded as limits, not usable data. [Dated UK report](https://ukathletics.com/news/2012/04/03/55aecf41e4b05936b8469e3b-131467965260307999/).

`collect.py` is resumable and restricted to the registered historical URLs. The bounded task consumed 20 operations: 13 data attempts and seven method/discovery operations, including one invalid tool-link call conservatively counted. The collector stops on 403/429, response-size or disk guards and has no remaining request allowance for this pilot. No 2019+ data endpoint was requested.

Run `python3 work/college_oliver_reconstruction/audit.py` and `python3 work/college_oliver_reconstruction/tests.py` to reproduce the dependency audit. Tests cover algebra, corrupted counts, dates, overtime, side reversal, aggregation lineage and explicit non-admission. They do not validate an Oliver rating implementation, because none was created. Only files listed in `PUBLIC_ALLOWLIST.json` may be copied publicly.

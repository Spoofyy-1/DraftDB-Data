# College player denominator audit — fixed 2018 pilot

The raw annual player table mixes statistical universes in this sample. Its games and shooting totals match a 31-game team schedule subset, while independently checked appended averages use the full 33-game schedule and each player's own appearances. This is a denominator/definition issue; it does **not** establish future-data leakage or explain all 10,662 previously counted discrepant rows.

The sample was registered before official numeric comparisons: all 12 discrepant Tennessee Tech players in the 2018 annual source, including six players at or below 15 minutes per game. No NBA participation, actual draft position, career outcome or model score selected the sample. Original annual files and all frozen packages remain unchanged.

## What is established

- All 12 annual GP values equal the count of each player's direct source game records. GP is a player-appearance count, not a team's game count.
- All 72 annual shooting count comparisons match exactly: two-point makes/attempts, three-point makes/attempts, and free-throw makes/attempts. Those numerators refer to the same season and subset as annual GP.
- The player-game file contains 31 distinct Tennessee Tech dates; the cached team file has 33. The missing games are November 10, 2017 against Midway and November 16, 2017 against Boyce. This is consistent with the author's general Division-I-only game-count convention, but a universal cross-year player-column definition has not been established.
- Of 72 appended ORB/DRB/AST/STL/BLK/PTS per-game checks, 67 disagree with direct counts divided by annual GP. The five matches do not demonstrate the same universe; zero-valued statistics can coincide across different schedules.
- Ten available official OVC comparisons across three sampled players match the full-schedule averages to the annual table's four-decimal rounding. For example, Kajon Mack has 32 official games and 407 points: 407/32=12.71875, matching appended PPG12.7188. The direct source subset has 30 appearances and391 points:391/30=13.03333, matching annual shooting counts but not appended PPG.
- The official OVC table and cached all-game team totals match on12/14 inspected counts. AST is472 versus471 official, and BLK107 versus108 official. Their cause is unresolved; corrections or revised statistics are possible, but not proven. No inferred replacement is made.

Official evidence comes from the [Ohio Valley Conference's historical statistics](https://ovcsports.com/stats.aspx?path=mbball&year=2017). The web tool retrieved the table; direct HTTP returned403. `official_evidence.json` records only the factual numeric projection and retrieval limits, with no invented HTML hash. Incidental secondary search results were not used as primary proof or candidate inputs.

## Candidate output and limits

`same_subset_basics_candidate.csv` retains all12 sampled subjects with14 numeric fields. Each field is a sum of direct player-game events divided by that player's number of included games: two-point makes/attempts, three-point makes/attempts, free-throw makes/attempts, points, offensive and defensive rebounds, assists, turnovers, steals, blocks and personal fouls. The `cgd_` names distinguish these candidates from the original mixed-source columns. `same_subset_totals.csv` contains exact event totals and player appearance denominators; `game_lineage.csv` identifies every contributing source row and both response hashes. Learner columns exclude identities; the source-name/ID crosswalk stays private.

All candidates remain **model_eligible=False**. This pilot proves arithmetic and subset alignment, not archived publication vintage, complete schedules in other years, or the correctness of every credited event. The original raw source's broader generalization remains unverified. Exact player minutes are not established: the game schema exposes a rounded `Min_per` field, which is excluded. No per-minute rate, reconstructed Oliver rating, existing impact value, NBA label, actual NBA pick, train/test join or model run was created here.

## Sources and next bounded collection

The [author's data documentation](https://adamcwisports.blogspot.com/p/data.html) discusses `YEAR_all_advgames.json` on August6,2021 and the `.gz` suffix on November30,2022. This task verified only [2018_all_advgames.json.gz](https://barttorvik.com/2018_all_advgames.json.gz):109,978 records,53 fields,10,407,565 compressed bytes; SHA256 `f61dcd425f3141019d253f4552a96aa68b040782386f7dba1b36716492c271bd`. Earlier years are suggested by the documented YEAR template but accessibility, schema and coverage have not been tested. Raw payloads remain private.

A separately authorized follow-up can collect one file per2008–2018 season, verify the year-specific header and historical dates, project only the basic count/identity allowlist, and match games to the existing team cache. Before joining predictors, it should audit missing games, player participation/zero-minute semantics, duplicate identities, count disagreements and source revisions across fixed teams and low-minute players. Direct TOV/PF is promising; exact MP and complete schedule proof remain separate dependencies. Scope changes must not silently widen this finished sample or treat every year as identical.

The task used all10 allowed network operations, including two blocked direct official fetches and one size-cap rejection followed by a compressed-transfer retry. No further requests were made. `network_ledger.json` is explicit about successful, blocked and rejected operations.

Run `python3 tests.py` for the eight checks: independent scoring arithmetic; negative/nonfinite/fractional counts; date/schema boundaries; ignored rating fields; fixed-sample totals including a genuine zero-scoring reserve; missing/duplicate-game rejection; source/sample hash tampering; and integration with official denominator evidence. `PUBLIC_ALLOWLIST.json` enumerates only public code, numeric facts, provenance and summaries. It excludes full source bodies and private crosswalks.

# Historical college player games: consistent basic-stat candidates

This package collects the documented historical player-game source for2008–2018 and creates15 candidate columns: observed player appearances plus14 direct-event averages using that same appearance denominator. It preserves the original datasets and does not join NBA identities, model populations, draft positions, outcomes or scores.

Ten new requests successfully obtained2008–2017;2018 reuses the frozen denominator-audit response. All11 files contain the same53-field array width. New compressed transfer bytes total101,080,074; each file is below25MiB compressed and150MiB decoded. The collector used exactly10 new requests, with no retries or later-year sources, under a30-minute deadline and1GiB free-space floor.

## Coverage and quarantine

| Source season | Game rows | Consistent player/team/seasons | Quarantined groups |
|---|---:|---:|---:|
|2008|106,122|4,573|18|
|2009|106,922|4,581|11|
|2010|109,511|4,670|28|
|2011|108,186|4,521|32|
|2012|108,263|4,573|18|
|2013|109,005|4,581|36|
|2014|111,386|4,705|30|
|2015|110,905|4,702|33|
|2016|111,455|4,639|85|
|2017|111,928|4,721|42|
|2018|109,978|4,674|54|

Across1,203,661 source game rows,1,203,590 pass basic parsing and arithmetic. The71 rejected rows comprise46 personal-foul bound failures,16 noninteger/nonfinite count failures and9 made/attempt bound failures. Their original row indices, response hashes and reasons are retained. No values are guessed or repaired.

50,940 of51,327 source player/team/seasons (99.246%) pass the consistency gate. Every passing group has exactly one same-year annual source record, matching source id/team and exact trimmed name, with an exact match on GP and all six shooting totals. The387 quarantined groups retain missing candidate values. The union includes124 game-source groups absent from the annual table; those remain quarantined instead of being dropped or treated as known zeros. Same-day identity ambiguity also quarantines entire groups. This percentage describes source consistency, **not prediction accuracy**.

## What the candidate columns mean

`cgd_observed_gp` counts that player's included source game records. The other14 columns are the totals of two-point makes/attempts, three-point makes/attempts, free-throw makes/attempts, points, offensive and defensive rebounds, assists, turnovers, steals, blocks and personal fouls divided by that exact observedGP. Direct turnovers and personal fouls are now available without estimating them from rounded ratios. No fitted formula or impact rating is used.

All statistics in a group use the same source game subset. This avoids mixing annual shooting totals with appended per-game averages that use a different schedule, as demonstrated by the frozen2018 pilot. We do not claim that every year's subset contains all games or follows one universally proven Division-I-only convention.

The source includes48,293 all-zero basic stat records. They are retained as observations when the source appearance count matches annualGP; a zero stat line is not assumed to mean DNP. Missing games, zero minutes and participation flags cannot be distinguished from the approved basic fields alone. Exact player minutes are not established, so no per-minute rates or Oliver ratings are created. No source-player thresholds select only future NBA participants.

**All features remain model_eligible=False pending review.** `source_consistent=True` proves the defined arithmetic/identity checks, not model admission, original publication vintage, complete schedules, or independent correctness of every credited rebound/assist/turnover/foul. The frozen primary OVC comparison also found small AST/BLK differences in one team's historical source totals. Those source-revision/data discrepancies remain unresolved. Reconstructed basic events do not import the excluded later NBA-calibrated impact coefficients, but their original source vintage still needs its own review.

## Files and provenance

- `source_manifest.json`: frozen response and annual-file hashes, URL, size, retrieval timestamp and exact input-column allowlist. Only the2018 body is referenced from the prior frozen package; all ten new response bodies are private here.
- `schema_manifest.json`: field mapping, units, boundaries, missingness semantics and admission limits. Annual index45 is excluded, as are all advanced ratings, possession estimates, heights/classes, player minutes and2019+ sources.
- `data/games_YEAR.csv.gz`: every valid parsed game, with14 direct counts, date, anonymized subject/team/opponent/game ids and original row/hash lineage. This preserves parsed rows from quarantined groups too; the group audit gate must be applied before using them.
- `data/candidates_YEAR.csv`: full union of annual and game-source groups, including missing candidate rows for quarantine. There are three nonpredictor identity/season keys and15 numeric candidates.
- `data/audit_YEAR.json.gz`: group gate, exact GP and shooting comparisons, all14 direct totals, date bounds, zero-record counts, and both source hashes.
- `data/quarantine_games_YEAR.json.gz` and `data/invalid_annual_rows_YEAR.json.gz`: rejected row provenance. All annual rows parsed successfully in this run.
- `private/crosswalk_YEAR.json.gz`: names and original source ids, excluded from the public allowlist. Full source responses are also private.

The source endpoint is `https://barttorvik.com/YEAR_all_advgames.json.gz`, documented through the [author's data page](https://adamcwisports.blogspot.com/p/data.html). The frozen denominator audit records the author discussion of the player-game endpoint (August6,2021), gzip suffix (November30,2022), and53-field header. Current retrieval succeeded for every2008–2018 file; this does not establish that the current file versions were published before2018. Hashes identify the exact retrieved versions, not invented historical snapshots.

`collect.py` has a fixed ten-year descending queue, hard byte/disk/time limits, and stops after three consecutive403/404 responses. `build.py` performs no network requests and rejects out-of-scope years/paths before opening them. The11 tests in `tests.py` cover arithmetic, ignored columns, boundaries, bad counts, duplicate/ambiguous games, annual comparison gates, observed zeros versus missing data, source/path tampering, a full1.2-million-game reaggregation, and exact reproduction of the frozen12-player pilot.

A final rerun checks that all55 generated numeric/audit files are byte-identical after the parser hardening. Public delivery uses the explicit `PUBLIC_ALLOWLIST.json`; full responses and private crosswalks are excluded. No model was trained or scored, and no original or frozen study input was changed.

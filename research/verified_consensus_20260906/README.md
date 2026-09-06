# Verified pre-draft mock-rank pilot

This package reconstructs a small consensus-rank family from 16 historically archived mock drafts spanning 2007–2014. It contains 715 verified publisher/player rank observations covering 402 exact player identities; 313 players appear in two publishers' lists. No models were launched, target files opened, or actual draft-pick values used.

`features_eligible.csv` contains four candidate numerical fields:

- `vcons_mock_mean_rank`: mean rank over observed publishers.
- `vcons_mock_best_rank`: smallest observed numerical rank.
- `vcons_mock_rank_range`: largest minus smallest observed rank, missing with fewer than two publishers.
- `vcons_mock_n_sources`: distinct verified publishers listing the player.

`publisher_ranks_eligible.csv` keeps three optional source-specific columns: `vcons_dx_rank`, `vcons_nbadraft_rank`, and `vcons_walter_rank`. All ranks are predictions from pre-draft mocks, not actual draft selections. There are no big-board fields or legacy `cons_` fills. Missing and unlisted players remain missing; absence is never converted into rank 61, rank 0, or an undrafted outcome.

## Evidence and identity rules

Every eligible page has an exact Wayback capture strictly before midnight America/New_York on its first draft day, an explicitly displayed mock update date before the draft, and a matching target-year mock heading. Original publication dates are unavailable and remain null. Displayed update times have no stated timezone, so their calendar dates are retained; the UTC archive capture provides the availability proof.

DraftExpress's older pages use two tables titled First Round and Second Round; second-round ordinal positions receive +30. The 2014 extended layout has one 60-position table. NBADraft.net has two explicit mock table IDs covering ranks 1–60. WalterFootball has a 30-item ordered mock list; its old HTML omits the closing OL, so extraction stops at the repeated Draft Links footer heading. Only ordinal positions and player-name headings/links are used. Team assignments, player statistics, biographies, trade notes, and article commentary are excluded.

Player joins use exact normalized names and exact draft cohorts. There are no nickname aliases, fuzzy joins or outcome-assisted resolutions. The parser leaves 185 original list entries unmatched, including identities absent from the roster and prospects projected into a different draft year. Those ranks are not reassigned or renumbered. Of the 402 eligible identities, 381 occur in the current model universe; the other 21 require omission when joining that fixed universe.

`rank_observations.csv` records source URLs, exact archive URLs, update dates, UTC captures, mock ranks, identity methods and evidence hashes. `validated_sources.json` documents table boundaries and source status. Full pages/tables stay under `private/` and must not be published. Use only `public_manifest.json`'s explicit allowlist.

## Coverage and archive freshness

| Draft year | Eligible players | Two publishers | In current model universe | Source mock update dates |
| --- | --- | --- | --- | --- |
| 2007 | 46 | 28 | 44 | DX June 22; Walter May 25 |
| 2008 | 43 | 29 | 40 | DX May 6; Walter May 31 |
| 2009 | 41 | 30 | 40 | DX February 26; NBADraft May 27 |
| 2010 | 53 | 48 | 49 | DX June 21; NBADraft June 15 |
| 2011 | 57 | 51 | 54 | DX June 22; NBADraft June 21 |
| 2012 | 55 | 45 | 53 | DX June 27; NBADraft June 26 |
| 2013 | 51 | 40 | 48 | DX June 19; NBADraft June 19 |
| 2014 | 56 | 42 | 53 | DX June 25; NBADraft June 20 |

For development folds 2012/2013/2014 using training cohorts through 2010/2011/2012, the fixed model universe contains respectively **173/227/280** training players with at least one rank, including **131/182/227** players with two publishers. Same-year model identity intersections are 53/48/53. These same-year counts include the whole model cohort; the experiment must apply its original validation membership without changing the score denominator. No draft-status or actual-pick columns were needed for this coverage report.

These are available verified snapshots, not guaranteed final mocks. The older 2008–2009 DraftExpress vintages are a material limitation, and Walter lists only 30 positions while the other publishers list 60. Publishers can also influence one another; source count is not a count of statistically independent opinions. Rank-range missingness and source coverage need matched controls in the planned separate experiment.

## What worked, limits, and continuation

The earlier mock collector queried today's `nbadraft.net/nba-mock-drafts/` path and found nothing for these years. Historical DraftExpress navigation revealed the original routes: `mymock.php?page=official&year=2007` and `/nba-mock-draft/YYYY/`; NBADraft.net used `/YYYYmock_draft`. These routes yielded all 14 DX/NBADraft tables used here. Two [WalterFootball](https://walterfootball.com/nbadraft2007.php) historical mock pages supplied a second publisher in 2007–2008. Every eligible source's exact archived evidence URL is in the provenance files.

The NBADraft.net route had no 2007–2008 captures in the bounded search. Additional 2008–2009 DraftExpress prefix searches found malformed relative navigation subpaths rather than newer canonical mock captures; those were not fetched or promoted. A useful next step is to recover later 2008–2009 vintages and then extend the verified same routes into 2015–2018. Inference years 2019–2026 have not been collected in this package and require their own pre-draft snapshots before use.

The resumable sequence is `discover.py`, `fetch.py`, `parse.py`, `build.py`, `verify.py`, then `package.py`. Discovery and retrieval are bounded to the registered publisher/year list with two network workers. Existing metadata is reused. `verify.py` replays all 715 source/identity checks and rejects truncated rounds, ambiguous player cells, wrong-year headers, and missing body boundaries. Models, runners and the R8p experiment were not modified.

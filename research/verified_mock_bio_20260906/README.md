# Archived pre-draft mock-table biographies

This package contains 10 factual features for **374 uniquely matched players** from
verified DraftExpress mock-table snapshots dated before the 2007–2014 drafts.
The same 480 source rows and identity matches used by the verified-consensus
package are independently rechecked. No new name aliases or fuzzy matches are
introduced.

| Feature | Interpretation |
|---|---|
| `vmb_age_reported_years` | Age displayed in the captured page; rounded reporting, not exact draft-night age |
| `vmb_listed_height_in` | Listed inches; shoes convention unknown |
| `vmb_listed_weight_lb` | Listed pounds |
| `vmb_listed_bmi` | kg/m² using height and weight from the same cell only |
| `vmb_college_class_year` | Explicit Freshman/Sophomore/Junior/Senior encoded 1–4; no class inference |
| Five `vmb_position_*` fields | Indicators for every explicitly listed PG/SG/SF/PF/C role; unknown roles remain missing |

These are archived listings, not certified measurements. Keep them separate from
official `vcmb_` measurements and the quarantined legacy `bio_` fields. Missing
height or weight means missing BMI. Integer ages have one-year reporting precision;
2014 decimal ages retain their displayed precision in row provenance. No birthday
or current NBA measurement is used to fill a missing value.

Coverage is 46/43/32/50/53/53/47/50 matched players for 2007 through 2014.
All matched players have listed height, weight and position; 373 have reported
age and 322 have explicit class year. Mock inclusion and archive availability
are selective, and some snapshots precede draft night by months. This source
package does not certify the broader model universe or any benchmark score.

The builder pins verified-source files to their public manifest, checks archive,
table and rank-fact hashes, verifies publication/capture/cutoff dates, and repeats
the original exact normalized-name/same-cohort identity join. It recognizes both
old `viewprofile.php` and newer `/profile/` links within the verified tables.
Malformed/ambiguous numeric and position tokens fail; blank age placeholders stay
missing. All explicit positions in triple-role listings are retained.

`test_build.py` checks every archived row and adversarial cases without models or
NBA outcomes. `verification.json` records its results. `review.md` documents the
independent findings; `change_audit.json` records the two corrected SF indicators
and every before/after file hash. All other numeric feature cells are unchanged.

Only files listed in `PUBLIC_ALLOWLIST.json` are intended for publication. The
archived HTML remains in the private source package and is not copied here.
No model join, training, test scoring or GPU execution is performed by this package.

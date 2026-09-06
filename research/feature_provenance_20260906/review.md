# Legacy feature provenance audit

The current legacy input table cannot be described as leak-free. Two confirmed construction problems survive into the current inputs: current NBA weight/global future-pool imputation in the weight/BMI block, and a measurement published five years after a prospect's draft that was inserted into the `bio_combine_` block. R8n therefore quarantines **all 20 `bio_` columns**, including combine and age. Medical and consensus inputs have insufficient date lineage to certify. Their quarantine is precautionary, not a claim that every value leaks.

This audit read pre-2019 feature values, source code, collector records and the parent's final-college-season metadata check. It did not read held-out NBA outcomes. The exact lists, source hashes, status distinctions and dependency map are in `quarantine_manifest.json`; the registered diagnostic is `work/r8n/plan.json`.

## Evidence that remains in the present model

`inheritance_check.json` compares 1,428 shared pre-2019 rows against the original handoff. All 23 audited features are unchanged, including selected BMI, medical durations/counts, consensus, college BPM aggregates, lineup RAPM and season-normalized statistics. These are current concerns, not merely flaws in an abandoned script. BMI was selected in the 2013 development fold; medical duration and several consensus/BPM fields were selected in every 2012–2014 fold.

The main reference is `/Users/kennakao/Downloads/nba_redraft_handoff/reference_code/tabular.py`:

| Family | Evidence and decision |
|---|---|
| `bio_weight_lb`, `bio_bmi_proxy` | Lines 129–134 explicitly use current NBA weight when combine weight is absent. Lines 184–188 fill missing values with height/position, height, and global medians from the combined prospect pool loaded at lines 43–45. BMI inherits both dependencies. Confirmed contaminated construction; remove or rebuild. |
| `bio_height_in`, `bio_pos_code` | Lines 132, 135 copy upstream NBA/player bio without a historical-date constraint; lines 177–179 fall back to final college values. Original upstream population and dates are unavailable. Not independently certified; quarantine. |
| `bio_age_at_draft` | Line 138 copies an upstream `age_at_draft`; lines 173–174 and 202 provide college/international age fallbacks. The comment says DOB-derived, but the upstream calculation/DOB dates were not recovered. Neither a safe formula nor current-age leakage is established. Quarantine until rebuilt from attributable birth dates. |
| `bio_combine_*` | Lines 139–140 copy measurements while excluding source detail. More seriously, later research patches write non-combine and post-draft measurements into this same prefix; concrete example below. The prefix is not an official-only guarantee. |
| `med_*` | Lines 250–258 copy measurements without event dates/source timestamps and uniformly zero-fill count/flag gaps. A 303.7-month interval on a prospect with age 22.92 exceeds the person's lifetime, showing malformed duration data. This is not by itself proof of post-draft leakage. Original collector unavailable; quarantine. |
| `cons_*` | Lines 246–249 copy four consensus metrics without source URL, snapshot date, or date filter. The original collector was not located. The newer `mock_` collector cannot certify this older `cons_` block. Quarantine pending reconstruction from dated publications. |

Concrete post-draft measurement: pre-2019 pid `Pabb4255b19` belongs to draft year 2010. The local research record `/private/tmp/claude-501/-Users-kennakao-nba/6b23c15b-6018-47b3-9476-45353eadffc2/scratchpad/anthro_result_6.json`, lines 146–154, cites a July 15, 2015 article, marks its context `later`, and acknowledges that no draft-era measurement was found. Current inputs contain its 93-inch wingspan, 115-inch reach and 262-pound weight with `bio_measure_src=5`. This conclusion is based on the stored source record, not independent verification of that article.

`/Users/kennakao/nba/datarebuild/make_anthro_patch.py` lines 2–5 permit `later`; lines 20–28 enforce numeric plausibility but no date filter and map values directly into `bio_combine_*`. `upload/apply_patches.py` lines 18–30 apply any numeric patch, line 44 includes the anthropometry patch, and lines 38–39 recompute wingspan minus height. Numeric plausibility and a source-category flag do not repair a post-draft input.

## College findings are more limited

College aggregation is not proven to contain future seasons. `tabular.py` lines 152–164 aggregate college timeline rows without an explicit draft-year filter, but the parent's `college_final_season_check.json` found **zero post-draft final college seasons** among 1,034 dated training prospects and 817 dated inference prospects across all eight inference classes. This substantially narrows the concern. It does not recover the original timeline or prove the upstream impact/lineup fitting windows.

`col_z_*` is normalized **within college season** at lines 166–172, not over all future years. It is not a training-fold-fitted scaler, but a same-season population statistic can be historically available if its underlying player-season pool existed before the draft. The missing timeline/pool construction prevents that stronger claim. Do not label these columns as confirmed future-normalization leakage.

`col_lu_*` is copied from the final college timeline at lines 154–157. The original lineup/RAPM builder was not recovered, so its source and estimation windows remain uncertain. BPM delta/mean/max/first formulas are visible, but the upstream `impact` definition remains unverified. R8n's broader quarantine diagnoses sensitivity to these unresolved families; it is not evidence that every aggregate is invalid.

## Dependencies and broader limitations

Removing a raw column from the selector alone is insufficient. `work/r8i/legacy_kernel.py` lines 55–63 can recreate height/age/consensus effects in engineered features. In particular, `x_rim` multiplies `col_blk_pct` by `bio_height_in` and was selected in both 2013 and 2014. Clear excluded raw values before engineering, remove stored descendants, rebuild feature coverage and its training thresholds, and refit training-only transforms. The exact dependency map is in the manifest. R8n enforces this clearing and checks that `x_rim` cannot retain height information after bio quarantine; its source-only arm bypasses all legacy engineering, shrinkage and coverage.

Two dataset-level issues remain even after dropping suspect feature families:

1. `tabular.py` lines 104–118 infer some undrafted players' draft year from later NBA debut and construct the pool partly from eventual NBA participation. A deployable draft-night universe must instead be fixed from contemporary eligibility/entry records. An input-only reconstruction still inherits this current evaluation universe.
2. Lines 321–327 remove a feature if absent from every post-2018 inference class. This lets future input availability influence the historical schema. Rebuild the schema with historical training-only rules. The finding concerns future inputs, not test-answer access.

The international block has an explicit season cutoff at lines 192–194. Its numeric unit conversion at lines 215–220 nevertheless chooses scaling from a combined-prospect median; fixed documented source units would remove this future-input dependency. No other broadly fitted imputation was established in the inspected feature-building section.

## R8n and the next admissible baseline

R8n registers 12 development-only trials: four variants × three model seeds, with the same 2012–2014 folds and dated labels. The variants are the explicitly uncertified legacy reference, all-bio removal, additional medical/consensus/unverified-college-derived removal, and 41 source-based college statistics. Differences between these dimensions are diagnostic, not evidence of incremental information or a clean-test promotion.

The source control uses only `ctx_base_` and `ctx_skill_`, excluding height and age. `work/r8/build_context.py` lines 23–40 allowlist raw Torvik statistical indices and exclude NBA-pick column 45; lines 47–60 require a unique matched player and source season no later than the draft; lines 65–66 and 85–88 compute deterministic transforms. Lines 90–98 retain source hashes and explicitly disclose that the tables were retrieved in 2026. Historical event seasons are checked; exact original publication vintages and the prospect universe are still unresolved.

For a future safe reconstruction, the current `/Users/kennakao/nba/datarebuild/combine_collect.py` provides a separate path to official event-year measurements: lines 29–38 permit only matching or earlier combine years and lines 39–58 extract documented fields. Rebuild from those source rows with per-cell event year, URL/hash and identity match; do not carry the overlaid legacy `bio_combine_` values forward. Consensus and medical features need similarly attributable pre-draft records. Until those steps pass, no R8n variant should be called a fully certified clean benchmark and no new held-out test is justified by this audit alone.

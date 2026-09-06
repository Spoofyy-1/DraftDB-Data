# Archived mock biographies, 2015–2026 extension

This **no-network** package extends the reviewed ten `vmb_` definitions using only the 18 previously verified archived mock sources. It checks all 945 source slots and reproduces 764 exact same-cohort source observations, then selects one historical source row for each of 600 players: 212 in 2015–2018 and 388 in separate 2019–2026 inference inputs. It performs no model execution or scoring and reads no draft-result or NBA outcome columns.

The unchanged definitions are reported snapshot age, listed height, listed weight, same-row BMI, explicit college class1–4, and five explicit PG/SG/SF/PF/C indicators. These are dated listings, separate from official `vcmb_` measurements and legacy `bio_` fields. Age is the displayed age at the snapshot, not exact draft-night age; no birthday is reconstructed.

## Source resolution and files

All 764 source observations remain in `source_observations.csv`, with cell/source/date/identity evidence in `row_provenance.csv`. Those repeated publisher observations are **provenance data, not independent model training rows**. `selected_sources.csv` records the one source chosen per player.

Resolution uses a fixed whole-row priority: DraftExpress, then NBADraft, then the serious David Kay/Walter source. It does not use mock rank, numerical values, completeness, NBA outcomes or model scores. The selected distribution is 149 DX, 445 NBADraft and six serious Walter rows. A lower-priority source cannot fill a missing age, class or measurement in the preferred row. Height and weight are never mixed across sources; BMI is absent whenever either value is missing in the selected row.

`features_training_2015_2018.csv` and `features_inference_2019_2026.csv` contain only pid, draft year and the ten reviewed columns. The sidecars preserve every original input identity and row order, reading only `pid` and `draft_year`:

| Input | Original rows | Rows with extension bios |
| --- | ---: | ---: |
| Training2000–2018 | 1,458 | 200 |
| Test2019 | 137 | 51 |
| Test2020 | 112 | 54 |
| Test2021 | 233 | 46 |
| Test2022 | 97 | 48 |
| Test2023 | 101 | 48 |
| Test2024 | 114 | 49 |
| Test2025 | 106 | 47 |
| Test2026 | 61 | 45 |

No prospect is removed because its bio is missing, and no draft-status filter is applied. The training sidecar is extension-only: 2000–2014 values remain missing here and must not overwrite the separate frozen earlier bio package. Twelve training source identities fall outside the original input universe. All 388 inference identities occur in the original test pools, which contain 961 rows overall.

## Typed extraction and missing values

DX2015 uses only the subject cell before its nested college statistics table. DX2016 uses only the subject `item` block, excluding statistics/video siblings. Both call the pinned reviewed text parser. DX2017 uses explicit position, age, height and weight columns from the checked extended table. It has no class column; that field stays missing for those selected rows.

NBADraft uses its explicit H/W/P/C cells. The source's listing convention is feet-and-inches for H and pounds for W; the headers abbreviate the fields and do not spell out pounds inline. This is recorded as a source-format convention, not an independent unit or measurement certification. Shoe convention is unknown. Age is absent from these tables and remains missing. Duplicate sticky tables must agree on actual bio cell text, in addition to the rank parser's identity checks.

The serious Walter top-15 headings provide only the explicitly listed height, position and class. No weight or age is inferred from another source, the narrative, or a year-like token. Broad F/G roles do not establish one of the five positions. Birth-year-like tokens do not establish age or college class.

Typed numerical parsers match the entire cell, reject signed/ranged/malformed values, enforce the reviewed plausible ranges and retain missing values. Valid literal fractional heights are converted exactly. Unknown positions leave all five indicators missing; every recognized explicit role is retained. Class maps only explicit Freshman/Fr., Sophomore/So./Soph., Junior/Jr. and Senior/Sr. values to1–4. International, high-school and other unsupported forms remain missing.

Twelve source observations have documented role/class omissions in `missing_field_reasons.json`. Invalid typed fields become missing while unrelated valid fields remain usable. A malformed DX text bio rejects that cell's ten extracted values; no such DX omission occurred in the saved source data.

## Coverage and transfer limits

Reported age is available for149 selected players in2015–2017 and **none from2018–2026**. Selected DX2017 rows lack class, so only four2017 players have class from another independently selected publisher row. This availability shift must be considered before applying the family to later cohorts; missing fields are not evidence of an absent trait.

All600 selected players have listed height and explicit positions. Weight and BMI cover594 players; the six selected serious Walter rows have no weight. Historical listings are selective because they originate in mock drafts, and snapshots may precede the draft by months. The rank extension's partial-source, publisher-quality and stale-vintage caveats still apply. The accepted2026 source is the May8 snapshot, using the correct June23 first-round cutoff; the ambiguous same-day update remains quarantined upstream.

No current biography, DOB reconstruction, alias expansion, cross-source fill, draft order or NBA outcome is used. The input universe and any benchmark score remain separate audit questions.

## Verification and publication

`test_build.py` replays all764 source observations from the pinned archived tables. It verifies decimal age precision, literal fractional height, triple positions, same-row BMI, fixed source priority, all eight complete original test pools and explicit missing rows. Eighteen malformed-field cases stay missing, and18 source/pool tamper cases reject, including future captures, wrong2026 cutoff, incorrect hashes, identity substitutions and conflicting sticky-table measurements.

All80 files in the frozen rank extension and all10 files in the reviewed original bio allowlist remain unchanged. No R8t file was modified. Full archived HTML stays private in the source package and is not copied here. Only the exact files in `PUBLIC_ALLOWLIST.json` are intended for publication. The extension is not connected to any model runner.

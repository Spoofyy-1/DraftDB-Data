# Independent review of archived mock-table biographies

The extractor now supports the 10 listed-biography features as **dated source facts** for the eight verified DraftExpress snapshots from 2007–2014. It does not certify official measurements, the model's candidate universe, or a clean benchmark. No current NBA biography, actual draft pick, outcome, or statistical performance field is used as a feature.

The review checked all 480 archived rank rows and reproduced the same 374 uniquely matched player identities. The old 2007–2013 two-table layout and different 2014 extended table both retain their exact parser boundaries. The 2014 cells contain other text/statistics, but the extractor accepts only the named age/size/class/position facts. Adjacent measurements or statistics cannot supply missing BMI inputs.

## Required repairs

1. The old numeric regex silently ignored negative signs and could accept truncated malformed tokens. The new parser rejects malformed, duplicated, implausible or ranged numeric values (`build.py:30`, `build.py:36`). Literal empty age placeholders remain missing; an unknown numeric value is never imputed.
2. The old position regex only retained two roles. Three genuine source rows list PG/SG/SF; all explicit distinct roles are now retained. Unsupported roles, incomplete slash tokens, duplicate roles and ambiguous separated position tokens reject the cell. Unspecified positions remain entirely missing.
3. The extractor now pins the verified input files to the source package's public manifest (`build.py:88`), rechecks archived HTML, parsed table and rank-fact hashes, update/capture/cutoff chronology and archive URL (`build.py:101`), and independently reproduces the original exact normalized-name/same-cohort identity rule using only pid, name, draft year and draft date. Rank-to-pid substitutions and newly introduced name aliases fail.
4. Reported age precision is computed from the displayed token. Integer listings retain one-year precision; 2014 decimal ages retain their displayed precision. This is age shown in the archive, not exact draft-night age or a reconstructed birthday.

## Verified data changes

After all tests passed, the extractor was regenerated. Player identities, order, draft years and provenance rows are unchanged. Exactly **two of 3,740 numeric feature cells changed**:

| Player source | Field | Before | After | Evidence |
|---|---|---:|---:|---|
| Jamont Gordon, 2008 (`P16bd14d8e6`) | `vmb_position_sf` | 0 | 1 | DX 2008 row 47 explicitly lists PG/SG/SF |
| Nemanja Bjelica, 2010 (`Pe97fa79993`) | `vmb_position_sf` | 0 | 1 | DX 2010 row 50 explicitly lists PG/SG/SF |

All other numeric cells are unchanged. `change_audit.json` records the exact before/after hashes. The feature CSV changed from `3f7e77b9f7f621e4e8855538eedf498391198bed6f3eafdb3c0989b4d46b7b6b` to `5f06d269cab48df89f66d8d3def6fcd4be207971826a73adc70a6ca978b45b6b`. The provenance CSV remains `03f10447f07b35c6807d40218c58a7a1d8562d3299bd48d012a03e09dfaba261`.

## Tests and limits

`test_build.py` passed 18 positive checks and rejected 38 adversarial cases: old/new layouts and profile URL forms, known Greg Oden/Kevin Durant/Andrew Wiggins values, triple positions, blank actual age placeholders, missing international class, missing-height/weight BMI, decimal precision, malformed age/height/weight/position/class, duplicate links, archive chronology, all source/fact hashes, observation substitutions, ambiguous identities and truncated tables. `verification.json` records source, builder and test hashes. Tests perform no model execution and read no NBA outcomes.

Height/weight are contemporaneous **listings**, not authenticated combine measurements. Shoe convention is unknown. BMI uses listed height and weight from the same player cell only, with no cross-source fallback. Missing class and unknown position stay missing. Source selection and mock-table inclusion create availability bias. Archive capture dates sometimes precede the draft by months, so the values must not be relabeled as draft-night measurements. Only 2007–2014 is covered. A subsequent model join must keep the `vmb_` namespace separate from `vcmb_` and legacy `bio_`, preserve source dates/missingness, and undergo its own calendar/model validation.

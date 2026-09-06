# Inference boundary review

The reviewed implementation is in `work/inference_v2/prepare_year.py`,
`run_year_sandbox.sh`, `code/predict_year.py`, and `code/model_core.py`.
This review performed no model fitting, prediction scoring, or WAR-column reads.

## Verified behavior

- The preparation step left-joins selected F50 columns to the original broker
  input rows and asserts preserved row count and PID order.
- The sandbox mounts one year's bundle and one year's prediction directory. The
  vault, all-year bundle root, host project, and other workers' results are not
  mounted. It uses separate process/network namespaces, read-only code/data,
  fresh temporary directories, dropped privileges/capabilities, and offline
  checkpoint access.
- The predictor rejects training/current-year identity overlap and checks actual
  label season ends against Y−1. Priors, feature transformations, feature
  selection, and targets use the training frame; seed averaging is fixed.
- A new predictor process is used per year, avoiding trained-state carryover.
- Predictions are required for every inference PID. The scorer must then select
  the fixed original drafted benchmark independently, after prediction freeze.

## Before inference use

1. Compare the actual loaded policy hash to
   `manifest['frozen_policy_sha256']`, and assert that the manifest extra-feature
   list exactly equals the policy list. Preparation writes these fields; the
   initial reviewed worker did not enforce them. The parent's patch is now
   present and was rechecked.
2. Require explicit horizons for all scored years (2019–25), and reject missing
   entries instead of defaulting to five seasons. In particular 2022–25 have
   shorter benchmark horizons. The parent's missing-horizon assertion is now
   present and was rechecked.
3. Freeze and verify every model implementation input: `predict_year.py`,
   `model_core.py`, `legacy_kernel.py`, and `incumbent.json`, plus the execution
   script/checkpoint identity as appropriate. Do not blindly reuse a development
   policy whose code filenames or horizons refer to a different runner.
4. Hash-check local model modules before importing them. The initial worker
   imported `model_core` (which imports the kernel) before checking policy hashes.
   This is an immutable-execution weakness, even though the namespace still
   restricts file access.
5. The independent scorer should require a single expected policy hash across all
   seven frozen year predictions, matching each bundle hash and its explicit
   horizon. It should reject an incomplete set of years and duplicate freezes.
6. Check for an existing freeze before expensive prediction work and use an
   exclusive per-year lock plus atomic prediction/freeze writes. The initial
   runner checks the freeze only after fitting; two concurrent runs of the same
   year could both pass the check and race to overwrite the files.

These are execution/reproducibility safeguards. They do not repair inherited
predictor provenance. The parent has paused final testing because existing body
measurements and descendants require a separate provenance repair. The old
42.5% strict result remains uncertified; this review does not validate it.

## Original inference and benchmark pools

The server audit read only PID, declared draft year, the input drafted flag, and
answer `actual_pick` missingness. It never inspected WAR values or prediction
scores. Every broker inference file preserves the original input PID list and
order exactly. The drafted status in the input files agrees with the scorer's
non-null-pick benchmark membership.

| Year | Original inference rows | Original benchmark rows | Additional original prospects |
| --- | --- | --- | --- |
| 2019 | 137 | 58 | 79 |
| 2020 | 112 | 58 | 54 |
| 2021 | 233 | 56 | 177 |
| 2022 | 97 | 52 | 45 |
| 2023 | 101 | 56 | 45 |
| 2024 | 114 | 55 | 59 |
| 2025 | 106 | 57 | 49 |
| 2026 | 61 | 60 | 1 |

The complete supplied 2019–25 benchmark has **392** rows. This is the original
provided benchmark, not a claim that it contains every real NBA draft selection.
2026 remains prediction-only.

`pool_contract.py` demonstrates the intended scorer checks. Prediction IDs must
equal all original input IDs; drafted benchmark IDs must be a subset. Only after
those checks should the scorer left-join every original drafted answer row to a
prediction. Extra original prospects are allowed but do not enter the unchanged
drafted benchmark. Negative checks passed for missing drafted rows, missing
non-drafted original inputs, duplicate prediction IDs, and wrong-year predictions.

The new worker's rank average across all original prospects can differ from a
rank average formed over a drafted-only prediction batch. That is permitted by
the new declared inference universe, but comparative reference models should
use the same full input pool if their results are presented as a controlled
comparison.

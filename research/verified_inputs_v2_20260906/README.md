# Expanded dated input bundle

All9 input snapshots preserve2,419 existing rows and every existing CSV cell as exact text. Four dated mock-ranking fields and ten dated profile fields are appended. Together with the prior50 college and37 combine fields, this supplies101 additional research fields. Missing source observations remain missing.

Training coverage:588 of1,458 rows have dated mock ranks;565 have dated profiles. The961 inference rows retain their original identity order;388 have dated rank/profile observations. No imputation, actual draft picks or NBA outcomes are added.

Removing all2019–2026 rank/profile feature CSVs from the build leaves the training file byte-identical (SHA256 `83f2923ad06f98f34f167f72772c74303a05ad2cd28ad657e208f16db468dfd6`).

This bundle is partially audited and is not an approved model matrix: original cohort selection and remaining inherited columns still require review. The old bio/medical/consensus/scouting fields remain quarantined. Listed age and size are source snapshot facts, distinct from measured combine data.

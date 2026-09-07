# 2019–2025 stack predictor inputs

This package preserves all 127 predictor columns for the frozen M/N stack. The 16 predictor and metadata CSVs use lossless gzip compression. Decompressing each file restores the exact SHA256 recorded in package/manifest.json.

Predictor tables contain pid, draft_year, and 127 features. Actual draft membership is stored separately. No WAR labels, NBA outcomes, benchmark answers, or actual draft-order columns are included.

Twelve original M predictor matrices reproduced exactly. The 2018 control reproduced all 35 game/team values and missing cells for 75 players whose source season was 2018. Four invalid-game fixtures and checks of all 16 output files passed.

All 14 newly fetched 2019–2025 raw game/team sources were verified against their hashes. These archives already use gzip and total 75,174,983 bytes, exceeding the 35 MiB raw-source limit. They remain on the GPU server. REMOTE_SOURCE_MANIFEST.json provides paths, URLs, sizes, and hashes for restoration. All derived predictor tables and source-join provenance are included here. Original annual source files also remain remote.

Historical publication vintages, schedule completeness, and original population construction remain unverified. This is a diagnostic predictor package. The calendar broker and isolated model workers must enforce training on earlier cohorts and outcome labels from completed seasons only.

SCIENTIFIC_README.md documents the unchanged scientific builder contract. PUBLIC_ALLOWLIST.json lists every public file with its byte count and SHA256.

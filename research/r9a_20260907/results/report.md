R9a verification passed: 3,810/3,810 immutable task records, all 3 full reference replays, all 43 frozen file hashes and the complete recomputed summary match. No model or held-out evaluation was run during verification.

The queue completed in 3171.861 seconds (72.07 tasks/minute), with no errors. It covers all 47 single removals, all 1,081 double removals and 47 fixed-width permutation controls and remains a pre-2019 development diagnostic, with no model promotion. The deletion-width, correlated-permutation and retrospective source limitations in the registration still apply.

All original task files remain on the server. 17 deterministic gzip chunks preserve their exact bytes (520,580,415 original bytes; 127,677,372 compressed bytes); every record passed round-trip comparison. Each chunk is below 40 MB. task_archive_manifest.json records original file, task ID, byte length, SHA-256, chunk and line, plus compressed and uncompressed chunk hashes. To restore, decompress a chunk and remove exactly one final LF from each record line.

Full numerical diagnostics are in matched_summary.json. Verification deliberately performs no selection for the next study.

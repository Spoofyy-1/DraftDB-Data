The benchmark completed72 exact replays. Every configuration, raw/canonical prediction, score and full fold audit matched W on both the server and independent local verification. The frozen15 files stayed unchanged.

| Scheduler | Workers | Seconds for24 tasks | Trials/minute | Progress state |
|---|---:|---:|---:|---:|
| old | 4 | 74.438 | 19.34 | 94443102 bytes |
| immediate_refill | 4 | 27.135 | 53.07 | 479768 bytes |
| immediate_refill | 6 | 27.757 | 51.88 | 479772 bytes |

Use immediate-refill with4 workers for the next study. Its observed speedup was 2.74x over the original scheduler;6 workers were slightly slower. There were no predictor, input, seed, precision or checkpoint-reuse changes.

This single fixed-order comparison includes fresh process startup and actual scheduler work, but cache/thermal effects and future task sizes can alter the ratios. The original full old4 state remains on the server; all24 replayed records were also extracted and locally verified, and all48 new-scheduler records remain in immutable task files. Initial579 full records remain in the frozen W reference artifact.

The no-fit profile measured median1.887s for full94.44MB JSON encoding and0.240s for summary, or4.252s for two of each per old loop before disk writes. The new arms wrote nine compact snapshots and three full summaries, versus26 full snapshots/summaries in the old arm. Partial/corrupt append logs fail closed and require explicit repair.

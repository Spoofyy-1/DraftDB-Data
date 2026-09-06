# Matched pair registration

Run `python planner.py --summaries R8I_SUMMARY R8J_SUMMARY` only after both studies finish. Each summary must sit beside its completed `state.json`, with the corresponding `plan.json` and `worker.py` one directory above. The planner recomputes matched audits, requires all 50 distinct feature comparisons and every registered task, and freezes up to three overall gated singles ranked by matched gain. It then registers all their pairs, at most three.

Each pair has 10 configurations: RR once plus RP, PR, and PP for each of three registered permutation seeds. Across three model seeds this means 30 tasks per pair. Every fit has two identically named slots. Shuffling preserves each feature's own missingness and within-cohort marginal values. PP uses independent feature shuffles for the factorial diagnostic; it is not a joint-block conditional randomization test.

`summarize_pairs` audits base hashes, masks, cardinalities, dimensions and slot order. It reports RR-RP, RR-PR, and RR-RP-PR+PP by fold, model seed and permutation replicate, then class means. RR is shared across permutations and cannot count as three independent runs. The exploratory pair gate requires at least 0.005 gain against both single-real arms, improvement in at least two classes for each contrast, and no class decline worse than 0.01. Interaction is reported separately. There is no test access or automatic production promotion.

No plan is produced when either source is incomplete. If fewer than two singles qualify, the valid registration has zero tasks: record the result instead of relaxing the gate.

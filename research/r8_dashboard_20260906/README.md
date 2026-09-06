# Current research dashboard

The dark dashboard at `/stack` shows the latest study state, completed configuration averages, source-collection status and live GPU telemetry. This snapshot is presentation code; it does not change experiments or model selection.

Configuration completeness follows the frozen registered task seeds when available, allowing deterministic Ridge runs to complete with one seed while stochastic models require all registered seeds. Duplicate or incomplete seed records do not qualify for the best-configuration headline. Earlier three-seed studies remain supported.

Validation: all20 R8v configurations recognized, including six deterministic configurations; duplicate/incomplete records rejected; live API reproduces the TabICL16 mean0.33778204631520553.

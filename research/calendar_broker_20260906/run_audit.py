"""Run preparation for each year, print aggregate coverage only."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
summaries = []
for year in range(2019, 2027):
    out = ROOT / "bundles" / str(year)
    if not out.exists():
        cmd = [sys.executable, str(ROOT / "broker.py"), "--source", str(ROOT / "source/historical_RAPTOR_by_player.csv"),
               "--identity", str(ROOT / "source/tabular_names.csv"), "--feature-manifest", str(ROOT / "source/manifest.json"),
               "--project", str(PROJECT), "--vault", str(PROJECT / "vault"), "--year", str(year), "--output", str(out)]
        if year >= 2024:
            cmd.append("--allow-partial-calendar")
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    m = json.loads((out / "manifest.json").read_text())
    summary = {k: m[k] for k in ["predicted_draft_year", "training_players", "training_labels", "inference_rows", "actual_label_max", "partial_calendar", "missing_calendar_seasons", "eligible_answer_cohorts_opened", "label_verification", "label_coverage_by_cohort"]}
    summaries.append(summary)
    print(json.dumps(summary), flush=True)
(ROOT / "aggregate_coverage.json").write_text(json.dumps(summaries, indent=2))

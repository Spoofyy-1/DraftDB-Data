#!/usr/bin/env bash
set -euo pipefail
root=/home/ubuntu/nba/handoff/r9g
"$root/run_sandbox.sh" --gpu-fixture
"$root/run_sandbox.sh" --prepare-only
exec "$root/run_sandbox.sh"

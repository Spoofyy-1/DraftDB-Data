#!/usr/bin/env bash
set -euo pipefail
while systemctl is-active --quiet draftdb-r8d-20260906.service || systemctl is-active --quiet draftdb-r8baseline-20260906.service; do
  sleep 15
done
/bin/bash /home/ubuntu/nba/handoff/r8e/run_sandbox.sh
/bin/bash /home/ubuntu/nba/handoff/r8e/run_combinations_sandbox.sh

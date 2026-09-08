#!/bin/bash
# Waits for the background pull to exit, then rebuilds every derived table.
# Launched automatically; safe to re-run by hand.
cd "$(dirname "$0")"
PID=${1:-6003}
echo "[finish] waiting for pull pid $PID"
while ps -p "$PID" > /dev/null 2>&1; do sleep 60; done
echo "[finish] pull exited, rebuilding features"
python3 build.py
python3 make_readme.py
python3 validate.py
echo "[finish] done - features.csv and README.md are final"

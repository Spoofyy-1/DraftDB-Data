#!/bin/bash
cd /Users/kennakao/nba/datarebuild/tracking_raw
for y in $(seq 2008 2026); do f=torvik_team_$y.csv; [ -s $f ] && [ $(wc -c < $f) -gt 50000 ] && continue
  curl -s -m 60 -A "DraftDB-research/1.0 (mike@alphax.inc)" "https://barttorvik.com/${y}_team_results.csv" -o $f; echo "$y $(wc -c < $f) bytes"; sleep 2; done
echo TEAM_DONE

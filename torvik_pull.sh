#!/bin/bash
# Torvik advanced player table, one CSV per season (public endpoint, polite: sequential, 2 s apart, cached)
cd /Users/kennakao/nba/datarebuild/tracking_raw
for y in $(seq 2008 2026); do
  f=torvik_$y.csv
  if [ -s $f ] && [ $(wc -c < $f) -gt 100000 ]; then echo "cached $y"; continue; fi
  curl -s -m 120 -A "DraftDB-research/1.0 (mike@alphax.inc)" "https://barttorvik.com/getadvstats.php?year=$y&csv=1" -o $f
  echo "$y bytes $(wc -c < $f) rows $(wc -l < $f)"; sleep 2
done
echo TORVIK_DONE

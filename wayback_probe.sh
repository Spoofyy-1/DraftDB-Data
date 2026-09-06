#!/bin/bash
# Retry the Wayback index until it answers; save the 2022 nbadraft.net mock snapshot list and one snapshot's HTML for inspection.
for i in $(seq 1 12); do
  out=$(curl -s -m 30 "https://web.archive.org/cdx/search/cdx?url=nbadraft.net/nba-mock-drafts*&from=2022&to=2022&output=json&limit=40&filter=statuscode:200&collapse=timestamp:6")
  if echo "$out" | grep -q '"urlkey"'; then echo "$out" > mock_raw/cdx_2022.json; echo "cdx ok after $i tries"; 
    ts=$(python3 -c "import json;d=json.load(open('mock_raw/cdx_2022.json'));print(d[1][1],d[1][2])"); set -- $ts
    curl -s -m 60 "https://web.archive.org/web/${1}id_/${2}" > mock_raw/snap_2022_${1}.html; echo "saved snapshot $1 $2 bytes $(wc -c < mock_raw/snap_2022_${1}.html)"; exit 0
  fi
  sleep 300
done
echo "wayback still offline after 12 tries"

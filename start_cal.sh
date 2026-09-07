#!/bin/zsh
cd /Users/kennakao/nba/datarebuild
for s in 0 1; do SHARD=$s NSHARD=2 nohup python3 -u season_calendar_collect.py > season_calendar_$s.log 2>&1 < /dev/null & done
disown; sleep 2; echo "started 4 shards"

#!/bin/zsh
for p in $(ps -eo pid,command | grep 'gtrends_collect\|gtrends_topic\|season_calendar_collect\|mock_consensus_collect\|gtrends_run' | grep -v 'grep\|zsh -c\|kill_collectors' | awk '{print $1}'); do kill $p 2>/dev/null && echo "stopped pid $p"; done
sleep 1; echo "collectors left: $(ps -eo command | grep -c '[g]trends_collect\|[g]trends_topic\|[s]eason_calendar_collect\|[m]ock_consensus_collect')"

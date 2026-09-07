#!/bin/zsh
for p in $(ps -eo pid,command | grep 'season_calendar_collect.py' | grep -v 'grep\|zsh -c\|kill_cal' | awk '{print $1}'); do kill $p 2>/dev/null; done; sleep 1; echo "calendar collectors left: $(ps -eo command | grep -c '[s]eason_calendar_collect.py')"

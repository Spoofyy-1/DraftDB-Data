#!/bin/zsh
# Pause resumable collector pulls when the disk gets low (they checkpoint and can be resumed with their own scripts).
while true; do
  free_kb=$(df -k / | tail -1 | awk '{print $4}')
  if [ "$free_kb" -lt 600000 ]; then
    echo "$(date '+%F %T') LOW DISK ${free_kb}KB: pausing collector pulls" >> /Users/kennakao/nba/datarebuild/disk_guard.log
    pkill -f "euroleague/pull.py"; pkill -f "novel/euroleague/pull.py"; pkill -f "draftexpress/.*crawl"; pkill -f "nbadraftnet/.*(crawl|fetch)"; pkill -f "boards/.*(crawl|fetch)"; pkill -f "fiba_youth/.*(crawl|fetch|pull)"
    sleep 600
  fi
  sleep 120
done

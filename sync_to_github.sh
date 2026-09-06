#!/bin/zsh
# commit + push the data repo (called every 30 min by the sync loop and at each check-in)
cd /Users/kennakao/nba/datarebuild || exit 1
git add -A >/dev/null 2>&1
git diff --cached --quiet && exit 0
git commit -q -m "data sync $(date '+%Y-%m-%d %H:%M')" && git push -q origin HEAD:main 2>&1 | tail -1

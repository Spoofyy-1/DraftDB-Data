#!/bin/zsh
cd /Users/kennakao/nba/datarebuild
nohup ./gtrends_run.sh > /dev/null 2>&1 < /dev/null &
disown
echo started

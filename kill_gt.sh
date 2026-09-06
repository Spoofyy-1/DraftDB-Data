#!/bin/zsh
# kill the Trends collector chain without touching the shell that invoked this script
me=$$; par=$PPID
for p in $(ps -eo pid,ppid,command | grep 'gtrends_collect.py\|gtrends_run.sh\|gtrends_topic_pass.py' | grep -v 'grep\|zsh -c\|kill_gt' | awk -v m=$me -v q=$par '$1!=m && $1!=q {print $1}'); do kill $p 2>/dev/null; done
sleep 1; echo "remaining: $(ps -eo pid,command | grep 'gtrends_' | grep -v 'grep\|zsh -c\|kill_gt' | wc -l | tr -d ' ')"

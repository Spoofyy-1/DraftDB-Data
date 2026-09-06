#!/bin/zsh
cd /Users/kennakao/nba/datarebuild
python3 -u gtrends_collect.py >> gtrends.log 2>&1
python3 -u gtrends_topic_pass.py >> gtrends_topic.log 2>&1
python3 gt_features.py >> gtrends.log 2>&1
./sync_to_github.sh

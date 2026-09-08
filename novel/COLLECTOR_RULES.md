# Rules for every novel-data collector (read before writing code)

Project: NBA redraft model. Player identity file (names allowed ONLY on this Mac):
  /Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv  (pid, draft_year, actual_pick, player_name, nba_id; 2,560 drafted players 2000-2025)
Verified birthdates for 947 players: /Users/kennakao/nba/datarebuild/age_verified_wiki.csv (pid, birth_date, age_at_draft_wiki, rev_ts)
RSCI features (class year = draft_year - rsci_years_to_draft when rsci_top100=1): /Users/kennakao/nba/datarebuild/rsci_features.csv
Current model inputs (pid-keyed, numeric): /Users/kennakao/nba/datarebuild/v4_build/data_v4/train_2000_2018.csv and tests/test_YYYY_inputs.csv (do NOT modify these)
Colin's reference builders (read-only, never merge, never import his package; port logic if useful):
  git -C /Users/kennakao/nba/site show origin/colin:infra/builders/<file>.py   (scouting.py, mocks.py, momentum.py, torvik_context.py, game_features.py, college_sources.py, intl.py, transfers.py, bio.py, population.py, coaches.py, development.py)

Draft-night cutoffs (a source is pre-draft only if its timestamp is before 22:00 UTC on this date):
  2000-06-28 2001-06-27 2002-06-26 2003-06-26 2004-06-24 2005-06-28 2006-06-28 2007-06-28 2008-06-26 2009-06-25 2010-06-24 2011-06-23
  2012-06-28 2013-06-27 2014-06-26 2015-06-25 2016-06-23 2017-06-22 2018-06-21 2019-06-20 2020-11-18 2021-07-29 2022-06-23 2023-06-22 2024-06-26 2025-06-25

Hard rules
1. Output = /Users/kennakao/nba/datarebuild/novel/<collector>/features.csv with a `pid` column plus NUMERIC feature columns only (no names, no free text), one row per pid, missing = empty (never 0 for unknown), plus README.md (feature definitions, source URLs, dating method, coverage table, ToS notes, known limitations) and provenance.csv where applicable. Keep raw caches under raw/ so re-runs are offline and resumable.
2. Every feature must be knowable before the player's draft night. Date every record (game date, capture timestamp, revision timestamp) and filter on that date, never on a season label alone.
3. Respect robots.txt and terms of service; polite rates (>= 1-2 s between requests to a site, exponential backoff on 429/503); identify with a descriptive User-Agent; never bypass Cloudflare/JS challenges, paywalls or logins. Off-limits: sports-reference.com, kenpom, synergy, realgm (403 to bots), proballers, legabasket stats pages, tblstat detail pages, acb.com, nikeeyb, EYBL data.
4. Rule-based extraction only (regex/dictionaries). No LLM scoring of text, no fuzzy judgments by you about individual players. Document every rule in the README.
5. Name matching: normalise (strip accents, punctuation, suffixes Jr/Sr/II/III), require draft-year plausibility and, where a birthdate/birth year is available on both sides, agreement; log ambiguous matches to unmatched.csv rather than guessing.
6. Long jobs: run with nohup in the background writing to <collector>/run.log, checkpoint frequently, and report partial coverage if the job cannot finish within your session; leave the process running with clear instructions in README on how to resume. Never kill processes with broad patterns (no `pkill python`); only your own script name.
7. Never touch /Users/kennakao/nba/datarebuild/v4_build/data_v4, the box (209.20.157.130), the site repo, or git in any way. Do not commit.
8. Finish by printing: rows in features.csv, coverage by draft-year band (2000-07, 2008-18, 2019-25), and the top 10 feature definitions.

# draftdb-data (private)

Collected data behind the DraftDB redraft model. Everything here is keyed by `pid`; **this repo contains player names** (raw scrapes and `identity/`), so it must stay private or have names stripped before sharing. The model box never reads this repo.

| dir | what | source |
|---|---|---|
| `wiki_raw/` | pre-draft Wikipedia revisions (infobox, career tables, parsed `career_rows`), team-season pages | Wikipedia API (en/fr), CC BY-SA |
| `tracking_raw/` | Torvik advanced-stat CSVs per season + team results | barttorvik.com `getadvstats` / `*_team_results.csv` |
| `recruit_raw/` | RSCI consensus recruiting rankings 1998–2026 (per-service ranks, HS height/position/city, destination) | RSCI Google Site published sheets |
| `trends_raw/` | Google Trends pre-draft interest per drafted player (daily US, Jan 1 → day before draft, anchored to "NBA draft") | pytrends |
| `mock_raw/` | mock-draft snapshots 2020+ | Wayback / archived mock pages |
| `raw/`, `upload/` | earlier collector outputs and the patch files applied on the box (`apply_patches.py`) | — |
| `identity/` | pid → name mapping | — |
| `*.py`, `*.sh` | collectors and feature builders (text features are rule-based word lists, no LLM scoring; see `docs/TEXT_FEATURES.md` in the model repo) | — |

Feature CSVs (`*_features.csv`) are the processed blocks merged by `make_weird_patches.py` into pid-keyed patches for the model repo. Synced automatically by `sync_to_github.sh` while collectors run.

# Prior draft membership, 2007–2011

This bounded audit recovered 283 of the expected 300 selected-player records. Three cohorts have complete 60-member source lists. The remaining 17 selections are explicitly unresolved. The package is not model ready and changes no research study, target, benchmark, or production input.

| Draft cohort | Recovered members | Complete source roster | Explicit primary/AP evidence | Exact same-cohort research name matches | Apparent identity/table gaps |
| --- | ---: | --- | ---: | ---: | ---: |
| 2007 | 44 | No | 1 | 35 | 9 |
| 2008 | 60 | Yes | 60 | 49 | 11 |
| 2009 | 60 | Yes | 60 | 46 | 14 |
| 2010 | 60 | Yes | 60 | 51 | 9 |
| 2011 | 59 | No | 59 | 54 | 5 |
| Total | 283 | No | 240 | 235 | 48 |

The 48 apparent gaps comprise 10 legacy identity rows absent from the frozen research table and 38 members without an exact legacy name match in the same cohort. They are review candidates, not a claim that 48 distinct people are missing: suffixes, source spelling errors, and wrong-person legacy identities can inflate this number. Among the 38, the broad identity key gives 14 unique exact-name suggestions, one ambiguous name, and 23 with no exact match. Broad IDs and legacy IDs remain separate. No fuzzy match is accepted or silently promoted.

Membership comes from prior draft selection records and is retained regardless of identity, NBA appearance, feature coverage, calendar availability, or label availability. A prior selected cohort can be historically valid training membership when its draft and the supporting record precede the prediction cutoff. Current-year selected membership and actual selection positions are not model inputs. No missing outcome is replaced with zero.

Source evidence:

- [AP's complete 2008 list, via Deseret News](https://www.deseret.com/2008/6/27/20260779/2008-nba-draft-selections/) and [complete 2009 list, via ESPN](https://www.espn.com/espn/wire/_/section/nba/id/4288601) each supply all 60 records.
- [The official Atlanta Hawks 2010–11 media guide](https://atlantahawkspr.wordpress.com/wp-content/uploads/2010/10/1011_hwk_mediaguide_final.pdf), PDF page 121, left side, printed page 238, supplies all 60 2010 records. Its PDF metadata reports creation on October 1 and modification on October 5, 2010; the URL has an October 2010 upload path. The conservative source availability field is October 31, 2010. A partial AP record and a restatement in the guide support two spelling variants; other possible typos stay unresolved.
- [AP's 2011 team-by-team list, via ESPN](https://www.espn.com/nba/story?id=6699165&src=desktop) has 61 event rows but only 59 distinct selections because one traded player appears three times. A missing selection is retained in the protected anomaly list.
- [The partial 2007 syndicated list](https://www.thespread.com/nba-news/2007-nba-draft-selections-2/) has visibly damaged/truncated text. Its 43 recovered records remain provisional because the captured fragment lacks an explicit AP attribution. [A dated AP report via Pittsburgh Post-Gazette](https://www.post-gazette.com/sports/nba/2007/06/28/NBA-Draft-Oden-goes-first-to-Portland-Durant-goes-to-Seattle-at-No-2/stories/200706280283) independently supplies one additional selection fact. Sixteen source selections remain unrecovered.

These are current retrievals of records bearing contemporary datelines or issue metadata. They are not independently timestamped captures of the original historical body. In particular, the 2008 live page has a 2024 modified timestamp. The provenance manifest preserves that limitation; no exact historical publication-body claim is made. The 2007 provisional records need explicit primary corroboration before use.

`data/membership_facts.csv` contains only nonordinal hashed member IDs, cohort, source reference, availability date, and source-completeness status. IDs derive from the published normalized name and cohort, never actual position; file order follows IDs. `data/source_manifest.csv` records URLs, source representation, hashes, retrieval times, and vintage limitations. No names, legacy/broad crosswalks, actual positions, or copyright article bodies are on the public allowlist.

The private roster, published name variants, identity suggestions, and gap inventory live in `private/`. Selection positions and unrecovered position identifiers live in `protected/`. Both directories use owner-only permissions. Code and tests are also excluded from the public allowlist because source parsing assertions contain protected verification facts.

To reproduce locally, run `python3 work/prior_membership_2007_2011/build.py`, then `python3 work/prior_membership_2007_2011/test_build.py`. The builder is offline. It uses the existing workspace Python environment only for a names-only parquet projection, reads only names/IDs/cohort from identity inputs and only IDs/cohort from the frozen r8l feature table, and checks source hashes. It never reads target columns. The review accessor rejects incomplete or provisionally attributed cohorts in model-ready mode and enforces prior-cohort membership and the independent information cutoff. An audit-only mode can list known partial membership explicitly; it is not a production pool.

The network cap was 20 initiated requests: 11 search queries, three web opens, and six HTTP requests. There were no redirect follows or retry loops. Collection stopped at the cap. The next useful source step is a complete primary 2007 list and the missing 2011 record; after that, resolve identities and independently join dated features and censored labels while preserving every selected member.

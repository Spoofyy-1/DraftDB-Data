#!/usr/bin/env python3
"""
Target competition list for the fiba_youth collector.

Selection rule (applied to the 259 competitions listed by
https://www.fiba.basketball/en/history-sitemap_index.xml on 2026-09-08):
keep every MEN'S national-team competition whose age category is U15-U19.
Women's events (slug contains "womens"), U20+, club, 3x3 and all-star events
are excluded.  Sub-continental zone events (Centrobasket, COCABA, CBC, South
American, WABA/SABA/GBA/CABA/SEA qualifiers, European Challengers, division
B/C, EYOF) are kept but ranked at the bottom of the level ladder.

Each entry: slug -> (tier, scope, age)
  tier  : "A" top division of its scope | "B" division B/C/qualifier/zone
  scope : "world" | "continental" | "zone"
  age   : 15 | 16 | 17 | 18 | 19
"""

COMPETITIONS = {
    # ---- world ------------------------------------------------------------
    "276-fiba-u19-basketball-world-cup":            ("A", "world", 19),
    "249-fiba-u17-basketball-world-cup":            ("A", "world", 17),
    # ---- Europe -----------------------------------------------------------
    "263-fiba-u18-eurobasket":                      ("A", "continental", 18),
    "261-fiba-u18-eurobasket-division-b":           ("B", "continental", 18),
    "262-fiba-u18-eurobasket-division-c":           ("B", "continental", 18),
    "264-fiba-u18-european-challengers":            ("B", "continental", 18),
    "235-fiba-u16-eurobasket":                      ("A", "continental", 16),
    "233-fiba-u16-eurobasket-division-b":           ("B", "continental", 16),
    "234-fiba-u16-eurobasket-division-c":           ("B", "continental", 16),
    "232-fiba-u16-eurobasket-qualifiers":           ("B", "continental", 16),
    "236-fiba-u16-european-challengers":            ("B", "continental", 16),
    "172-european-youth-olympic-days-basketball-tournament-for-junior-men":
                                                    ("B", "zone", 16),
    # ---- Americas ---------------------------------------------------------
    "256-fiba-u18-americup":                        ("A", "continental", 18),
    "225-fiba-u16-americup":                        ("A", "continental", 16),
    "335-south-american-u18-championship":          ("B", "zone", 18),
    "333-south-american-u17-championship":          ("B", "zone", 17),
    "331-south-american-u16-championship":          ("B", "zone", 16),
    "329-south-american-u15-championship":          ("B", "zone", 15),
    "133-centrobasket-u19-championship":            ("B", "zone", 19),
    "131-centrobasket-u18-championship":            ("B", "zone", 18),
    "128-centrobasket-u17-championship":            ("B", "zone", 17),
    "127-centrobasket-u17-championship-qualifiers": ("B", "zone", 17),
    "125-centrobasket-u16-championship":            ("B", "zone", 16),
    "123-centrobasket-u15-championship":            ("B", "zone", 15),
    "148-cocaba-u19-championship":                  ("B", "zone", 19),
    "145-cocaba-u17-championship":                  ("B", "zone", 17),
    "143-cocaba-u16-championship":                  ("B", "zone", 16),
    "141-cocaba-u15-championship":                  ("B", "zone", 15),
    "114-cbc-u18-championship":                     ("B", "zone", 18),
    # ---- Asia -------------------------------------------------------------
    "258-fiba-u18-asia-cup":                        ("A", "continental", 18),
    "257-fiba-u18-asia-cup-gba-qualifier":          ("B", "zone", 18),
    "259-fiba-u18-asia-cup-saba-qualifier":         ("B", "zone", 18),
    "260-fiba-u18-asia-cup-waba-qualifier":         ("B", "zone", 18),
    "228-fiba-u16-asia-cup":                        ("A", "continental", 16),
    "226-fiba-u16-asia-cup-caba-qualifier":         ("B", "zone", 16),
    "227-fiba-u16-asia-cup-gba-qualifier":          ("B", "zone", 16),
    "229-fiba-u16-asia-cup-saba-qualifier":         ("B", "zone", 16),
    "230-fiba-u16-asia-cup-sea-qualifiers":         ("B", "zone", 16),
    "231-fiba-u16-asia-cup-waba-qualifier":         ("B", "zone", 16),
    "346-waba-u17-championships":                   ("B", "zone", 17),
    # ---- Africa -----------------------------------------------------------
    "254-fiba-u18-afrobasket":                      ("A", "continental", 18),
    "253-fiba-u18-afrobasket-qualifiers":           ("B", "zone", 18),
    "224-fiba-u16-afrobasket":                      ("A", "continental", 16),
    "223-fiba-u16-afrobasket-qualifiers":           ("B", "zone", 16),
    "174-fiba-africa-u16-zonal-championship-for-men": ("B", "zone", 16),
    # ---- Oceania ----------------------------------------------------------
    "266-fiba-u18-oceania-championship":            ("A", "continental", 18),
    "250-fiba-u17-oceania-championship":            ("A", "continental", 17),
    "237-fiba-u16-oceania-championship":            ("A", "continental", 16),
    "221-fiba-u15-oceania-championship":            ("B", "zone", 15),
}

# Numeric level ladder required by the feature spec.
#   4 = U19 World Cup
#   3 = U17 World Cup, U18/U19 top-division continental championship
#   2 = U16/U17 top-division continental championship
#   1 = any division B/C, qualifier, challenger or sub-continental zone event


def level_of(tier, scope, age):
    if tier == "B" or scope == "zone":
        return 1
    if scope == "world":
        return 4 if age >= 19 else 3
    # continental, division A
    if age >= 18:
        return 3
    return 2


LEVEL_LABEL = {
    4: "U19 World Cup",
    3: "U17 World Cup / U18-U19 continental division A",
    2: "U16-U17 continental division A",
    1: "division B/C, qualifier, challenger or sub-continental zone event",
}

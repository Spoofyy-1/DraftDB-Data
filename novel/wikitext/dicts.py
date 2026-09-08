#!/usr/bin/env python3
"""Every dictionary used by the wikitext collector. Rule-based only; no LLM judgement.
All tables here are mirrored in README.md."""

# ---------------------------------------------------------------- kinship ---
# class of the LINKED person relative to the prospect
PARENT, SIBLING, EXTENDED, OTHER = 1, 2, 3, 4

# (regex, class, form)  form: 'of'  = "<kin> of ... [[Name]]"
#                             'poss'= "his/her <kin>, [[Name]]" (link may follow or precede)
KIN_PATTERNS = [
    (r"\b(?:the\s+)?(?:oldest|older|youngest|younger|elder|eldest|twin|half|step|adopted|adoptive|foster|biological)?[\s-]*(?:son|daughter|child)\s+of\b", PARENT, "of"),
    (r"\b(?:his|her)\s+(?:half[\s-]?|step[\s-]?|adoptive\s+|biological\s+|late\s+|estranged\s+)?(?:father|dad|mother|mom|parents)\b", PARENT, "poss"),
    (r"\b(?:the\s+)?(?:oldest|older|youngest|younger|elder|eldest|twin|half|step|identical|fraternal)?[\s-]*(?:brother|sister|sibling|twin)\s+of\b", SIBLING, "of"),
    (r"\b(?:his|her)\s+(?:oldest\s+|older\s+|youngest\s+|younger\s+|elder\s+|eldest\s+|twin\s+|half[\s-]?|step[\s-]?|identical\s+|fraternal\s+)*(?:brother|sister|sibling|twin)\b", SIBLING, "poss"),
    (r"\b(?:the\s+)?(?:nephew|niece|cousin|grandson|granddaughter|grandchild|godson)\s+of\b", EXTENDED, "of"),
    (r"\b(?:his|her)\s+(?:great[\s-]?|first\s+|second\s+)*(?:uncle|aunt|cousin|grandfather|grandmother|godfather|nephew|brother[\s-]in[\s-]law)\b", EXTENDED, "poss"),
    (r"\b(?:the\s+)?(?:father|mother|uncle|aunt|grandfather|grandmother)\s+of\b", OTHER, "of"),
]

# any kinship word (used to *exclude* sentences when attributing HS sports / handedness)
KIN_ANY = (r"\b(?:son|daughter|brother|sister|sibling|twin|father|mother|dad|mom|parents|uncle|aunt|"
           r"cousin|nephew|niece|grandson|granddaughter|grandfather|grandmother|grandparents|"
           r"stepfather|stepmother|godfather|godmother|in-law|family friend)\b")

# professional-sport tokens (relative counted as "pro in any sport")
PRO_SPORT_TOKENS = [
    r"\bNBA\b", r"National Basketball Association", r"\bWNBA\b", r"\bABA\b",
    r"\bNFL\b", r"National Football League", r"\bAFL\b", r"American Football League",
    r"\bMLB\b", r"Major League Baseball", r"\bNHL\b", r"National Hockey League",
    r"\bMLS\b", r"Major League Soccer", r"\bCFL\b", r"Canadian Football League",
    r"\bOlympic", r"Olympian", r"\bEuroLeague\b", r"\bFIBA\b", r"\bNCAA\b(?=[^.]{0,80}\bprofessional)",
    r"\bprofessional(?:ly)?\s+(?:basketball|football|soccer|baseball|volleyball|handball|rugby|hockey|tennis|athlete|player|career)",
    r"\bplayed professionally\b", r"\bpro basketball\b", r"\bNippon Professional Baseball\b",
    r"\bPremier League\b", r"\bLa Liga\b", r"\bSerie A\b", r"\brugby league\b", r"\brugby union\b",
]

# occupations that mark the linked person as a non-athlete: if one of these words sits between
# the kinship phrase and the name, the name-only match against the NBA list is rejected
NON_SPORT_OCCUPATION = (
    r"\b(?:senator|congress(?:man|woman)|representative|governor|mayor|judge|lawyer|attorney|"
    r"doctor|physician|surgeon|dentist|nurse|pastor|minister|priest|imam|rabbi|missionary|"
    r"teacher|professor|principal|educator|engineer|businessman|businesswoman|entrepreneur|"
    r"executive|banker|accountant|singer|rapper|musician|actor|actress|artist|writer|author|"
    r"journalist|broadcaster|police|officer|sheriff|soldier|marine|sergeant|veteran|firefighter|"
    r"chef|farmer|driver|barber|mechanic|janitor|pharmacist|scientist|politician)\b")

# ------------------------------------------------------ high-school sports ---
# sport -> list of regexes that count as evidence of that sport
HS_SPORTS = {
    "football": [r"\b(?:American )?football\b", r"\bgridiron\b", r"\bquarterback\b", r"\bwide receiver\b",
                 r"\btight end\b", r"\blinebacker\b", r"\bdefensive (?:end|back|lineman)\b",
                 r"\brunning back\b", r"\bsafety \(gridiron", r"\bfree safety\b", r"\bcornerback\b"],
    "track":    [r"\btrack and field\b", r"\btrack team\b", r"\bran track\b", r"\bruns track\b",
                 r"\btrack\b(?!\s+(?:record|meet of|to |for ))",
                 r"\btrack \(sport\)", r"\bhigh jump\b", r"\blong jump\b", r"\btriple jump\b",
                 r"\bshot put\b", r"\bdiscus\b", r"\bjavelin\b", r"\bhurdles\b", r"\bsprinter\b",
                 r"\b(?:100|200|400|800)[- ]met(?:er|re)s?\b", r"\brelay team\b"],
    "baseball": [r"\bbaseball\b", r"\bshortstop\b", r"\boutfielder\b", r"\bpitcher\b", r"\bcatcher \(baseball\)"],
    "soccer":   [r"\bsoccer\b", r"\bassociation football\b", r"\bfutsal\b"],
    "volleyball": [r"\bvolleyball\b"],
    "swimming": [r"\bswimming\b", r"\bswim team\b", r"\bswam\b", r"\bwater polo\b"],
    "tennis":   [r"\btennis\b"],
    "cross_country": [r"\bcross[- ]country\b"],
}

# a sport counts only if one of these participation verbs appears shortly BEFORE it
HS_VERBS = (r"\b(?:played|plays|playing|play|ran|run|running|competed|competing|competes|"
            r"participated|participates|participating|lettered|letterman|letters|starred|"
            r"stars|starring|excelled|excels|threw|throws|swam|swims|wrestled|wrestles|"
            r"member of|part of|starter (?:on|for)|standout in|took up|picked up|"
            r"three[- ]sport|two[- ]sport|multi[- ]sport|multisport|all[- ]state in|"
            r"quarterback(?:ed)? for|also did|dabbled in)\b")

# HS / early-life section headings
HS_SECTION = (r"(early life|high school|highschool|youth|prep|early years|amateur career|"
              r"childhood|early career and|schooling|junior career|recruit)")
COLLEGE_SECTION = r"(college|university|ncaa|junior college)"

# ---------------------------------------------------------------- pathway ---
# prep school / post-graduate year.  "<Name> Prep" catches the school names that carry no
# "school" token (Findlay Prep, Huntington Prep, Brewster Academy is NOT caught - see README).
PREP_RX = (r"\bprep(?:aratory)? school\b|\bpost[- ]?grad(?:uate)?(?: year| season)?\b|\bPG year\b|"
           r"\bfifth year of high school\b|\b[A-Z][a-z]{2,} Prep\b")
JUCO_RX = r"\bjunior college\b|\bJUCO\b|\bcommunity college\b|\bNJCAA\b"
TRANSFER_RX = (r"\btransferr?ed to\b|\btransferr?ed from\b|\bannounced (?:his|that he would) transfer\b|"
               r"\bentered the transfer portal\b|\btransfer portal\b|\bdecided to transfer\b|"
               r"\bwould transfer\b|\bafter transferring\b|\btransferring to\b")

# ---------------------------------------------------------------- injuries ---
# severity 3: career-scale structural injuries
SEV3 = [
    r"\b(?:tore|torn|tearing|tears)\s+(?:his |her |a |an |the )?(?:left |right )?"
    r"(?:anterior cruciate ligament|ACL)\b",
    r"\bACL (?:tear|injury|reconstruction|surgery|repair)\b",
    r"\banterior cruciate ligament\b",
    r"\bAchilles\b", r"\bmicrofracture\b", r"\bnavicular\b", r"\bLisfranc\b",
    r"\bstress fracture[^.;]{0,60}\b(?:back|lumbar|spine|spinal|vertebra|tibia|tibial|pars|femur|foot|navicular)\b",
    r"\b(?:back|lumbar|spine|spinal|vertebra|tibia|tibial|femur|foot|navicular)[^.;]{0,60}\bstress fracture\b",
    r"\bherniated disc\b", r"\bherniated disk\b", r"\bdisc herniation\b",
    r"\bspondylolysis\b", r"\bspondylolisthesis\b",
    r"\bpatellar tendon (?:tear|rupture)\b", r"\bruptured (?:his |her )?(?:patellar|Achilles|ACL)\b",
    r"\btorn (?:his |her )?(?:MCL|PCL|medial collateral ligament|posterior cruciate ligament)\b",
]
# severity 2: surgery / season-ending
SEV2 = [
    r"\bsurgery\b", r"\bsurgeries\b", r"\bsurgical\b", r"\bunderwent (?:an? )?operation\b",
    r"\barthroscopic\b", r"\bmeniscus\b", r"\bmeniscal\b",
    r"\bfractured\b", r"\bfracture\b", r"\bbroke (?:his|her) (?:hand|wrist|foot|leg|arm|finger|thumb|jaw|nose|ankle|collarbone|clavicle)\b",
    r"\bbroken (?:hand|wrist|foot|leg|arm|finger|thumb|jaw|nose|ankle|collarbone|clavicle)\b",
    r"\bout for the (?:rest of the |remainder of the )?season\b",
    r"\bseason[- ]ending (?:injury|surgery|procedure|operation|knee|ankle|foot|back|shoulder|"
    r"wrist|hand|leg|hip|elbow|torn|tear|fracture|illness)\b",
    r"\b(?:injury|surgery|torn|tear|fracture)[^.;]{0,30}\bseason[- ]ending\b",
    r"\bligament (?:injury|damage|tear|reconstruction)\b",
    r"\bmissed the (?:rest|remainder) of the season\b", r"\bsidelined for the season\b",
    r"\bredshirt(?:ed)?[^.;]{0,40}\b(?:injur|surgery|medical)\b",
    r"\bmedical redshirt\b",
    r"\b(?:tore|torn|tearing)\s+(?:his |her |a |an |the )?(?:left |right )?(?:ligament|ligaments|labrum|meniscus|"
    r"rotator cuff|hamstring|quadriceps|quad|groin|tendon|cartilage|ACL|MCL|PCL|UCL|"
    r"plantar fascia|abdominal|pectoral|calf|hip)\b",
]
# severity 1: minor / time-loss
SEV1 = [
    r"\bsprain(?:ed|s)?\b", r"\bconcussion\b", r"\bstrain(?:ed|s)?\b", r"\bbone bruise\b",
    # plural "games" only: "missed the game-winning shot" is not an injury
    r"\bmissed [^.;]{0,25}\bgames\b", r"\bmissed (?:\w+\s+){0,2}\d{1,3} games?\b",
    r"\bsidelined\b", r"\bwas placed in a cast\b",
    r"\bhyperextend(?:ed)?\b", r"\bdislocated\b", r"\btendinitis\b", r"\btendonitis\b",
    r"\bplantar fasciitis\b", r"\bshin splints\b", r"\bstitches\b", r"\bmononucleosis\b",
]
SURGERY_RX = r"\bsurgery\b|\bsurgeries\b|\bunderwent (?:an? )?operation\b|\barthroscopic (?:procedure|surgery)\b"
# negation guards (checked on the <=90 chars preceding the hit, same sentence)
NEGATION = [
    r"\b(?:did|does|do|was|were|is|are|had|has|would|will|could)\s*n[o']t\b",
    r"\bnot (?:require|need|undergo|suffer|sustain|miss|expected)\b",
    r"\bnever (?:required|needed|underwent|suffered|missed|had)\b",
    r"\bavoid(?:ed|ing|s)?\b", r"\bopted against\b", r"\bdecided against\b",
    r"\bruled out\b", r"\bwithout (?:the need for |needing |any )?(?:surgery|an operation)\b",
    r"\bno (?:surgery|structural damage|serious|significant|major)\b",
    r"\bfree of\b", r"\bin lieu of surgery\b", r"\bnon[- ]surgical\b",
    r"\bshould (?:he|she) (?:require|need)\b", r"\bif (?:he|she) (?:requires|needs|had)\b",
    r"\b(?:may|might|could)\b(?:[^.;]{0,25}?)\b(?:require|need)\b", r"\bpotentially (?:require|need)\b",
]
# sentences about other people / not the prospect
INJ_EXCLUDE = (r"\b(?:teammate|teammates|opponent|his coach|his father|his mother|his brother|"
               r"his sister|replacing|in place of|filled in for)\b|\binjur(?:y|ies) to\b")

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}
MONTHS.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
               "sept": 9, "sep": 9, "oct": 10, "nov": 11, "dec": 12})

# ------------------------------------------------------------- birthplace ---
# ISO 3166-1 numeric where the country exists today; ISO 3166-3 numeric for historical states.
COUNTRY_ID = {
    "us": 840, "usa": 840, "u s": 840, "u s a": 840, "united states": 840,
    "united states of america": 840, "america": 840,
    "canada": 124, "france": 250, "australia": 36, "spain": 724, "brazil": 76,
    "germany": 276, "west germany": 280, "east germany": 278,
    "argentina": 32, "senegal": 686, "nigeria": 566, "england": 826, "scotland": 826,
    "wales": 826, "northern ireland": 826, "united kingdom": 826, "great britain": 826,
    "lithuania": 440, "greece": 300, "china": 156, "italy": 380,
    "dominican republic": 214, "belgium": 56, "switzerland": 756, "turkey": 792,
    "netherlands": 528, "bosnia and herzegovina": 70, "japan": 392, "croatia": 191,
    "israel": 376, "mali": 466, "ukraine": 804, "jamaica": 388, "cameroon": 120,
    "mexico": 484, "russia": 643, "latvia": 428, "panama": 591, "sudan": 729,
    "south sudan": 728, "poland": 616, "slovenia": 705, "ghana": 288, "guinea": 324,
    "new zealand": 554, "sweden": 752, "haiti": 332, "denmark": 208, "gabon": 266,
    "venezuela": 862, "estonia": 233, "south korea": 410, "guadeloupe": 312,
    "dr congo": 180, "democratic republic of the congo": 180, "zaire": 180,
    "republic of congo": 178, "congo": 178, "egypt": 818, "uzbekistan": 860,
    "uruguay": 858, "dominica": 212, "tanzania": 834, "taiwan": 158, "tunisia": 788,
    "czech republic": 203, "czechia": 203, "trinidad and tobago": 780,
    "antigua and barbuda": 28, "uganda": 800, "north macedonia": 807, "macedonia": 807,
    "angola": 24, "finland": 246, "kenya": 404, "colombia": 170, "portugal": 620,
    "ireland": 372, "luxembourg": 442, "cyprus": 196, "iran": 364, "guyana": 328,
    "cape verde": 132, "nicaragua": 558, "saint lucia": 662, "slovakia": 703,
    "martinique": 474, "south africa": 710, "french guiana": 254, "serbia": 688,
    "montenegro": 499, "bulgaria": 100, "romania": 642, "hungary": 348, "austria": 40,
    "norway": 578, "iceland": 352, "georgia (country)": 268, "armenia": 51,
    "belarus": 112, "kazakhstan": 398, "india": 356, "philippines": 608,
    "bahamas": 44, "the bahamas": 44, "puerto rico": 630, "us virgin islands": 850,
    "u s virgin islands": 850, "british virgin islands": 92, "guam": 316,
    "ivory coast": 384, "cote divoire": 384, "morocco": 504, "algeria": 12,
    "libya": 434, "lebanon": 422, "syria": 760, "jordan": 400, "iraq": 368,
    "somalia": 706, "ethiopia": 231, "rwanda": 646, "burundi": 108, "chad": 148,
    "togo": 768, "benin": 204, "burkina faso": 854, "niger": 562, "gambia": 270,
    "sierra leone": 694, "liberia": 430, "guinea bissau": 624, "mozambique": 508,
    "zambia": 894, "zimbabwe": 716, "malawi": 454, "botswana": 72, "namibia": 516,
    "central african republic": 140, "equatorial guinea": 226, "madagascar": 450,
    "cuba": 192, "barbados": 52, "grenada": 308, "saint vincent and the grenadines": 670,
    "belize": 84, "costa rica": 188, "honduras": 340, "guatemala": 320,
    "el salvador": 222, "ecuador": 218, "peru": 604, "chile": 152, "bolivia": 68,
    "paraguay": 600, "curacao": 531, "aruba": 533, "suriname": 740,
    # historical states (ISO 3166-3 numeric)
    "soviet union": 810, "ussr": 810, "sfr yugoslavia": 891, "fr yugoslavia": 891,
    "yugoslavia": 891, "serbia and montenegro": 891, "czechoslovakia": 200,
}

# FIPS state codes (integers) for US births
STATE_ID = {
    "alabama": 1, "alaska": 2, "arizona": 4, "arkansas": 5, "california": 6,
    "colorado": 8, "connecticut": 9, "delaware": 10, "district of columbia": 11,
    "dc": 11, "d c": 11, "washington d c": 11, "florida": 12, "georgia": 13,
    "hawaii": 15, "idaho": 16, "illinois": 17, "indiana": 18, "iowa": 19,
    "kansas": 20, "kentucky": 21, "louisiana": 22, "maine": 23, "maryland": 24,
    "massachusetts": 25, "michigan": 26, "minnesota": 27, "mississippi": 28,
    "missouri": 29, "montana": 30, "nebraska": 31, "nevada": 32,
    "new hampshire": 33, "new jersey": 34, "new mexico": 35, "new york": 36,
    "north carolina": 37, "north dakota": 38, "ohio": 39, "oklahoma": 40,
    "oregon": 41, "pennsylvania": 42, "rhode island": 44, "south carolina": 45,
    "south dakota": 46, "tennessee": 47, "texas": 48, "utah": 49, "vermont": 50,
    "virginia": 51, "washington": 53, "west virginia": 54, "wisconsin": 55,
    "wyoming": 56,
}

# NB: "lefty" is deliberately excluded - it collides with the Lefty Driesell Award
HANDED_LEFT = r"\bleft[- ]handed\b|\bleft[- ]hander\b|\bnaturally left[- ]hand"
HANDED_RIGHT = r"\bright[- ]handed\b|\bright[- ]hander\b"

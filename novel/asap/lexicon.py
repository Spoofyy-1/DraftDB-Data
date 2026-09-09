# -*- coding: utf-8 -*-
"""Hand-built, free word lists (no LIWC licence). Every list is documented in
README.md exactly as written here.  Matching is on lowercased word tokens after
apostrophe-splitting ("i'll" -> "i" + "'ll"), so contraction suffixes are
listed as their own tokens ('ll, 're, 'm, 've, n't, 's, 'd)."""

FUTURE = set("""will 'll wont won't shall gonna gunna tomorrow tomorrows future
futures next upcoming soon later eventually someday somedays plan plans planning
planned ahead forthcoming afterwards afterward""".split())
# "going to" and "about to" are counted by FUTURE_PHRASES below.
# phrases must NOT contain a word that is already a FUTURE token, otherwise the
# same span would be counted twice ("next year" -> "next" + "next year")
FUTURE_PHRASES = ["going to", "about to", "fixing to", "hoping to",
                  "looking forward", "down the road"]

PRESENT = set("""am 'm is 's are 're be being do does don't doesn't have has
haven't hasn't can can't cannot want wants need needs know knows think thinks
feel feels try tries trying play plays playing go goes going get gets getting
make makes making see sees say says come comes take takes like likes love loves
work works working stay stays staying keep keeps keeping now today currently
nowadays presently right-now""".split())

PAST = set("""was were wasn't weren't had did didn't been went got said thought
played came took made saw knew felt gave came ran won lost came told found
brought became began grew held kept left met put ran sat spoke stood took taught
told understood wore wrote used had've""".split())
# plus the regex rule PAST_ED below

CONJ = set("""and but or so because although though while whereas however plus
therefore thus yet since unless whether nor also then besides moreover
furthermore anyway otherwise""".split())

NEGATE = set("""no not never none nobody nothing nowhere neither nor cannot
n't ain't without can't don't didn't doesn't won't wouldn't shouldn't couldn't
isn't aren't wasn't weren't haven't hasn't hadn't""".split())

CERTAIN = set("""always never definitely absolutely certain certainly sure
surely totally completely obviously clearly undoubtedly guarantee guaranteed
must all every everything everyone everybody entirely fully forever
undeniably truly indeed exactly precisely 100 hundred""".split())

TENTAT = set("""maybe perhaps probably possibly possible might could guess
guessing hopefully somewhat seems seem seemed kinda sorta somehow
apparently supposedly assume assuming suppose chance chances depends depend
unsure""".split())
# "kind"/"sort"/"whatever" are deliberately NOT tokens: only the hedging phrases
TENTAT_PHRASES = ["kind of", "sort of", "or something", "or whatever",
                  "a little bit"]

POSEMO = set("""good great awesome amazing excellent fantastic wonderful happy
happiness excited exciting excitement fun enjoy enjoyed enjoying love loved
loves proud pride blessed blessing thankful thanks thank grateful glad
positive positivity best better perfect beautiful special incredible
tremendous outstanding terrific solid strong confident confidence comfortable
smooth easy easier ready willing hope hopeful smile smiling laugh laughing
win winning won victory success successful successfully improve improved
improvement opportunity opportunities honored honour honor honored respect
respectful appreciate appreciated appreciation cool nice fine fair worthy""".split())

NEGEMO = set("""bad worse worst terrible awful horrible sad sadly unhappy angry
mad upset frustrated frustrating frustration disappointed disappointing
disappointment tough hard difficult struggle struggled struggling struggles
hurt hurting injury injured pain painful sorry regret afraid scared fear
nervous anxious worry worried stress stressful annoyed annoying hate hated
lose losing lost loss losses fail failed failure failing mistake mistakes
wrong problem problems trouble weak weakness weaknesses miss missed missing
critic criticism doubt doubts""".split())

I_WORDS = set("i me my mine myself i'm i've i'll i'd".split())
WE_WORDS = set("we us our ours ourselves we're we've we'll we'd let's".split())
YOU_WORDS = set("you your yours yourself yourselves you're you've you'll y'all".split())
THEY_WORDS = set("he him his she her hers they them their theirs himself herself themselves he's she's they're".split())

ARTICLES = set("a an the".split())

PREPS = set("""about above across after against along among around at before
behind below beneath beside besides between beyond by down during except for
from in inside into near of off on onto out outside over past since through
throughout to toward towards under underneath until up upon with within
without""".split())

AUXVERB = set("""am is are was were be been being have has had do does did
will would shall should can could may might must 'm 're 's 've 'll 'd""".split())

QUANT = set("""all any both each every few little lot lots many more most much
several some enough less least plenty couple bunch""".split())

# LIWC-ish "verbs": auxiliaries + the common-verb lists + -ing forms (regex)
COMMON_VERBS = PRESENT | PAST | AUXVERB | set("""said say tell told talk talked
talking give gave given put putting run running shoot shooting shot score
scored scoring guard guarding pass passed passing rebound rebounding defend
defending compete competing competed learn learned learning grow growing
build building help helped helping start started starting finish finished
""".split())

# Newman/Pennebaker (2003) deception cues -> our transparent "authenticity"
EXCLUSIVE = set("""but without exclude excluding except unless however
although though rather than whereas besides else other others otherwise""".split())
MOTION = set("""go goes going went gone come comes coming came move moves moved
moving walk walked walking run runs running ran arrive arrived carry carried
drive drove driven bring brought take took travel traveled leave left enter
""".split())

FILLER = set("""um uh er hmm well basically literally honestly actually
really just yeah yep okay ok man""".split())
FILLER_PHRASES = ["you know", "i mean", "kind of", "sort of", "at the end of the day"]

SOCIAL = set("""team teams teammate teammates coach coaches coaching guys guy
family families brother brothers sister sisters mom dad mother father parents
friend friends people fans crowd program staff group everybody everyone
together us we our""".split())

ACHIEVE = set("""work works worked working hard harder hardest win wins winning
won best better improve improved improving improvement goal goals compete
competing competitive prepare prepared preparation earn earned earning
achieve achieved achievement succeed success successful effort focus focused
determined discipline disciplined grind push pushed pushing challenge
challenges opportunity practice practices practicing""".split())

DICTS = {
    "future":   FUTURE,
    "present":  PRESENT,
    "past":     PAST,
    "conj":     CONJ,
    "negate":   NEGATE,
    "certain":  CERTAIN,
    "tentat":   TENTAT,
    "posemo":   POSEMO,
    "negemo":   NEGEMO,
    "i":        I_WORDS,
    "we":       WE_WORDS,
    "you":      YOU_WORDS,
    "they":     THEY_WORDS,
    "article":  ARTICLES,
    "prep":     PREPS,
    "auxverb":  AUXVERB,
    "quant":    QUANT,
    "verb":     COMMON_VERBS,
    "exclusive": EXCLUSIVE,
    "motion":   MOTION,
    "filler":   FILLER,
    "social":   SOCIAL,
    "achieve":  ACHIEVE,
}

PHRASE_DICTS = {
    "future":  FUTURE_PHRASES,
    "tentat":  TENTAT_PHRASES,
    "filler":  FILLER_PHRASES,
}

# function words = pronouns + articles + preps + auxverbs + conjunctions
#                  + negations + quantifiers
FUNCTION = (I_WORDS | WE_WORDS | YOU_WORDS | THEY_WORDS | ARTICLES | PREPS |
            AUXVERB | CONJ | NEGATE | QUANT |
            set("it its this that these those there here what which who whom "
                "whose when where why how".split()))
DICTS["function"] = FUNCTION

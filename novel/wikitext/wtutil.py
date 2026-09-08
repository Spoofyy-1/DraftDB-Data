#!/usr/bin/env python3
"""Shared wikitext parsing helpers (rule-based only: regex + dictionaries)."""
import re
import unicodedata

# ---------------------------------------------------------------- cleaning ---
RE_COMMENT = re.compile(r"<!--.*?-->", re.S)
RE_REF_PAIR = re.compile(r"<ref(?![^>]*/\s*>)[^>]*>.*?</ref>", re.S | re.I)
RE_REF_SELF = re.compile(r"<ref[^>]*/\s*>", re.S | re.I)
RE_GALLERY = re.compile(r"<(gallery|timeline|imagemap|math|score)[^>]*>.*?</\1>", re.S | re.I)
RE_TABLE = re.compile(r"^\{\|.*?^\|\}", re.S | re.M)
RE_FILE = re.compile(r"\[\[(?:File|Image|Category)\s*:[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]", re.I)
RE_TAG = re.compile(r"<[^>]{1,200}>")
RE_HEAD = re.compile(r"^(={2,6})\s*(.*?)\s*\1\s*$", re.M)


def strip_templates(s: str, rounds: int = 8) -> str:
    """Remove {{...}} innermost-out (templates are markup noise for prose rules)."""
    inner = re.compile(r"\{\{[^{}]*\}\}")
    for _ in range(rounds):
        s, n = inner.subn(" ", s)
        if not n:
            break
    return s


def clean_keep_links(s: str) -> str:
    """Strip refs/comments/tables/templates/tags but KEEP [[wikilinks]] intact."""
    s = RE_COMMENT.sub(" ", s)
    s = RE_GALLERY.sub(" ", s)
    s = RE_REF_SELF.sub(" ", s)      # self-closing <ref name=x /> FIRST
    s = RE_REF_PAIR.sub(" ", s)
    s = RE_TABLE.sub(" ", s)
    s = RE_FILE.sub(" ", s)
    s = strip_templates(s)
    s = RE_TAG.sub(" ", s)
    s = s.replace("'''", "").replace("''", "")
    s = re.sub(r"\[(?:https?|//)\S+?(?:\s+([^\]]*))?\]", r"\1", s)   # bare ext links
    s = re.sub(r"^[*#:;]+\s*", " ", s, flags=re.M)
    s = RE_HEAD.sub("\n", s)                 # headings are sentence/paragraph breaks
    return re.sub(r"[ \t]+", " ", s)


def unlink(s: str) -> str:
    """[[A|B]] -> B, [[A]] -> A  (display text)."""
    s = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    return re.sub(r"[ \t]+", " ", s).strip()   # newlines kept: they delimit paragraphs


def plain(s: str) -> str:
    return unlink(clean_keep_links(s))


# --------------------------------------------------------------- sections ---
def sections(wikitext: str):
    """[(heading, body_with_links), ...]; heading '' == lead."""
    out = []
    ms = list(RE_HEAD.finditer(wikitext))
    lead_end = ms[0].start() if ms else len(wikitext)
    out.append(("", wikitext[:lead_end]))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(wikitext)
        out.append((m.group(2), wikitext[m.end():end]))
    return out


def infobox_field(wikitext: str, name: str):
    """Value of an infobox field (raw wikitext), or None."""
    m = re.search(r"^\s*\|\s*" + name.replace("_", "[_ ]") +
                  r"\s*=[ \t]*(.*?)(?=^\s*\|\s*[A-Za-z_0-9][A-Za-z_0-9 ]{0,30}=|^\s*\}\})",
                  wikitext, re.M | re.S)
    if not m:
        return None
    v = m.group(1).strip()
    return v or None


# -------------------------------------------------------------- sentences ---
ABBR = r"(?:Mr|Mrs|Ms|Dr|Jr|Sr|St|Mt|No|vs|etc|Inc|Co|Ltd|Ave|Rev|Gen|Col|Sgt|Prof|Fr|U\.S|U\.K|D\.C|Ph\.D|B\.C|A\.D|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
RE_SPLIT_PT = re.compile(r"[.!?][\"')\]]*\s+(?=[A-Z0-9\[])")
RE_ABBR_END = re.compile(r"(?:^|[\s(\[\"])" + ABBR + r"\.$", re.I)


def sentences(text_with_links: str):
    """Split cleaned text into sentences (abbreviation-aware); wikilinks preserved."""
    out = []
    for para in re.split(r"\n{1,}", text_with_links):
        para = para.strip()
        if not para:
            continue
        start = 0
        for m in RE_SPLIT_PT.finditer(para):
            cut = m.start() + 1
            piece = para[start:cut]
            if RE_ABBR_END.search(piece.rstrip()):
                continue                      # abbreviation, not a sentence end
            piece = piece.strip()
            if piece:
                out.append(piece)
            start = m.end()
        tail = para[start:].strip()
        if tail:
            out.append(tail)
    return out


# ------------------------------------------------------------------ links ---
RE_LINK = re.compile(r"\[\[([^\]\[|]{1,120})(?:\|([^\]\[]{0,120}))?\]\]")
RE_DISAMB = re.compile(r"\s*\([^)]*\)\s*$")
NS_PREFIX = re.compile(r"^\s*:?[a-z-]{2,12}\s*:\s*")   # ':lt:', 'wikt:' interwiki/ns prefixes


def links(sentence: str):
    """[(start, end, target, display)] for each [[...]] in the sentence."""
    out = []
    for m in RE_LINK.finditer(sentence):
        tgt = m.group(1).strip()
        disp = (m.group(2) or tgt).strip()
        out.append((m.start(), m.end(), tgt, disp))
    return out


SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?\s*$")


def norm_name(s: str) -> str:
    """Accent-strip, lowercase, drop punctuation/suffixes -> matching key."""
    s = NS_PREFIX.sub("", s)
    s = RE_DISAMB.sub("", s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("’", "'").lower()
    s = re.sub(r"[.'`ʼ]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    for _ in range(2):
        s2 = SUFFIX.sub("", s).strip()
        if s2 == s:
            break
        s = s2
    return re.sub(r"\s+", " ", s)


NON_PERSON = re.compile(
    r"\b(university|universities|college|school|academy|league|association|conference|"
    r"team|teams|club|olympic|olympics|games|championship|championships|tournament|cup|"
    r"basketball|football|baseball|soccer|hockey|nba|wnba|nfl|mlb|nhl|ncaa|fiba|euroleague|"
    r"draft|award|trophy|state|county|city|national|american|united|company|magazine|news|"
    r"television|network|academy|institute|program|series|season|region|province|republic|"
    r"island|islands|army|navy|force|church|center|centre|arena|stadium|hall|fame|"
    r"contest|classic|finals|final|invitational|open|bowl|medal|festival|showcase|camp|"
    r"hornets|warriors|lakers|celtics|bulls|knicks|nets|heat|magic|wizards|pistons|pacers|"
    r"bucks|cavaliers|raptors|hawks|nuggets|timberwolves|thunder|blazers|jazz|kings|suns|"
    r"clippers|mavericks|rockets|grizzlies|pelicans|spurs|76ers|sixers|supersonics|bobcats|"
    r"sonics|hornet|jets|giants|eagles|cowboys|packers|steelers|yankees|dodgers|red sox)\b", re.I)
PARTICLES = {"de", "van", "der", "den", "da", "di", "dos", "del", "la", "le", "el", "bin", "al", "mc", "st"}


def person_like(target: str) -> bool:
    """Heuristic (documented): 2-5 tokens, capitalised, no institution keyword, no digits."""
    t = NS_PREFIX.sub("", target)
    t = RE_DISAMB.sub("", t).strip()
    if not t or any(ch.isdigit() for ch in t):
        return False
    if NON_PERSON.search(t):
        return False
    toks = t.split()
    if not (2 <= len(toks) <= 5):
        return False
    for tk in toks:
        if tk.lower().strip(".") in PARTICLES:
            continue
        if not tk[0].isupper():
            return False
    return True

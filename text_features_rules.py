"""Deterministic text features from each player's Wikipedia article AS OF THE NIGHT BEFORE HIS DRAFT (wiki_raw/prerev_*.json).
No language model anywhere: every feature is a count or a regex match against a fixed, published word list, so nothing
about how the player later turned out can leak in. The lists below ARE the definition (copied into docs/TEXT_FEATURES.md)."""
import json,re,glob,csv,collections
LEX={
 "hype":      [r"\btop[- ]\d+ (prospect|pick|player)",r"\blottery\b",r"\bfive[- ]star\b",r"\bconsensus\b",r"\bprojected\b",r"\bfranchise\b",r"\bphenom\b",r"\bgenerational\b",r"\belite\b",r"\bbest (player|prospect)\b",r"\bnumber[- ]one\b",r"\bno\. ?1\b",r"\bhighly[- ]touted\b",r"\bmcdonald'?s all[- ]american\b",r"\bplayer of the year\b",r"\ball[- ]american\b",r"\bnational champion",r"\bmost valuable player\b|\bmvp\b"],
 "injury":    [r"\binjur(y|ies|ed)\b",r"\bsurger(y|ies)\b",r"\btorn\b",r"\btear\b",r"\bfractur",r"\bsprain",r"\bconcussion",r"\bsidelined\b",r"\bmissed .{0,20}(games|season|weeks|months)",r"\bstress (fracture|reaction)\b",r"\bacl\b",r"\bmeniscus\b",r"\bachilles\b",r"\bredshirt",r"\bout for the season\b"],
 "character": [r"\bsuspend",r"\barrest",r"\bdismiss",r"\bineligib",r"\bacademic",r"\bcontrovers",r"\bcharged with\b",r"\bviolat",r"\bkicked off\b",r"\bdisciplin",r"\bfailed (a )?drug test\b",r"\bmisdemeanor|\bfelony\b"],
 "pro_family":[r"\b(father|mother|dad|mom|brother|sister|uncle|cousin|nephew|son|daughter|twin)\b.{0,120}\b(played|plays|career|professional|nba|wnba|euroleague|drafted)\b",r"\b(son|daughter|brother|sister|nephew|cousin) of\b.{0,80}\b(basketball|nba|wnba|player)\b"],
 "nba_family":[r"\b(father|mother|dad|mom|brother|sister|uncle|cousin|nephew|son|daughter|twin)\b.{0,120}\b(nba|wnba)\b",r"\b(former|ex-)?(nba|wnba) (player|guard|forward|center)\b.{0,60}\b(father|mother|brother|sister|uncle|cousin)\b"],
 "breakout":  [r"\bbreakout\b",r"\bimprov(ed|ement|ing)\b",r"\btook a leap\b",r"\bemerg(ed|ing)\b",r"\bris(er|ing|en)\b",r"\bdevelop(ed|ment|ing)\b",r"\bgrowth spurt\b",r"\bgrew (from|to|\d)",r"\blate bloomer\b",r"\bunranked\b",r"\bwalk[- ]on\b",r"\blightly recruited\b",r"\bunder[- ]the[- ]radar\b"],
 "shooter":   [r"\bshoot(er|ing)\b",r"\bthree[- ]point",r"\b3[- ]point",r"\bjump ?shot\b",r"\bcatch[- ]and[- ]shoot\b",r"\bfree[- ]throw",r"\brange\b",r"\bstroke\b"],
 "athlete":   [r"\bathletic",r"\bexplosiv",r"\bvertical\b",r"\bleap",r"\bdunk",r"\bwingspan\b",r"\bspeed\b",r"\bquickness\b",r"\bbounce\b",r"\bmotor\b"],
 "playmaker": [r"\bpassing\b",r"\bpasser\b",r"\bplaymak",r"\bassists?\b",r"\bcourt vision\b",r"\bvision\b",r"\bball[- ]handl",r"\bpoint guard\b",r"\bfacilitat"],
 "defender":  [r"\bdefen(se|sive|der)\b",r"\brim protect",r"\bblocks?\b",r"\bsteals?\b",r"\bshot[- ]block",r"\blockdown\b",r"\bversatil"],
 "size":      [r"\b(7|six|seven)[- ]foot",r"\bwingspan\b",r"\blength\b",r"\bundersized\b",r"\bsize for (his|the) position\b",r"\bstanding reach\b"],
 "national":  [r"\bnational team\b",r"\bfiba\b",r"\bu1[6-9]\b|\bunder-1[6-9]\b",r"\bworld cup\b",r"\beurobasket\b",r"\bolympi",r"\bgold medal\b|\bsilver medal\b|\bbronze medal\b"],
 "transfer":  [r"\btransferr?(ed|ing)\b",r"\btransfer portal\b"],
 "left":      [r"\bleft[- ]handed\b",r"\bsouthpaw\b"],
 "prep":      [r"\bimg academy\b",r"\bmontverde\b",r"\boak hill\b",r"\bsunrise christian\b",r"\bfindlay prep\b",r"\bla lumiere\b",r"\bprolific prep\b",r"\bhuntington prep\b",r"\bbrewster academy\b",r"\bwasatch academy\b",r"\bnba academy\b",r"\bovertime elite\b"],
 "positive":  [r"\bbest\b",r"\boutstanding\b",r"\bexceptional\b",r"\bdominant\b",r"\bstar\b",r"\bstandout\b",r"\bremarkable\b",r"\bimpressive\b",r"\bhonou?rs?\b",r"\bawards?\b",r"\brecord\b",r"\bled (the|his)\b"],
 "negative":  [r"\bstruggl",r"\bdisappoint",r"\binconsisten",r"\bconcern",r"\bquestion(s|ed|able)?\b",r"\bdecline",r"\bpoor\b",r"\bbench(ed)?\b",r"\bcriticis",r"\bslump\b",r"\blimited\b",r"\bweakness"],
}
def clean(wt):
    wt=re.sub(r"\{\{[^{}]*\}\}","",wt); wt=re.sub(r"\{\{[^{}]*\}\}","",wt); wt=re.sub(r"<ref[^>]*/>|<ref.*?</ref>","",wt,flags=re.S)
    wt=re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]",r"\1",wt); wt=re.sub(r"'{2,}","",wt); wt=re.sub(r"<[^>]+>","",wt); return wt
def pick_num(text):
    m=re.findall(r"projected[^.]{0,60}?\b(?:no\.?|number|#)\s?(\d{1,2})\b|\btop[- ](\d{1,2})\b (?:pick|prospect)",text,flags=re.I)
    vals=[int(a or b) for a,b in m if (a or b)]; return min(vals) if vals else None
out=[]; c=collections.Counter()
for fp in sorted(glob.glob("wiki_raw/prerev_*.json")):
    d=json.load(open(fp)); pid=fp.split("prerev_")[1][:-5]
    if d.get("status")!="ok": out.append(dict(pid=pid,txt_exists=0)); c[d.get("status")]+=1; continue
    raw=d["wikitext"]; text=clean(raw); words=len(re.findall(r"\b\w+\b",text)) or 1
    r=dict(pid=pid,txt_exists=1,txt_words=words,txt_refs=len(re.findall(r"<ref",raw)),txt_sections=len(re.findall(r"^==+[^=]",raw,flags=re.M)),txt_size_bytes=d.get("size"),txt_projected_pick=pick_num(text))
    for k,pats in LEX.items():
        n=sum(len(re.findall(p,text,flags=re.I)) for p in pats); r[f"txt_{k}"]=n; r[f"txt_{k}_per1k"]=round(1000*n/words,3)
    r["txt_pro_family"]=int(r["txt_pro_family"]>0); r["txt_nba_family"]=int(r["txt_nba_family"]>0); r["txt_left"]=int(r["txt_left"]>0); r["txt_prep"]=int(r["txt_prep"]>0); r["txt_transfer"]=int(r["txt_transfer"]>0)
    r["txt_tone"]=round((r["txt_positive"]-r["txt_negative"])/(r["txt_positive"]+r["txt_negative"]+3),3)
    out.append(r); c["ok"]+=1
cols=["pid"]+sorted({k for x in out for k in x if k!="pid"})
with open("txt_features.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); [w.writerow(x) for x in out]
print("text features:",dict(c),"cols",len(cols))

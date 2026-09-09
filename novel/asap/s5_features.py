# -*- coding: utf-8 -*-
"""Stage 5: pool each player's pre-draft answer text and emit numeric features."""
import csv, gzip, json, os, re, sys, collections, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asaplib import RAW
import lexicon
from s4_answers import build_plan, CUTOFF, WINDOW_YEARS

HERE = os.path.dirname(os.path.abspath(__file__))
IDENT = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"

TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)*|'[a-z]+")
ED_RE = re.compile(r"^[a-z]{3,}ed$")
ING_RE = re.compile(r"^[a-z]{4,}ing$")
ED_STOP = set("""need indeed speed exceed succeed proceed embed shed sled wed
agreed breed creed freed greed tweed seed feed deed bleed instead ahead
head sacred hundred red bed fed led""".split())
ING_STOP = set("""thing things king kings ring rings spring string morning
evening during something everything nothing anything ceiling wing wings
sibling meeting building""".split())   # 'building','meeting' kept out of verbs


def tokens(text):
    t = text.lower().replace(u"’", "'").replace(u"‘", "'")
    return TOKEN_RE.findall(t)


def keys(tok):
    """Match keys for one token: itself plus contraction head/suffix."""
    k = {tok}
    if "'" in tok:
        h, _, s = tok.partition("'")
        if h:
            k.add(h)
        k.add("'" + s)
        if s in ("t",):
            k.add("n't")
        if h.endswith("n") and s == "t":
            k.add("n't"); k.add(h[:-1])
    return k


PAREN_RE = re.compile(r"\([^)]{0,80}\)")     # (Laughter.) (Applause) (indiscernible)
BRACKET_RE = re.compile(r"\[[^\]]{0,80}\]")   # [Penny] - transcriptionist insertions


def demojibake(t, rounds=3):
    """The archive serves ISO-8859-1 headers over (sometimes doubly) UTF-8
    encoded bytes, so latin-1 decoding leaves 'Ã'/'Â' sequences - almost always
    non-breaking spaces.  latin-1 is byte-lossless, so re-encoding and decoding
    as UTF-8 recovers the original characters without re-crawling."""
    for _ in range(rounds):
        if "\u00c3" not in t and "\u00c2" not in t:
            break
        try:
            t2 = t.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if t2 == t:
            break
        t = t2
    return t.replace(u"\xa0", " ")


def clean(text):
    """Drop stage directions and transcriptionist insertions: they are not the
    player's own words."""
    return BRACKET_RE.sub(" ", PAREN_RE.sub(" ", demojibake(text)))


def count_text(text):
    text = clean(text)
    toks = tokens(text)
    n = len(toks)
    cnt = collections.Counter()
    for tk in toks:
        ks = keys(tk)
        for name, d in lexicon.DICTS.items():
            if ks & d:
                cnt[name] += 1
        if ED_RE.match(tk) and tk not in ED_STOP:
            if not (ks & lexicon.DICTS["past"]):
                cnt["past"] += 1
            if not (ks & lexicon.DICTS["verb"]):
                cnt["verb"] += 1
        elif ING_RE.match(tk) and tk not in ING_STOP:
            if not (ks & lexicon.DICTS["verb"]):
                cnt["verb"] += 1
    low = " " + re.sub(r"\s+", " ", text.lower()) + " "
    for name, phrases in lexicon.PHRASE_DICTS.items():
        for ph in phrases:
            cnt[name] += len(re.findall(r"(?<![a-z])" + re.escape(ph) + r"(?![a-z])", low))
    long_w = sum(1 for t in toks if len(t.replace("'", "")) >= 7)
    sents = len([s for s in re.split(r"[.!?]+", text) if s.strip()])
    qm = text.count("?")
    return n, cnt, long_w, sents, qm, toks


def ttr(toks, chunk=500):
    vals = []
    for i in range(0, len(toks) - chunk + 1, chunk):
        c = toks[i:i + chunk]
        vals.append(len(set(c)) / float(chunk))
    return sum(vals) / len(vals) if vals else None


def main():
    plan, dropped, amb_person, amb_name = build_plan()
    ambiguous = amb_person | amb_name
    # pid -> list of (iv, asap, index_date)
    want = collections.defaultdict(list)
    for pid, aid, iid, date, title in plan:
        want[pid].append((iid, aid, date))

    cache = {}
    if os.path.exists(os.path.join(RAW, "answers.jsonl.gz")):
        with gzip.open(os.path.join(RAW, "answers.jsonl.gz"), "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                cache[(r["iv"], r["asap"])] = r

    ident = list(csv.DictReader(open(IDENT)))
    dicts = sorted(lexicon.DICTS)
    cols = (["pid", "li_has_transcript", "li_n_transcripts", "li_n_listed",
             "li_silent_share", "li_n_answers",
             "li_total_words", "li_words_per_answer", "li_words_per_sentence",
             "li_long_word_pct", "li_ttr500", "li_qmark_rate", "li_solo_share",
             "li_days_to_draft_last", "li_days_to_draft_first", "li_span_days",
             "li_authenticity", "li_i_we_ratio"] +
            ["li_r_" + d for d in dicts])

    prov = open(os.path.join(HERE, "provenance.csv"), "w", newline="")
    pw = csv.writer(prov); pw.writerow(["pid", "url", "date", "event_kind"])
    out = open(os.path.join(HERE, "features.csv"), "w", newline="")
    w = csv.writer(out); w.writerow(cols)

    n_datedrop = [0]
    cov = collections.Counter()
    spot = []
    bandof = lambda y: "2000-07" if y <= 2007 else ("2008-18" if y <= 2018 else "2019-26")
    for r in ident:
        pid, dy = r["pid"], int(r["draft_year"])
        band = "2000-07" if dy <= 2007 else ("2008-18" if dy <= 2018 else "2019-26")
        row = {c: "" for c in cols}
        row["pid"] = pid
        if pid in ambiguous:
            cov[(band, "ambiguous")] += 1
            w.writerow([row[c] for c in cols]); continue
        # A transcript is kept only if BOTH the archive index date and the
        # transcript page's own <h2> date satisfy the pre-draft window.  They
        # disagree for ~0.8% of records; requiring both makes leakage
        # impossible whichever one is right.
        cut = CUTOFF[dy]
        wstart = "%04d-07-01" % (dy - WINDOW_YEARS)
        listed = []
        for i, a, idate in want.get(pid, []):
            rec = cache.get((i, a))
            if rec is None:
                continue
            pdate = rec.get("date") or ""
            if not pdate:
                continue
            if max(idate, pdate) >= cut or min(idate, pdate) < wstart:
                n_datedrop[0] += 1
                continue
            listed.append(rec)
        recs = [x for x in listed if x["text"].strip()]
        n_tr = len(recs)
        if listed:
            row["li_n_listed"] = len(listed)
            row["li_silent_share"] = round(1.0 - n_tr / float(len(listed)), 4)
        row["li_has_transcript"] = 1 if n_tr else 0
        row["li_n_transcripts"] = n_tr
        cov[(band, "has" if n_tr else "none")] += 1
        if not n_tr:
            row["li_total_words"] = 0
            row["li_n_answers"] = 0
            w.writerow([row[c] for c in cols]); continue
        text = "\n".join(x["text"] for x in recs)
        n, cnt, long_w, sents, qm, toks = count_text(text)
        turns = sum(x.get("n_turns", 0) or 0 for x in recs) or len(recs)
        row["li_total_words"] = n
        row["li_n_answers"] = turns
        row["li_words_per_answer"] = round(n / float(turns), 3) if turns else ""
        row["li_words_per_sentence"] = round(n / float(sents), 3) if sents else ""
        row["li_long_word_pct"] = round(100.0 * long_w / n, 4) if n else ""
        t = ttr(toks)
        row["li_ttr500"] = round(t, 5) if t is not None else ""
        row["li_qmark_rate"] = round(1000.0 * qm / n, 4)
        solo = sum(1 for x in recs if x.get("n_spk", 0) == 1)
        row["li_solo_share"] = round(solo / float(n_tr), 4)
        cutd = datetime.date(*map(int, CUTOFF[dy].split("-")))
        ds = sorted(datetime.date(*map(int, x["date"].split("-")))
                    for x in recs if x["date"])
        if ds:
            row["li_days_to_draft_last"] = (cutd - ds[-1]).days
            row["li_days_to_draft_first"] = (cutd - ds[0]).days
            row["li_span_days"] = (ds[-1] - ds[0]).days
        rates = {}
        for d in dicts:
            rates[d] = 1000.0 * cnt[d] / n
            row["li_r_" + d] = round(rates[d], 4)
        row["li_authenticity"] = round(rates["i"] + rates["exclusive"]
                                       - rates["negemo"] - rates["motion"], 4)
        den = rates["i"] + rates["we"]
        row["li_i_we_ratio"] = round(rates["i"] / den, 5) if den > 0 else ""
        w.writerow([row[c] for c in cols])
        for x in recs:
            pw.writerow([pid,
                         "http://www.asapsports.com/show_interview.php?id=%s" % x["iv"],
                         x["date"], x["event"][:80]])
        spot.append((r["player_name"], dy, n_tr, n, rates["future"]))
    out.close(); prov.close()

    lines = ["| draft years | players | has transcript | none | ambiguous | median words (of those with text) | median transcripts |",
             "|---|---|---|---|---|---|---|"]
    def med(v):
        v = sorted(v)
        return "" if not v else (v[len(v)//2] if len(v) % 2 else
                                 round((v[len(v)//2 - 1] + v[len(v)//2]) / 2.0, 1))
    print("\ncoverage by draft-year band")
    for band in ("2000-07", "2008-18", "2019-26"):
        h = cov[(band, "has")]; nn = cov[(band, "none")]; a = cov[(band, "ambiguous")]
        tot = h + nn + a
        print("  %-8s n=%4d  has_transcript=%4d (%5.1f%%)  none=%4d  ambiguous=%3d"
              % (band, tot, h, 100.0 * h / max(tot, 1), nn, a))
        ww = [x[3] for x in spot if bandof(x[1]) == band]
        tt = [x[2] for x in spot if bandof(x[1]) == band]
        lines.append("| %s | %d | %d (%.1f%%) | %d | %d | %s | %s |"
                     % (band, tot, h, 100.0 * h / max(tot, 1), nn, a, med(ww), med(tt)))
    rd = os.path.join(HERE, "README.md")
    txt = open(rd, encoding="utf-8").read()
    body = ("\n".join(lines) +
            "\n\nBands follow `../COLLECTOR_RULES.md` (2019-26 also holds the 61 "
            "players with `draft_year = 2026`).  \"Ambiguous\" players are listed in "
            "`unmatched.csv` and carry an EMPTY `li_has_transcript`.\n")
    txt = re.sub(r"(?s)<!--COVERAGE-->.*?<!--/COVERAGE-->",
                 "<!--COVERAGE-->\n" + body + "<!--/COVERAGE-->", txt)
    open(rd, "w", encoding="utf-8").write(txt)
    # spot-check file (contains names) is written OUTSIDE the repo dir on purpose
    sp = os.environ.get("ASAP_SPOT", "/private/tmp/claude-501/-Users-kennakao-nba/6b23c15b-6018-47b3-9476-45353eadffc2/scratchpad/_spot.json")
    json.dump([list(x) for x in spot], open(sp, "w"))
    print("players with text:", len(spot))
    print("records dropped on the two-date agreement rule:", n_datedrop[0])


if __name__ == "__main__":
    main()

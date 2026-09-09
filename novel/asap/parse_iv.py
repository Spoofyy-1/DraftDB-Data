# -*- coding: utf-8 -*-
"""Parse an ASAP show_interview.php page: event / date / speakers, and split the
body into speaker-attributed blocks.  Pure regex + a state machine, no LLM."""
import re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asaplib import norm_name, unescape

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}

H1_RE = re.compile(r"<h1>(?:<a[^>]*>)?(.*?)(?:</a>)?</h1>", re.S)
H2_RE = re.compile(r"<h2>\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\s*</h2>", re.S)
H3_RE = re.compile(r'<h3>\s*<a[^>]*show_player\.php\?id=(\d+)"?[^>]*>(.*?)</a>\s*</h3>', re.S)
H3_PLAIN_RE = re.compile(r"<h3>(?!\s*<a)(.*?)</h3>", re.S)
END_RE = re.compile(r"End\s+of\s+FastScripts|FastScripts\s+Transcript\s+by\s+ASAP|ASAP\s+Sports\s+&bull;|About\s+ASAP\s+Sports\s*</a>", re.I)
# a speaker label at the start of a block: run of caps/punct then a colon
LABEL_RE = re.compile(r"^\s*([A-Z][A-Za-z0-9 .,'\u2019\-]{1,58}?)\s*:\s*(.*)$", re.S)


def _is_label(lab):
    """Speaker labels are shouted (ALL CAPS, allowing McDERMOTT / O'BRIEN).
    Requires <= 6 words and >= 60% of letters uppercase, which rejects ordinary
    sentences that happen to contain a colon."""
    letters = [c for c in lab if c.isalpha()]
    if len(letters) < 2 or len(lab.split()) > 6:
        return False
    up = sum(1 for c in letters if c.isupper())
    return up >= 0.6 * len(letters)
Q_RE = re.compile(r"^\s*(Q\.|Q\b|QUESTION\s*:)", re.I)


def strip_tags(s):
    s = re.sub(r"(?is)<!--.*?-->", " ", s)
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?i)</p\s*>|<p[^>]*>|<br\s*/?>|</div>|</tr>|</table>", "\n", s)
    s = re.sub(r"<[^>]*>", "", s)
    return unescape(s)


def parse(html):
    """-> dict(event, date, speakers=[(asap_id, name)], blocks=[(label, text)])"""
    out = {"event": "", "date": "", "speakers": [], "blocks": [], "ok": False}
    m = H1_RE.search(html)
    if m:
        out["event"] = unescape(re.sub(r"<[^>]*>", "", m.group(1))).strip()
    m2 = H2_RE.search(html)
    if m2:
        mo = MONTHS.get(m2.group(1).lower())
        if mo:
            out["date"] = "%04d-%02d-%02d" % (int(m2.group(3)), mo, int(m2.group(2)))
    body_start = 0
    for m3 in H3_RE.finditer(html):
        out["speakers"].append((m3.group(1),
                                unescape(re.sub(r"<[^>]*>", "", m3.group(2))).strip()))
        body_start = m3.end()
    if not out["speakers"]:
        for m3 in H3_PLAIN_RE.finditer(html):
            nm = unescape(re.sub(r"<[^>]*>", "", m3.group(1))).strip()
            if nm and len(nm) < 60:
                out["speakers"].append(("", nm))
                body_start = m3.end()
    if body_start == 0:
        h1 = H1_RE.search(html)
        body_start = h1.end() if h1 else 0
    tail = html[body_start:]
    e = END_RE.search(tail)
    if e:
        tail = tail[:e.start()]
        out["ok"] = True
    else:
        # belt-and-braces: never let the page footer become transcript text
        for mark in ("<div id=\"footer", "id='footer", "Browse by Sport",
                     "ASAP Sports, Inc."):
            k = tail.find(mark)
            if k > 0:
                tail = tail[:k]
    txt = strip_tags(tail)
    blocks = []
    for raw in txt.split("\n"):
        t = re.sub(r"\s+", " ", raw).strip()
        if not t:
            continue
        if Q_RE.match(t):
            blocks.append(("__Q__", t))
            continue
        lm = LABEL_RE.match(t)
        if lm and _is_label(lm.group(1)):
            blocks.append((lm.group(1).strip(), lm.group(2).strip()))
        else:
            blocks.append((None, t))
    out["blocks"] = blocks
    return out


def resolve_label(label, speakers):
    """Map an ALL-CAPS transcript label to one of the h3 speakers.
    Returns asap_id / display name / None (unresolved or non-speaker)."""
    n = norm_name(label)
    if not n or n.split()[0] in ("coach", "q", "moderator", "the") or n in (
            "question", "interpreter", "translator", "thank you"):
        return None      # coaches / moderators are never one of our targets
    cand = []
    for sid, nm in speakers:
        sn = norm_name(nm)
        if not sn:
            continue
        if n == sn:
            return sid or sn
        toks, stoks = n.split(), sn.split()
        last = stoks[-1] if stoks else ""
        if not last:
            continue
        # bare surname, or "first-initial + surname", or "COACH SURNAME"
        if toks == [last]:
            cand.append((sid or sn, "surname"))
        elif len(toks) == 2 and toks[1] == last and (
                len(toks[0]) == 1 or toks[0] == stoks[0][:len(toks[0])]):
            cand.append((sid or sn, "initial"))
    uniq = {c[0] for c in cand}
    if len(uniq) == 1:
        return cand[0][0]
    return None            # ambiguous or unknown speaker -> never attributed


def extract_for(html, target_asap_id):
    """Return only target speaker's own answer text (questions & other speakers
    dropped).  Continuation paragraphs inherit the current speaker."""
    p = parse(html)
    speakers = p["speakers"]
    ids = [s for s, _ in speakers]
    single = (len(speakers) == 1 and ids and ids[0] == str(target_asap_id))
    cur, keep, n_turns = None, [], 0
    for label, text in p["blocks"]:
        if label == "__Q__":
            if single:
                cur, n_turns = str(target_asap_id), n_turns + 1
            else:
                cur = None
            continue
        if label is not None:
            r = resolve_label(label, speakers)
            prev = cur
            cur = r
            if r is not None and str(r) == str(target_asap_id):
                n_turns += 1
                if text:
                    keep.append(text)
            continue
        if cur is not None and str(cur) == str(target_asap_id) and text:
            keep.append(text)
    p["text"] = "\n".join(keep)
    p["n_answer_paras"] = len(keep)
    p["n_turns"] = n_turns
    p["is_speaker"] = any(str(s) == str(target_asap_id) for s in ids)
    return p

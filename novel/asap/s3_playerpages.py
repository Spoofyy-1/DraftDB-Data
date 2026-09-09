"""Stage 3: fetch each candidate ASAP person page; record dated transcript list."""
import csv, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asaplib import fetch, RAW, unescape

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(RAW, "person_transcripts.csv")

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}

ROW_RE = re.compile(
    r"\[\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\s*\].*?"
    r'show_interview\.php\?id=(\d+)"[^>]*>(.*?)</a>', re.S)

done = set()
if os.path.exists(OUT):
    for r in csv.DictReader(open(OUT)):
        done.add(r["asap_id"])

cands = sorted({r["asap_id"] for r in csv.DictReader(open(os.path.join(HERE, "candidates.csv")))},
               key=int)
todo = [a for a in cands if a not in done]
print("todo:", len(todo), "of", len(cands), flush=True)

new = not os.path.exists(OUT)
f = open(OUT, "a", newline="")
w = csv.writer(f)
if new:
    w.writerow(["asap_id", "interview_id", "date", "event_title"])
    f.flush()

for i, a in enumerate(todo):
    h = fetch("http://www.asapsports.com/show_player.php?id=%s" % a)
    if h is None:
        w.writerow([a, "", "", "FETCH_FAILED"]); f.flush(); continue
    body = h.split("<h1>", 1)[-1]
    rows = 0
    for mo, dd, yy, iid, title in ROW_RE.findall(body):
        m = MONTHS.get(mo.lower())
        if not m:
            continue
        title = unescape(re.sub(r"<[^>]*>", "", title)).strip()
        w.writerow([a, iid, "%04d-%02d-%02d" % (int(yy), m, int(dd)), title])
        rows += 1
    if rows == 0:
        w.writerow([a, "", "", "NO_TRANSCRIPTS"])
    f.flush()
    if i % 50 == 0:
        print("%d/%d asap_id=%s rows=%d" % (i, len(todo), a, rows), flush=True)
f.close()
print("done", flush=True)

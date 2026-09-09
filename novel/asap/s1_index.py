"""Stage 1: crawl the basketball (category=11) A-Z player index."""
import csv, os, re, sys, gzip
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asaplib import fetch, RAW, unescape

OUT = os.path.join(RAW, "players_index.csv.gz")
rows, seen = [], set()
for letter in "abcdefghijklmnopqrstuvwxyz":
    url = "http://www.asapsports.com/show_player.php?category=11&letter=%s" % letter
    h = fetch(url)
    if h is None:
        sys.stderr.write("FAIL %s\n" % letter); continue
    n = 0
    for pid, label in re.findall(
            r'href="http://www\.asapsports\.com/show_player\.php\?id=(\d+)"[^>]*>(.*?)</a>',
            h, re.S):
        label = unescape(re.sub(r"<[^>]*>", "", label)).strip()
        if not label or pid in seen:
            continue
        seen.add(pid); rows.append((pid, label, letter)); n += 1
    print("%s %d" % (letter, n), flush=True)

with gzip.open(OUT, "wt", encoding="utf-8", newline="") as f:
    w = csv.writer(f); w.writerow(["asap_id", "display_name", "letter"])
    w.writerows(rows)
print("total players indexed:", len(rows))

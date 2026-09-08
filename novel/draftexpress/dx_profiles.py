"""Fetch archived DraftExpress player profiles for the 2,560 players in the identity file.

The listing tables do not carry a Source column; the profile page does -- its "Measurements"
table is exactly (Year, Source, Ht w/o shoes, Ht w/ shoes, Weight, Wingspan, Standing reach,
No-step vert, Max vert), one row per measurement event.  The profile header also carries
"Drafted #N in the YYYY NBA Draft" (for draft-year verification / disambiguation),
"RCSI: r (YYYY)" (high-school class year -> age proxy) and "Age: A.B" as of the capture date.

Candidate DX ids come from the CDX index of draftexpress.com/profile* (55,786 distinct ids).
Every candidate id for a matching normalised name is fetched; disambiguation happens in the
parser using the drafted-year string, never by guessing.

Waits for dx_crawl.py to finish first so we never exceed ~1 request/s to web.archive.org.
Checkpointed per profile (raw/profiles_manifest.jsonl); re-runs skip cached ids.
"""
import json, os, re, sys, csv, time, gzip, random, collections, unicodedata, subprocess
from urllib.parse import unquote

sys.path.insert(0, os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages"))
import warnings; warnings.filterwarnings("ignore")
import requests

D = "/Users/kennakao/nba/datarebuild/novel/draftexpress"
RAW = f"{D}/raw"
PROF = f"{RAW}/profiles"
MANIFEST = f"{RAW}/profiles_manifest.jsonl"
IDENT = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) DraftDB-research/1.0 "
      "(academic NBA-draft research; polite 1 req/s; contact mike@alphax.inc)")
DELAY = 1.2
TARGET_TS = "20170601000000"      # site's last full year; Wayback serves the nearest capture

os.makedirs(PROF, exist_ok=True)

SUF = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
PROFILE_RE = re.compile(r"^/profile(?:\.php)?/([^/?#]+?)-(\d+)(?:/.*)?$")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("-", " ").replace("_", " ").replace("'", "")
    s = re.sub(r"[^a-z ]", " ", s)
    s = SUF.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def slug_index():
    """normalised name -> {dx_id: slug}"""
    d = json.load(open(f"{RAW}/cdx_profiles.json"))
    idx = collections.defaultdict(dict)
    for ts, orig, ln in d[1:]:
        p = re.sub(r"^https?://(www\.)?draftexpress\.com(:80)?", "", orig).split("?")[0]
        m = PROFILE_RE.match(p)
        if not m:
            continue
        slug = unquote(m.group(1))
        idx[norm(slug)][m.group(2)] = slug
    return idx


def build_queue():
    idx = slug_index()
    ids = list(csv.DictReader(open(IDENT)))
    queue, index_rows = [], []
    seen = set()
    for r in ids:
        k = norm(r["player_name"])
        cands = idx.get(k, {})
        for dxid, slug in sorted(cands.items(), key=lambda x: int(x[0])):
            index_rows.append({"pid": r["pid"], "draft_year": r["draft_year"],
                               "dx_id": dxid, "dx_slug": slug, "n_cand": len(cands)})
            if dxid not in seen:
                seen.add(dxid)
                queue.append((dxid, slug))
    with open(f"{RAW}/candidate_index.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["pid", "draft_year", "dx_id", "dx_slug", "n_cand"])
        w.writeheader(); w.writerows(index_rows)
    return queue


def wait_for_crawler():
    while True:
        try:
            out = subprocess.run(["pgrep", "-f", "dx_crawl.py"], capture_output=True, text=True).stdout
        except Exception:
            return
        if not out.strip():
            return
        print("waiting for dx_crawl.py ...", flush=True)
        time.sleep(30)


def load_done():
    done = set()
    if os.path.exists(MANIFEST):
        for line in open(MANIFEST):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("ok") or r.get("code") == 404:
                done.add(r["dx_id"])
    return done


def fetch(url, sess):
    delay = 5.0
    for _ in range(6):
        try:
            r = sess.get(url, timeout=90, headers={"User-Agent": UA})
        except Exception as e:
            print(f"  ERR {type(e).__name__}", flush=True)
            time.sleep(delay); delay *= 2; continue
        if r.status_code in (429, 500, 502, 503, 504):
            print(f"  {r.status_code} backoff {delay:.0f}s", flush=True)
            time.sleep(delay); delay *= 2; continue
        return r
    return None


def main():
    wait_for_crawler()
    queue = build_queue()
    done = load_done()
    print(f"profiles to fetch={len(queue)} cached={len(done)}", flush=True)
    sess = requests.Session()
    mf = open(MANIFEST, "a")
    n = 0
    for i, (dxid, slug) in enumerate(queue):
        if dxid in done:
            continue
        url = f"https://web.archive.org/web/{TARGET_TS}id_/http://www.draftexpress.com/profile/{slug}-{dxid}/"
        r = fetch(url, sess)
        code = r.status_code if r is not None else 0
        body = r.content if r is not None else b""
        ok = code == 200 and len(body) > 5000
        if ok:
            with gzip.open(f"{PROF}/{dxid}.html.gz", "wb") as f:
                f.write(body)
        cap = ""
        if r is not None:
            m = re.search(r"/web/(\d{14})", r.url)
            cap = m.group(1) if m else ""
        mf.write(json.dumps({"dx_id": dxid, "slug": slug, "code": code, "bytes": len(body),
                             "capture_ts": cap, "ok": ok,
                             "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
        mf.flush()
        n += 1
        if n % 25 == 0:
            print(f"[{i+1}/{len(queue)}] {code} {len(body):>7} {slug}-{dxid} cap={cap}", flush=True)
        time.sleep(DELAY + random.uniform(0, 0.4))
    mf.close()
    print(f"PROFILES DONE new={n}", flush=True)


if __name__ == "__main__":
    main()

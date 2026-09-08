"""DraftExpress pre-draft measurements database -> Wayback Machine crawler.

draftexpress.com is dead (shut down late 2017). Its measurement listing is archived.
Two generations of the same listing exist in the archive:
  * legacy query-string UI  /nba-pre-draft-measurements/?year=YYYY&source=S&pos=P&draft=D&sort=N&sort2=DIR
    (and /nba-pre-draft-measurements.php?..., /nba-pre-draft-measurements/measurements.php?...)
    -- UNPAGINATED: one capture returns every row matching the filter.
  * 2016/17 slash UI       /nba-pre-draft-measurements/{year}/{source}/{pos}/{draft}/{page}/{sort}/{dir}
    -- 100 rows/page, ~155 pages for the unfiltered listing.
We can only fetch URLs that were actually captured, so the crawl target list is derived
from the CDX index, not generated. One fetch per distinct URL-shape (best capture).

Polite: >=1.2 s between requests, exponential backoff on 429/503/5xx, descriptive UA.
Checkpointed per page (raw/manifest.jsonl); re-runs skip anything already cached.
"""
import json, os, re, sys, time, gzip, hashlib, random
from urllib.parse import parse_qs

sys.path.insert(0, os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages"))
import warnings; warnings.filterwarnings("ignore")
import requests

D = "/Users/kennakao/nba/datarebuild/novel/draftexpress"
RAW = f"{D}/raw"
PAGES = f"{RAW}/pages"
MANIFEST = f"{RAW}/manifest.jsonl"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) DraftDB-research/1.0 "
      "(academic NBA-draft research; polite 1 req/s; contact mike@alphax.inc)")
DELAY = 1.2
# the site went dark in Dec 2017; captures after this are ~5.5 kB error shells
LIVE_UNTIL = 20171215000000

os.makedirs(PAGES, exist_ok=True)


def strip_host(orig):
    return re.sub(r"^https?://(www\.)?draftexpress\.com(:80)?", "", orig)


def build_targets():
    """One target per distinct URL shape; keep the biggest capture from while the site was live."""
    cdx = json.load(open(f"{RAW}/cdx_full.json"))
    best = {}                       # key -> (score, ts, path)
    for ts, orig, st, dig, ln in cdx[1:]:
        if st not in ("200", "-"):
            continue
        p = strip_host(orig)
        if not p.startswith("/nba-pre-draft-measurements"):
            continue
        try:
            ln = int(ln)
        except Exception:
            ln = 0
        tsn = int(ts + "0" * (14 - len(ts)))
        live = tsn < LIVE_UNTIL
        if "?" in p:
            base, q = p.split("?", 1)
            qs = parse_qs(q, keep_blank_values=True)
            page = qs.get("page", [""])[0]
            if page in ("averages", "avepos"):     # aggregate tables, not player rows
                continue
            key = ("q", base, qs.get("year", [""])[0].lower(),
                   qs.get("source", [""])[0].lower(), qs.get("pos", [""])[0],
                   qs.get("draft", [""])[0])
        else:
            seg = [x for x in p.split("/") if x]
            base, parts = seg[0], seg[1:]   # base = nba-pre-draft-measurements[.php]
            if parts and parts[0] == "nba-mock-draft":
                continue
            # junk captures from broken links: %22, ), .Drinkwater, ...
            if parts and not re.match(r"^(all|\d{4}|measurements\.php|[A-Za-z0-9+%._-]+)$", parts[0]):
                continue
            # year/source/pos/draft/page (sort ignored); keep the base so the bare listing,
            # the .php alias and measurements.php are all fetched -- each is a full legacy dump
            key = ("s", base) + tuple(parts[:6])
        # prefer live-era captures, then the largest record
        score = (1 if live else 0, ln)
        if key not in best or score > best[key][0]:
            best[key] = (score, ts, p)
    return sorted(((ts, p, k) for k, (_, ts, p) in best.items()), key=lambda r: (r[2][0] != "s", r[1]))


def load_done():
    done = {}
    if os.path.exists(MANIFEST):
        for line in open(MANIFEST):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("ok"):
                done[(r["ts"], r["path"])] = r
    return done


def fetch(ts, path, sess):
    url = f"https://web.archive.org/web/{ts}id_/http://www.draftexpress.com{path}"
    delay = 5.0
    for attempt in range(6):
        try:
            r = sess.get(url, timeout=90, headers={"User-Agent": UA})
        except Exception as e:
            print(f"  ERR {type(e).__name__} attempt {attempt}", flush=True)
            time.sleep(delay); delay *= 2; continue
        if r.status_code in (429, 503, 502, 504, 500):
            print(f"  {r.status_code} backoff {delay:.0f}s", flush=True)
            time.sleep(delay); delay *= 2; continue
        return r.status_code, r.content
    return 0, b""


def main():
    targets = build_targets()
    done = load_done()
    print(f"targets={len(targets)} already_cached={len(done)}", flush=True)
    sess = requests.Session()
    mf = open(MANIFEST, "a")
    n_new = 0
    for i, (ts, path, key) in enumerate(targets):
        if (ts, path) in done:
            continue
        code, body = fetch(ts, path, sess)
        h = hashlib.sha1(f"{ts}|{path}".encode()).hexdigest()[:16]
        fn = f"{PAGES}/{h}.html.gz"
        ok = code == 200 and len(body) > 2000
        if ok:
            with gzip.open(fn, "wb") as f:
                f.write(body)
        rec = {"ts": ts, "path": path, "code": code, "bytes": len(body),
               "file": os.path.basename(fn) if ok else None, "ok": ok,
               "gen": key[0], "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        mf.write(json.dumps(rec) + "\n"); mf.flush()
        n_new += 1
        if n_new % 20 == 0 or not ok:
            print(f"[{i+1}/{len(targets)}] {code} {len(body):>8} {path[:110]}", flush=True)
        time.sleep(DELAY + random.uniform(0, 0.4))
    mf.close()
    print(f"DONE new={n_new}", flush=True)


if __name__ == "__main__":
    main()

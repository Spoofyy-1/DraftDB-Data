"""Second pass over profiles that came back from a post-shutdown capture.

dx_profiles.py asks the Wayback Machine for the capture nearest 2017-06-01. For some players
the nearest capture is 2018+ -- draftexpress.com was dead by then, so those pages are content
free shells with no Measurements table and no header block. Re-requesting the same profile with
an earlier target timestamp (2016-12-01) often lands on a live-era capture instead. The cached
page is replaced only when the replacement is from the live era (<= 2017), i.e. only ever an
improvement; a new manifest line records the retry and dx_parse.py keeps the last line per id.

Same politeness as the other crawlers: one request at a time, >=1.2 s apart, backoff on 429/5xx.
"""
import json, os, re, sys, gzip, time, random

sys.path.insert(0, os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages"))
import warnings; warnings.filterwarnings("ignore")
import requests
import lxml.html as LH

D = "/Users/kennakao/nba/datarebuild/novel/draftexpress"
RAW = f"{D}/raw"
PROF = f"{RAW}/profiles"
MANIFEST = f"{RAW}/profiles_manifest.jsonl"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) DraftDB-research/1.0 "
      "(academic NBA-draft research; polite 1 req/s; contact mike@alphax.inc)")
DELAY = 1.2
RETRY_TS = "20161201000000"


def has_meas(html):
    try:
        doc = LH.fromstring(html)
    except Exception:
        return False
    for t in doc.xpath("//table"):
        trs = t.xpath(".//tr")
        if len(trs) < 2:
            continue
        hdr = [" ".join(c.text_content().split()).lower() for c in trs[0].xpath("./th|./td")]
        if hdr[:2] == ["year", "source"] and "wingspan" in hdr:
            return True
    return False


def main():
    last = {}
    for line in open(MANIFEST):
        r = json.loads(line)
        last[r["dx_id"]] = r
    todo = [r for r in last.values()
            if r.get("ok") and not r.get("retry")
            and (r.get("capture_ts", "")[:4] or "0") > "2017"]
    print(f"post-shutdown captures to retry: {len(todo)}", flush=True)
    sess = requests.Session()
    mf = open(MANIFEST, "a")
    fixed = 0
    for i, r in enumerate(todo):
        url = (f"https://web.archive.org/web/{RETRY_TS}id_/"
               f"http://www.draftexpress.com/profile/{r['slug']}-{r['dx_id']}/")
        delay, resp = 5.0, None
        for _ in range(5):
            try:
                resp = sess.get(url, timeout=90, headers={"User-Agent": UA})
            except Exception as e:
                print(f"  ERR {type(e).__name__}", flush=True)
                time.sleep(delay); delay *= 2; continue
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(delay); delay *= 2; continue
            break
        cap = ""
        if resp is not None:
            m = re.search(r"/web/(\d{14})", resp.url)
            cap = m.group(1) if m else ""
        good = (resp is not None and resp.status_code == 200 and len(resp.content) > 5000
                and cap[:4] <= "2017")
        if good:
            with gzip.open(f"{PROF}/{r['dx_id']}.html.gz", "wb") as f:
                f.write(resp.content)
            fixed += 1
        mf.write(json.dumps({
            "dx_id": r["dx_id"], "slug": r["slug"],
            "code": resp.status_code if resp is not None else 0,
            "bytes": len(resp.content) if resp is not None else 0,
            "capture_ts": cap if good else r.get("capture_ts", ""),
            "ok": True, "retry": True, "replaced": bool(good),
            "has_measurements": bool(good and has_meas(resp.content.decode("utf-8", "replace"))),
            "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
        mf.flush()
        if (i + 1) % 25 == 0:
            print(f"[{i+1}/{len(todo)}] replaced={fixed}", flush=True)
        time.sleep(DELAY + random.uniform(0, 0.4))
    mf.close()
    print(f"RETRY DONE replaced={fixed}/{len(todo)}", flush=True)


if __name__ == "__main__":
    main()

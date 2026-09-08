"""Shared helpers for the boards collector (Wayback Machine, polite rates).

Rules honoured (see ../COLLECTOR_RULES.md):
  * >=1 s between requests to web.archive.org, exponential backoff on 429/503.
  * descriptive User-Agent, no Cloudflare bypass (the live nbadraft.net /
    draftexpress.com sites are NEVER contacted -- only web.archive.org).
  * everything cached under raw/ so re-runs are offline.
"""
import gzip
import json
import os
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "raw")
UA = ("nba-redraft-research/1.0 (non-commercial academic draft-model research; "
      "contact mike@alphax.inc) python-urllib")

# --- politeness -------------------------------------------------------------
_MIN_GAP = 1.05           # seconds between requests to web.archive.org
_last_req = [0.0]


def _throttle():
    now = time.time()
    wait = _MIN_GAP - (now - _last_req[0])
    if wait > 0:
        time.sleep(wait)
    _last_req[0] = time.time()


try:                                        # keep-alive session (fewer TCP
    import requests                          # handshakes = politer + faster)
    _SESSION = requests.Session()
    _SESSION.headers.update({"User-Agent": UA, "Accept": "*/*",
                             "Accept-Encoding": "gzip", "Connection": "keep-alive"})
except Exception:                            # pragma: no cover
    requests = None
    _SESSION = None


def fetch(url, tries=8, timeout=120, accept_404=True):
    """GET a URL from web.archive.org with exponential backoff.

    Returns (status, bytes) -- status 0 means gave up.
    """
    delay = 5.0
    conn_delay = 2.0
    gone = 0
    for attempt in range(tries):
        _throttle()
        try:
            if _SESSION is not None:
                r = _SESSION.get(url, timeout=timeout, allow_redirects=True)
                code = r.status_code
                if code == 200:
                    return 200, r.content
                if code in (404, 403) and accept_404:
                    return code, b""
                if code in (429, 503):          # real rate-limit signals
                    sl = delay * (1.0 + random.random() * 0.4)
                    sys.stderr.write("  HTTP %d on %s -> sleep %.1fs\n"
                                     % (code, url[:100], sl))
                    sys.stderr.flush()
                    time.sleep(sl)
                    delay = min(delay * 2, 300)
                    continue
                if code in (500, 502, 504, 520, 523):
                    # the archive cannot serve this memento; try a couple of
                    # times then record it as a miss instead of hammering
                    gone += 1
                    if gone >= 3:
                        return code, b""
                    sys.stderr.write("  HTTP %d on %s (try %d/3)\n"
                                     % (code, url[:100], gone))
                    sys.stderr.flush()
                    time.sleep(3.0)
                    continue
                return code, b""
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    try:
                        data = gzip.decompress(data)
                    except Exception:
                        pass
                return r.status, data
        except urllib.error.HTTPError as e:
            code = e.code
            if code in (404, 403) and accept_404:
                return code, b""
            if code in (429, 503, 502, 504, 500, 520, 523):
                sl = delay * (1.0 + random.random() * 0.4)
                sys.stderr.write("  HTTP %d on %s -> sleep %.1fs\n" % (code, url[:110], sl))
                sys.stderr.flush()
                time.sleep(sl)
                delay = min(delay * 2, 300)
                continue
            return code, b""
        except Exception as e:  # timeouts, connection resets, DNS
            # transport-level hiccups are not a rate-limit signal from the
            # archive, so back off gently (429/503 above keep the hard backoff)
            sl = conn_delay * (1.0 + random.random() * 0.4)
            sys.stderr.write("  ERR %s (%s) on %s -> sleep %.1fs\n"
                             % (type(e).__name__, str(getattr(e, "reason", e))[:60],
                                url[:100], sl))
            sys.stderr.flush()
            time.sleep(sl)
            conn_delay = min(conn_delay * 2, 30)
    return 0, b""


def timemap(url):
    """Snapshot list for one URL via the timemap/link endpoint.

    Returns sorted list of (timestamp14, memento_url_original).
    """
    tm = "http://web.archive.org/web/timemap/link/" + url
    st, data = fetch(tm)
    if st != 200 or not data:
        return []
    out = []
    txt = data.decode("utf-8", "replace")
    for m in re.finditer(r'<(http://web\.archive\.org/web/(\d{14})/([^>]+))>;\s*rel="[^"]*memento[^"]*"', txt):
        out.append((m.group(2), m.group(3)))
    # de-dup on (ts, original) keeping www variant order stable
    seen = set()
    ded = []
    for ts, orig in sorted(out):
        if ts in seen:
            continue
        seen.add(ts)
        ded.append((ts, orig))
    return ded


def cdx(url, matchType=None, extra=None, limit=None):
    """CDX listing. Returns list of dicts with timestamp/original/statuscode."""
    q = {"url": url, "output": "json", "fl": "timestamp,original,statuscode,mimetype",
         "collapse": "digest"}
    if matchType:
        q["matchType"] = matchType
    if limit:
        q["limit"] = str(limit)
    if extra:
        q.update(extra)
    u = "http://web.archive.org/cdx/search/cdx?" + urllib.parse.urlencode(q)
    st, data = fetch(u, timeout=300)
    if st != 200 or not data:
        return []
    try:
        rows = json.loads(data.decode("utf-8", "replace"))
    except Exception:
        return []
    if not rows:
        return []
    hdr = rows[0]
    return [dict(zip(hdr, r)) for r in rows[1:]]


def wb_raw_url(ts, original):
    return "http://web.archive.org/web/%sid_/%s" % (ts, original)


# --- capture cache ----------------------------------------------------------
def cache_path(source, ts, original):
    import hashlib
    h = hashlib.sha1(original.encode("utf-8")).hexdigest()[:12]
    d = os.path.join(RAW, source)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "%s_%s.html.gz" % (ts, h))


def get_capture(source, ts, original):
    """Download (or read from cache) one raw memento. Returns text or None."""
    p = cache_path(source, ts, original)
    if os.path.exists(p):
        try:
            with gzip.open(p, "rb") as f:
                b = f.read()
            if b:
                return b.decode("utf-8", "replace")
        except Exception:
            pass
    st, data = fetch(wb_raw_url(ts, original))
    if st != 200 or not data:
        # remember the miss so re-runs do not re-hit the archive
        with gzip.open(p + ".miss", "wb") as f:
            f.write(("HTTP %d" % st).encode())
        return None
    with gzip.open(p, "wb") as f:
        f.write(data)
    return data.decode("utf-8", "replace")


def capture_missing(source, ts, original):
    return os.path.exists(cache_path(source, ts, original) + ".miss")


# --- draft calendar ---------------------------------------------------------
DRAFT_DATE = {
    2000: "2000-06-28", 2001: "2001-06-27", 2002: "2002-06-26", 2003: "2003-06-26",
    2004: "2004-06-24", 2005: "2005-06-28", 2006: "2006-06-28", 2007: "2007-06-28",
    2008: "2008-06-26", 2009: "2009-06-25", 2010: "2010-06-24", 2011: "2011-06-23",
    2012: "2012-06-28", 2013: "2013-06-27", 2014: "2014-06-26", 2015: "2015-06-25",
    2016: "2016-06-23", 2017: "2017-06-22", 2018: "2018-06-21", 2019: "2019-06-20",
    2020: "2020-11-18", 2021: "2021-07-29", 2022: "2022-06-23", 2023: "2023-06-22",
    2024: "2024-06-26", 2025: "2025-06-25",
}
# a source is pre-draft only if its timestamp is before 22:00 UTC on the draft date
DRAFT_CUTOFF = {y: datetime.strptime(d + " 22:00:00", "%Y-%m-%d %H:%M:%S")
                for y, d in DRAFT_DATE.items()}


def ts_dt(ts):
    return datetime.strptime(ts, "%Y%m%d%H%M%S")


def days_before_draft(ts, year):
    return (DRAFT_CUTOFF[year] - ts_dt(ts)).total_seconds() / 86400.0


def board_year_for_ts(ts):
    """Which draft class a nbadraft.net-style rolling board belongs to.

    Boards freeze after the draft and reset to the next class in late August,
    so a capture in [Aug 15 of Y-1 .. draft night of Y] is class Y, and a
    capture in (draft night of Y .. Aug 15 of Y] is the FROZEN final board of
    class Y (verified by checking the top entries against class-Y draftees).
    """
    d = ts_dt(ts)
    y = d.year
    if d < DRAFT_CUTOFF.get(y, datetime(y, 6, 25, 22)):
        return y, "pre"
    if d < datetime(y, 8, 15):
        return y, "frozen"
    return y + 1, "pre"


# --- name normalisation -----------------------------------------------------
SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?$", re.I)


def norm_name(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("’", "'").replace("`", "'")
    s = s.lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z' ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for _ in range(3):
        s2 = SUFFIX.sub("", s).strip()
        if s2 == s:
            break
        s = s2
    s = s.replace("'", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def name_keys(s):
    """Return a set of matching keys for a name (full, and first-initial+last)."""
    n = norm_name(s)
    if not n:
        return set()
    keys = {n}
    parts = n.split()
    if len(parts) >= 2:
        keys.add(parts[0][0] + " " + parts[-1])
        keys.add(" ".join([parts[0], parts[-1]]))
    return keys


def html_unescape(s):
    try:
        import html
        return html.unescape(s)
    except Exception:
        return s


def strip_tags(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_unescape(s)
    s = s.replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", s)


def log(msg):
    sys.stdout.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), msg))
    sys.stdout.flush()

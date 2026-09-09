"""Shared polite HTTP + parsing helpers for the ASAP Sports collector."""
import gzip, os, re, sys, time, unicodedata
import urllib.request, urllib.error

UA = ("DraftDB-Research/1.0 (academic NBA draft research, non-commercial; "
      "contact mike@alphax.inc) Python-urllib")
BASE = "http://www.asapsports.com/"
MIN_INTERVAL = 1.2          # seconds between requests (>= 1 req/s rule)
_last = [0.0]

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
os.makedirs(RAW, exist_ok=True)


def fetch(url, tries=4):
    """GET url politely; return decoded HTML text or None."""
    for attempt in range(tries):
        wait = MIN_INTERVAL - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": "text/html"})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read().decode("latin-1", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(5 * (2 ** attempt))   # exponential backoff
                continue
            sys.stderr.write("HTTP %s %s\n" % (e.code, url))
            return None
        except Exception as e:
            time.sleep(5 * (2 ** attempt))
    sys.stderr.write("GIVEUP %s\n" % url)
    return None


# ---------------------------------------------------------------- name rules
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm_name(s):
    """Lowercase, strip accents/punctuation/suffixes, collapse whitespace."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&amp;", " ")
    s = re.sub(r"[^a-z ]+", " ", s)          # drops . ' - digits
    toks = [t for t in s.split() if t and t not in SUFFIXES]
    return " ".join(toks)


def flip_lastfirst(s):
    """'Achiuwa, Precious' -> 'Precious Achiuwa'."""
    if "," in s:
        a, b = s.split(",", 1)
        return "%s %s" % (b.strip(), a.strip())
    return s.strip()


def unescape(s):
    for a, b in (("&amp;", "&"), ("&#39;", "'"), ("&quot;", '"'),
                 ("&nbsp;", " "), ("&rsquo;", "'"), ("&lsquo;", "'"),
                 ("&ldquo;", '"'), ("&rdquo;", '"'), ("&eacute;", "e"),
                 ("&ndash;", "-"), ("&mdash;", "-"), ("&amp;amp;", "&")):
        s = s.replace(a, b)
    return s


def gz_write(path, text):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(text)


def gz_read(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return f.read()

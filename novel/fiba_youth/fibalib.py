#!/usr/bin/env python3
"""
Shared helpers for the fiba_youth collector: polite HTTP with an on-disk cache,
Next.js RSC "flight" payload decoding, and rule-based extraction of the JSON
objects that fiba.basketball embeds in its server-rendered HTML.

No third-party HTML parser is used: every extraction is a documented regex or a
brace-balanced JSON slice (COLLECTOR_RULES rule 4).
"""
import gzip
import json
import os
import random
import re
import time
import unicodedata
from datetime import datetime

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
PAGES = os.path.join(RAW, "pages")
SITEMAPS = os.path.join(RAW, "sitemaps")
PARSED = os.path.join(RAW, "parsed")

BASE = "https://www.fiba.basketball"
UA = ("DraftDB-Research/1.0 (non-commercial NBA draft research; "
      "contact mike@alphax.inc)")
SLEEP = 1.1            # >= 1 s between requests to fiba.basketball
MAX_RETRY = 6

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en",
})

_last = [0.0]


def log(msg):
    print("[%s] %s" % (datetime.now().isoformat(timespec="seconds"), msg),
          flush=True)


def _throttle():
    dt = time.time() - _last[0]
    if dt < SLEEP:
        time.sleep(SLEEP - dt)
    _last[0] = time.time()


def fetch(url, cache_path, force=False):
    """GET url with polite throttling + exponential backoff; cache gzipped.

    Returns the decoded text, or None if the page could not be retrieved.
    Cached pages are served from disk so re-runs are offline and resumable.
    """
    if not force and os.path.exists(cache_path):
        try:
            with gzip.open(cache_path, "rt", encoding="utf-8",
                           errors="replace") as fh:
                return fh.read()
        except Exception:
            pass  # corrupt cache -> refetch
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    delay = 2.0
    for _ in range(MAX_RETRY):
        _throttle()
        try:
            r = SESSION.get(url, timeout=60)
        except requests.RequestException as e:
            log("  net error %s on %s -> sleep %.0fs" % (e, url, delay))
            time.sleep(delay)
            delay = min(delay * 2, 180)
            continue
        if r.status_code == 200:
            txt = r.text
            with gzip.open(cache_path, "wt", encoding="utf-8") as fh:
                fh.write(txt)
            return txt
        if r.status_code == 404:
            log("  HTTP 404 %s" % url)
            return None
        if r.status_code in (429, 500, 502, 503, 504):
            wait = delay + random.uniform(0, 1.5)
            log("  HTTP %s on %s -> backoff %.0fs" % (r.status_code, url, wait))
            time.sleep(wait)
            delay = min(delay * 2, 180)
            continue
        log("  HTTP %s on %s -> giving up" % (r.status_code, url))
        return None
    log("  exhausted retries on %s" % url)
    return None


# ---------------------------------------------------------------- flight ----
_PUSH = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')


def flight(html):
    """Concatenate and JSON-unescape the Next.js RSC payload chunks.

    Each self.__next_f.push([1,"..."]) argument is a complete JS string
    literal, so json.loads('"'+chunk+'"') decodes it exactly (including \\uXXXX
    escapes, which keeps accented player names intact).
    """
    out = []
    for chunk in _PUSH.findall(html):
        try:
            out.append(json.loads('"' + chunk + '"'))
        except ValueError:
            out.append(chunk)
    return "".join(out)


def json_at(buf, idx):
    """Return the JSON object that starts at buf[idx] == '{' (brace-balanced,
    string-aware).  Returns None if it does not parse."""
    if idx < 0 or idx >= len(buf) or buf[idx] != "{":
        return None
    depth, i, n = 0, idx, len(buf)
    in_str, esc = False, False
    while i < n:
        c = buf[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(buf[idx:i + 1])
                    except ValueError:
                        return None
        i += 1
    return None


def json_array_at(buf, idx):
    """Return the JSON array that starts at buf[idx] == '['."""
    if idx < 0 or idx >= len(buf) or buf[idx] != "[":
        return None
    depth, i, n = 0, idx, len(buf)
    in_str, esc = False, False
    while i < n:
        c = buf[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(buf[idx:i + 1])
                    except ValueError:
                        return None
        i += 1
    return None


def find_obj(buf, key):
    """First `"key":{...}` object in buf."""
    m = re.search(r'"%s"\s*:\s*\{' % re.escape(key), buf)
    if not m:
        return None
    return json_at(buf, m.end() - 1)


def find_arr(buf, key):
    """First `"key":[...]` array in buf."""
    m = re.search(r'"%s"\s*:\s*\[' % re.escape(key), buf)
    if not m:
        return None
    return json_array_at(buf, m.end() - 1)


# ---------------------------------------------------------------- names -----
_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?$")


def norm_name(s):
    """Lower-case, strip accents/punctuation/suffixes, squeeze whitespace."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("Ø", "O").replace("ø", "o")
    s = s.replace("Đ", "D").replace("đ", "d")
    s = s.replace("Ł", "L").replace("ł", "l")
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for _ in range(2):
        s2 = _SUFFIX.sub("", s).strip()
        if s2 == s:
            break
        s = s2
    return s

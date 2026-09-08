"""Parse every cached DraftExpress page into measurements_all.csv (one row per player-event).

Three table shapes are handled, all with rule-based (position/header) extraction only:

A) legacy listing  <table class="inputbox">, single header row
   Name | Height w/o Shoes | Height w/shoes | Weight | Wingspan | Reach | Body Fat | Hand Length |
   Hand Width | No Step Vert | No Step Vert Reach | Max Vert | Max Vert Reach | Bench | Agility |
   Sprint | Rank | Drafted        -- first cell is "Player Name - YYYY" (optionally "* " prefixed)
   Hand Length/Width are literally "0" when missing.  No Source column.

B) 2016/17 listing  <table class="sorttable">, two header rows, 18 data cells
   Player | Year | Draft pick | Ht no-shoes | Ht w/shoes | Wingspan | Standing reach |
   Max vert | Max vert reach | No-step vert | No-step vert reach | Weight | Body fat |
   Hand length | Hand width | Bench | Agility | Sprint      -- no Source column either

C) player profile  <table class="alt">, single header row
   Year | Source | Height w/o Shoes | Height w/ Shoes | Weight | Wingspan | Standing Reach |
   No Step Vert | Max Vert                                -- this is the only Source we get

Source is otherwise recovered from the request URL when the capture was of a source-filtered
listing.  Profile rows are matched back onto same-(player, year) listing rows on their shared
measures so the listing's extra columns inherit the profile's Source.
"""
import csv, gzip, json, os, re, sys, collections
from urllib.parse import unquote, parse_qs

sys.path.insert(0, os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages"))
import warnings; warnings.filterwarnings("ignore")
import lxml.html as LH

D = "/Users/kennakao/nba/datarebuild/novel/draftexpress"
RAW = f"{D}/raw"

FRAC = {"¼": .25, "½": .5, "¾": .75, "⅛": .125, "⅜": .375,
        "⅝": .625, "⅞": .875, "⅓": 1/3., "⅔": 2/3.}
NULLS = {"", "-", "--", "na", "n/a", "none", "0.0\"", "?"}

FT_RE = re.compile(r"^\s*(\d+)\s*'\s*([\d.]+)?\s*(?:\+\s*([\d.]+))?\s*\"?\s*$")
NUM_RE = re.compile(r"^\s*([\d.]+)\s*(?:\+\s*([\d.]+))?\s*\"?\s*$")
NAMEYEAR_RE = re.compile(r"^\*?\s*(.+?)\s*[-–]\s*(\d{4})\s*$")
PROFILE_HREF = re.compile(r"/profile(?:\.php)?/([^/?#]+?)-(\d+)(?:/|$)")


def _defrac(s):
    for k, v in FRAC.items():
        s = s.replace(k, f" +{v}")
    return s


def to_inches(v):
    """'7\\' 5.5\"', '6\\'11 1/4\"', '34\"', '19.5' -> inches (float) or None."""
    if v is None:
        return None
    s = " ".join(str(v).split()).replace("’", "'").replace("′", "'")
    if s.lower() in NULLS:
        return None
    s = _defrac(s)
    m = FT_RE.match(s)
    if m:
        x = int(m.group(1)) * 12 + float(m.group(2) or 0) + float(m.group(3) or 0)
        return x if x > 0 else None          # DX writes 0'0" for "not measured"
    m = NUM_RE.match(s)
    if m:
        x = float(m.group(1)) + float(m.group(2) or 0)
        return x if x > 0 else None
    return None


def to_float(v, zero_is_null=False):
    if v is None:
        return None
    s = " ".join(str(v).split())
    if s.lower() in NULLS:
        return None
    s = _defrac(s)
    m = NUM_RE.match(s)
    if not m:
        return None
    x = float(m.group(1)) + float(m.group(2) or 0)
    if zero_is_null and x == 0:
        return None
    return x


def to_pick(v):
    s = " ".join(str(v or "").split())
    if s.lower() in NULLS or s.lower() in ("no", "undrafted"):
        return None
    m = re.match(r"^(\d+)$", s)
    return int(m.group(1)) if m else None


COLS = ["src_kind", "src_path", "capture_ts", "player_name", "dx_id", "dx_slug", "event_year",
        "source", "source_from", "draft_pick", "height_noshoes_in", "height_shoes_in",
        "wingspan_in", "standing_reach_in", "max_vert_in", "max_vert_reach_in",
        "nostep_vert_in", "nostep_vert_reach_in", "weight_lb", "body_fat_pct",
        "hand_length_in", "hand_width_in", "bench_reps", "agility_s", "sprint_s"]

LEGACY_HDR = ["name", "height w/o shoes", "height w/shoes", "weight", "wingspan", "reach"]
NEW_HDR = ["player", "year", "draft pick", "height", "wingspan", "standing reach", "vertical",
           "weight", "body fat", "hand", "bench", "agility", "sprint"]
PROF_HDR = ["year", "source", "height w/o shoes", "height w/ shoes", "weight", "wingspan",
            "standing reach", "no step vert", "max vert"]
# the profile "Measurements" table has two layouts (the pre-2016 one adds Body Fat), so it is
# read header-driven rather than positionally.
PROF_MAP = {
    "year": "_year", "source": "_source", "height w/o shoes": "height_noshoes_in",
    "height w/ shoes": "height_shoes_in", "height w/shoes": "height_shoes_in",
    "weight": "weight_lb", "wingspan": "wingspan_in", "standing reach": "standing_reach_in",
    "reach": "standing_reach_in", "body fat": "body_fat_pct", "no step vert": "nostep_vert_in",
    "no step vert reach": "nostep_vert_reach_in", "max vert": "max_vert_in",
    "max vert reach": "max_vert_reach_in", "hand length": "hand_length_in",
    "hand width": "hand_width_in", "bench": "bench_reps", "agility": "agility_s",
    "sprint": "sprint_s",
}


def cells(tr):
    return [" ".join(c.text_content().split()) for c in tr.xpath("./th|./td")]


def href_id(tr):
    for a in tr.xpath(".//a"):
        m = PROFILE_HREF.search(a.get("href") or "")
        if m:
            return unquote(m.group(1)), m.group(2)
    return None, None


def source_from_path(path):
    """Recover the source filter from the captured URL, if any."""
    if "?" in path:
        qs = parse_qs(path.split("?", 1)[1], keep_blank_values=True)
        s = unquote(qs.get("source", [""])[0]).strip()
    else:
        parts = [x for x in path.split("/") if x][1:]
        s = unquote(parts[1].replace("+", " ")).strip() if len(parts) > 1 else ""
    return "" if s.lower() in ("", "all", "0") else s


# legacy header text -> field.  Some 2016/17 captures render the legacy grid with the header
# row detached from the table, so the canonical 18-column order below is the documented fallback.
LEGACY_MAP = {
    "name": "name", "height w/o shoes": "height_noshoes_in",
    "height w/shoes": "height_shoes_in", "height w/ shoes": "height_shoes_in",
    "weight": "weight_lb", "wingspan": "wingspan_in", "reach": "standing_reach_in",
    "standing reach": "standing_reach_in", "body fat": "body_fat_pct",
    "hand length": "hand_length_in", "hand width": "hand_width_in",
    "no step vert": "nostep_vert_in", "no step vert reach": "nostep_vert_reach_in",
    "max vert": "max_vert_in", "max vert reach": "max_vert_reach_in",
    "bench": "bench_reps", "agility": "agility_s", "sprint": "sprint_s",
    "rank": "_rsci_rank", "drafted": "draft_pick",
}
LEGACY_ORDER = ["name", "height_noshoes_in", "height_shoes_in", "weight_lb", "wingspan_in",
                "standing_reach_in", "body_fat_pct", "hand_length_in", "hand_width_in",
                "nostep_vert_in", "nostep_vert_reach_in", "max_vert_in", "max_vert_reach_in",
                "bench_reps", "agility_s", "sprint_s", "_rsci_rank", "draft_pick"]
INCH_FIELDS = {"height_noshoes_in", "height_shoes_in", "wingspan_in", "standing_reach_in",
               "max_vert_in", "max_vert_reach_in", "nostep_vert_in", "nostep_vert_reach_in"}
ZERO_NULL = {"hand_length_in", "hand_width_in"}


def parse_legacy(t, path, ts, out):
    trs = t.xpath(".//tr")
    if len(trs) < 2:
        return
    order = None
    for tr in trs[:3]:
        h = [c.lower() for c in cells(tr)]
        if h[:1] == ["name"] and "wingspan" in h:
            order = [LEGACY_MAP.get(x, "_") for x in h]
            break
    src = source_from_path(path)
    for tr in trs:
        c = cells(tr)
        if len(c) < 16:
            continue
        m = NAMEYEAR_RE.match(c[0])
        if not m:
            continue
        cols = order if (order and len(order) == len(c)) else LEGACY_ORDER
        if len(cols) != len(c):
            continue
        rec = {"src_kind": "listing_legacy", "src_path": path, "capture_ts": ts,
               "player_name": m.group(1), "event_year": int(m.group(2)), "source": src,
               "source_from": "url" if src else "", "draft_pick": None}
        for k in MEAS:
            rec[k] = None
        for name, val in zip(cols, c):
            if name in INCH_FIELDS:
                rec[name] = to_inches(val)
            elif name == "draft_pick":
                rec[name] = to_pick(val)
            elif name in ZERO_NULL:
                rec[name] = to_float(val, zero_is_null=True)
            elif name in MEAS:
                rec[name] = to_float(val)
        slug, dxid = href_id(tr)
        rec["dx_id"], rec["dx_slug"] = dxid or "", slug or ""
        out.append(rec)


def parse_new(t, path, ts, out):
    trs = t.xpath(".//tr")
    if len(trs) < 3:
        return
    hdr = [c.lower() for c in cells(trs[0])]
    if hdr != NEW_HDR and hdr[:1] != ["player"]:
        return
    src = source_from_path(path)
    for tr in trs:
        c = cells(tr)
        if len(c) != 18 or not re.match(r"^\d{4}$", c[1] or ""):
            continue
        slug, dxid = href_id(tr)
        out.append({
            "src_kind": "listing_2017", "src_path": path, "capture_ts": ts,
            "player_name": c[0], "dx_id": dxid or "", "dx_slug": slug or "",
            "event_year": int(c[1]), "source": src, "source_from": "url" if src else "",
            "draft_pick": to_pick(c[2]),
            "height_noshoes_in": to_inches(c[3]), "height_shoes_in": to_inches(c[4]),
            "wingspan_in": to_inches(c[5]), "standing_reach_in": to_inches(c[6]),
            "max_vert_in": to_inches(c[7]), "max_vert_reach_in": to_inches(c[8]),
            "nostep_vert_in": to_inches(c[9]), "nostep_vert_reach_in": to_inches(c[10]),
            "weight_lb": to_float(c[11]), "body_fat_pct": to_float(c[12]),
            "hand_length_in": to_float(c[13]), "hand_width_in": to_float(c[14]),
            "bench_reps": to_float(c[15]), "agility_s": to_float(c[16]),
            "sprint_s": to_float(c[17]),
        })


def parse_listings():
    out = []
    n_pages = 0
    for line in open(f"{RAW}/manifest.jsonl"):
        r = json.loads(line)
        if not r.get("ok"):
            continue
        fp = f"{RAW}/pages/{r['file']}"
        if not os.path.exists(fp):
            continue
        try:
            html = gzip.open(fp, "rb").read().decode("utf-8", "replace")
            doc = LH.fromstring(html)
        except Exception:
            continue
        n_pages += 1
        for t in doc.xpath('//table[contains(@class,"inputbox")]'):
            parse_legacy(t, r["path"], r["ts"], out)
        for t in doc.xpath('//table[contains(@class,"sorttable")]'):
            parse_new(t, r["path"], r["ts"], out)
    return out, n_pages


PROF_DRAFTED = re.compile(r"Drafted\s*#?(\d+)?\s*in the\s*(\d{4})\s*NBA Draft", re.I)
PROF_RCSI = re.compile(r"RCSI:\s*(\d+)\s*\((\d{4})\)", re.I)
PROF_AGE = re.compile(r"Age:\s*([\d.]+)")


def parse_profiles():
    out, meta = [], {}
    n = 0
    mfp = f"{RAW}/profiles_manifest.jsonl"
    if not os.path.exists(mfp):
        return out, meta, 0
    for line in open(mfp):
        r = json.loads(line)
        if not r.get("ok"):
            continue
        fp = f"{RAW}/profiles/{r['dx_id']}.html.gz"
        if not os.path.exists(fp):
            continue
        try:
            html = gzip.open(fp, "rb").read().decode("utf-8", "replace")
            doc = LH.fromstring(html)
        except Exception:
            continue
        n += 1
        h1 = doc.xpath("//h1")
        name = " ".join(h1[0].text_content().split()) if h1 else r["slug"].replace("-", " ")
        blk = doc.xpath('//div[contains(@class,"player")]')
        txt = " ".join(blk[0].text_content().split()) if blk else ""
        md = PROF_DRAFTED.search(txt)
        mr = PROF_RCSI.search(txt)
        ma = PROF_AGE.search(txt)
        meta[r["dx_id"]] = {
            "dx_id": r["dx_id"], "dx_slug": r["slug"], "player_name": name,
            "capture_ts": r.get("capture_ts", ""),
            "dx_draft_year": int(md.group(2)) if md else None,
            "dx_draft_pick": int(md.group(1)) if (md and md.group(1)) else None,
            "dx_rcsi_rank": int(mr.group(1)) if mr else None,
            "dx_hs_class_year": int(mr.group(2)) if mr else None,
            "dx_age_at_capture": float(ma.group(1)) if ma else None,
        }
        for t in doc.xpath("//table"):
            trs = t.xpath(".//tr")
            if len(trs) < 2:
                continue
            hdr = [c.lower() for c in cells(trs[0])]
            if hdr[:2] != ["year", "source"] or "wingspan" not in hdr:
                continue
            cols = [PROF_MAP.get(x, "_") for x in hdr]
            for tr in trs[1:]:
                c = cells(tr)
                if len(c) != len(cols) or not re.match(r"^\d{4}$", c[0] or ""):
                    continue
                rec = {"src_kind": "profile",
                       "src_path": f"/profile/{r['slug']}-{r['dx_id']}/",
                       "capture_ts": r.get("capture_ts", ""), "player_name": name,
                       "dx_id": r["dx_id"], "dx_slug": r["slug"], "event_year": int(c[0]),
                       "source": c[1].strip(), "source_from": "profile", "draft_pick": None}
                for k in MEAS:
                    rec[k] = None
                for nm, val in zip(cols, c):
                    if nm in INCH_FIELDS:
                        rec[nm] = to_inches(val)
                    elif nm in ZERO_NULL:
                        rec[nm] = to_float(val, zero_is_null=True)
                    elif nm in MEAS:
                        rec[nm] = to_float(val)
                out.append(rec)
    return out, meta, n


MEAS = ["height_noshoes_in", "height_shoes_in", "wingspan_in", "standing_reach_in",
        "max_vert_in", "max_vert_reach_in", "nostep_vert_in", "nostep_vert_reach_in",
        "weight_lb", "body_fat_pct", "hand_length_in", "hand_width_in", "bench_reps",
        "agility_s", "sprint_s"]


def fingerprint(r):
    """identity of a measurement event when the Source is unknown"""
    return tuple(round(r[k], 2) if isinstance(r.get(k), float) else None
                 for k in ("height_shoes_in", "height_noshoes_in", "wingspan_in",
                           "weight_lb", "standing_reach_in"))


def player_key(r):
    return r["dx_id"] or ("name:" + re.sub(r"[^a-z]", "", (r["player_name"] or "").lower()))


def main():
    listings, n_pages = parse_listings()
    profiles, meta, n_prof = parse_profiles()
    print(f"pages parsed={n_pages} listing rows={len(listings)} | "
          f"profiles parsed={n_prof} profile rows={len(profiles)}", flush=True)

    # ---- attach Source from profile rows onto same-(player, year) listing rows -------------
    prof_by = collections.defaultdict(list)
    for r in profiles:
        prof_by[(r["dx_id"], r["event_year"])].append(r)

    def close(a, b, tol):
        return a is not None and b is not None and abs(a - b) <= tol

    n_att = 0
    for r in listings:
        if r["source"] or not r["dx_id"]:
            continue
        cands = prof_by.get((r["dx_id"], r["event_year"]), [])
        hit = [p for p in cands
               if (close(r["height_shoes_in"], p["height_shoes_in"], 0.30) or
                   close(r["height_noshoes_in"], p["height_noshoes_in"], 0.30))
               and (r["weight_lb"] is None or p["weight_lb"] is None
                    or abs(r["weight_lb"] - p["weight_lb"]) <= 2)]
        if len(cands) == 1:
            hit = cands
        if len(hit) == 1:
            r["source"] = hit[0]["source"]
            r["source_from"] = "profile_join"
            n_att += 1
    print(f"listing rows given a source from profiles: {n_att}", flush=True)

    # ---- de-duplicate by (player, source, year) ------------------------------------------
    # Listing tables carry no Source, so within one (player, year) two different events are
    # separated by their measurements: a candidate row merges into an existing event only if
    # no shared measure disagrees by more than the tolerance below; otherwise it starts a new
    # event.  Profile rows (which do carry Source) are processed first so they seed the events.
    TOL = {"height_shoes_in": .3, "height_noshoes_in": .3, "wingspan_in": .3,
           "standing_reach_in": .5, "weight_lb": 3.0}

    def dist(m, r):
        d, n = 0.0, 0
        for k, tol in TOL.items():
            a, b = m.get(k), r.get(k)
            if a is None or b is None:
                continue
            if abs(a - b) > tol:
                return None                      # incompatible -> different event
            d += abs(a - b) / tol; n += 1
        return d if n else 0.0

    def coalesce(m, r):
        for k in MEAS + ["draft_pick"]:
            if m.get(k) is None and r.get(k) is not None:
                m[k] = r[k]
        if not m["source"] and r["source"]:
            m["source"], m["source_from"] = r["source"], r["source_from"]
        if not m["dx_id"] and r["dx_id"]:
            m["dx_id"], m["dx_slug"] = r["dx_id"], r["dx_slug"]

    order = {"profile": 0, "listing_2017": 1, "listing_legacy": 2}
    groups = collections.defaultdict(list)
    for r in sorted(listings + profiles, key=lambda x: order[x["src_kind"]]):
        g = groups[(player_key(r), r["event_year"])]
        tgt = None
        if r["source"]:
            same = [m for m in g if m["source"].lower() == r["source"].lower()]
            tgt = same[0] if same else None
        if tgt is None:
            cands = [(dist(m, r), i) for i, m in enumerate(g)
                     if (not m["source"] or not r["source"]) and dist(m, r) is not None]
            if cands:
                tgt = g[min(cands)[1]]
        if tgt is None:
            g.append(dict(r))
        else:
            coalesce(tgt, r)

    rows = sorted((r for g in groups.values() for r in g),
                  key=lambda r: (r["player_name"].lower(), r["event_year"]))
    with open(f"{D}/measurements_all.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLS})

    with open(f"{RAW}/profile_meta.csv", "w", newline="") as f:
        flds = ["dx_id", "dx_slug", "player_name", "capture_ts", "dx_draft_year",
                "dx_draft_pick", "dx_rcsi_rank", "dx_hs_class_year", "dx_age_at_capture"]
        w = csv.DictWriter(f, fieldnames=flds)
        w.writeheader()
        for m in meta.values():
            w.writerow({k: ("" if m.get(k) is None else m.get(k)) for k in flds})

    print(f"measurements_all.csv rows={len(rows)} "
          f"players={len(set(player_key(r) for r in rows))} "
          f"with_source={sum(1 for r in rows if r['source'])}", flush=True)
    yr = collections.Counter(r["event_year"] for r in rows)
    print("event years:", min(yr), "-", max(yr), flush=True)
    print("top sources:", collections.Counter(r["source"] for r in rows if r["source"]).most_common(12),
          flush=True)


if __name__ == "__main__":
    main()

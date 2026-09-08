"""measurements_all.csv -> pid-keyed growth-trajectory features (features.csv, dx_ prefix).

Identity match  : normalised name (accents/punctuation/suffixes stripped) between the DX profile
                  slug and tabular_names.csv, then a draft-year gate --
                  the DX profile's own "Drafted #N in the YYYY NBA Draft" must equal our
                  draft_year when present; otherwise every archived event year must be
                  <= draft_year and the last event within 6 years of it.  Anything that stays
                  ambiguous (>1 surviving DX id, or a draft-year contradiction) goes to
                  unmatched.csv and contributes nothing.
Dating          : DX records only a YEAR per event.  Every event is dated 1 June of that year
                  (essentially all sources -- combine, Portsmouth, Eurocamp, Hoop Summit and the
                  summer camps -- run April-July), so ages carry ~+-3 months of slack.
                  event_year <= draft_year is enforced, so every feature is pre-draft.
Birthdate       : 1 = age_verified_wiki.csv; 2 = the DX profile's "Age: A.B" as of its capture
                  date; 3 = class-year proxy, age = (event_year - hs_class_year) + 18.
"""
import csv, os, re, sys, math, json, collections, unicodedata, datetime as dt

sys.path.insert(0, os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages"))
import warnings; warnings.filterwarnings("ignore")
import numpy as np

D = "/Users/kennakao/nba/datarebuild/novel/draftexpress"
RAW = f"{D}/raw"
HAND = "/Users/kennakao/Downloads/nba_redraft_handoff"
IDENT = f"{HAND}/identity_KEEP_SEPARATE/tabular_names.csv"
AGEF = "/Users/kennakao/nba/datarebuild/age_verified_wiki.csv"
RSCIF = "/Users/kennakao/nba/datarebuild/rsci_features.csv"

EVENT_MONTH_DAY = (6, 1)          # nominal event date = 1 June of the event year
YOUTH_AGE_MAX = 17.5
SUF = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")

YOUTH_SOURCES = {
    "hoop summit", "nike hoop summit", "nike skills academy", "nike elite 100",
    "nike basketball academy", "nba top 100 camp", "usa basketball", "usa pan am team",
    "reebok breakout", "ua all-american camp", "elite 24", "lebron james camp",
    "kevin durant camp", "paul pierce camp", "vince carter camp", "deron williams camp",
    "amare stoudemire camp", "pg skills acad", "big man skills acad",
    "biosteel all-canadian game", "adidas nations",
}
PREDRAFT_SOURCES = {
    "nba draft combine", "2011 nba draft combine", "nba pre-draft camp", "predraft camp",
    "portsmouth", "pit", "eurocamp", "d-league elite camp", "nets workout",
    "clippers workout", "uk pro day", "official team", "official college team", "newspaper",
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("-", " ").replace("_", " ").replace("'", "")
    s = re.sub(r"[^a-z ]", " ", s)
    s = SUF.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def f(v):
    try:
        return float(v)
    except Exception:
        return None


def event_date(year):
    return dt.date(year, *EVENT_MONTH_DAY)


def ts_to_date(ts):
    try:
        return dt.date(int(ts[:4]), int(ts[4:6]), int(ts[6:8]))
    except Exception:
        return None


# ---------------------------------------------------------------- load ---------------------
rows = list(csv.DictReader(open(f"{D}/measurements_all.csv")))
ident = list(csv.DictReader(open(IDENT)))
wiki = {r["pid"]: r["birth_date"] for r in csv.DictReader(open(AGEF)) if r.get("birth_date")}
rsci = {r["pid"]: r for r in csv.DictReader(open(RSCIF))}
meta = {}
if os.path.exists(f"{RAW}/profile_meta.csv"):
    meta = {r["dx_id"]: r for r in csv.DictReader(open(f"{RAW}/profile_meta.csv"))}

for r in rows:
    r["event_year"] = int(r["event_year"])
    for k in ("height_noshoes_in", "height_shoes_in", "wingspan_in", "standing_reach_in",
              "max_vert_in", "nostep_vert_in", "weight_lb"):
        r[k] = f(r[k])

# shoe allowance, measured from the archive itself (median with-shoes minus no-shoes)
gaps = [r["height_shoes_in"] - r["height_noshoes_in"] for r in rows
        if r["height_shoes_in"] and r["height_noshoes_in"]
        and 0 < r["height_shoes_in"] - r["height_noshoes_in"] < 3]
SHOE_GAP = round(float(np.median(gaps)), 2) if gaps else 1.0

for r in rows:
    r["height_in"] = (r["height_shoes_in"] if r["height_shoes_in"] is not None
                      else (r["height_noshoes_in"] + SHOE_GAP
                            if r["height_noshoes_in"] is not None else None))

by_dx = collections.defaultdict(list)
for r in rows:
    if r["dx_id"]:
        by_dx[r["dx_id"]].append(r)

# ---------------------------------------------------------------- match --------------------
dx_names = collections.defaultdict(set)
for r in rows:
    if r["dx_id"]:
        dx_names[norm(r["dx_slug"] or r["player_name"])].add(r["dx_id"])

matched, unmatched = {}, []
for p in ident:
    pid, dy = p["pid"], int(float(p["draft_year"]))
    cands = sorted(dx_names.get(norm(p["player_name"]), set()))
    if not cands:
        continue
    keep, reasons = [], []
    for c in cands:
        m = meta.get(c)
        dxy = f(m["dx_draft_year"]) if m and m.get("dx_draft_year") else None
        yrs = [x["event_year"] for x in by_dx[c]]
        if dxy is not None:
            if int(dxy) == dy:
                keep.append(c)
            else:
                reasons.append(f"{c}:dx_draft_year={int(dxy)}!={dy}")
        elif yrs and max(yrs) <= dy and max(yrs) >= dy - 6:
            keep.append(c)
        else:
            reasons.append(f"{c}:event_years={min(yrs) if yrs else '-'}..{max(yrs) if yrs else '-'}")
    if len(keep) == 1:
        matched[pid] = keep[0]
    else:
        unmatched.append({"pid": pid, "draft_year": dy, "n_candidates": len(cands),
                          "n_surviving": len(keep), "dx_ids": "|".join(cands),
                          "surviving": "|".join(keep), "reject_reasons": ";".join(reasons)})

# ---------------------------------------------------------------- ages ---------------------
def birth_and_src(pid, dxid):
    if pid in wiki:
        try:
            y, mth, d = [int(x) for x in wiki[pid].split("-")[:3]]
            return dt.date(y, mth, d), 1
        except Exception:
            pass
    m = meta.get(dxid or "")
    if m and f(m.get("dx_age_at_capture")) and ts_to_date(m.get("capture_ts", "")):
        cap = ts_to_date(m["capture_ts"])
        return cap - dt.timedelta(days=f(m["dx_age_at_capture"]) * 365.25), 2
    return None, None


def age_at(pid, dxid, year, draft_year):
    b, src = birth_and_src(pid, dxid)
    if b is not None:
        return (event_date(year) - b).days / 365.25, src
    cy = None
    m = meta.get(dxid or "")
    if m and m.get("dx_hs_class_year"):
        cy = int(float(m["dx_hs_class_year"]))
    else:
        r = rsci.get(pid)
        if r and r.get("rsci_top100") == "1" and r.get("rsci_years_to_draft"):
            cy = draft_year - int(float(r["rsci_years_to_draft"]))
    if cy is not None:
        return (year - cy) + 18.0, 3
    return None, None


# ---------------------------------------------------------------- per-player series --------
def is_youth(ev, age):
    s = (ev["source"] or "").strip().lower()
    if s in YOUTH_SOURCES:
        return True
    if s in PREDRAFT_SOURCES:
        return False
    if age is not None:
        return age <= YOUTH_AGE_MAX
    return None


def series(pid, dxid, draft_year):
    evs = [dict(e) for e in by_dx.get(dxid, []) if e["event_year"] <= draft_year]
    evs.sort(key=lambda e: e["event_year"])
    src = None
    for e in evs:
        a, s = age_at(pid, dxid, e["event_year"], draft_year)
        e["age"] = a
        if s is not None and src is None:
            src = s
        e["youth"] = is_youth(e, a)
    return evs, src


# ---------------------------------------------------------------- late-grower regression ---
# fitted on ALL archived players (not just ours) who have a height at age <= 16 and a later
# height; ages for non-identity players come from the DX profile / class-year proxy only.
fit_x, fit_y = [], []
pid_by_dx = {v: k for k, v in matched.items()}
dy_by_pid = {p["pid"]: int(float(p["draft_year"])) for p in ident}
for dxid, evs in by_dx.items():
    pid = pid_by_dx.get(dxid)
    dy = dy_by_pid.get(pid, 9999)
    ev, _ = series(pid, dxid, dy)
    hs = [e for e in ev if e["height_in"] is not None and e["age"] is not None]
    if len(hs) < 2:
        continue
    early = [e for e in hs if e["age"] <= 16.0]
    if not early:
        continue
    e0, e1 = early[0], hs[-1]
    if e1["event_year"] <= e0["event_year"]:
        continue
    fit_x.append(e0["height_in"]); fit_y.append(e1["height_in"])

if len(fit_x) >= 20:
    A = np.vstack([np.ones(len(fit_x)), np.array(fit_x)]).T
    coef, *_ = np.linalg.lstsq(A, np.array(fit_y), rcond=None)
    LG_A, LG_B = float(coef[0]), float(coef[1])
    pred = A @ coef
    ss = 1 - ((np.array(fit_y) - pred) ** 2).sum() / ((np.array(fit_y) - np.mean(fit_y)) ** 2).sum()
    LG_N, LG_R2 = len(fit_x), float(ss)
else:
    LG_A = LG_B = LG_N = LG_R2 = None

# ---------------------------------------------------------------- features -----------------
FEATS = ["dx_n_events", "dx_n_sources_known", "dx_n_youth_events", "dx_years_spanned",
         "dx_first_event_year", "dx_last_event_year", "dx_has_youth_measurement",
         "dx_first_is_youth", "dx_earliest_age", "dx_last_age", "dx_age_src", "dx_age_is_proxy",
         "dx_first_height_in", "dx_first_wingspan_in", "dx_first_weight_lb", "dx_first_reach_in",
         "dx_first_ws_ht_ratio", "dx_last_height_in", "dx_last_wingspan_in", "dx_last_weight_lb",
         "dx_last_reach_in", "dx_last_ws_ht_ratio", "dx_d_height_in", "dx_d_wingspan_in",
         "dx_d_weight_lb", "dx_d_reach_in", "dx_d_max_vert_in", "dx_height_growth_per_yr",
         "dx_weight_gain_per_yr", "dx_height_at_16_in", "dx_late_grower_resid",
         "dx_still_growing"]


def first_last(evs, key):
    a = [e for e in evs if e.get(key) is not None]
    return (a[0], a[-1]) if a else (None, None)


out = []
prov = []
for p in ident:
    pid, dy = p["pid"], int(float(p["draft_year"]))
    dxid = matched.get(pid)
    if not dxid:
        continue
    evs, asrc = series(pid, dxid, dy)
    if not evs:
        continue
    r = {"pid": pid}
    r["dx_n_events"] = len(evs)
    r["dx_n_sources_known"] = sum(1 for e in evs if e["source"])
    r["dx_n_youth_events"] = sum(1 for e in evs if e["youth"] is True)
    r["dx_first_event_year"] = evs[0]["event_year"]
    r["dx_last_event_year"] = evs[-1]["event_year"]
    r["dx_years_spanned"] = evs[-1]["event_year"] - evs[0]["event_year"]
    r["dx_has_youth_measurement"] = 1 if any(e["youth"] is True for e in evs) else 0
    r["dx_first_is_youth"] = 1 if evs[0]["youth"] is True else (0 if evs[0]["youth"] is False else "")
    r["dx_earliest_age"] = round(evs[0]["age"], 2) if evs[0]["age"] is not None else ""
    r["dx_last_age"] = round(evs[-1]["age"], 2) if evs[-1]["age"] is not None else ""
    r["dx_age_src"] = asrc if asrc else ""
    r["dx_age_is_proxy"] = "" if not asrc else (0 if asrc == 1 else 1)

    for tag, key, col in (("height", "height_in", "dx_%s_height_in"),
                          ("wingspan", "wingspan_in", "dx_%s_wingspan_in"),
                          ("weight", "weight_lb", "dx_%s_weight_lb"),
                          ("reach", "standing_reach_in", "dx_%s_reach_in")):
        a, b = first_last(evs, key)
        r[col % "first"] = round(a[key], 2) if a else ""
        r[col % "last"] = round(b[key], 2) if b else ""

    for tag in ("first", "last"):
        h, w = r[f"dx_{tag}_height_in"], r[f"dx_{tag}_wingspan_in"]
        r[f"dx_{tag}_ws_ht_ratio"] = round(w / h, 4) if (h and w) else ""

    def delta(key, name, tol_years=1):
        a, b = first_last(evs, key)
        if a and b and b["event_year"] > a["event_year"]:
            r[name] = round(b[key] - a[key], 2)
            return a, b
        r[name] = ""
        return None, None

    h0, h1 = delta("height_in", "dx_d_height_in")
    delta("wingspan_in", "dx_d_wingspan_in")
    w0, w1 = delta("weight_lb", "dx_d_weight_lb")
    delta("standing_reach_in", "dx_d_reach_in")
    delta("max_vert_in", "dx_d_max_vert_in")
    r["dx_height_growth_per_yr"] = (round((h1["height_in"] - h0["height_in"]) /
                                          (h1["event_year"] - h0["event_year"]), 3)
                                    if h0 else "")
    r["dx_weight_gain_per_yr"] = (round((w1["weight_lb"] - w0["weight_lb"]) /
                                        (w1["event_year"] - w0["event_year"]), 2)
                                  if w0 else "")

    hs = [e for e in evs if e["height_in"] is not None]
    early = [e for e in hs if e["age"] is not None and e["age"] <= 16.0]
    r["dx_height_at_16_in"] = round(early[0]["height_in"], 2) if early else ""
    if early and LG_A is not None and hs[-1]["event_year"] > early[0]["event_year"]:
        r["dx_late_grower_resid"] = round(
            hs[-1]["height_in"] - (LG_A + LG_B * early[0]["height_in"]), 2)
    else:
        r["dx_late_grower_resid"] = ""

    win = [e for e in hs if e["event_year"] >= hs[-1]["event_year"] - 2] if hs else []
    r["dx_still_growing"] = (1 if (len(win) >= 2 and
                                   hs[-1]["height_in"] - win[0]["height_in"] >= 0.5)
                             else (0 if len(win) >= 2 else ""))
    out.append(r)
    prov.append({"pid": pid, "dx_id": dxid, "n_events": len(evs),
                 "event_years": "|".join(str(e["event_year"]) for e in evs),
                 "sources": "|".join(e["source"] or "?" for e in evs),
                 "age_src": asrc or "", "capture_ts": "|".join(
                     sorted({e["capture_ts"] for e in evs if e["capture_ts"]}))[:200]})

with open(f"{D}/features.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["pid"] + FEATS)
    w.writeheader()
    for r in out:
        w.writerow(r)

with open(f"{D}/unmatched.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["pid", "draft_year", "n_candidates", "n_surviving",
                                       "dx_ids", "surviving", "reject_reasons"])
    w.writeheader(); w.writerows(unmatched)

with open(f"{D}/provenance.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["pid", "dx_id", "n_events", "event_years", "sources",
                                       "age_src", "capture_ts"])
    w.writeheader(); w.writerows(prov)

stats = {"shoe_gap_in": SHOE_GAP, "late_grower_intercept": LG_A, "late_grower_slope": LG_B,
         "late_grower_n": LG_N, "late_grower_r2": LG_R2,
         "measurement_rows": len(rows), "dx_players": len(by_dx),
         "matched_pids": len(matched), "unmatched_rows": len(unmatched),
         "feature_rows": len(out)}
json.dump(stats, open(f"{D}/build_stats.json", "w"), indent=1)
print(json.dumps(stats, indent=1))

band = lambda y: "2000-07" if y <= 2007 else ("2008-18" if y <= 2018 else "2019-25")
cov = collections.Counter(); tot = collections.Counter()
have = {r["pid"] for r in out}
for p in ident:
    y = int(float(p["draft_year"])); tot[band(y)] += 1
    if p["pid"] in have:
        cov[band(y)] += 1
for b in ("2000-07", "2008-18", "2019-25"):
    print(f"coverage {b}: {cov[b]}/{tot[b]} = {100.0*cov[b]/max(tot[b],1):.1f}%")

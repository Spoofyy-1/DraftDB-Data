"""Bounded, resumable ESPN participation-calendar pilot. No WAR or fitting.

Raw responses remain private because source athlete metadata and statistics have
fields unrelated to this calendar task. Export only identity, actual played
season, season type, and source provenance. Do not promote candidate crosswalks
or treat an unfinished athlete catalog as a complete league calendar.
"""
import argparse
import hashlib
import http.client
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd


def norm(s):
    return re.sub("[^a-z0-9]", "", unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower())


def read_json_response(response):
    chunks = []
    try:
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
    except http.client.IncompleteRead as error:
        chunks.append(error.partial)
    raw = b"".join(chunks)
    # A valid complete JSON object is mandatory even when a server omits a
    # chunked-transfer trailer. Truncated JSON is never accepted or cached.
    return raw, json.loads(raw)


class Fetcher:
    def __init__(self, root, max_requests, delay, total_ceiling=30, web_attempts=3):
        self.root, self.limit, self.delay = root, max_requests, delay
        self.total_ceiling, self.web_attempts = total_ceiling, web_attempts
        self.sent = 0
        self.log = root / "collector_requests.jsonl"
        self.private = root / "private"
        self.private.mkdir(exist_ok=True, mode=0o700)
        self.index_path = root / "cache_index.json"
        self.index = json.loads(self.index_path.read_text()) if self.index_path.exists() else {}

    def fetch(self, url):
        if url in self.index:
            entry = self.index[url]
            path = self.root / entry["path"]
            raw = path.read_bytes()
            assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
            return json.loads(raw), entry
        if self.sent >= self.limit:
            raise RuntimeError("per_run_request_budget_exhausted")
        host = urllib.parse.urlparse(url).hostname
        histories = [self.root / "pilot_requests.jsonl", self.log]
        for history in histories:
            if not history.exists():
                continue
            for line in history.read_text().splitlines():
                prior = json.loads(line)
                if urllib.parse.urlparse(prior["url"]).hostname != host:
                    continue
                status = prior.get("status")
                if status == 403 or "HTTP Error 403" in prior.get("error", ""):
                    raise RuntimeError("source_403_requires_review_before_retry")
                if status == 429 or "HTTP Error 429" in prior.get("error", ""):
                    stamp = prior.get("requested_at", prior.get("time", 0))
                    try:
                        seconds = max(3600, float(prior.get("retry_after") or 3600))
                    except ValueError:
                        from email.utils import parsedate_to_datetime
                        seconds = max(3600, parsedate_to_datetime(prior["retry_after"]).timestamp() - stamp)
                    if time.time() < stamp + seconds:
                        raise RuntimeError("source_429_cooldown_active")
        # This pilot's cumulative ceiling includes the earlier exploratory calls
        # and three failed web-tool opens, not merely successful HTTP responses.
        pilot_log = self.root / "pilot_requests.jsonl"
        old = len(pilot_log.read_text().splitlines()) if pilot_log.exists() else 0
        new = len(self.log.read_text().splitlines()) if self.log.exists() else 0
        if old + new + self.web_attempts >= self.total_ceiling:
            raise RuntimeError("cumulative_request_ceiling_reached")
        time.sleep(self.delay)
        event = {"url": url, "requested_at": time.time()}
        self.sent += 1
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                event["status"] = response.status
                raw, value = read_json_response(response)
            digest = hashlib.sha256(raw).hexdigest()
            path = self.private / (hashlib.sha256(url.encode()).hexdigest() + ".json")
            path.write_bytes(raw)
            event.update(sha256=digest, path=str(path.relative_to(self.root)))
            self.index[url] = event
            self.index_path.write_text(json.dumps(self.index, indent=2))
        except urllib.error.HTTPError as error:
            event.update(status=error.code, error=str(error), retry_after=error.headers.get("Retry-After"))
            raise
        except Exception as error:
            event["error"] = str(error)
            raise
        finally:
            with self.log.open("a") as file:
                file.write(json.dumps(event) + "\n")
        return value, event


def parse_participation(value, season_type):
    filters = {x["name"]: str(x["value"]) for x in value["filters"]}
    assert filters["league"] == "nba", "source did not return NBA statistics"
    if not value.get("categories"):
        return set(), "no_statistics_table_returned"
    season_filter = next(x for x in value["filters"] if x["name"] == "seasontype")
    available_types = {str(x["value"]) for x in season_filter["options"]}
    if season_type == 3 and filters["seasontype"] == "2" and "3" not in available_types:
        # ESPN silently returns regular-season data when no postseason table is
        # offered. Never relabel those rows as postseason participation.
        return set(), "source_has_no_postseason_table"
    assert filters["seasontype"] == str(season_type), "source ignored requested season type"
    categories = [x for x in value["categories"] if "gamesPlayed" in x.get("names", [])]
    assert len(categories) == 1
    category = categories[0]
    names = category["names"]
    index = names.index("gamesPlayed")
    dates = set()
    for row in category["statistics"]:
        assert len(row["stats"]) == len(names)
        year = int(row["season"]["year"])
        # Use the explicit publisher season year. The display name is a second
        # independent format check; neither date comes from draft year.
        display = row["season"]["displayName"]
        assert display == f"{year-1}-{str(year)[-2:]}"
        games = float(str(row["stats"][index]).replace(",", ""))
        assert games >= 0 and games.is_integer()
        if games > 0:
            dates.add(year)
    return dates, "explicit_played_season_rows"


def main(args):
    root = args.output or Path(__file__).resolve().parent
    root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    fetcher = Fetcher(root, args.max_requests, max(1, args.delay), args.request_ceiling, args.web_attempts)
    identities = pd.read_csv(args.identity, usecols=["pid", "draft_year", "player_name", "nba_id"])
    identities["key"] = identities.player_name.map(norm)
    source = pd.read_csv(args.raptor, usecols=["player_name", "player_id", "season"])
    source["key"] = source.player_name.map(norm)
    completed_path = root / "completed_athletes.json"
    completed = json.loads(completed_path.read_text()) if completed_path.exists() else {}
    athlete_ids = args.athletes or json.loads(args.athlete_list.read_text())
    athlete_ids = athlete_ids[:args.limit_athletes]
    state = {"status": "running", "requested_athletes": len(athlete_ids), "completed_athletes": len(completed),
             "source": "ESPN explicit NBA played-season rows, regular season and postseason", "model_safe": False}
    def checkpoint_state():
        current_values = list(completed.values())
        state.update(completed_athletes=len(completed), request_count_this_run=fetcher.sent, updated_at=time.time(),
                     elapsed_seconds=time.monotonic() - started,
                     verified_timelines=sum(v.get("timeline_verified", False) for v in current_values),
                     partial_timelines=sum(v.get("timeline_partial", False) for v in current_values),
                     participation_rows=sum(len(v.get("participation", [])) for v in current_values))
        temp = root / "pilot_summary.json.tmp"
        temp.write_text(json.dumps(state, indent=2))
        temp.replace(root / "pilot_summary.json")
    checkpoint_state()
    try:
        for athlete_id in athlete_ids:
            if time.monotonic() - started >= args.max_seconds:
                raise RuntimeError("wall_time_budget_exhausted")
            if str(athlete_id) in completed:
                continue
            base = f"https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/athletes/{athlete_id}"
            try:
                identity, identity_provenance = fetcher.fetch(base)
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
                completed[str(athlete_id)] = {"status": "identity_source_404_unresolved", "source_url": base,
                                              "timeline_verified": False, "timeline_partial": True}
                completed_path.write_text(json.dumps(completed, indent=2))
                checkpoint_state()
                continue
            assert str(identity["id"]) == str(athlete_id)
            key = norm(identity["fullName"])
            matches = identities[(identities.key == key) & identities.nba_id.notna()]
            if len(matches) != 1:
                completed[str(athlete_id)] = {"status": "no_unique_project_name", "match_count": len(matches)}
                completed_path.write_text(json.dumps(completed, indent=2))
                checkpoint_state()
                continue
            match = matches.iloc[0]
            if int(match.draft_year) > 2024:
                completed[str(athlete_id)] = {"status": "project_cohort_after_required_calendar_window"}
                completed_path.write_text(json.dumps(completed, indent=2))
                checkpoint_state()
                continue
            records, union, availability = [], set(), {}
            for season_type in [2, 3]:
                url = f"https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{athlete_id}/stats"
                if season_type == 3:
                    url += "?seasontype=3"
                try:
                    stats, provenance = fetcher.fetch(url)
                except urllib.error.HTTPError as error:
                    if error.code != 404:
                        raise
                    availability[str(season_type)] = "source_table_404_unresolved"
                    continue
                dates, table_status = parse_participation(stats, season_type)
                availability[str(season_type)] = table_status
                union |= dates
                for year in sorted(dates):
                    if 2023 <= year <= 2025:
                        records.append(dict(pid=match.pid, nba_id=int(match.nba_id), espn_id=str(athlete_id),
                                            season_end=year, season_type=season_type, source_url=url,
                                            source_sha256=provenance["sha256"]))
            historical = source[source.key == key]
            historical_unique = historical.player_id.nunique() == 1
            historical_dates = set(int(x) for x in historical.season if x > int(match.draft_year))
            espn_prior = {x for x in union if int(match.draft_year) < x <= 2022}
            historical_agreement = bool(historical_dates) and historical_unique and historical_dates == espn_prior
            both_explicit = all(v == "explicit_played_season_rows" for v in availability.values())
            result = dict(status="dates_collected" if union else "no_participation_evidence", pid=match.pid, nba_id=int(match.nba_id), espn_id=str(athlete_id),
                          identity_join="exact_unique_normalized_project_name; NBA ID supplied by project identity table, not ESPN",
                          historical_calendar_agreement=historical_agreement,
                          source_table_availability=availability,
                          timeline_verified=bool(historical_agreement and both_explicit),
                          timeline_partial=not (historical_agreement and both_explicit),
                          NBA_ID_source="existing project identity mapping, not supplied by ESPN",
                          all_recorded_seasons=sorted(union),
                          verified_historical_season_count=len(historical_dates) if historical_agreement else 0,
                          crosswalk_needs_review=not historical_agreement,
                          identity_source_url=base, identity_source_sha256=identity_provenance["sha256"],
                          date_of_birth_available=bool(identity.get("dateOfBirth")), participation=records)
            completed[str(athlete_id)] = result
            completed_path.write_text(json.dumps(completed, indent=2))
            checkpoint_state()
        state["status"] = "bounded_collection_complete"
    except urllib.error.HTTPError as error:
        state.update(status="paused_source_error", error=f"HTTP {error.code}", retry_after=error.headers.get("Retry-After"))
        # Stop immediately on all HTTP errors. In particular, never switch
        # credentials, proxies, or hosts to work around a source's 403/429.
    except Exception as error:
        state.update(status="paused", error=f"{type(error).__name__}: {error}")
    values = list(completed.values())
    rows = [r for v in values for r in v.get("participation", [])]
    state.update(completed_athletes=len(completed), collected_athletes=sum(v["status"] == "dates_collected" for v in values),
                 request_count_this_run=fetcher.sent,
                 crosswalk_historical_checks_passed=sum(v.get("historical_calendar_agreement", False) for v in values),
                 crosswalks_needing_review=sum(v.get("crosswalk_needs_review", False) for v in values),
                 verified_timelines=sum(v.get("timeline_verified", False) for v in values),
                 partial_timelines=sum(v.get("timeline_partial", False) for v in values),
                 participation_rows=len(rows), seasons=sorted({r["season_end"] for r in rows}),
                 counts_by_season_type={str(t): len({(r["pid"], r["season_end"]) for r in rows if r["season_type"] == t}) for t in [2, 3]},
                 league_calendar_complete=False, updated_at=time.time())
    (root / "pilot_summary.json").write_text(json.dumps(state, indent=2))
    if rows:
        pd.DataFrame(rows).to_csv(root / "participation_dates.csv", index=False)
    print(json.dumps(state))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--raptor", type=Path, required=True)
    seeds = parser.add_mutually_exclusive_group(required=True)
    seeds.add_argument("--athletes", nargs="+", type=int)
    seeds.add_argument("--athlete-list", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit-athletes", type=int, default=300)
    parser.add_argument("--max-seconds", type=int, default=7200)
    parser.add_argument("--request-ceiling", type=int, default=30)
    parser.add_argument("--web-attempts", type=int, default=3)
    parser.add_argument("--max-requests", type=int, default=10)
    parser.add_argument("--delay", type=float, default=1.0)
    main(parser.parse_args())

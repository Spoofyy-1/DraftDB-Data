"""Fixed arithmetic college team context; candidate data, no model or NBA labels.

Only fully passing cached team-seasons are used. This is not proof that the
upstream schedule is complete or that its original publication vintage is known.
"""
from pathlib import Path
import argparse, collections, csv, datetime as dt, hashlib, json, math

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'college_oliver_reconstruction'
LINEAGE = ROOT.parent / 'fifty_audit/source_row_lineage.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def divide(numerator, denominator):
    return numerator / denominator if denominator > 0 else None


def features(row):
    """No fitted coefficients, guessed player totals or possession estimates."""
    t = {k: float(v) for k, v in row.items() if k.startswith(('team_', 'opponent_')) and k != 'team_id'}
    g = float(row['validated_games'])
    f = {
        'tctx_points_pg': t['team_pts'] / g,
        'tctx_opponent_points_pg': t['opponent_pts'] / g,
        'tctx_margin_pg': (t['team_pts'] - t['opponent_pts']) / g,
        'tctx_shot_attempts_pg': t['team_fga'] / g,
        'tctx_opponent_shot_attempts_pg': t['opponent_fga'] / g,
        'tctx_efg': divide(t['team_fgm'] + .5 * t['team_fg3m'], t['team_fga']),
        'tctx_opponent_efg': divide(t['opponent_fgm'] + .5 * t['opponent_fg3m'], t['opponent_fga']),
        'tctx_ft_attempts_per_fga': divide(t['team_fta'], t['team_fga']),
        'tctx_opponent_ft_attempts_per_fga': divide(t['opponent_fta'], t['opponent_fga']),
        'tctx_three_attempt_share': divide(t['team_fg3a'], t['team_fga']),
        'tctx_opponent_three_attempt_share': divide(t['opponent_fg3a'], t['opponent_fga']),
        'tctx_offensive_rebound_share': divide(t['team_orb'], t['team_orb'] + t['opponent_drb']),
        'tctx_defensive_rebound_share': divide(t['team_drb'], t['team_drb'] + t['opponent_orb']),
        'tctx_turnovers_per_fga': divide(t['team_tov'], t['team_fga']),
        'tctx_opponent_turnovers_per_fga': divide(t['opponent_tov'], t['opponent_fga']),
        'tctx_assists_per_made_fg': divide(t['team_ast'], t['team_fgm']),
        'tctx_opponent_assists_per_made_fg': divide(t['opponent_ast'], t['opponent_fgm']),
        'tctx_steals_per_opponent_turnover': divide(t['team_stl'], t['opponent_tov']),
        'tctx_blocks_per_opponent_fga': divide(t['team_blk'], t['opponent_fga']),
    }
    f['tctx_efg_margin'] = f['tctx_efg'] - f['tctx_opponent_efg'] if f['tctx_efg'] is not None and f['tctx_opponent_efg'] is not None else None
    assert len(f) == 20 and all(v is None or math.isfinite(v) for v in f.values())
    return f


def eligible(row, year):
    try:
        season = int(row['source_season'])
        start = dt.date.fromisoformat(row['min_date'])
        end = dt.date.fromisoformat(row['max_date'])
        return (2008 <= season <= min(year, 2018)
                and 0 <= year - season <= 1
                and dt.date(season - 1, 7, 1) <= start <= end <= dt.date(season, 5, 31)
                and int(row['rejected_source_games']) == 0
                and int(row['raw_source_games']) == int(row['validated_games'])
                and int(row['validated_games']) >= 20)
    except (ValueError, KeyError, TypeError):
        return False


def build(max_source_season=2018, output=ROOT):
    output.mkdir(parents=True, exist_ok=True)
    allow = json.loads((SOURCE/'PUBLIC_ALLOWLIST.json').read_text())
    source_files = ['team_season_totals_candidate.csv', 'coverage.json', 'schema_manifest.json', 'team_game_lineage.csv.gz']
    for name in source_files:
        assert name in allow['files'], name
        assert sha(SOURCE/name) == allow['files'][name]['sha256'], name
    with (SOURCE/source_files[0]).open() as stream:
        totals = list(csv.DictReader(stream))
    by_key = {}
    for row in totals:
        if int(row['source_season']) > max_source_season:
            continue
        key = (int(row['source_season']), row['team_id'])
        assert key not in by_key, 'Duplicate team-season'
        by_key[key] = row
    lineage = [p for p in json.loads(LINEAGE.read_text()) if int(p['draft_year']) <= 2018]
    assert len({p['pid'] for p in lineage}) == len(lineage)
    rows = []; provenance = []; rejected = []; columns = None
    for player in lineage:
        year = int(player['draft_year']); focal = player['focal']; season = int(focal['season'])
        team = 'team_' + hashlib.sha256(focal['team'].encode()).hexdigest()[:20]
        record = {'pid': player['pid'], 'draft_year': year, 'source_season': season}
        source = by_key.get((season, team))
        if source is not None and eligible(source, year):
            values = features(source); columns = sorted(values)
            record.update(values)
            provenance.append({'pid':player['pid'], 'draft_year':year, 'source_season':season,
                               'team_id':team, 'validated_games':int(source['validated_games']),
                               'min_game_date':source['min_date'], 'max_game_date':source['max_date'],
                               'college_source_row':focal['source_row'],
                               'college_allowed_values_hash':focal['allowed_values_hash'],
                               'match':'exact existing focal team and source season',
                               'source_file':f'team_season_totals_candidate.csv',
                               'source_totals_sha256':sha(SOURCE/source_files[0]),
                               'original_publication_vintage_verified':False,
                               'complete_schedule_verified':False})
        else:
            rejected.append({'pid':player['pid'], 'source_season':season,
                             'reason':'no team match' if source is None else 'cached season incomplete, invalid or fewer than20 games'})
        rows.append(record)
    assert columns
    write_csv(output/'team_context_train_candidates.csv', rows, ['pid','draft_year','source_season']+columns)
    write_csv(output/'provenance.csv', provenance, list(provenance[0]))
    write_csv(output/'quarantine.csv', rejected, ['pid','source_season','reason'])
    coverage = collections.Counter(str(r['draft_year']) for r in provenance)
    summary = {'source_seasons':[2008,max_source_season], 'features':20, 'historical_lineage_rows_preserved':len(rows),
               'rows_with_features':len(provenance), 'rows_all_missing':len(rejected),
               'coverage_by_draft_year':dict(sorted(coverage.items())),
               'NBA_outcomes_or_picks_read':False, 'models_run':0, 'original_inputs_modified':False,
               'model_eligible':False, 'status':'Candidate features pending independent review and schedule/vintage checks',
               'minimum_cached_games':20, 'whole_team_season_rejected_if_any_cached_game_fails':True,
               'all_missing_rows_preserved':True, 'source_files_sha256':{name:sha(SOURCE/name) for name in source_files},
               'focal_lineage_sha256':sha(LINEAGE),
               'limitation':'Reconstructed historical game facts, not verified original publication snapshots; complete schedule not established. Per-game values include overtime. Raw context is unadjusted for opponent strength.'}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['source_files_sha256','limitation']}))
    return summary


def write_csv(path, rows, columns):
    with path.open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=columns); writer.writeheader(); writer.writerows(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--max-source-season',type=int,default=2018)
    parser.add_argument('--output',type=Path,default=ROOT); args = parser.parse_args()
    assert 2008 <= args.max_source_season <= 2018
    build(args.max_source_season,args.output)

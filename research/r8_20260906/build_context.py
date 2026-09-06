"""Build new college opportunity/context features without reading NBA outcomes.

Names stay on the Mac. Exact normalized names must resolve to one Torvik player ID;
ambiguous matches are rejected. Source season must be <= the prospect's draft year.
Never use Torvik column 45 (NBA pick), outcomes, or future college seasons.
"""
import csv, gzip, glob, hashlib, json, re, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[2]
RAW = REPO/'tracking_raw'
IDS = REPO/'identity'

def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'\b(jr|sr|ii|iii|iv)\b', '', s)
    return re.sub(r'[^a-z0-9]', '', s)

def main():
    # Explicit source indices rather than permissive use of every numeric field.
    fields = {3:'gp',4:'minutes_share',6:'usage',7:'efg',8:'ts',9:'orb',10:'drb',
              11:'ast_pct',12:'tov_pct',13:'ftm',14:'fta',15:'ft_pct',16:'fg2m',
              17:'fg2a',18:'fg2_pct',19:'fg3m',20:'fg3a',21:'fg3_pct',22:'blk_pct',
              23:'stl_pct',24:'ftr',30:'fouls40',35:'ast_tov',36:'rim_made',
              37:'rim_attempts',38:'mid_made',39:'mid_attempts',42:'dunk_made',
              43:'dunk_attempts',54:'mpg',57:'oreb_pg',58:'dreb_pg',60:'ast_pg',
              61:'stl_pg',62:'blk_pg',63:'pts_pg'}
    records=[]; sources={}
    for fp in sorted(RAW.glob('torvik_*.csv.gz')):
        year=int(fp.name.split('_')[1].split('.')[0])
        if year>2018: continue  # Research preparation has no test-year source access.
        sources[fp.name]=hashlib.sha256(fp.read_bytes()).hexdigest()
        for r in csv.reader(gzip.open(fp,'rt')):
            if len(r)!=67 or int(r[31])!=year: raise ValueError(f'Unexpected source schema: {fp}')
            rec=dict(name=norm(r[0]),team=r[1],season=year,tpid=r[32],height=r[26],birthdate=r[66])
            for i,c in fields.items():
                try: rec[c]=float(r[i])
                except ValueError: rec[c]=np.nan
            records.append(rec)
    d=pd.DataFrame(records)
    names={n:x for n,x in d.groupby('name')}
    teams={k:x for k,x in d.groupby(['season','team'])}
    ids=pd.read_csv(next(IDS.glob('*.csv')))
    rows=[]; provenance=[]; rejected=[]
    for p in ids[ids.draft_year<=2018].itertuples():
        cand=names.get(norm(p.player_name))
        if cand is None: continue
        cand=cand[cand.season<=p.draft_year]
        if cand.empty: continue
        last_year=int(cand.season.max())
        last=cand[cand.season==last_year]
        if p.draft_year-last_year>1 or last.tpid.nunique()!=1:
            rejected.append(dict(pid=p.pid,reason='stale_or_ambiguous')); continue
        last=last.sort_values('minutes_share').iloc[-1]
        # Only historical records for the identified college player, never later revisions of his career.
        history=cand[cand.tpid==last.tpid].sort_values('season')
        f={'pid':p.pid,'source_season':last_year}
        for c in fields.values(): f['ctx_base_'+c]=last[c]
        bd=pd.to_datetime(last.birthdate,errors='coerce')
        f['ctx_base_age']=((pd.Timestamp(int(p.draft_year),6,1)-bd).days/365.25) if pd.notna(bd) else np.nan
        hm=re.fullmatch(r'(\d)-(\d{1,2})',str(last.height))
        f['ctx_base_height']=12*int(hm[1])+int(hm[2]) if hm else np.nan
        total=last.fg2a+last.fg3a
        f['ctx_base_three_share']=last.fg3a/total if total>0 else np.nan
        peers=teams[(last_year,last.team)]
        peers=peers[peers.tpid!=last.tpid]
        w=peers.minutes_share.clip(lower=0).fillna(0)
        for c in ['usage','ts','ast_pct','orb','drb','stl_pct','blk_pct']:
            ok=peers[c].notna()&(w>0)
            avg=float(np.average(peers.loc[ok,c],weights=w[ok])) if ok.any() else np.nan
            f['ctx_team_peer_'+c]=avg
            f['ctx_team_gap_'+c]=last[c]-avg
        f['ctx_team_rotation_depth']=int((peers.minutes_share>=30).sum())
        f['ctx_team_creator_competition']=int(((peers.usage>=22)&(peers.minutes_share>=30)).sum())
        f['ctx_team_guard_competition']=int(((peers.ast_pct>=20)&(peers.minutes_share>=30)).sum())
        prev=history[history.season<last_year]
        f['ctx_growth_seasons']=history.season.nunique()
        if not prev.empty:
            previous=prev.iloc[-1]
            for c in ['usage','minutes_share','ts','ast_pct','tov_pct','stl_pct','blk_pct','fg3a','ft_pct']:
                f['ctx_growth_'+c]=(last[c]-previous[c])/(last_year-previous.season)
            f['ctx_growth_changed_team']=int(previous.team!=last.team)
        f['ctx_skill_defense_discipline']=(last.stl_pct+last.blk_pct)/(last.fouls40+1) if last.fouls40>=0 else np.nan
        f['ctx_skill_creation_control']=last.ast_pct/(last.tov_pct+1) if last.tov_pct>=0 else np.nan
        f['ctx_skill_usage_efficiency']=(last.usage-20)*(last.ts-50)/100
        f['ctx_skill_ft_volume']=last.ft_pct*np.log1p(last.fta) if last.fta>=0 else np.nan
        rows.append(f)
        provenance.append(dict(pid=p.pid,draft_year=int(p.draft_year),source_season=last_year,
                               source=f'torvik_{last_year}.csv.gz',match='exact_unique_name_and_tpid'))
    out=pd.DataFrame(rows)
    assert out.pid.is_unique
    out.to_csv(ROOT/'context_train.csv',index=False)
    json.dump(dict(source_hashes=sources,rows=len(out),features=len(out.columns)-2,
                   provenance=provenance,rejected=rejected,
                   limitation='Historical season tables retrieved in 2026; original publication vintages unavailable.'),
              open(ROOT/'context_manifest.json','w'),indent=2)
    print(json.dumps(dict(rows=len(out),features=len(out.columns)-2,rejected=len(rejected))))

if __name__=='__main__': main()

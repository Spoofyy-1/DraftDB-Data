"""50 explicit pre-draft hypotheses from observed college-season box scores.
No NBA pick, outcome, rating or current biography field is used.
"""
import argparse,csv,gzip,hashlib,json,re,unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

FIELDS={3:'gp',4:'minutes',6:'usage',8:'ts',9:'orb',10:'drb',11:'ast',12:'tov',13:'ftm',14:'fta',15:'ftp',16:'two_m',17:'two_a',18:'two_p',19:'three_m',20:'three_a',21:'three_p',22:'blk',23:'stl',24:'ftr',30:'foul',35:'ast_tov',36:'rim_m',37:'rim_a',38:'mid_m',39:'mid_a',42:'dunk_m',43:'dunk_a',54:'mpg',60:'ast_pg'}
PEER=['usage','ts','ast','tov','orb','drb','stl','blk']
SLOPE=['two_p','three_p','ftp','ftr','ast_tov','orb','drb','minutes','ts','usage']
SHARE=['fta','three_a','rim_a','dunk_a','ftm','three_m']
POST={'ft':('ftm','fta',.70,20),'three':('three_m','three_a',.34,50),'rim':('rim_m','rim_a',.60,30),'mid':('mid_m','mid_a',.40,30),'dunk':('dunk_m','dunk_a',.90,10),'two':('two_m','two_a',.50,40)}
def norm(s):
    s=unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower()
    return re.sub('[^a-z0-9]','',re.sub(r'\b(jr|sr|ii|iii|iv)\b','',s))
def div(a,b):return float(a/b) if np.isfinite(a) and np.isfinite(b) and b>0 else np.nan
def weighted(values,weights):
    ok=np.isfinite(values)&np.isfinite(weights)&(weights>0)
    return float(np.average(values[ok],weights=weights[ok])) if ok.any() else np.nan
def catalog():
    defs=[]
    def add(name,group,formula):defs.append(dict(name='f50_'+name,group=group,formula=formula,source='Bart Torvik public player-season CSV; explicit raw box-score fields only'))
    for c in PEER:add('peer_sd_'+c,'teammate_distribution',f'Minutes-weighted SD of teammate {c}; focal player excluded')
    for c in PEER:add('peer_rank_'+c,'within_team_role',f'(number of eligible teammates with {c} below player + half ties) / eligible teammate count')
    for c in SHARE:add('team_share_'+c,'team_opportunity',f'Player {c} / (player {c} + sum of teammate {c}); null if any teammate value missing')
    for name,formula in [('peer_three_diet','Minutes-weighted teammate 3PA / (2PA+3PA)'),('peer_rim_diet','Minutes-weighted teammate rim attempts / (2PA+3PA)'),('peer_defense_density','Minutes-weighted teammate (STL%+BLK%)'),('peer_creation_density','Minutes-weighted teammate AST% / (TOV%+1)'),('minutes_concentration','Herfindahl concentration of team minute shares, including focal player'),('usage_concentration','Herfindahl concentration of minutes×usage across team')]:add(name,'roster_structure',formula)
    for c in SLOPE:add('career_slope_'+c,'development',f'OLS slope of {c} against actual college season year; at least two unique prior seasons')
    for c,(_,_,mu,n) in POST.items():add('posterior_'+c,'shooting_reliability',f'(makes + {mu}×{n}) / (attempts+{n}); fixed prior, observed attempts only')
    for name,formula in [('nondunk_rim_pct','(rim makes−dunk makes)/(rim attempts−dunk attempts)'),('rim_ft_pressure','(rim attempts+0.44×FTA)/(2PA+3PA+0.44×FTA)'),('perimeter_ft_agreement','3PA/(2PA+3PA) × posterior FT probability'),('assist_usage_efficiency','AST%/(usage+1) × (1−clip(TOV%,0,100)/100)'),('balanced_stocks','2×STL%×BLK%/(STL%+BLK%)'),('foul_adjusted_rebounds','(ORB%+DRB%)/(fouls per 40+1)')]:add(name,'skill_combinations',formula)
    assert len(defs)==50 and len({d['name'] for d in defs})==50
    return defs
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--repo',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--source-cutoff',type=int,default=2026);a=parser.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    rows=[];sources={}
    for fp in sorted((a.repo/'tracking_raw').glob('torvik_*.csv.gz')):
        year=int(fp.name.split('_')[1].split('.')[0])
        if year>a.source_cutoff:continue
        sources[fp.name]=hashlib.sha256(fp.read_bytes()).hexdigest()
        for r in csv.reader(gzip.open(fp,'rt')):
            if len(r)!=67 or int(r[31])!=year:raise ValueError(f'Bad source schema {fp}')
            d=dict(name=norm(r[0]),team=r[1],season=year,tpid=r[32])
            for i,k in FIELDS.items():
                try:d[k]=float(r[i])
                except ValueError:d[k]=np.nan
            rows.append(d)
    raw=pd.DataFrame(rows);names={k:g for k,g in raw.groupby('name')};teams={k:g for k,g in raw.groupby(['season','team'])}
    identity=pd.read_csv(a.repo/'identity/tabular_names.csv',usecols=['pid','draft_year','player_name'])
    defs=catalog();features=[];provenance=[];rejected=[]
    for p in identity.itertuples():
        c=names.get(norm(p.player_name))
        if c is None:continue
        c=c[c.season<=p.draft_year]
        if c.empty:continue
        lastyear=int(c.season.max());last=c[c.season==lastyear]
        if p.draft_year-lastyear>1 or last.tpid.nunique()!=1:
            rejected.append(dict(pid=p.pid,reason='stale_or_ambiguous'));continue
        last=last.sort_values('minutes').iloc[-1]
        hist=c[c.tpid==last.tpid].sort_values(['season','minutes']).drop_duplicates('season',keep='last')
        peers=teams[(lastyear,last.team)];peers=peers[peers.tpid!=last.tpid]
        w=peers.minutes.clip(lower=0).to_numpy(float)
        f={}
        for k in PEER:
            vals=peers[k].to_numpy(float);mean=weighted(vals,w)
            f['peer_sd_'+k]=np.sqrt(weighted((vals-mean)**2,w))
            vals=vals[np.isfinite(vals)]
            f['peer_rank_'+k]=float(((vals<last[k]).sum()+.5*(vals==last[k]).sum())/len(vals)) if len(vals) and np.isfinite(last[k]) else np.nan
        for k in SHARE:
            vals=peers[k]
            f['team_share_'+k]=div(last[k],last[k]+vals.sum()) if vals.notna().all() else np.nan
        pa=peers.two_a+peers.three_a
        f['peer_three_diet']=weighted((peers.three_a/pa.replace(0,np.nan)).to_numpy(),w)
        f['peer_rim_diet']=weighted((peers.rim_a/pa.replace(0,np.nan)).to_numpy(),w)
        f['peer_defense_density']=weighted((peers.stl+peers.blk).to_numpy(),w)
        f['peer_creation_density']=weighted((peers.ast/(peers.tov+1)).to_numpy(),w)
        team=teams[(lastyear,last.team)]
        for name,v in [('minutes_concentration',team.minutes),('usage_concentration',team.minutes*team.usage)]:
            f[name]=float(((v/v.sum())**2).sum()) if v.notna().all() and v.sum()>0 else np.nan
        for k in SLOPE:
            valid=hist[['season',k]].dropna()
            f['career_slope_'+k]=float(np.polyfit(valid.season,valid[k],1)[0]) if len(valid)>=2 else np.nan
        for k,(m,n,mu,strength) in POST.items():
            f['posterior_'+k]=(last[m]+mu*strength)/(last[n]+strength) if np.isfinite(last[m]) and np.isfinite(last[n]) and 0<=last[m]<=last[n] else np.nan
        f['nondunk_rim_pct']=div(last.rim_m-last.dunk_m,last.rim_a-last.dunk_a)
        f['rim_ft_pressure']=div(last.rim_a+.44*last.fta,last.two_a+last.three_a+.44*last.fta)
        f['perimeter_ft_agreement']=div(last.three_a,last.two_a+last.three_a)*f['posterior_ft']
        f['assist_usage_efficiency']=div(last.ast,last.usage+1)*(1-np.clip(last.tov,0,100)/100)
        f['balanced_stocks']=div(2*last.stl*last.blk,last.stl+last.blk)
        f['foul_adjusted_rebounds']=div(last.orb+last.drb,last.foul+1)
        f={'f50_'+k:float(v) if np.isfinite(v) else np.nan for k,v in f.items()}
        assert set(f)=={d['name'] for d in defs}
        features.append(dict(pid=p.pid,draft_year=int(p.draft_year),**f))
        provenance.append(dict(pid=p.pid,draft_year=int(p.draft_year),source_season=lastyear,source=f'torvik_{lastyear}.csv.gz',history_seasons=hist.season.astype(int).tolist(),match='normalized unique identity and source player ID'))
    full=pd.DataFrame(features);assert full.pid.is_unique
    full[full.draft_year<=2018].to_csv(a.out/'fifty_train.csv',index=False)
    for year in range(2019,2027):full[full.draft_year==year].to_csv(a.out/f'fifty_test_{year}_inputs.csv',index=False)
    for d in defs:
        d['train_nonmissing']=int(full.loc[full.draft_year<=2018,d['name']].notna().sum());d['test_nonmissing']=int(full.loc[full.draft_year>=2019,d['name']].notna().sum())
    (a.out/'catalog.json').write_text(json.dumps(defs,indent=2))
    manifest=dict(features=50,source_fields=FIELDS,source_hashes=sources,rows=len(full),provenance=provenance,rejected=rejected,limitation='Observed pre-draft seasons retrieved retrospectively; original release vintages unavailable. Missing is not zero. No NBA pick or outcome source field used.')
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(dict(features=50,rows=len(full),by_year=full.groupby('draft_year').size().to_dict(),minimum_training_coverage=min(d['train_nonmissing'] for d in defs))))
if __name__=='__main__':main()

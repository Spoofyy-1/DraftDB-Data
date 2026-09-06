"""Registered incumbent data ablation, development only, no test access.

This diagnostic does not select a replacement based on the previous confirmation.
Legacy input variants are explicitly uncertified pending source-provenance review.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS','6');os.environ.setdefault('OPENBLAS_NUM_THREADS','6')
from pathlib import Path
import json,time,traceback,hashlib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import legacy_kernel as E

ROOT=Path(__file__).resolve().parent;DATA=ROOT/'data';OUT=ROOT/'results';OUT.mkdir(exist_ok=True)
def write(s):
    s['updated']=time.time();t=OUT/'state.tmp';t.write_text(json.dumps(s,indent=2,allow_nan=False));t.replace(OUT/'state.json')
def rho(p,w):
    value=float(spearmanr(p,w).statistic);return value if np.isfinite(value) else 0.
def main():
    m=json.load(open(DATA/'manifest.json'))
    for f,h in m['files'].items(): assert hashlib.sha256((DATA/f).read_bytes()).hexdigest()==h
    x=pd.read_csv(DATA/'features.csv');lab=pd.read_csv(DATA/'labels.csv')
    g=json.load(open(DATA/'incumbent.json'))['champ']
    assert not any(g.get(k) for k in ['beatpick','consres','gltb','midw','el','wk','pss','star','hurdle'])
    assert g['labelmix']=='single' and g['meta']=='rankavg'
    for path in ['/home/ubuntu/nba/handoff/vault/answers_2020.csv','/home/ubuntu/nba/handoff/data/tests/test_2020_inputs.csv']:
        try: open(path).read(1)
        except (FileNotFoundError,PermissionError): pass
        else: raise AssertionError('Unexpected access to test files')
    variants=[
        dict(id='noscout_reference',noscout=1,drafted_only=False,context=None,drop=[]),
        dict(id='scout_removed_from_coverage',noscout=1,drafted_only=False,context=None,drop=['scout_']),
        dict(id='no_scout_medical',noscout=1,drafted_only=False,context=None,drop=['scout_','med_']),
        dict(id='no_scout_percentiles_projection',noscout=1,drafted_only=False,context=None,drop=['scout_','col_bpm_pct_','col_usg_pct_','col_ts_pct_','col_ast_pct_','col_stl_pct_','col_blk_pct_','col_orb_pct_','col_shot_proj_']),
        dict(id='no_scout_game_logs',noscout=1,drafted_only=False,context=None,drop=['scout_','col_gl_']),
        dict(id='no_scout_college_impact',noscout=1,drafted_only=False,context=None,drop=['scout_','col_impact','col_value','col_ortg','col_drtg','col_adj_','col_z_']),
        dict(id='no_scout_highschool',noscout=1,drafted_only=False,context=None,drop=['scout_','hs_']),
        dict(id='no_scout_listed_size',noscout=1,drafted_only=False,context=None,drop=['scout_','bio_height','bio_weight','bio_bmi']),
        dict(id='no_scout_nominal_maturity',noscout=1,drafted_only=False,context=None,drop=['scout_'],mature=True),
        dict(id='no_scout_window2010',noscout=1,drafted_only=False,context=None,drop=['scout_'],window=2010),
        dict(id='no_scout_uniform_war',noscout=1,drafted_only=False,context=None,drop=['scout_'],hw='uniform'),
        dict(id='no_scout_skill',noscout=1,drafted_only=False,context='ctx_skill_',drop=['scout_'])]
    weights={'rich':(0.,.75,.25),'thin':(.5,0.,.5)}
    plan=dict(variants=variants,folds=[2012,2013,2014],weights=weights,
              purpose='Fixed incumbent data-removal and label-maturity diagnostics; development only',
              no_confirmation_or_test_scoring=True,created=time.time())
    assert not (OUT/'preregistered_plan.json').exists()
    (OUT/'preregistered_plan.json').write_text(json.dumps(plan,indent=2))
    state=dict(status='running',phase='incumbent data ablation · development only',started=time.time(),completed=0,total=len(variants),
               candidates=[],best=None,confirmation=None,test_result=None,message=plan['purpose'])
    write(state)
    for v in variants:
        state['current']=v['id'];write(state);start=time.time()
        try:
            gg={**g,'noscout':v['noscout'],'win':v.get('window',g['win']),'hw':v.get('hw',g['hw'])}
            features=[c for c in m['legacy_features'] if not any(c.startswith(pre) for pre in v['drop'])]+[c for c in m['context_features'] if v['context'] and c.startswith(v['context'])]
            E.setup(features);rows=[]
            for year in plan['folds']:
                cutoff=year-1;k=min(5,2018-year)
                tr=x[(x.draft_year>=int(gg['win']))&(x.draft_year<=cutoff-1)].copy()
                if v['drafted_only']:tr=tr[tr.was_drafted==1].copy()
                if v.get('mature'):tr=tr[tr.draft_year<=cutoff-k].copy()
                te=x[(x.draft_year==year)&(x.was_drafted==1)].copy()
                tr=tr.reset_index(drop=True);te=te.reset_index(drop=True)
                assert not set(tr.pid)&set(te.pid)
                used=lab[(lab.season_end<=cutoff)&lab.pid.isin(tr.pid)]
                assert (used.season_end<=cutoff).all()
                for i in range(1,6):
                    vals=used[used.ordinal==i].set_index('pid').war
                    tr[f'y_s{i}_war']=tr.pid.map(vals)
                opts=E.opts_of(gg);base=E.H.cols_for(opts);cols=E.cols_of(gg,base)
                E.H.audit_features(cols)
                prior,cq=E.H.fit_prior(tr)
                Btr=E.H.build(tr,prior,cq,opts);Bte=E.H.build(te,prior,cq,opts)
                rate=[c for c in base if c.startswith(('col_','intl_')) and not c.startswith('col_gl_')]
                Btr,Bte=E.feat_tx(Btr,Bte,gg['fx'],tr,te,rate)
                st=E.stats_of(Btr);Btr=E.add_feats(Btr,gg['fx'],st);Bte=E.add_feats(Bte,gg['fx'],st)
                preds=E.member_preds(gg,Btr,Bte,cols,tr,k)
                p=E.stack(preds,Bte,gg,weights)
                truth=lab[(lab.season_end<=2018)&(lab.ordinal<=k)].groupby('pid').war.sum()
                yy=te.pid.map(truth).fillna(0)
                row=dict(season=year,k=k,n=len(te),ntrain=len(tr),cutoff=cutoff,max_label_season=int(used.season_end.max()),
                         stack=rho(p,yy),draft=rho(-te.actual_pick,yy),members={model:rho(score,yy) for model,score in preds.items()})
                rows.append(row);print(json.dumps(dict(variant=v['id'],fold=row)),flush=True)
            entry=dict(config={'id':v['id'],**v},score=float(np.mean([r['stack'] for r in rows])),rows=rows,seconds=round(time.time()-start,1))
        except Exception as e:
            traceback.print_exc();entry=dict(config={'id':v['id'],**v},error=str(e),seconds=round(time.time()-start,1))
        state['candidates'].append(entry);state['completed']+=1
        good=[r for r in state['candidates'] if 'score' in r]
        state['best']=max(good,key=lambda r:r['score']) if good else None
        write(state)
    state['status']='completed';state['phase']='incumbent data ablation complete'
    state['message']='Development diagnostics only. Legacy feature provenance unresolved; no test result or new champion declared.'
    write(state)
if __name__=='__main__':main()

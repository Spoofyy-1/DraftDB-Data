"""Frozen H input reconstruction only. No outcomes, scoring, network or draft picks."""
from pathlib import Path
import collections, csv, datetime as dt, gzip, hashlib, json, math
from zoneinfo import ZoneInfo
import numpy as np

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parent
RAW=Path('/Users/kennakao/nba/datarebuild/tracking_raw')
FIELDS={3:'gp',4:'minutes_share',6:'usage',7:'efg',8:'ts',9:'orb',10:'drb',11:'ast_pct',12:'tov_pct',13:'ftm',14:'fta',15:'ft_pct',16:'fg2m',17:'fg2a',18:'fg2_pct',19:'fg3m',20:'fg3a',21:'fg3_pct',22:'blk_pct',23:'stl_pct',24:'ftr',30:'fouls40',35:'ast_tov',36:'rim_made',37:'rim_attempts',38:'mid_made',39:'mid_attempts',42:'dunk_made',43:'dunk_attempts',54:'mpg',57:'oreb_pg',58:'dreb_pg',60:'ast_pg',61:'stl_pg',62:'blk_pg',63:'pts_pg'}
TRACE_FIELDS=[3,4,6,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,30,35,36,37,38,39,42,43,54,60]
CONS=['vcons_mock_mean_rank','vcons_mock_best_rank','vcons_mock_rank_range','vcons_mock_n_sources']
FIFTY=['f50_career_slope_usage','f50_posterior_rim']
YEARS=list(range(2019,2026))
PINS={}
def digest(b): return hashlib.sha256(b).hexdigest()
def read(path):
    path=Path(path); b=path.read_bytes(); PINS[str(path)]=digest(b); return b

def obj(path): return json.loads(read(path))
def rows(path,columns=None):
    it=csv.reader(read(path).decode().splitlines());header=next(it)
    selected=columns if columns is not None else header
    assert len(header)==len(set(header))
    indexes=[header.index(k) for k in selected]
    return [{k:r[i] for k,i in zip(selected,indexes)} for r in it]

def number(x):
    try: v=float(x)
    except (ValueError,TypeError): return np.nan
    return v if np.isfinite(v) else np.nan

def dump(path,data): path.write_text(json.dumps(data,indent=2,allow_nan=False,default=lambda x:x.item())+'\n')
def matrix_hash(a):
    a=np.asarray(a,dtype=np.float64);a=np.where(a==0.,0.,a);mask=np.isnan(a);a=np.where(mask,0.,a)
    return digest(json.dumps(list(a.shape),sort_keys=True,separators=(',',':')).encode()+mask.tobytes()+a.tobytes())

def validate_trace(t,cutoff):
    y=t['draft_year']; f=t['focal']; hist=t['history']
    assert y<=cutoff and 0<=y-int(f['season'])<=1
    assert hist and len(hist)==len({r['season'] for r in hist})
    assert hist==sorted(hist,key=lambda r:r['season'])
    assert all(int(r['season'])<=int(f['season'])<=y and r['tpid']==f['tpid'] for r in hist)
    assert hist[-1]==f
    for r in [f]+hist:
        assert r['source']==f"torvik_{r['season']}.csv.gz" and isinstance(r['source_row'],int) and r['source_row']>=0


def validate_source(s):
    assert s['feature_eligible'] and s['status']=='verified_predraft_mock'
    y=s['draft_year']; day=dt.date.fromisoformat(s['draft_date']);assert day.year==y
    expected=dt.datetime.combine(day,dt.time(),ZoneInfo('America/New_York')).astimezone(dt.timezone.utc)
    cutoff=dt.datetime.fromisoformat(s['cutoff_utc']);capture=dt.datetime.fromisoformat(s['source_available_by_utc'])
    assert cutoff==expected and capture<cutoff
    assert dt.date.fromisoformat(s['source_last_updated_date'])<day
    assert dt.datetime.strptime(s['source']['timestamp'],'%Y%m%d%H%M%S').replace(tzinfo=dt.timezone.utc)==capture
    assert s['source']['statuscode']=='200'


def raw_lookup(traces,hashes):
    needed=collections.defaultdict(dict)
    for t in traces:
        for r in [t['focal']]+t['history']:
            key=r['source_row']; old=needed[r['source']].get(key)
            assert old is None or old==r
            needed[r['source']][key]=r
    raw={}
    for name,indices in sorted(needed.items()):
        payload=read(RAW/name);assert digest(payload)==hashes[name],name
        year=int(name.split('_')[1].split('.')[0]);assert 2008<=year<=2025
        for i,r in enumerate(csv.reader(gzip.decompress(payload).decode().splitlines())):
            if i not in indices: continue
            p=indices[i]; assert len(r)==67 and int(r[31])==year and r[1]==p['team'] and r[32]==p['tpid']
            # No unlisted predictor value, including raw index45, is accessed.
            assert digest(json.dumps([r[j] for j in TRACE_FIELDS],separators=(',',':')).encode())==p['allowed_values_hash']
            raw[(name,i)]={c:number(r[j]) for j,c in FIELDS.items()}
        assert all((name,i) in raw for i in indices)
    return raw


def reconstruct(t,raw):
    f=t['focal']; x=raw[(f['source'],f['source_row'])];out={'ctx_base_'+k:v for k,v in x.items()}
    total=x['fg2a']+x['fg3a'];out['ctx_base_three_share']=x['fg3a']/total if total>0 else np.nan
    out['ctx_skill_defense_discipline']=(x['stl_pct']+x['blk_pct'])/(x['fouls40']+1) if x['fouls40']>=0 else np.nan
    out['ctx_skill_creation_control']=x['ast_pct']/(x['tov_pct']+1) if x['tov_pct']>=0 else np.nan
    out['ctx_skill_usage_efficiency']=(x['usage']-20)*(x['ts']-50)/100
    out['ctx_skill_ft_volume']=x['ft_pct']*np.log1p(x['fta']) if x['fta']>=0 else np.nan
    hist=[(r['season'],raw[(r['source'],r['source_row'])]['usage']) for r in t['history']]
    good=[p for p in hist if np.isfinite(p[1])]
    out[FIFTY[0]]=float(np.polyfit([p[0] for p in good],[p[1] for p in good],1)[0]) if len(good)>=2 else np.nan
    m,n=x['rim_made'],x['rim_attempts'];out[FIFTY[1]]=(m+.60*30)/(n+30) if np.isfinite(m) and np.isfinite(n) and 0<=m<=n else np.nan
    return out


def consensus_for_year(year,observations,sources):
    bypid=collections.defaultdict(list);seen=set()
    for r in observations:
        if int(r['draft_year'])!=year:continue
        s=sources[r['source_id']]; validate_source(s)
        assert s['draft_year']==year and r['publisher']==s['publisher']
        assert r['capture_utc']==s['source_available_by_utc'] and r['draft_date']==s['draft_date']
        assert r['source_last_updated_date']==s['source_last_updated_date']
        assert all(r[k]==s[k] for k in ['rank_facts_sha256','table_sha256'])
        key=(r['pid'],r['publisher']);assert key not in seen;seen.add(key)
        rank=int(r['mock_rank']);assert rank>0 and rank<=int(s['listed_count'])
        assert r['match_method']=='unique_exact_normalized_same_cohort_name'
        bypid[r['pid']].append(rank)
    return {pid:dict(zip(CONS,[float(np.mean(v)),min(v),max(v)-min(v) if len(v)>=2 else np.nan,len(v)])) for pid,v in bypid.items()}


def main():
    assert 45 not in FIELDS and 45 not in TRACE_FIELDS
    plan=obj(WORK/'r9h/plan.json');columns=plan['columns'];physical=plan['physical_source_fields']
    assert len(columns)==44 and columns==sorted(columns) and len(set(physical))==44
    assert physical[-6:]==CONS+FIFTY and physical[:-6]==columns[:-6]
    lin=obj(WORK/'fifty_audit/source_row_lineage.json');assert len(lin)==len({t['pid'] for t in lin})
    traces=[t for t in lin if t['draft_year']<=2025]
    for t in traces: validate_trace(t,2025)
    raw=raw_lookup(traces,obj(WORK/'fifty/manifest.json')['source_hashes'])
    reconstructed={t['pid']:reconstruct(t,raw) for t in traces}
    # Replay only frozen predictors. Neither actual_pick nor was_drafted nor labels are read.
    old=rows(WORK/'r8w/data/features.csv',['pid','draft_year']+columns[:-6]);replay=[]
    for r in old:
        if r['pid'] not in reconstructed:
            assert all(math.isnan(number(r[c])) for c in columns[:-6]);continue
        values=reconstructed[r['pid']]
        for c in columns[:-6]:
            v,w=values[c],number(r[c]);assert (math.isnan(v) and math.isnan(w)) or np.isclose(v,w,rtol=0,atol=1e-12),(r['pid'],c,v,w)
            replay.append((c,v,w))
    # Cross-check both source-defined F50 fields against original full caches, not cutoff-removal audit caches.
    f50_replay=0;f50_exact=0
    for year in [2018]+YEARS:
        name='fifty_train.csv' if year==2018 else f'fifty_test_{year}_inputs.csv'
        for r in rows(WORK/'fifty'/name,['pid','draft_year']+FIFTY):
            for c in FIFTY:
                v,w=reconstructed[r['pid']][c],number(r[c]);assert (math.isnan(v) and math.isnan(w)) or np.isclose(v,w,rtol=0,atol=1e-12),(r['pid'],c,v,w)
                f50_replay+=1;f50_exact+=int((math.isnan(v) and math.isnan(w)) or v==w)
    ext=WORK/'verified_consensus_extension';public=obj(ext/'public_manifest.json')['files']
    def certified(name):
        b=read(ext/name); assert digest(b)==public[name]['sha256'];return b
    sources={s['source_id']:s for s in json.loads(certified('validated_sources.json'))}
    observations=list(csv.DictReader(certified('rank_observations.csv').decode().splitlines()))
    cohorts={};outfiles={};private=[]
    membership=obj(ROOT/'private/membership_projection.json')
    for year in YEARS:
        pool=rows(WORK/f'verified_inputs_v2/{year}_inputs.csv',['pid','draft_year'])
        assert pool and len(pool)==len({r['pid'] for r in pool}) and all(int(r['draft_year'])==year for r in pool)
        m=membership[str(year)];assert m['read_columns']==['pid','was_drafted']
        assert m['projection_sha256']==digest(json.dumps(m['rows'],sort_keys=True,separators=(',',':')).encode())
        assert [r['pid'] for r in m['rows']]==[r['pid'] for r in pool]
        with (ROOT/f'metadata_{year}.csv').open('w') as mf:
            mw=csv.DictWriter(mf,fieldnames=['pid','draft_year','was_drafted']);mw.writeheader()
            mw.writerows({'pid':r['pid'],'draft_year':year,'was_drafted':int(float(r['was_drafted']))} for r in m['rows'])
        cons=consensus_for_year(year,observations,sources)
        side=list(csv.DictReader(certified(f'sidecars/consensus_extension_test_{year}_inputs.csv').decode().splitlines()))
        assert [(r['pid'],r['draft_year']) for r in side]==[(r['pid'],r['draft_year']) for r in pool]
        ts={t['pid']:t for t in traces if t['draft_year']==year}
        output=[];missing=collections.Counter();ranked=0;college=0
        for p,cr in zip(pool,side):
            pid=p['pid'];values=reconstructed[pid] if pid in ts else {}
            values={**values,**cons.get(pid,{})}
            for c in CONS:
                v,w=values.get(c,np.nan),number(cr[c]);assert (math.isnan(v) and math.isnan(w)) or v==w
            record={**p};college+=pid in ts;ranked+=pid in cons
            for c,field in zip(columns,physical):
                v=float(values.get(field,np.nan));assert not math.isinf(v)
                record[c]='' if math.isnan(v) else repr(v);missing[c]+=math.isnan(v)
            output.append(record)
            if pid in ts:
                t=ts[pid];private.append({'pid':pid,'draft_year':year,'focal':t['focal'],'history':t['history'],'source_eligibility':'candidate: season convention only, historical publication vintage unavailable'})
        target=ROOT/f'inputs_{year}.csv'
        with target.open('w') as f:
            w=csv.DictWriter(f,fieldnames=['pid','draft_year']+columns);w.writeheader();w.writerows(output)
        x=np.array([[number(r[c]) for c in columns] for r in output]);zero=np.isnan(x).all(axis=1)
        outfiles[target.name]={'sha256':digest(target.read_bytes()),'rows':len(pool),'matrix_hash':matrix_hash(x),'pid_order_sha256':digest(json.dumps([r['pid'] for r in pool],separators=(',',':')).encode())}
        cohorts[str(year)]={'rows':len(pool),'college_lineage_rows':college,'verified_mock_rows':ranked,'both':sum(r['pid'] in ts and r['pid'] in cons for r in pool),'all44_missing_rows':int(zero.sum()),'missing_by_column':dict(missing),'source_season_gaps':dict(collections.Counter(year-t['focal']['season'] for pid,t in ts.items() if pid in {r['pid'] for r in pool})),'was_drafted_metadata_rows':sum(int(float(r['was_drafted'])) for r in m['rows']),'source_ids':sorted({r['source_id'] for r in observations if int(r['draft_year'])==year})}
    (ROOT/'private').mkdir(exist_ok=True,mode=0o700);dump(ROOT/'private/college_lineage.json',private);(ROOT/'private/college_lineage.json').chmod(0o600)
    limitations=[
      'College tables are retrospective annual snapshots. Season<=draft year and latest season gap<=1 are checked; individual game dates and original publication vintages are not established by these annual files.',
      'Original raw context definitions are deliberately preserved. D1-subset count totals and some appended per-game denominators are not uniformly the same subset; no opportunistic repairs were made.',
      'College identity pointers inherit exact normalized name plus unique same-year source-player-ID checks; no new aliases or fuzzy matches are introduced.',
      'Mock sources prove dated pre-draft availability, but coverage/publisher quality varies. 2019 and2020 have serious partial top15 Walter lists;2021 onward has only one publisher, so rank range stays missing.',
      'Input population is the full original provided universe, whose historical construction remains uncertified. The server input-file was_drafted metadata is projected separately and never enters predictors. Future-cohort membership is for matching the specified drafted query population only; expanding training may use it only after that cohort draft date.',
      'Old2000–2018 cohort predictor values and1428 study rows must be copied from H frozen source by the evaluation builder; this package only checks their38-context definitions and does not replace that base.',
      'All candidates require explicit parent diagnostic admission; model_eligible remainsfalse. No outcomes, test answers, labels, benchmark performance, network or model calls were used.'
    ]
    manifest={'status':'candidate_inputs_ready_for_review','model_eligible':False,'years':YEARS,'columns':columns,'physical_source_fields':physical,'raw_numeric_index_allowlist':sorted(FIELDS),'raw_identity_index_allowlist':[1,31,32],'raw_lineage_hash_index_allowlist':TRACE_FIELDS,'raw_index45_accessed':False,'pool_identity_columns_only':['pid','draft_year'],'source_files':PINS,'output_files':outfiles,'cohort_coverage':cohorts,'old_context_replay':{'old_rows':len(old),'compared_cells':len(replay),'equal_or_nan_exact':int(sum((math.isnan(v) and math.isnan(w)) or v==w for _,v,w in replay)),'max_absolute_difference':max([abs(v-w) for _,v,w in replay if np.isfinite(v) and np.isfinite(w)],default=0),'tolerance':1e-12},'fifty_cache_replay':{'cells':f50_replay,'exact_or_nan':f50_exact,'tolerance':1e-12},'expanding_reuse':'The identical predraft inputs_YEAR.csv serves that query cohort and can later be included as an earlier training cohort. Training selection/labels must obey evaluation-year cutoff; no target-cohort self-training. Root owns eligibility and labels.','limitations':limitations}
    dump(ROOT/'manifest.json',manifest)
    print(json.dumps({'status':manifest['status'],'coverage':{y:{k:v for k,v in x.items() if k in ['rows','college_lineage_rows','verified_mock_rows','both','all44_missing_rows']} for y,x in cohorts.items()},'context_replay':manifest['old_context_replay'],'fifty_replay':manifest['fifty_cache_replay']}))
if __name__=='__main__':main()

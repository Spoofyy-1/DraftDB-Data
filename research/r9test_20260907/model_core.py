"""Exact H target/predictor policy. Never accepts or scores query outcomes."""
import hashlib,json,math,collections
import numpy as np
import pandas as pd
from scipy.special import ndtri
from scipy.stats import rankdata

def digest(raw):return hashlib.sha256(raw).hexdigest()
def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def values_hash(a):
 a=np.asarray(a,dtype=np.float64);a=np.where(a==0.,0.,a);mask=np.isnan(a);a=np.where(mask,0.,a);return digest(canon(list(a.shape))+mask.tobytes()+a.tobytes())
def canonical_rows(frame):
 assert frame.pid.is_unique
 return frame.iloc[sorted(range(len(frame)),key=lambda i:(digest(str(frame.iloc[i].pid).encode()),str(frame.iloc[i].pid)))].copy().reset_index(drop=True)
def build_payload(training,query,labels,recipe,year):
 assert year in recipe['years']or year in recipe['reference_gate']['years']
 fields=recipe['physical_source_fields'];columns=recipe['columns'];assert len(columns)==44 and columns==sorted(columns)
 assert list(training)==['pid','draft_year','was_drafted']+fields and list(query)==['pid','draft_year']+fields and list(labels)==['pid','draft_year','ordinal','season_end','war']
 assert training.pid.is_unique and query.pid.is_unique and len(query)>0 and not set(training.pid)&set(query.pid)
 assert training.draft_year.between(2000,year-1).all()and query.draft_year.eq(year).all()and training.was_drafted.isin([0,1]).all()
 assert labels.ordinal.isin([1,2]).all()and labels.season_end.le(year-1).all()and np.isfinite(labels.war).all()and set(labels.pid)<=set(training.pid)and not set(labels.pid)&set(query.pid)
 assert labels.season_end.ge(labels.draft_year+labels.ordinal).all()
 assert not labels.duplicated(['pid','ordinal']).any();assert labels.draft_year.eq(labels.pid.map(training.set_index('pid').draft_year)).all()
 base=training[training.was_drafted==1];dated=labels[labels.pid.isin(base.pid)].copy();complete=dated.groupby('pid').ordinal.agg(lambda x:sorted(x)==[1,2]);tr=canonical_rows(base[base.pid.isin(complete[complete].index)]);te=canonical_rows(query)
 facts=dated[dated.pid.isin(tr.pid)].sort_values(['pid','ordinal']).reset_index(drop=True);cumulative=tr.pid.map(facts.groupby('pid').war.sum()).to_numpy(dtype=float);assert np.isfinite(cumulative).all()and len(facts)==2*len(tr)
 clipped=np.clip(cumulative,-40.,40.);target=np.empty(len(tr),dtype=float)
 for cohort in tr.draft_year.unique():
  mask=(tr.draft_year==cohort).to_numpy();n=int(mask.sum());rank=pd.Series(clipped[mask]).rank(method='average').to_numpy();target[mask]=ndtri(np.clip((rank-.5)/n,.01,.99))
 counts={str(int(k)):int(v)for k,v in tr.groupby('draft_year').size().items()};assert len(tr)>=recipe['minimum_training_rows']and min(counts.values())>=recipe['minimum_observed_rows_each_admitted_cohort']and np.isfinite(target).all()
 atr=pd.DataFrame(tr[fields].to_numpy(dtype=float),columns=columns);ate=pd.DataFrame(te[fields].to_numpy(dtype=float),columns=columns);assert not np.isinf(atr).any().any()and not np.isinf(ate).any().any()
 audit={'year':year,'permitted_label_cutoff':year-1,'actual_admitted_label_max':int(facts.season_end.max()),'admitted_label_cutoff_lag':year-1-int(facts.season_end.max()),'source_export_label_max':int(labels.season_end.max()),'training_rows':len(tr),'query_rows':len(te),'cohort_counts':counts,'input_columns':columns,'training_matrix_hash':values_hash(atr),'query_matrix_hash':values_hash(ate),'target_hash':values_hash(target),'cumulative_WAR_hash':values_hash(cumulative),'clipped_WAR_hash':values_hash(clipped),'training_PID_hash':digest(canon(tr.pid.tolist())),'query_PID_hash':digest(canon(te.pid.tolist())),'training_max_cohort':int(tr.draft_year.max()),'source_fact_hash':digest(canon(facts[['pid','draft_year','ordinal','season_end','war']].to_dict(orient='records'))),'source_fact_rows':len(facts),'no_unknown_training_WAR_zero_fill':True,'no_query_outcomes_or_pick_predictors':True}
 return atr,ate,target,tr.pid.tolist(),te.pid.tolist(),audit

def exact_vector_keys(frame):
    # Use exact float representations, but normalize equivalent zeros/NaNs.
    # No tolerance or decimal rounding can merge distinct numerical vectors.
    assert np.isfinite(frame.stack().dropna().to_numpy(dtype=float)).all()
    return [tuple(None if pd.isna(v) else ('0x0.0p+0' if float(v) == 0 else float(v).hex()) for v in row)
            for row in frame.to_numpy()]


def canonical_predictions(frame, raw, pids):
    raw = np.asarray(raw, dtype=float)
    assert len(raw) == len(frame) == len(pids) and len(set(pids)) == len(pids) and np.isfinite(raw).all()
    groups = collections.defaultdict(list)
    vector_keys = exact_vector_keys(frame)
    for i, key in enumerate(vector_keys):
        groups[key].append(i)
    result = raw.copy()
    duplicates = []
    for indices in groups.values():
        if len(indices) < 2:
            continue
        mean = math.fsum(sorted(float(raw[i]) for i in indices)) / len(indices)
        result[indices] = mean
        duplicates.append({'pids': sorted(pids[i] for i in indices), 'rows': len(indices),
                           'all_predictors_missing': bool(frame.iloc[indices].isna().all().all()),
                           'raw_min': float(raw[indices].min()), 'raw_max': float(raw[indices].max()),
                           'assigned_score': mean})
    audit = {'policy': 'sha256_pid_exact_vector_mean_v1', 'rows': len(raw), 'distinct_input_vectors': len(groups),
             'duplicate_groups': sorted(duplicates, key=lambda g: g['pids']),
             'changed_rows': int(np.count_nonzero(result != raw)),
             'max_abs_change': float(np.max(np.abs(result - raw))),
             'raw_prediction_hash': hashlib.sha256(raw.tobytes()).hexdigest(),
             'canonical_prediction_hash': hashlib.sha256(result.tobytes()).hexdigest(),
             'row_vector_hashes': [digest(canon(key)) for key in vector_keys],
             'distinct_vectors_quantized': False}
    return result, audit



def fixed_rank_average(vectors):
 assert len(vectors)==3 and len({len(v)for v in vectors})==1
 ranked=[np.rint(2*rankdata(v,method='average')).astype(np.int64)for v in vectors];return np.sum(ranked,axis=0,dtype=np.int64)/(6*len(ranked[0]))

def predict_one(atr,ate,target,pids,recipe,seed):
 from tabicl import TabICLRegressor
 import torch
 assert seed in recipe['seeds'];params={**recipe['model_profile']['parameters'],'random_state':seed};model=TabICLRegressor(**params);assert all(model.get_params()[k]==v for k,v in params.items());before=values_hash(target);model.fit(atr,target.copy());assert values_hash(target)==before
 raw=np.asarray(model.predict(ate),dtype=float);score,ties=canonical_predictions(ate,raw,pids);modules={k:v for k,v in vars(model).items()if isinstance(v,torch.nn.Module)};devices=sorted({str(x.device)for module in modules.values()for x in module.parameters()});assert devices and all(x.startswith('cuda')for x in devices)
 gen=model.ensemble_generator_;return {'seed':seed,'parameters':params,'effective_constructor':model.get_params(deep=False),'actual_devices':devices,'effective_features':int(gen.n_features_in_),'effective_estimators':sum(len(v)for v in gen.ensemble_configs_.values()),'prediction_ties':ties,'predictions':[{'pid':pid,'raw_score':float(a),'score':float(b)}for pid,a,b in zip(pids,raw,score)]}

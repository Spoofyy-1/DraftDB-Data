"""Fit once and audit query permutation/composition; never score player outcomes."""
import os
os.environ['OMP_NUM_THREADS']='2'
os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import hashlib
import inspect
import json
import time
import traceback
import importlib.metadata
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import torch
import xgboost as xgb
from tabicl import TabICLRegressor
import legacy_kernel as E
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/order_audit.json'


def hash_json(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def matrix_hash(frame):
    return hashlib.sha256(pd.util.hash_pandas_object(frame,index=True).to_numpy().tobytes()).hexdigest()


def jsonable(value):
    if isinstance(value,(str,int,float,bool,type(None))):return value
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,dict):return {str(k):jsonable(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [jsonable(v) for v in value]
    return repr(value)


def compare(reference,current,plan):
    difference=np.abs(reference-current)
    ra=pd.Series(reference).rank(method='average').to_numpy();rb=pd.Series(current).rank(method='average').to_numpy()
    counts=np.unique(current,return_counts=True)[1]
    da=reference[:,None]-reference[None,:];db=current[:,None]-current[None,:]
    upper=np.triu(np.ones(da.shape,dtype=bool),1)
    strict=int(((da*db<0)&upper).sum())
    nontiny=int(((da*db<0)&(np.abs(da)>plan['material_rank_gap'])&upper).sum())
    ties=int(((da==0)!=(db==0))[upper].sum())
    corr=float(spearmanr(reference,current).statistic)
    if np.isnan(corr):corr=1.0 if np.array_equal(reference,current) else 0.0
    return {'exact_equal':bool(np.array_equal(reference,current)),
            'max_abs_delta':float(difference.max()),'mean_abs_delta':float(difference.mean()),
            'prediction_rank_correlation':corr,'same_average_ranks':bool(np.array_equal(ra,rb)),
            'same_stable_sort_order':bool(np.array_equal(np.argsort(reference,kind='stable'),np.argsort(current,kind='stable'))),
            'strict_pair_order_inversions':strict,'nontiny_pair_order_inversions':nontiny,
            'pair_tie_status_changes':ties,'unique_predictions':int(len(counts)),
            'tied_prediction_pairs':int(sum(int(n)*(int(n)-1)//2 for n in counts)),
            'material':bool(float(difference.max())>plan['material_numeric_delta'] or nontiny>0)}


def main():
    start=time.time();plan=json.loads((ROOT/'data/manifest.json').read_text())
    payload={'status':'preparing','diagnostic_only':True,'no_WAR_scoring':True,'one_fit_only':True,
             'plan':plan,'records':[],'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'constructor_typeerror_fallback_allowed':False}
    try:
        for name,digest in plan['files'].items():
            assert Path(name).name==name and hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()==digest
        tr=pd.read_csv(ROOT/'data/train_inputs.csv');q=pd.read_csv(ROOT/'data/query_inputs.csv');extra=pd.read_csv(ROOT/'data/append_inputs.csv')
        lab=pd.read_csv(ROOT/'data/train_labels.csv');columns=plan['base_columns']
        assert len(columns)==41 and all(c.startswith(('ctx_base_','ctx_skill_')) for c in columns)
        assert 'ctx_base_age' not in columns and 'ctx_base_height' not in columns
        for frame in [tr,q,extra]:
            assert list(frame)==['pid','draft_year']+columns and frame.pid.is_unique
            assert not any(c in columns for c in ['pid','draft_year','actual_pick','index','row_position','was_drafted'])
        assert (tr.draft_year.between(2007,2010)).all() and (q.draft_year==2012).all() and (extra.draft_year==2011).all()
        assert lab.pid.isin(tr.pid).all() and lab.season_end.max()<=2011
        assert not set(lab.pid)&(set(q.pid)|set(extra.pid))
        assert not lab.duplicated(['pid','ordinal']).any()
        g=json.loads((ROOT/'data/incumbent.json').read_text())['champ']
        cfg=plan['backbone'];g={**g,'noscout':1,'win':cfg['window'],'hw':cfg['hw'],'M':cfg['M'],'icl_n':cfg['icl_n']}
        assert not any(g.get(k) for k in ['beatpick','consres','gltb','midw','el','wk','pss','star','hurdle'])
        assert g['labelmix']=='single' and g['meta']=='rankavg'
        E.setup(columns)
        for ordinal in range(1,6):tr[f'y_s{ordinal}_war']=tr.pid.map(lab[lab.ordinal==ordinal].set_index('pid').war)
        yy=E.label(tr,E.specs(g)[0],5)
        selector=xgb.XGBRegressor(max_depth=3,n_estimators=300,learning_rate=.05,subsample=.8,colsample_bytree=.6,n_jobs=2,device='cpu',tree_method='hist',random_state=11)
        selector.fit(tr[columns],yy)
        selected=[c for _,c in sorted(zip(selector.feature_importances_,columns),reverse=True)]
        assert len(selected)==41 and set(selected)==set(columns)
        atr=tr[selected].copy().reset_index(drop=True);query=q[selected].copy().reset_index(drop=True);additional=extra[selected].copy().reset_index(drop=True)
        assert list(atr)==list(query)==list(additional)==selected
        E.H.audit_features(selected)
        os.environ['SEED_SHIFT']='0'
        model_cfg=E.cfg_of('tabicl',g,selected)
        constructor={'device':'cuda','n_estimators':int(model_cfg['icl_n']),**model_cfg['icl_kwargs']}
        assert constructor['random_state']==0 and constructor['n_estimators']==32
        payload.update(constructor_requested=constructor,constructor_signature=str(inspect.signature(TabICLRegressor)),
                       installed_tabicl=importlib.metadata.version('tabicl'),torch_version=torch.__version__,
                       ordered_base_columns=selected,base_columns_hash=hash_json(selected),
                       training_pid_hash=hash_json(tr.pid.tolist()),query_pid_hash=hash_json(q.pid.tolist()),
                       training_matrix_hash=matrix_hash(atr),query_matrix_hash=matrix_hash(query),
                       training_label_hash=hashlib.sha256(np.asarray(yy,dtype=np.float64).tobytes()).hexdigest(),
                       no_index_or_position_column=True,training_rows=len(tr),query_rows=len(q),append_rows=len(extra),
                       cuda_device=torch.cuda.get_device_name(),data_labels_exclude_every_query_and_append_pid=True)
        # Do not catch TypeError to silently construct a default estimator.
        model=TabICLRegressor(**constructor)
        payload['constructor_effective']=jsonable(model.get_params(deep=False))
        fit_start=time.perf_counter();model.fit(atr,yy);torch.cuda.synchronize()
        payload['fit_seconds']=time.perf_counter()-fit_start
        payload['fitted_feature_names']=jsonable(getattr(model,'feature_names_in_',None))
        generator=getattr(model,'ensemble_generator_',None)
        groups=getattr(generator,'ensemble_configs_',None)
        assert isinstance(groups,dict), 'Cannot audit effective ensemble configuration count'
        payload['effective_ensemble_configs']=sum(len(group) for group in groups.values())
        payload['effective_features_after_preprocessing']=int(generator.n_features_in_)
        payload['legacy_kernel_sha256']=hashlib.sha256((ROOT/'legacy_kernel.py').read_bytes()).hexdigest()
        calls=0;reference=None
        def predict_case(name,frame,restore,kind):
            nonlocal calls,reference
            assert calls<plan['maximum_predictions'] and time.time()-start<110
            assert list(frame)==selected and frame.shape[1]==41
            torch.cuda.synchronize();t=time.perf_counter();values=np.asarray(model.predict(frame),dtype=float);torch.cuda.synchronize()
            calls+=1;assert len(values)==len(frame) and np.isfinite(values).all()
            aligned=values[np.asarray(restore,dtype=int)]
            assert len(aligned)==len(query)
            if reference is None:reference=aligned.copy()
            record={'case':name,'kind':kind,'predict_call':calls,'input_rows':len(frame),
                    'seconds':time.perf_counter()-t,'input_column_hash':hash_json(list(frame)),
                    'input_index_hash':hash_json(frame.index.tolist()),'restored_prediction_hash':hashlib.sha256(aligned.tobytes()).hexdigest(),
                    'comparison':compare(reference,aligned,plan)}
            payload['records'].append(record);payload.update(status='running',predict_calls=calls)
            OUT.write_text(json.dumps(payload,indent=2)+'\n');print(json.dumps(record),flush=True)
            if record['comparison']['material']:print('MATERIAL_INFERENCE_DEPENDENCE '+name,flush=True)
        n=len(query);identity=np.arange(n)
        predict_case('baseline',query,identity,'reference')
        predict_case('repeat_identical_query',query,identity,'repeatability')
        reverse=identity[::-1];predict_case('reverse_query_rows',query.iloc[reverse].reset_index(drop=True),np.argsort(reverse),'row_order')
        for seed in plan['random_query_seeds']:
            order=np.random.default_rng(seed).permutation(n)
            predict_case(f'random_query_order_{seed}',query.iloc[order].reset_index(drop=True),np.argsort(order),'row_order')
        indexed=query.copy();indexed.index=[f'nonfeature_index_{v}' for v in np.random.default_rng(7103).permutation(n)]
        predict_case('same_values_changed_pandas_index',indexed,identity,'index_only')
        combined=pd.concat([query,additional],ignore_index=True)
        predict_case('append_unlabeled_historical_rows',combined,identity,'query_composition')
        prepended=pd.concat([additional,query],ignore_index=True)
        predict_case('prepend_same_unlabeled_historical_rows',prepended,np.arange(len(additional),len(prepended)),'query_composition')
        order=np.random.default_rng(plan['composition_seed']).permutation(len(combined));locations=np.argsort(order)[:n]
        predict_case('shuffle_combined_query_pool',combined.iloc[order].reset_index(drop=True),locations,'query_composition')
        assert calls==10
        payload.update(status='completed',predict_calls=calls,elapsed_seconds=time.time()-start,
                       material_row_order_dependence=any(r['comparison']['material'] for r in payload['records'] if r['kind']=='row_order'),
                       material_index_dependence=any(r['comparison']['material'] for r in payload['records'] if r['kind']=='index_only'),
                       material_query_composition_dependence=any(r['comparison']['material'] for r in payload['records'] if r['kind']=='query_composition'),
                       material_repeatability_variation=any(r['comparison']['material'] for r in payload['records'] if r['kind']=='repeatability'))
        OUT.write_text(json.dumps(payload,indent=2)+'\n')
        print(json.dumps({k:payload[k] for k in ['status','predict_calls','elapsed_seconds','material_row_order_dependence','material_index_dependence','material_query_composition_dependence','material_repeatability_variation']}),flush=True)
    except Exception as error:
        payload.update(status='failed_closed',error=repr(error),elapsed_seconds=time.time()-start)
        OUT.write_text(json.dumps(payload,indent=2)+'\n');traceback.print_exc();raise


if __name__=='__main__':main()

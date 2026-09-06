"""Tiny preprocessing fixtures only; no research model outcomes or GPU calls."""
import numpy as np
import pandas as pd
from worker import make_registered_model

def run_cpu_tests(plan):
    train=pd.DataFrame({'missing':[1.,np.nan,3.],'empty':[np.nan]*3,'constant':[5.]*3})
    validation=pd.DataFrame({'missing':[1e12,np.nan],'empty':[99.,np.nan],'constant':[-1e12,5.]})
    pipeline,_=make_registered_model(plan['models']['ridge300'],0)
    # Exercise the actual registered preprocessing, never fit a research model.
    imputer,scaler=pipeline.named_steps['imputer'],pipeline.named_steps['scaler']
    filled=imputer.fit_transform(train)
    scaled=scaler.fit_transform(filled)
    assert np.array_equal(imputer.statistics_,[2.,0.,5.])
    assert np.array_equal(imputer.indicator_.features_,[0,1]) and filled.shape==(3,5)
    assert np.isfinite(scaled).all() and scaler.n_samples_seen_==3
    before=[imputer.statistics_.copy(),scaler.mean_.copy(),scaler.scale_.copy()]
    transformed=scaler.transform(imputer.transform(validation))
    assert transformed.shape==(2,5) and np.isfinite(transformed).all()
    assert all(np.array_equal(a,b) for a,b in zip(before,[imputer.statistics_,scaler.mean_,scaler.scale_]))
    assert scaler.n_samples_seen_==3
    for mid in ['extratrees_leaf5','extratrees_leaf15']:
        model,_=make_registered_model(plan['models'][mid],0)
        assert model.__sklearn_tags__().input_tags.allow_nan
    for mid in ['xgb_depth3','xgb_depth5']:
        model,parameters=make_registered_model(plan['models'][mid],101)
        assert model.get_params()['device']=='cpu' and parameters['random_state']==101
    return {'passed':True,'training_only_medians_missing_indicators_scaling':True,'all_missing_columns_retained':True,
            'validation_extremes_leave_fitted_statistics_unchanged':True,'native_nan_extratrees_tags':True,
            'cpu_xgb_configuration':True,'research_estimators_fitted':0,'gpu_predictor_calls':0}

"""Outcome-free fixed rank blending; no fitted weights."""
import numpy as np
from scipy.stats import rankdata

def doubled_ranks(values):
    a=np.asarray(values,dtype=float)
    assert a.ndim==1 and len(a)>0 and np.isfinite(a).all()
    return np.rint(2*rankdata(a,method='average')).astype(np.int64)

def family_seed_average(vectors):
    assert len(vectors)==3 and len({len(x)for x in vectors})==1
    return np.sum([doubled_ranks(x)for x in vectors],axis=0,dtype=np.int64)/(6*len(vectors[0]))

def blend(vectors,recipe,query_matrix):
    assert len(vectors)==len(recipe['members']) and len({len(x)for x in vectors})==1
    n=len(vectors[0]);assert len(query_matrix)==n
    ranks=np.stack([doubled_ranks(x)for x in vectors],axis=1)
    if recipe['kind']=='fixed_rank_weights':
        units=np.asarray([m['units']for m in recipe['members']],dtype=np.int64)
        assert (units>0).all()and units.sum()==60
        numerator=ranks@units
    else:
        assert recipe['kind']=='adapted_coverage_control' and len(vectors)==3
        coverage=np.isfinite(np.asarray(query_matrix,dtype=float)).mean(axis=1)
        thin=coverage<np.median(coverage)
        rich=np.asarray(recipe['rich_units'],dtype=np.int64);poor=np.asarray(recipe['thin_units'],dtype=np.int64)
        assert np.array_equal(rich,[0,15,45])and np.array_equal(poor,[60,0,0])
        numerator=np.where(thin,ranks@poor,ranks@rich)
    return numerator/(2*n*60)

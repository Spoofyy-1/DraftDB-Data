"""Scorer runs outside model sandbox only after immutable predictions exist."""
from pathlib import Path
import json,hashlib,time,fcntl
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results';VAULT=ROOT.parent/'vault'
def main():
    freeze=json.loads((OUT/'prediction_freeze.json').read_text());protocol=json.loads((ROOT/'frozen_protocol.json').read_text())
    assert hashlib.sha256((OUT/'predictions.csv').read_bytes()).hexdigest()==freeze['prediction_sha256']
    assert hashlib.sha256((ROOT/'frozen_protocol.json').read_bytes()).hexdigest()==freeze['protocol_sha256']
    pred=pd.read_csv(OUT/'predictions.csv');rows=[]
    for year_s,k in protocol['horizons'].items():
        year=int(year_s);p=pred[pred.season==year];a=pd.read_csv(VAULT/f'answers_{year}.csv').dropna(subset=['actual_pick'])
        assert not p.pid.duplicated().any() and not a.pid.duplicated().any()
        assert set(p.pid)==set(a.pid),f'Full drafted pool mismatch for {year}: predictions={len(p)}, answers={len(a)}'
        joined=a.merge(p[['pid','score']],on='pid',validate='one_to_one')
        truth=joined[[f'y_s{i}_war' for i in range(1,k+1)]].apply(pd.to_numeric,errors='raise').fillna(0).sum(axis=1)
        rho=float(spearmanr(joined.score,truth).statistic);draft=float(spearmanr(-joined.actual_pick,truth).statistic)
        assert np.isfinite(rho) and np.isfinite(draft)
        rows.append(dict(season=year,k=k,n=len(joined),stack=rho,draft=draft,cutoff=2018))
    result=dict(protocol=protocol['protocol'],score=float(np.mean([r['stack'] for r in rows])),rows=rows,scored_at=time.time(),freeze=freeze,provenance=protocol['feature_provenance'],selection='Never use this result to select the next development experiment',class2026='prediction board only; no NBA outcomes')
    ledger=VAULT/'r8_frozen_benchmark_ledger.jsonl'
    with open(str(ledger)+'.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        lines=ledger.read_text().splitlines(keepends=True) if ledger.exists() else []
        prior=hashlib.sha256(lines[-1].encode()).hexdigest() if lines else 'GENESIS'
        assert not any(json.loads(line).get('freeze',{}).get('prediction_sha256')==freeze['prediction_sha256'] for line in lines),'Already scored; read stored result'
        with open(ledger,'a') as f:f.write(json.dumps(dict(result,prev=prior))+'\n');f.flush();__import__('os').fsync(f.fileno())
    (OUT/'test_result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
if __name__=='__main__':main()

"""Left-join official combine sidecars to quarantined, predictor-only snapshots."""
from pathlib import Path
import hashlib
import json
import pandas as pd
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'verified_inputs_v1'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    OUT.mkdir(exist_ok=True)
    rows=[]
    for p in sorted((ROOT/'quarantined_inputs').glob('*_inputs.csv')):
        side=ROOT/'verified_combine/data'/p.name
        base=pd.read_csv(p);extra=pd.read_csv(side)
        assert base.pid.is_unique and extra.pid.is_unique
        assert base[['pid','draft_year']].equals(extra[['pid','draft_year']])
        cols=[c for c in extra if c.startswith('vcmb_')]
        assert len(cols)==37 and not set(cols)&set(base)
        merged=base.merge(extra,on=['pid','draft_year'],how='left',validate='one_to_one',sort=False)
        assert merged.pid.tolist()==base.pid.tolist()
        assert not any(c.startswith('y_') or c in ['actual_pick','actual_round'] for c in merged)
        assert merged[[c for c in merged if c.startswith(('bio_','med_','cons_','scout_'))]].isna().all().all()
        pd.testing.assert_frame_equal(merged[base.columns],base)
        pd.testing.assert_frame_equal(merged[cols],extra[cols])
        merged.to_csv(OUT/p.name,index=False)
        rows.append(dict(file=p.name,rows=len(merged),combine_covered=int(merged[cols].notna().any(axis=1).sum()),source_sha256=sha(p),sidecar_sha256=sha(side),sha256=sha(OUT/p.name)))
    assert len(rows)==9
    manifest=dict(version='verified_inputs_v1_20260906',status='Partially audited; remaining inherited predictors and original cohort eligibility are uncertified',files=rows,added_features=cols,combine_source_manifest_sha256=sha(ROOT/'verified_combine/data/manifest.json'),combine_boundary_checks_sha256=sha(ROOT/'verified_combine/data/leakage_checks.json'),policy='All original rows retained, 37 official same-cohort combine columns appended; quarantined bio/medical/consensus/scouting columns stay missing. No imputation, outcomes, actual draft picks, model fitting or scoring. All existing F50 columns retained.',limitations=['This is a source correction, not a clean benchmark certification.','Source-only cohort eligibility and remaining inherited inputs still need verification.','2026 combine observations unavailable and remain missing.'])
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'files':len(rows),'rows':sum(r['rows'] for r in rows),'added':37,'covered':sum(r['combine_covered'] for r in rows)}))
if __name__=='__main__':main()

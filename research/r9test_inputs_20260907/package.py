"""Finalize the candidate input-only package; no source or model mutations."""
from pathlib import Path
import csv,hashlib,json
import numpy as np
import pandas as pd
import build as B
R=B.ROOT
m=json.loads((R/'manifest.json').read_text())
for y in B.YEARS:
    p=R/f'inputs_{y}.csv';a=pd.read_csv(p,float_precision='round_trip',usecols=m['columns'])[m['columns']].to_numpy(float)
    assert B.matrix_hash(a)==m['output_files'][p.name]['matrix_hash']
    p=R/f'metadata_{y}.csv';m['output_files'][p.name]={'sha256':B.digest(p.read_bytes()),'rows':m['cohort_coverage'][str(y)]['rows'],'predictor_eligible':False}
m['serialization']='Each finite feature uses Python repr(float), a shortest exact FP64 round-trip string. Read pandas CSV using float_precision=round_trip; all seven matrix hashes reproduce exactly. Blank cells are NaN. Old H matrices are outside this export and remain frozen.'
B.dump(R/'manifest.json',m)
raw_to_index={v:k for k,v in B.FIELDS.items()}
special={
'ctx_base_three_share':([17,20],'fg3a/(fg2a+fg3a), positive denominator'),
'ctx_skill_creation_control':([11,12],'ast_pct/(tov_pct+1), tov_pct>=0'),
'ctx_skill_defense_discipline':([22,23,30],'(stl_pct+blk_pct)/(fouls40+1), fouls40>=0'),
'ctx_skill_ft_volume':([14,15],'ft_pct*log1p(fta), fta>=0'),
'ctx_skill_usage_efficiency':([6,8],'(usage-20)*(ts-50)/100'),
'f50_career_slope_usage':([6,31],'Original NumPy polyfit slope of usage against source season, at least2 finite distinct seasons; exact verified same source-player ID, no future seasons.'),
'f50_posterior_rim':([36,37],'(rim_made+0.60*30)/(rim_attempts+30), finite0<=makes<=attempts. Fixed original prior, no empirical refit.')}
fields=[]
for c,p in zip(m['columns'],m['physical_source_fields']):
    if p in B.CONS:
        definition=json.loads((B.WORK/'verified_consensus_extension/metric_dictionary.json').read_text())[p]
        contract={'family':'dated_mock_ranks','raw_indices':[],'definition':definition,'date_proof':'Exact archived response before draft-day Eastern midnight AND explicit update calendar date before draft date.','identity':'Previously verified unique exact normalized same-cohort name; no new mapping.'}
    else:
        if p in special:idx,formula=special[p]
        else:idx=[raw_to_index[p.removeprefix('ctx_base_')]];formula='Unchanged raw annual field; no scaling, repair or imputation.'
        contract={'family':'college_annual_candidate','raw_indices':idx,'definition':formula,'date_proof':'Known source season<=draft year; latest source year gap0or1; all history<=focal season. No per-game timestamp or historical publication date in annual tables.','identity':'Exact pinned source filename/zero-based row/team/source-player-ID plus allowed-value hash.','units':'Original frozen context/F50 units unchanged; percentage fields retain the source scale.'}
    fields.append({'model_column':c,'physical_source_field':p,**contract,'nonmissing_by_cohort':{y:d['rows']-d['missing_by_column'][c] for y,d in m['cohort_coverage'].items()}})
B.dump(R/'field_contracts.json',fields)
B.dump(R/'verification.json',{'unit_tests_passed':6,'test_file':'test_inputs.py','fp64_roundtrip_all7_matrix_hashes_exact':True,'rows_preserved':sum(x['rows'] for x in m['cohort_coverage'].values()),'metadata_separate_from44_predictors':True,'raw_index45_accessed':False,'model_or_scoring_calls':0,'outcome_label_answer_files_read':0,'new_source_collection_requests':0,'authorized_server_read':'One SSH read projecting only pid,was_drafted from existing7 input files; private/membership_projection.json records projection hashes, not fabricated full-source hashes.','future_source_removal_cutoffs':[2019,2021,2023],'fifty_cache_cells_exact':m['fifty_cache_replay']['exact_or_nan'],'old_context_replay_max_difference':m['old_context_replay']['max_absolute_difference'],'model_eligible':False})
lines=['# Frozen H input candidates, 2019–2025','','Seven CSVs contain the exact44 sorted H model columns plus PID and draft year. They preserve all900 original input rows. The original1428 pre-2019 H feature rows are not replaced. No model, label export or test scoring is performed here.','','`metadata_YEAR.csv` holds only PID, year and the existing server input-file drafted flag. It is separate from predictors. Model/scorer owners select the registered query population and enforce training eligibility and label cutoffs.','','|Year|Full rows|College source|Verified mock|Drafted metadata|All44 missing|','|---|---:|---:|---:|---:|---:|']
for y,d in m['cohort_coverage'].items():lines.append(f"|{y}|{d['rows']}|{d['college_lineage_rows']}|{d['verified_mock_rows']}|{d['was_drafted_metadata_rows']}|{d['all44_missing_rows']}|")
lines+=['','Each feature is documented in `field_contracts.json`; per-column missingness, source hashes and matrix/order hashes are in `manifest.json`. Blank values remain NaN. Source-unmatched players, unlisted mock players and one-publisher disagreement remain missing. No name guessing, rank imputation, current biographies or actual draft order enters the feature matrix.','','The college40-field portion uses the same38 context definitions and2 selected F50 definitions as H. All3020 original selected F50 cache values replay exactly. The old38-context check covers25,118 cells, with max8.9e-16 numeric difference against CSV round-trip values; it does not authorize rewriting old H matrices. New finite exports use exact FP64 round-trip strings; read with `float_precision="round_trip"`. All seven resulting matrix hashes reproduce exactly.','','The `work/fifty_audit/fifty_test_*` files are negative cutoff-2018 fixtures and must not be used as future-cohort caches. Reconstruction instead pins the original work/fifty source manifest and existing exact source-row lineage. No future2026 source is loaded. Earlier exported feature values survive complete removal of later sources at three cutoff years.','','Same pre-draft cohort inputs can later serve expanding training for2019–2023 without refilling or reconstructing them with later player information. The independent label/recipe builder must prohibit the current query cohort in training and restrict outcomes to completed seasons allowed by that evaluation year.','','## Limits and admission','','Package-wide `model_eligible=false` means parent review is still required. The main missing contract is a strict original-publication-date guarantee for annual college tables: they were retrieved retrospectively, and their source seasons are known, but game-level calendar evidence and original vintage are absent here. These numeric candidates support only an explicitly admitted retrospective diagnostic. The raw annual count/per-game subset mismatch is preserved to match the frozen recipe, not silently repaired. No later NBA-calibrated impact metrics are imported.','','The archived mock ranks have stronger dated availability proof, but only one publisher is available for2021–2025, and2019–2020 include stale and partial serious top15 forecasts. Source count/range reflects this changing coverage. Original pool construction and inherited identity limitations remain documented. Six focused tests cover row/order/metadata/schema, future/stale/identity rejection, future-source removal, mock-date/duplicate rejection, missingness and raw hash tampering.','','Only explicitly allowlisted files are public candidates. Raw responses, source-player identities and detailed college row pointers stay private. No source package was modified.']
# Count is derived rather than copied from the prose draft.
lines=[x.replace('all900 original input rows',f"all{sum(d['rows'] for d in m['cohort_coverage'].values())} original input rows") for x in lines]
(R/'README.md').write_text('\n'.join(lines)+'\n')
for p in (R/'private').iterdir():p.chmod(0o600)
(R/'private').chmod(0o700)
names=['build.py','test_inputs.py','package.py','README.md','manifest.json','field_contracts.json','verification.json']+[f'{prefix}_{y}.csv' for y in B.YEARS for prefix in ['inputs','metadata']]
B.dump(R/'PUBLIC_ALLOWLIST.json',{'model_eligible':False,'publication_policy':'Only enumerated numeric pseudonymous inputs, separate metadata and audit/code files. Private identities/raw references excluded. No model admission implied.','files':{n:{'sha256':B.digest((R/n).read_bytes()),'bytes':(R/n).stat().st_size} for n in names},'private_excluded':['private/']})
print(json.dumps({'public_files':len(names),'allowlist_sha256':B.digest((R/'PUBLIC_ALLOWLIST.json').read_bytes()),'total_input_rows':sum(d['rows'] for d in m['cohort_coverage'].values()),'roundtrip_pass':True}))

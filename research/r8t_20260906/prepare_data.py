"""Freeze R8t dated mock biography study; no model runs or held-out access."""
from pathlib import Path
import csv
import copy
import hashlib
import json
import shutil
import pandas as pd

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'r8s'
BIO=ROOT.parent/'verified_mock_bio'
DATA=ROOT/'data'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    DATA.mkdir(exist_ok=True)
    original=json.loads((SOURCE/'data/manifest.json').read_text())
    source_plan=json.loads((SOURCE/'plan.json').read_text())
    for name,digest in original['files'].items():
        assert Path(name).name==name and sha(SOURCE/'data'/name)==digest
        shutil.copyfile(SOURCE/'data'/name,DATA/name)
    shutil.copyfile(SOURCE/'legacy_kernel.py',ROOT/'legacy_kernel.py')
    allowlist=json.loads((BIO/'PUBLIC_ALLOWLIST.json').read_text())
    before={name:sha(BIO/name) for name in allowlist['files']}
    assert all(before[name]==record['sha256'] for name,record in allowlist['files'].items())
    bio_manifest=json.loads((BIO/'manifest.json').read_text())
    verification=json.loads((BIO/'verification.json').read_text())
    assert verification['matched_players']==bio_manifest['players']==374
    assert verification['source_cells_checked']==480 and not verification['models_or_NBA_outcomes_used']
    columns=bio_manifest['features'];assert len(columns)==10 and all(c.startswith('vmb_') for c in columns)
    with (DATA/'features.csv').open(newline='') as stream:base_rows=list(csv.DictReader(stream))
    with (BIO/'features_eligible.csv').open(newline='') as stream:
        reader=csv.DictReader(stream);assert reader.fieldnames==['pid','draft_year']+columns;bio_rows=list(reader)
    by_pid={r['pid']:r for r in bio_rows};assert len(by_pid)==len(bio_rows)
    assert all(2007<=int(r['draft_year'])<=2014 for r in bio_rows)
    # Preserve original numeric text while joining, including BMI precision.
    with (DATA/'bio_features.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['pid','draft_year']+columns,lineterminator='\n');writer.writeheader()
        for row in base_rows:
            source=by_pid.get(row['pid'])
            assert source is None or int(source['draft_year'])==int(row['draft_year'])
            writer.writerow(source or {'pid':row['pid'],'draft_year':row['draft_year']})
    for name,target in [('row_provenance.csv','bio_provenance.csv'),('metric_dictionary.json','bio_dictionary.json'),
                        ('manifest.json','bio_metadata.json'),('verification.json','bio_verification.json')]:
        shutil.copyfile(BIO/name,DATA/target)
    x=pd.read_csv(DATA/'features.csv')
    assert list(x)==['pid','draft_year','was_drafted','actual_pick']+source_plan['baseline_source_variant']['context_features']
    assert x.pid.is_unique and (x.draft_year<=2018).all()
    bio=pd.read_csv(DATA/'bio_features.csv')
    assert bio[['pid','draft_year']].equals(x[['pid','draft_year']])
    matched=bio[bio.pid.isin(by_pid)].sort_values('pid').reset_index(drop=True)
    published=pd.read_csv(BIO/'features_eligible.csv')
    pd.testing.assert_frame_equal(matched,published[published.pid.isin(x.pid)].sort_values('pid').reset_index(drop=True))
    families={**source_plan['families'],'bio':columns}
    selection=copy.deepcopy(source_plan['training_eligibility_registration'])
    for year in source_plan['folds']:
        training=bio[bio.draft_year.between(source_plan['backbone']['window'],year-2)]
        selection[str(year)]['bio']=[c for c in columns if training[c].notna().sum()>=5 and training[c].nunique()>=2]
        assert len(selection[str(year)]['bio'])==10
    backgrounds={'college':[],'college_combine':['combine'],'college_consensus':['consensus'],
                 'college_combine_consensus':['combine','consensus']}
    variants=[]
    for background,parts in backgrounds.items():
        fixed={family:'real' for family in parts}
        variants.append({'id':background+'_baseline','background':background,'bio_arm':'absent','arms':fixed,'permutation_seed':None})
        variants.append({'id':background+'_bio_real','background':background,'bio_arm':'real','arms':{**fixed,'bio':'real'},'permutation_seed':None})
        for seed in source_plan['permutation_seeds']:
            variants.append({'id':f'{background}_bio_shuffle{seed}','background':background,'bio_arm':'permuted',
                             'arms':{**fixed,'bio':'permuted'},'permutation_seed':seed})
    plan={k:copy.deepcopy(source_plan[k]) for k in ['backbone','folds','seeds','permutation_seeds','source_filter',
           'calendar_policy','confirmation_note','baseline_source_variant']}
    plan.update(study='R8t dated mock biography incremental diagnostics',diagnostic_only=True,
                purpose='Test the incremental dated biography family over four fixed backgrounds with matched full-family controls.',
                no_confirmation_or_test_scoring=True,backgrounds=backgrounds,variants=variants,families=families,
                baseline='college_baseline',training_eligibility_registration=selection,
                model_constructor={'device':'cuda','n_estimators':32,'random_state':'task_seed',
                                   'batch_size':32,'norm_methods':'none','outlier_threshold':2.0},
                slot_mapping={c:f'slot_{i:03d}' for i,c in enumerate(sum(families.values(),[]))},
                selection={'base_features':41,'selector_seed':11,'scope':'Fit the unchanged CPU selector on the41 source columns after canonical training order; retain all41 in its importance ordering. Appended family eligibility uses training rows only.'},
                ordering_policy={'version':'sha256_pid_exact_vector_mean_v1',
                                 'row_order':'Sort train and query rows by SHA256(UTF8(pid)), with pid as deterministic collision tiebreaker, before selection and prediction. Identity/order keys never become predictors.',
                                 'input_equivalence':'All selected predictor values must be numerically identical. NaNs compare equal; positive/negative zero compare equal. Distinct vectors are never quantized or merged.',
                                 'prediction_ties':'Within each query group of exactly identical full predictor vectors, assign every row the arithmetic mean of its raw predictions using math.fsum over sorted float64 values.',
                                 'raw_preservation':'Save raw and canonical prediction for every pid, exact duplicate groups and policy hash. All scoring uses canonical predictions with Spearman average ranks.',
                                 'registration_basis':'R8order numerical audit found8 all-missing duplicate inputs with floating-point score splitting; no outcome score was used to choose this policy.',
                                 'new_baseline':'Every background baseline reruns under this policy. Do not pool these scores with raw-prediction R8s or earlier studies.'},
                controls={'shuffle':'Permute all selected biography columns as a whole row vector within draft cohort AND exact missingness pattern, using stable identity order.',
                          'seed_stream':source_plan['controls']['seed_stream'],
                          'preserved':source_plan['controls']['preserved'],
                          'limitations':'Sparse/singleton/constant-vector strata cannot move. Full biography algebra/covariance and missingness are retained. Conditional randomization is limited to observed strata; this is exploratory, not a significance test.'},
                summary={'primary':'For each background pair actual biography with the mean of its three matched biography shuffles at each fold/model seed. Report each control and fold/seed contrasts.',
                         'baseline':'No-biography baseline is descriptive only; it has different feature width and cannot isolate new information.',
                         'automatic_promotion':False,'interpretation':'Do not infer individual biography metric effects or complementarity between backgrounds from this family-level diagnostic.'},
                registration_basis='Four source backgrounds fixed without inspecting R8s scores. Original frozen consensus snapshot, never its extension. Verified mock biography facts only.',
                execution={'workers':4,'task_count':60,'xgboost_selector':'cpu','predictor':'GPU TabICL only','gpu_launch_performed':False})
    assert len(variants)*len(plan['seeds'])==60
    (ROOT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    manifest=copy.deepcopy(original)
    manifest.update(files={p.name:sha(p) for p in sorted(DATA.iterdir()) if p.is_file() and p.name!='manifest.json'},
                    source_families=families,source_package_hashes={**original['source_package_hashes'],'bio':before},
                    s_plan_reference_sha256=sha(SOURCE/'plan.json'),s_data_manifest_sha256=sha(SOURCE/'data/manifest.json'),
                    biography_unmatched_model_identities=published.loc[~published.pid.isin(x.pid),['pid','draft_year']].to_dict('records'),
                    bio_public_allowlist_sha256=sha(BIO/'PUBLIC_ALLOWLIST.json'))
    manifest['limitations']+=bio_manifest['limitations']
    (DATA/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    assert before=={name:sha(BIO/name) for name in allowlist['files']}
    print(json.dumps({'tasks':60,'players':len(x),'bio_columns_per_fold':{y:len(s['bio']) for y,s in selection.items()},'no_gpu_launch':True}))

if __name__=='__main__':main()

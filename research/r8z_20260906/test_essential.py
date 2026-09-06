"""Small registration/reference checks; reuses the proven X pair design."""
import copy,json,itertools
from pathlib import Path
import worker as Z
R=Path(__file__).resolve().parent;p=Z.load_plan();refs=list(Z.reference_records().values())
assert len(p['selected_features'])==19 and len(p['pairs'])==161 and len(p['variants'])*3==4893 and len(refs)==63
assert len({tuple(pair) for pair in p['pairs']})==161 and not {tuple(pair) for pair in p['pairs']} & {tuple(pair) for pair in p['registration']['excluded_completed_X_pairs']}
assert all(pair==sorted(pair) and set(pair)<=set(p['selected_features']) for pair in p['pairs'])
for e in refs:Z.validate_entry(e,p)
s=Z.summarize_matched(refs);assert s['reference_replays_passed']==63 and s['interpretation_allowed'] and len(s['pending'])==161 and not s['pairs']
assert not Z.summarize_matched(refs[:-1])['interpretation_allowed']
tests=[]
for name,mutate in [('raw_reference',lambda e:e['rows'][0]['predictions'][0].__setitem__('raw_score',999.)),('reference_constructor',lambda e:e['rows'][0]['audit']['registered_model_parameters'].__setitem__('n_estimators',64)),('future_label',lambda e:e['rows'][0]['audit'].__setitem__('max_label_season',2020))]:
 e=copy.deepcopy(refs[0]);mutate(e)
 try:Z.validate_entry(e,p)
 except AssertionError:tests.append(name)
 else:raise AssertionError('Tamper accepted')
(R/'tests.json').write_text(json.dumps({'passed':True,'models_fitted':0,'tasks':4893,'new_pairs':161,'no_duplicate_X_pairs':True,'exact_reference_contracts':63,'missing_reference_withholds_interpretation':True,'tamper_rejections':tests,'pair_control_tests_inherited_from_completed_X':True},indent=2)+'\n');print('Z essential registration/reference checks passed.')

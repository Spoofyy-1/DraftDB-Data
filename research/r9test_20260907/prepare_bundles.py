"""CPU-only preparation: admitted sources and root cutoff labels, no model/score calls."""
from pathlib import Path
import json,hashlib,importlib.util,copy
import numpy as np
import pandas as pd
import model_core as M
CODE=Path('/code');SOURCE=Path('/input_package');LABELS=Path('/label_exports');HR=Path('/h_reference');OUT=Path('/prepared')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,x):path.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def nofit(*a,**k):raise AssertionError('No model fitting/prediction in source preparation')
def read(path):return pd.read_csv(path,dtype={'pid':str},float_precision='round_trip')
def main():
 recipe=json.loads((CODE/'recipe.json').read_text());admission=json.loads((CODE/'source_admission.json').read_text());assert admission['scoped_diagnostic_admission']and sha(SOURCE/'manifest.json')==admission['source_input_manifest_sha256'];source=json.loads((SOURCE/'manifest.json').read_text());assert source['model_eligible']is False
 spec=importlib.util.spec_from_file_location('prepare_frozen_H',HR/'worker.py');H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H);H.plan();H.environment();assert sha(HR/'frozen.json')==recipe['selected_H_frozen_sha256'];H.run_variant=nofit;H.B._prepared=nofit;M.predict_one=nofit
 from tabicl import TabICLRegressor
 TabICLRegressor.fit=nofit;TabICLRegressor.predict=nofit
 bp,manifest,data,labels_unused=H.B._load_inputs();del labels_unused
 fields=recipe['physical_source_fields'];columns=recipe['columns'];assert source['columns']==columns and source['physical_source_fields']==fields and len(data)==1428 and data.draft_year.between(2000,2018).all();old=data[['pid','draft_year','was_drafted']+fields].copy();old_hash=M.values_hash(old[fields]);future={}
 for year in recipe['years']:
  for name in [f'inputs_{year}.csv',f'metadata_{year}.csv']:assert sha(SOURCE/name)==source['output_files'][name]['sha256']
  x=read(SOURCE/f'inputs_{year}.csv');meta=read(SOURCE/f'metadata_{year}.csv');assert list(x)==['pid','draft_year']+columns and list(meta)==['pid','draft_year','was_drafted'];assert x[['pid','draft_year']].equals(meta[['pid','draft_year']])and x.pid.is_unique and x.draft_year.eq(year).all()and meta.was_drafted.isin([0,1]).all();assert M.values_hash(x[columns])==source['output_files'][f'inputs_{year}.csv']['matrix_hash'];frame=x.rename(columns=dict(zip(columns,fields)));frame.insert(2,'was_drafted',meta.was_drafted.to_numpy());future[year]=frame
 assert sum(len(f)for f in future.values())==900
 all_reports=[];bundle_hashes={}
 for year in recipe['years']:
  directory=OUT/str(year);assert not directory.exists(),'Do not overwrite prepared inputs';directory.mkdir()
  tr=pd.concat([old]+[future[y]for y in recipe['years']if y<year],ignore_index=True);q=future[year].loc[future[year].was_drafted==1,['pid','draft_year']+fields].copy();assert len(q)==admission['query_was_drafted_counts'][str(year)]and tr.pid.is_unique and not set(tr.pid)&set(q.pid);assert M.values_hash(tr.iloc[:1428][fields])==old_hash
  lm=json.loads((LABELS/str(year)/'manifest.json').read_text());lp=LABELS/str(year)/'training_labels.csv';assert lm['predicted_year']==year and lm['permitted_season_end']==year-1 and sha(lp)==lm['export_labels_sha256'];ll=read(lp);assert len(ll)==lm['rows']and ll.draft_year.lt(year).all()and ll.season_end.le(year-1).all()and not set(ll.pid)&set(q.pid)
  keep=ll.pid.isin(tr.pid);omitted=ll[~keep];ll=ll[keep].copy();atr,ate,yy,pids,querypids,audit=M.build_payload(tr,q,ll,recipe,year);frames={'train_features.csv':tr,'query_features.csv':q,'train_labels.csv':ll};info={}
  for name,frame in frames.items():
   path=directory/name;frame.to_csv(path,index=False,float_format='%.17g');decoded=read(path);assert list(decoded)==list(frame)and decoded.pid.tolist()==frame.pid.tolist();numeric=[c for c in frame if c!='pid'];assert np.array_equal(decoded[numeric].to_numpy(dtype=float),frame[numeric].to_numpy(dtype=float),equal_nan=True);info[name]={'sha256':sha(path),'rows':len(frame),'columns':list(frame)}
  replay=M.build_payload(read(directory/'train_features.csv'),read(directory/'query_features.csv'),read(directory/'train_labels.csv'),recipe,year);assert audit==replay[-1]and np.array_equal(yy,replay[2])and np.array_equal(atr.to_numpy(),replay[0].to_numpy(),equal_nan=True)and np.array_equal(ate.to_numpy(),replay[1].to_numpy(),equal_nan=True)
  report={'year':year,'label_cutoff':year-1,'recipe_sha256':sha(CODE/'recipe.json'),'files':info,'canonical_query_PID_hash':audit['query_PID_hash'],'canonical_query_PIDs':querypids,'source_all_query_rows':len(future[year]),'selected_drafted_query_rows':len(q),'source_membership_sha256':sha(SOURCE/f'metadata_{year}.csv'),'source_inputs_sha256':sha(SOURCE/f'inputs_{year}.csv'),'input_package_manifest_sha256':sha(SOURCE/'manifest.json'),'source_label_export_manifest_sha256':sha(LABELS/str(year)/'manifest.json'),'source_label_export_sha256':sha(lp),'training_feature_pool_rows':len(tr),'out_of_feature_pool_label_rows':len(omitted),'out_of_feature_pool_label_players':int(omitted.pid.nunique()),'out_of_feature_pool_label_PID_hash':M.digest(M.canon(sorted(omitted.pid.unique().tolist()))),'label_source_calendar':{'actual_max':lm['actual_label_max'],'partial_calendar':lm['partial_calendar'],'missing_calendar_seasons':lm['missing_calendar_seasons'],'H_facts_absent_from_verified_broker':lm['H_facts_absent_from_verified_broker']},'prepared_payload_audit':audit,'old1428_feature_rows_exact':True,'old_H_matrix_hash':old_hash,'FP64_CSV_roundtrip_exact':True,'source_global_model_eligible_remains_false':True,'scoped_diagnostic_admission_sha256':sha(CODE/'source_admission.json'),'no_test_answers_or_scoring':True}
  save(directory/'manifest.json',report);bundle_hashes[str(year)]=sha(directory/'manifest.json');all_reports.append({k:report[k]for k in ['year','source_all_query_rows','selected_drafted_query_rows','training_feature_pool_rows','out_of_feature_pool_label_rows','out_of_feature_pool_label_players','label_source_calendar','prepared_payload_audit']})
 save(OUT/'preparation.json',{'passed':True,'model_fits':0,'test_scores':0,'years':recipe['years'],'year_manifest_sha256':bundle_hashes,'old_H1428_rows_exact':True,'all900_source_rows_preserved_outside_model_bundles':True,'all_FP64_roundtrips_exact':True,'reports':all_reports,'prepare_code_sha256':sha(Path(__file__))});print(json.dumps({'passed':True,'model_fits':0,'bundle_manifest_hashes':bundle_hashes,'query_counts':[r['selected_drafted_query_rows']for r in all_reports],'admitted_training_counts':[r['prepared_payload_audit']['training_rows']for r in all_reports]}))
if __name__=='__main__':main()

"""Export a minimal pre-2019 research dataset. No legacy engine/vault imports."""
from pathlib import Path
import json, hashlib
import pandas as pd

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'data'
OUT.mkdir(exist_ok=True)
t=pd.read_csv(ROOT/'train_source.csv')
assert t.pid.is_unique and t.draft_year.between(2000,2018).all()
# Raw physical measurements and college box-score quantities only. No scout grades,
# draft order, learned projections, global percentiles, names, or target-derived features.
core=['bio_age_at_draft','bio_combine_height_in','bio_combine_weight_lb',
      'bio_combine_wingspan_in','bio_combine_reach_in','bio_combine_vertical_standing_in',
      'bio_combine_vertical_max_in','bio_combine_lane_agility_s','bio_combine_sprint_s',
      'col_gp','col_mpg','col_pts36','col_reb36','col_ast36','col_stl36','col_blk36',
      'col_usg_pct','col_ts_pct','col_efg_pct','col_ast_pct','col_tov_pct',
      'col_orb_pct','col_drb_pct','col_stl_pct','col_blk_pct','col_fg3ar','col_ftar',
      'col_ft_pct','col_fg3_pct','col_fg2_pct','col_minutes_total',
      'cons_mock_consensus_rank','cons_mock_best_rank','cons_mock_n_sources','cons_bigboard_consensus_rank',
      'hs_mcdonalds_aa','hs_jordan_brand','hs_hoop_summit','hs_rsci_rank',
      'intl_gp','intl_minutes','intl_mpg','intl_pts36','intl_reb36','intl_ast36',
      'intl_stl36','intl_blk36','intl_ts_pct','intl_ft_pct','intl_fg3_pct','intl_level']
core=[c for c in core if c in t]
for c in core: t[c]=pd.to_numeric(t[c],errors='coerce')
if 'col_final_season' in t:
    invalid=t.col_final_season.isna()|(t.col_final_season>t.draft_year)
    t.loc[invalid,[c for c in core if c.startswith('col_')]]=float('nan')
x=t[['pid','draft_year','was_drafted','actual_pick']+core].copy()
c=pd.read_csv(ROOT/'context_train.csv')
x=x.merge(c,on='pid',how='left',validate='one_to_one')
assert (x.source_season.fillna(0)<=x.draft_year).all()
x=x.drop(columns=['source_season'])
labels=pd.read_csv(ROOT/'calendar_train_labels.csv')
eligible=set(labels.pid)  # Reject unresolved identities rather than making zero labels.
x=x[x.pid.isin(eligible)&(x.was_drafted==1)].reset_index(drop=True)
labels=labels[labels.pid.isin(x.pid)&(labels.season_end<=2018)].copy()
x.to_csv(OUT/'features.csv',index=False)
labels.to_csv(OUT/'labels.csv',index=False)
manifest=dict(protocol='R8 calendar cutoff v1',selection_label_cutoff=2018,
              training_cutoff_rule='season_end <= predicted_draft_year - 1',
              tuning_folds=[2012,2013,2014],confirmation_folds=[2015,2016,2017],
              score='Mean class Spearman; k=min(5,2018-draft_year), observed first k played seasons by 2018',
              score_limit='Pre-2019 development metric; not a 2019-2026 test result',
              label_policy='Retrospective WAR definition explicitly authorized; calendar dates enforced',
              input_limit='Legacy core fields retain inherited source-vintage uncertainty; new context is reconstructed from dated college season tables',
              rows=len(x),dated_labels=len(labels),core=core,
              context=[v for v in x if v.startswith('ctx_')],
              files={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in OUT.glob('*.csv')})
json.dump(manifest,open(OUT/'manifest.json','w'),indent=2)
print(json.dumps({k:manifest[k] for k in ['rows','dated_labels','training_cutoff_rule']}))

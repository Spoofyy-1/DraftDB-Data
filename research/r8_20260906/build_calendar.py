"""Date existing training WAR labels using the published historical RAPTOR series.

Run on the data-preparation machine, never in a model worker. This script reads
only the 2000-2018 training snapshot and matching identities. Download the source
CSV separately and pass its path. Names never enter the output training tables.
"""
import argparse,hashlib,json,re,unicodedata
from pathlib import Path
import pandas as pd

def norm(s):
    return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower())

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--identity',type=Path,required=True)
    p.add_argument('--train',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    r=pd.read_csv(a.source);r['name']=r.player_name.map(norm)
    groups={n:g.sort_values('season') for n,g in r.groupby('name')}
    t=pd.read_csv(a.train);assert t.pid.is_unique and t.draft_year.between(2000,2018).all()
    ids=pd.read_csv(a.identity)
    t=t.merge(ids[['pid','player_name']],on='pid',validate='one_to_one')
    rows=[];bad=[];matched=0
    for row in t.to_dict('records'):
        s=groups.get(norm(row['player_name']))
        if s is None or s.player_id.nunique()!=1:
            bad.append(dict(pid=row['pid'],reason='no_unique_source_identity'));continue
        s=s[s.season>row['draft_year']]
        ok=all(abs(float(sr.war_total)-float(row[f'y_s{k}_war']))<1e-5
               for k,sr in enumerate(s.head(5).itertuples(),1) if pd.notna(row[f'y_s{k}_war']))
        if not ok:
            bad.append(dict(pid=row['pid'],reason='source_label_mismatch'));continue
        matched+=1
        for k,sr in enumerate(s.head(5).itertuples(),1):
            if pd.notna(row[f'y_s{k}_war']):
                rows.append(dict(pid=row['pid'],draft_year=int(row['draft_year']),ordinal=k,
                                 season_end=int(sr.season),war=float(row[f'y_s{k}_war'])))
    pd.DataFrame(rows).to_csv(a.output/'calendar_train_labels.csv',index=False)
    audit=dict(source='https://raw.githubusercontent.com/fivethirtyeight/data/master/nba-raptor/historical_RAPTOR_by_player.csv',
               source_sha256=hashlib.sha256(a.source.read_bytes()).hexdigest(),
               train_sha256=hashlib.sha256(a.train.read_bytes()).hexdigest(),
               matched_train_players=matched,unresolved=bad,
               label_vintage='Retrospective RAPTOR; not contemporaneously published ratings',
               no_test_outcomes_read_from_project=True)
    (a.output/'calendar_audit.json').write_text(json.dumps(audit,indent=2))
    print(json.dumps(dict(matched=matched,unresolved=len(bad),dated_labels=len(rows))))

if __name__=='__main__':main()

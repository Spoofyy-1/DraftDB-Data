"""Factual-only pilot; no outcomes, names as lookup keys only, no model promotion.
Source dates and article bodies checked in web results on 2026-09-06.
Archive snapshot verification is a separate gate; all outputs remain quarantined.
"""
from pathlib import Path
import csv,json,hashlib,unicodedata,datetime,collections,re,html
R=Path(__file__).parent
players=json.load(open(R.parent/'collectors/players.json'))
def norm(s):
 return ''.join(c for c in unicodedata.normalize('NFKD',s).lower() if c.isalnum())
lookup=collections.defaultdict(list)
for p in players:lookup[norm(p['name'])].append(p)
sources={
 'dx2010sf':{'url':'https://www.draftexpress.com/amp/article/Situational-Statistics-This-Yearas-Small-Forward-Crop-3503/','published_date':'2010-06-12','title':'Situational Statistics: This Year’s Small Forward Crop','body_section':'Findings, through immediately before Read Next; earlier NBA retrospective excluded','body_verified':True,'date_verified':True,'primary_publisher':'DraftExpress','underlying_stat_provider':'Synergy Sports Technology'},
 'dx2010pf':{'url':'https://www.draftexpress.com/amp/article/Situational-Statistics-This-Yearas-Power-Forward-Crop-3505/','published_date':'2010-06-14','title':'Situational Statistics: This Year’s Power Forward Crop','body_section':'Findings only; prior-class NBA retrospective excluded','body_verified':True,'date_verified':True,'primary_publisher':'DraftExpress','underlying_stat_provider':'Synergy Sports Technology'},
 'dx2011fw':{'url':'https://www.draftexpress.com/amp/article/Situational-Statistics-the-2011-Forward-Crop-3762/','published_date':'2011-06-19','title':'Situational Statistics: the 2011 Forward Crop','body_section':'How do the Top Prospects Stack Up, through immediately before Read Next','body_verified':True,'date_verified':True,'primary_publisher':'DraftExpress','underlying_stat_provider':'Synergy Sports Technology'},
 'dx2007camp':{'url':'https://www.draftexpress.com/amp/article/2007-NBA-Pre-Draft-Camp-Rosters-and-Physical-Only-2085/','published_date':'2007-05-29','title':'2007 NBA Pre-Draft Camp Rosters and Physical Only','body_section':'Named Camp Players, Physical Only Players and Media Availability rosters only','body_verified':True,'date_verified':True,'primary_publisher':'DraftExpress','underlying_stat_provider':'Reported NBA invitation roster'},
}
# Fields preserve the denominator used by the source. Percentages remain 0..100.
# PPP and PPS are separate: points per possession and points per shot.
raw={
'dx2010sf':{
'Wesley Johnson':{'overall_ppp':1.021,'poss_pg':15.1,'turnover_pct':13.3,'shots_fouled_pct':6.3,'post_ppp':.979,'post_poss_pg':1.4,'cut_poss_pct':16.1,'putback_ppp':1.379,'jump_ppp':.965,'jump_fg_pct':36.5,'finish_ppp':1.23},
'Al-Farouq Aminu':{'overall_ppp':.841,'jump_fg_pct':24,'rim_fg_pct':48.9,'halfcourt_shots_fouled_pct':9.9,'putback_poss_pg':3.1},
'Paul George':{'turnover_pct':18.8,'isolation_turnover_pct':30,'transition_turnover_pct':25,'transition_poss_pg':4.2,'transition_ppp':1.127,'spotup_fga_pg':3.5,'spotup_ppp':1.056,'open_catchshoot_pps':1.2,'guarded_catchshoot_pps':.862,'pullup_pps':.433,'finish_pps':1.19,'post_ppp':.67,'isolation_shots_fouled_pct':12.9},
'Xavier Henry':{'overall_ppp':1.012,'poss_pg':12.1,'halfcourt_ppp':.994,'spotup_poss_pct':35.9,'spotup_ppp':1.1,'guarded_catchshoot_pps':1.26,'open_catchshoot_pps':1.16,'pullup_fg_pct':28.6,'finish_fga_pg':2.1,'finish_ppp':1.12,'isolation_ppp':1.048,'post_ppp':1.2},
'Luke Babbitt':{'overall_ppp':.97,'poss_pg':20.6,'transition_ppp':.9,'halfcourt_ppp':.98,'halfcourt_poss_pg':18.1,'turnover_pct':12.2,'shots_fouled_pct':8.4,'isolation_poss_pg':5.9,'isolation_fg_pct':45.4,'post_ppp':1.,'post_poss_pg':3.1,'finish_ppp':1.26,'pullup_fga_pg':4.6,'pullup_fg_pct':42},
'Damion James':{'overall_ppp':1.,'shots_fouled_pct':10.2,'open_catchshoot_fg_pct':42.9,'putback_poss_pg':2.,'cut_poss_pg':2.3,'isolation_ppp':.672},
'Stanley Robinson':{'overall_ppp':.96,'transition_ppp':1.36,'jump_ppp':.87,'finish_ppp':1.26},
'James Anderson':{'overall_ppp':1.07,'poss_pg':20.,'pickroll_poss_pg':2.9},
'Gordon Hayward':{'finish_ppp':1.316},
'Quincy Pondexter':{'overall_ppp':1.066,'isolation_ppp':.972,'pullup_fg_pct':42},
'Devin Ebanks':{'jump_ppp':.592,'jump_fg_pct':28.2,'finish_ppp':1.1},
'Marqus Blakely':{'post_poss_pg':7.1},
},
'dx2010pf':{
'Derrick Favors':{'poss_pg':12.1,'overall_ppp':1.,'post_ppp':.844,'post_turnover_pct':21.5},
'Patrick Patterson':{'poss_pg':12.3,'overall_ppp':1.139,'turnover_pct':8.3,'spotup_poss_pct':18.,'transition_poss_pct':16.,'putback_poss_pct':15.4,'post_fg_pct':65.,'jump_ppp':.894,'finish_ppp':1.368},
'Larry Sanders':{'overall_ppp':1.03,'poss_pg':13.,'post_fg_pct':55.3,'jump_ppp':.421,'finish_ppp':1.421},
'Charles Garcia':{'poss_pg':21.2,'free_throw_poss_pct':24.1,'overall_ppp':.909},
'Gani Lawal':{'overall_ppp':.913,'poss_pg':13.6,'putback_poss_pct':16.5,'free_throw_poss_pct':21.1},
'Jarvis Varnado':{'overall_ppp':1.03,'shots_fouled_pct':13.4,'jump_fga_pg':.4,'post_fg_pct':51.6,'post_poss_pct':46.3},
'Craig Brackins':{'overall_ppp':.86,'post_poss_pg':6.9},
},
'dx2011fw':{
'Derrick Williams':{'poss_pg':16.4,'overall_ppp':1.16,'jump_shot_pct':25.,'jump_fg_pct':56.,'jump_pps':1.6,'pullup_fga_total':5.,'isolation_ppp':1.3,'post_ppp':1.06,'pickroll_finish_ppp':1.37,'cut_ppp':1.26},
'Jon Diebler':{'overall_ppp':1.3},
'Kyrie Irving':{'overall_ppp':1.2},
'Kyle Singler':{'jump_shot_pct':63.,'isolation_ppp':.99,'catchshoot_fga_pg':4.6,'catchshoot_fg_pct':34.},
'Robin Benzing':{'jump_shot_pct':63.,'spotup_poss_pct':39.},
'Chris Singleton':{'jump_shot_pct':56.,'overall_ppp':.86,'turnover_pct':14.2,'transition_poss_pg':3.,'transition_ppp':.905,'pullup_fga_pg':1.5,'pullup_fg_pct':29.,'catchshoot_fg_pct':43.,'catchshoot_pps':1.28},
'Marcus Morris':{'poss_pg':16.4,'overall_ppp':1.12,'turnover_pct':10.5,'post_ppp':1.18,'jump_pps':.96,'jump_fg_pct':38.,'pullup_fga_pg':.8,'pullup_fg_pct':42.},
'Jan Vesely':{'poss_pg':10.,'isolation_poss_pct':2.8,'turnover_pct':15.,'spotup_poss_pct':25.,'jump_pps':.78,'rim_fg_pct':74.,'free_throw_poss_pct':19.4},
'Chandler Parsons':{'spotup_poss_pct':26.2},
'Justin Harper':{'spotup_poss_pct':25.5},
'Tobias Harris':{'halfcourt_turnover_pct':10.2,'isolation_ppp':.486,'jump_ppp':.725,'jump_fg_pct':27.5},
'Jimmy Butler':{'catchshoot_fg_pct':36.},
}}
# Positive-only observations: the announced camp roster explicitly had two
# unresolved slots, so absence is not evidence for a zero feature.
camp={
'camp_invited':'''Mohamed Abukar|Mario Boggan|Craig Bradshaw|Aaron Brooks|Bobby Brown|Russell Carter|Coleman Collins|Daequan Cook|Ryvon Covile|Jermareo Davidson|Justin Doellman|Zabian Dowdell|Jared Dudley|Rashaun Freeman|Aaron Gray|Caleb Green|Taurean Green|Brandon Heath|Herbert Hill|Quinton Hosley|James Hughes|Jeremy Hunt|Ekene Ibekwe|Dominic James|Trey Johnson|Joseph Jones|Rashad Jones-Jennings|Jared Jordan|Coby Karl|Antanas Kavaliauskas|Marcelus Kemp|Carl Landry|Stephane Lasme|Marko Lekic|Ron Lewis|Cartier Martin|James Mays|Dominic McGuire|Sammy Mejia|Brad Newley|Demetris Nichols|Ivan Radenovic|J.R. Reynolds|Chris Richard|Dustin Salisbery|Blake Schilb|Renaldas Seibutis|Ramon Sessions|Mustafa Shakur|Sean Singletary|D.J. Strawberry|Curtis Sumpter|Sun Yue|Jamaal Tatum|Reyshawn Terry|Anthony Tolliver|Ali Traore|Kyle Visser|Darryl Watkins|Major Wingate|DaShaun Wood|Avis Wyatt''',
'physical_only_invited':'''Corey Brewer|Mike Conley Jr.|Javaris Crittenton|Kevin Durant|Jeff Green|Spencer Hawes|Al Horford|Acie Law|Josh McRoberts|Joakim Noah|Greg Oden|Jason Smith|Rodney Stuckey|Al Thornton|Brandan Wright|Julian Wright|Yi Jianlian|Nick Young|Thaddeus Young''',
'media_invited':'''Corey Brewer|Mike Conley Jr.|Kevin Durant|Jeff Green|Spencer Hawes|Al Horford|Acie Law|Joakim Noah|Greg Oden|Al Thornton|Brandan Wright|Julian Wright'''}
raw['dx2007camp']={}
for field,names in camp.items():
 for name in names.split('|'):raw['dx2007camp'].setdefault(name,{})[field]=1.
sources['dx2009guards']={'url':'https://www.draftexpress.com/article/Situational-Statistics-This-Years-Point-Guard-Crop-3209/','published_date':'2009-05-08','title':'Situational Statistics: This Year’s Point Guard Crop','body_section':'Findings through Feedback; no profile sidebars','body_verified':True,'date_verified':True,'primary_publisher':'DraftExpress','underlying_stat_provider':'Synergy Sports Technology'}
raw['dx2009guards']={
'Ty Lawson':{'overall_ppp':1.13,'pullup_fg_pct':47.,'catchshoot_fg_pct':48.,'transition_poss_pct':38.6,'transition_ppp':1.2,'spotup_ppp':1.2,'pickroll_ppp':1.19,'isolation_ppp':1.,'halfcourt_turnover_pct':13.8},
'Ricky Rubio':{'finish_ppp':1.11,'pullup_fgm_total':5.,'pullup_fga_total':25.,'catchshoot_poss_pg':1.1,'catchshoot_fg_pct':41.,'pickroll_poss_pct':27.,'poss_pg':9.,'halfcourt_turnover_pct':28.5},
'Brandon Jennings':{'poss_pg':7.6,'overall_ppp':.77,'pullup_fga_pg':2.1,'pullup_fg_pct':21.,'halfcourt_shots_fouled_pct':6.2,'spotup_ppp':1.07,'open_catchshoot_ppp':1.39,'halfcourt_turnover_pct':15.2,'scoring_poss_pct':29.7},
'Tyreke Evans':{'finish_poss_pg':8.8,'finish_ppp':1.14,'overall_ppp':.88,'open_catchshoot_ppp':.86,'pullup_ppp':.69,'isolation_ppp':.54},
'Stephen Curry':{'poss_pg':31.9,'overall_ppp':.94,'catchshoot_fga_pg':5.4,'guarded_catchshoot_ppp':1.15,'open_catchshoot_ppp':1.33,'pullup_fga_pg':11.6,'spotup_poss_pct':8.9,'transition_fg_pct':41.,'pickroll_ppp':1.3,'offscreen_poss_pg':2.6},
'Jrue Holiday':{'overall_ppp':.86,'poss_pg':9.7,'finish_ppp':1.2,'transition_ppp':1.34,'catchshoot_fg_pct':28.,'pullup_ppp':.75,'spotup_poss_pct':27.8},
'Jonny Flynn':{'finish_poss_pg':8.8,'open_catchshoot_ppp':1.24,'pullup_ppp':.94,'isolation_poss_pg':4.3,'isolation_fg_pct':41.,'pickroll_ppp':.84},
'Darren Collison':{'overall_ppp':1.02,'finish_ppp':1.26,'pullup_ppp':.99,'isolation_ppp':1.02,'pickroll_ppp':1.14},
'Eric Maynor':{'poss_pg':21.2,'overall_ppp':.99,'finish_poss_pg':8.,'finish_ppp':1.12,'isolation_ppp':1.01},
'Nick Calathes':{'finish_ppp':1.26,'turnover_pct':19.,'spotup_ppp':1.17},
'Toney Douglas':{'poss_pg':20.7,'overall_ppp':1.04,'finish_ppp':1.22,'open_catchshoot_ppp':1.41,'pullup_ppp':1.,'offscreen_ppp':1.23,'spotup_ppp':1.14,'isolation_ppp':.85,'halfcourt_turnover_pct':9.7,'pickroll_poss_pg':5.3},
'Lester Hudson':{'poss_pg':28.},
'Sergio Llull':{'open_catchshoot_ppp':1.81,'pickroll_ppp':.88,'finish_poss_pg':2.7,'spotup_ppp':1.31},
'Aaron Jackson':{'rim_fg_pct':64.,'finish_poss_pg':8.7,'catchshoot_fga_pg':1.6},
}
# Rule-based extraction of the archived representation table, excluding every
# sidebar and unrelated table. Source spellings are preserved (not hindsight-fixed).
agent_html=(R/'private/dx2008agents.html').read_text(errors='replace')
agent_table=re.search(r'<table class=article>(.*?)</table>',agent_html,re.S).group(1)
agent_rows=[]
for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',agent_table,re.I|re.S):
 cells=[html.unescape(re.sub('<[^>]+>','',c)).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>',tr,re.I|re.S)]
 if len(cells)==3:agent_rows.append(cells)
agent_counts=collections.Counter(a.strip() for _,_,a in agent_rows if a.strip() not in ['?','Testing waters','Withdrawn',''])
raw['dx2008agents']={}
for name,cls,agent in agent_rows:
 named=agent in agent_counts
 raw['dx2008agents'][name]={'agent_named_in_listing':float(named),'listed_testing_waters':float(agent=='Testing waters'),'listed_withdrawn':float(agent=='Withdrawn')}
 if named:raw['dx2008agents'][name]['same_agent_listed_client_count']=float(agent_counts[agent])
sources['dx2008agents']={'url':'https://www.draftexpress.com/article/2008-NBA-Draft-Prospects-Agent-Listings-2684/','published_date':'2008-05-08','last_updated_date':'2008-06-05','title':'2008 NBA Draft Prospects Agent Listings','body_section':'table class=article only; three cells player/class/agent','body_verified':True,'date_verified':True,'primary_publisher':'DraftExpress','underlying_stat_provider':'Original reporting of representation status'}
rows=[];unmatched=[]
for sid,byplayer in raw.items():
 src=sources[sid]
 for name,stats in byplayer.items():
  found=[p for p in lookup[norm(name)] if int(src['published_date'][:4])==p['draft_year']]
  if len(found)!=1:
   unmatched.append({'source_id':sid,'name':name,'reason':'No unique exact normalized name in same-year cohort','candidate_count':len(found)});continue
  p=found[0]
  assert src['published_date']<p['draft_date']
  for metric,value in stats.items():
   rows.append({'pid':p['pid'],'draft_year':p['draft_year'],'source_id':sid,'source_date':src['published_date'],'draft_date':p['draft_date'],'metric':'report_'+metric,'value':value,'publisher_date_verified':True,'body_fact_verified':True,'archive_snapshot_verified':False,'feature_eligible':False,'quarantine_reason':'No pre-draft archived body captured; sparse cohort coverage requires development-only pilot registration'})
for sid,src in sources.items():
 src.update({'retrieved_at':'2026-09-06','retrieval_method':'Web tool primary-publisher indexed body; direct HTTP returned404 for sampled canonical/AMP URLs','archive_snapshot_verified':False,'feature_eligible':False,'no_copyrighted_article_body_stored':True,'source_id':sid})
(R/'sources.json').write_text(json.dumps(sources,indent=2))
(R/'unmatched_identity.json').write_text(json.dumps(unmatched,indent=2))
with (R/'pilot_observations_quarantined.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
# Sparse matrix is deliberately named quarantined and must not be auto-ingested.
wide={}
for r in rows:
 d=wide.setdefault(r['pid'],{'pid':r['pid'],'draft_year':r['draft_year']});assert r['metric'] not in d;d[r['metric']]=r['value']
columns=['pid','draft_year']+sorted({r['metric'] for r in rows})
with (R/'pilot_features_quarantined.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(wide.values())
summary={'observations':len(rows),'players':len(wide),'candidate_metrics':len(columns)-2,'eligible_model_rows':0,'date_and_body_verified_rows':len(rows),'per_year':{str(y):len([p for p in wide.values() if p['draft_year']==y]) for y in sorted({p['draft_year'] for p in wide.values()})},'unmatched_identity_records':len(unmatched),'reason':'Factual pilot extracted; archival authenticity and broader coverage still gate training integration','excluded_conflict':{'player':'Damion James','metric':'finish_ppp','reason':'Same article reports both1.25 and1.2; omitted rather than choosing'}}
summary['artifact_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in R.glob('*.csv')}
(R/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))

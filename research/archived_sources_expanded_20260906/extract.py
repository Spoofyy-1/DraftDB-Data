"""Conservative, reproducible extraction from pre-draft archived article bodies.
No embeddings, LLM grades, career facts, pick order or outcomes.
"""
from pathlib import Path
import json,re,csv,collections,unicodedata,hashlib
R=Path(__file__).parent
players=json.load(open(R.parents[1]/'collectors/players.json'))
def norm(s):return ''.join(c for c in unicodedata.normalize('NFKD',s).lower() if c.isalnum())
def namepat(s):
 tokens=re.findall(r'[a-z0-9]+',unicodedata.normalize('NFKD',s).lower())
 if tokens[-1] in ['jr','sr']:tokens=tokens[:-1]
 return re.compile(r'\b'+r'[\W_]*'.join(map(re.escape,tokens))+r'(?:[\W_]*(?:jr|sr))?\b',re.I)
patterns={p['pid']:namepat(p['name']) for p in players}
lexicons={
'finishing':r'\b(?:finish(?:er|ers|ing|es)?|rim|basket|dunk(?:s|ing)?|layups?|lobs?)\b',
'creation':r'\b(?:creat(?:e|es|ing|ion|or)|isolations?|dribbl(?:e|es|ing)|penetrat\w*)\b',
'passing':r'\b(?:pass(?:es|er|ers|ing)?|playmak\w*|assists?|distribut\w*)\b',
'shooting':r'\b(?:shoot(?:er|ers|ing)?|jump(?:er|ers|shot|shots)?|perimeter|threes?)\b',
'defense':r'\b(?:defen\w*|steals?|blocks?|rotat\w*)\b',
'rebounding':r'\b(?:rebounds?|rebounding|putbacks?|boards?)\b',
'athleticism':r'\b(?:athlet\w*|explos\w*|quick\w*|speed|leap\w*)\b',
'strength':r'\b(?:strength|strong|powerful|physic\w*|frame|contact)\b',
'length':r'\b(?:wingspan|length|long|tall|height|size)\b',
'decisions':r'\b(?:decision\w*|turnovers?|mistakes?|disciplin\w*|selection)\b',
'effort':r'\b(?:motor|effort|hustle|energy|work.ethic|competi\w*)\b',
'development':r'\b(?:improv\w*|develop\w*|raw|potential|upside|matur\w*)\b',
'injury':r'\b(?:injur\w*|surgery|surgeries|injured|wrist|knee|ankle|back.pain)\b',
'limitations':r'\b(?:struggl\w*|weak\w*|poor|limited|limitation\w*|inconsisten\w*)\b',
'efficiency':r'\b(?:efficient|efficiency|effective|productive|productivity)\b',
'pickroll':r'\bpick[ -]and[ -]roll\b',
'catchshoot':r'\bcatch[ -]and[ -]shoot\b',
'pullup':r'\bpull[ -]up\b',
}
play_patterns={
 'halfcourt':r'half[ -]?court','transition':r'transition|fast[ -]break','isolation':r'isolation|one[ -]on[ -]one','spotup':r'spot[ -]?up','post':r'post[ -]?up|back[ -]to[ -]the[ -]basket|back to the basket|post scorer','offscreen':r'off[ -]screen|off (?:of )?screens','catchshoot':r'catch[ -]and[ -]shoot|off the catch','pullup':r'pull[ -]?up|off[ -]the[ -]dribble','pickroll':r'pick[ -]and[ -]roll','finish':r'finish\w*|at the rim|around the rim|around the basket','jump':r'jump[ -]?shot|jumpers?|jump[ -]shoot',
}
valuepat=re.compile(r'(?P<v>\d+(?:\.\d+)?|\.\d+)\s*(?P<unit>PPP|PPS|points?\s+per[ -]possessions?|points?\s+per[ -]shots?|possessions?\s+per[ -]game)',re.I)
records=[];sections=[];unresolved=[];numeric_debug=[]
for file in sorted(R.glob('dx*.json')):
 d=json.load(open(file))
 if not d.get('feature_eligible'):continue
 body=(R/'private'/f'{file.stem}.body.txt').read_text();year=d['draft_year'];cohort=[p for p in players if p['draft_year']==year]
 if year<=2010:
  assert 'Findings' in body
  body=body[body.index('Findings'):]
 article_html=(R/'private'/f'{file.stem}.body.html').read_text()
 linked_names=set(re.sub('<[^>]+>','',m).strip() for m in re.findall(r'<a\s+href=["\']?/profile/[^>]+>(.*?)</a>',article_html,re.S|re.I))
 linked_patterns={n:namepat(n) for n in linked_names if n and len(n.split())>=2}
 blocks=re.split(r'(?:^|\n)\s*[-•]\s*',body)
 for i,b in enumerate(blocks[1:],1):
  b=' '.join(b.split());heads=[]
  for source_name,pattern in linked_patterns.items():
   m=pattern.search(b[:500])
   if m:heads.append((m.start(),m.end(),source_name))
  heads.sort(key=lambda x:x[0])
  if not heads:continue
  chosen=heads[0];pos,end,source_name=chosen
  # The early header must name one subject. Comparisons or paired subjects fail closed.
  if len(heads)>1 and heads[1][0]-end<65:
   unresolved.append({'source_id':d['source_id'],'section':i,'reason':'multiple linked header subjects','source_names':[x[2] for x in heads]});continue
  matches=[p for p in cohort if patterns[p['pid']].fullmatch(source_name)]
  if len(matches)!=1:continue
  p=matches[0]
  if pos>400:continue
  wc=len(re.findall(r'\b\w+\b',b))
  if wc<30:continue
  sid=f"{d['source_id']}:section{i}"
  common={'pid':p['pid'],'draft_year':year,'source_id':d['source_id'],'section_id':sid,'publication_date':d['publication_date'],'capture_utc':d['capture_utc'],'source_url':d['source']['original'],'archive_url':d['archive_url'],'body_sha256':d['body_sha256'],'section_sha256':hashlib.sha256(b.encode()).hexdigest(),'feature_eligible':True}
  sections.append(common|{'word_count':wc,'subject_match':'unique normalized name in same-cohort section heading'})
  records.append(common|{'metric':'report_text_words','value':wc,'unit':'count'})
  for key,pattern in lexicons.items():
   n=len(re.findall(pattern,b,re.I));records.append(common|{'metric':f'report_text_{key}_per1k','value':1000*n/wc,'unit':'literal matched terms per 1000 words; not a player grade'})
  # Numeric facts use explicit units and one explicit play type within the clause.
  # Reject clauses containing another player name, mixed play types, rankings, or comparisons.
  clauses=re.split(r'(?<=[.!?])\s+(?=[A-Z])|;|\bbut\b|\bwhile\b',b)
  for clause in clauses:
   if any(q['pid']!=p['pid'] and patterns[q['pid']].search(clause) for q in players):continue
   for match in valuepat.finditer(clause):
    v=float(match['v']);unit=match['unit'].lower();context=clause[max(0,match.start()-100):min(len(clause),match.end()+100)]
    plays=[name for name,pat in play_patterns.items() if re.search(pat,context,re.I)]
    # Catch-and-shoot/pull-up are subclasses of generic jump shots.
    if 'jump' in plays and ('catchshoot' in plays or 'pullup' in plays):plays.remove('jump')
    if 'halfcourt' in plays and len(plays)>1:plays.remove('halfcourt')
    if len(plays)>1:continue
    play=plays[0] if plays else 'overall' if re.search('overall|usage',context,re.I) else None
    if play is None:continue
    if unit.startswith('possession'):
     if not 0<v<40:continue
     metric='poss_pg' if play=='overall' else play+'_poss_pg';measure='possessions per game'
    else:
     if not 0<v<3:continue
     den='pps' if unit=='pps' or re.search(r'per[ -]shots?',unit) else 'ppp'
     metric=play+'_'+den;measure='points per shot' if den=='pps' else 'points per possession'
    row=common|{'metric':'report_'+metric,'value':v,'unit':measure}
    records.append(row);numeric_debug.append(row|{'private_context':context})
# Repeated or conflicting facts within one source/player/metric are not averaged.
groups=collections.defaultdict(list)
for row in records:groups[(row['pid'],row['metric'])].append(row)
accepted=[];conflicts=[]
for key,items in groups.items():
 if len(items)==1:accepted+=items
 elif len({r['value'] for r in items})==1:accepted.append(items[0])
 else:conflicts.append({'pid':key[0],'metric':key[1],'values':[r['value'] for r in items],'source_ids':[r['source_id'] for r in items]})
cols=list(accepted[0]) if accepted else []
with (R/'observations_candidate.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(accepted)
(R/'sections.json').write_text(json.dumps(sections,indent=2))
(R/'unresolved_sections.json').write_text(json.dumps(unresolved,indent=2))
(R/'numeric_conflicts.json').write_text(json.dumps(conflicts,indent=2))
(R/'private/numeric_candidates.json').write_text(json.dumps(numeric_debug,indent=2))
(R/'extraction_rules.json').write_text(json.dumps({'lexicons':lexicons,'play_patterns':play_patterns,'numeric_rule':'Explicit number+PPP/PPS/points-per-unit in one unambiguous named-player clause; review numeric candidates before promotion','text_rule':'literal predefined term frequency in dated archived subject section; no semantic score'},indent=2))
print(json.dumps({'articles':len(set(r['source_id'] for r in sections)),'sections':len(sections),'players':len(set(r['pid'] for r in sections)),'per_year':dict(collections.Counter(r['draft_year'] for r in sections)),'candidate_observations':len(accepted),'numeric_candidates':len(numeric_debug),'conflicts':len(conflicts)},indent=2))

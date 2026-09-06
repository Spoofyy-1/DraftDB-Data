"""Build pid-keyed patches (no names) for the handoff dataset:
 intl_patch_{train,test}.csv : corrected/inserted international block (latest pre-draft season) + new strength/two-season columns
 col_patch_{train,test}.csv  : basic college line for drafted players who had no college block at all
Merge rule: replace the dataset's intl block only when the Wikipedia latest pre-draft season is NEWER than the season the dataset used."""
import csv,glob,re,json,collections
H="/Users/kennakao/Downloads/nba_redraft_handoff"; D="/Users/kennakao/nba/datarebuild"
names={r["pid"]:r["player_name"] for r in csv.DictReader(open(f"{H}/identity_KEEP_SEPARATE/tabular_names.csv"))}
I2={r["pid"]:r for r in csv.DictReader(open(f"{D}/intl2_features.csv"))}
def fl(v):
    try:
        x=float(v); return x
    except: return None
LEVEL_STR={4:1.0,3:0.72,2:0.85,1:0.3}
rows=[]
for r in csv.DictReader(open(f"{H}/data/train_2000_2018.csv")): r["_split"]="train"; rows.append(r)
for fp in sorted(glob.glob(f"{H}/data/tests/test_*_inputs.csv")):
    yr=re.search(r"test_(\d{4})",fp).group(1)
    for r in csv.DictReader(open(fp)): r["_split"]="test"; r.setdefault("draft_year",yr); rows.append(r)
stats=collections.Counter(); ipatch={"train":[],"test":[]}; cpatch={"train":[],"test":[]}; rep=[]
for r in rows:
    pid=r["pid"]; dy=int(float(r["draft_year"])); sp=r["_split"]; i2=I2.get(pid); dage=fl(r.get("bio_age_at_draft"))
    has_col=fl(r.get("col_gp")) is not None; ds_gp=fl(r.get("intl_gp")); has_ds=ds_gp is not None
    wiki_L=int(float(i2["intl2_season_end"])) if i2 and i2.get("intl2_season_end") else None
    lvl=fl(r.get("intl_level")); new={}
    # ---- estimate the season the dataset's block came from
    ds_L=None
    if has_ds:
        ia=fl(r.get("intl_age"))
        if ia is not None and dage is not None: ds_L=dy-max(0,min(5,round(dage-ia-0.35)))
        elif i2 and i2.get("intl2_seasons_gp"):
            for part in i2["intl2_seasons_gp"].split("|"):
                e,tot,singles=part.split(":"); 
                if abs(float(tot)-ds_gp)<=1 or any(abs(float(g)-ds_gp)<=1 for g in singles.split("/")): ds_L=int(e); break
        if ds_L is None: ds_L=dy
    action="keep"
    if not has_col and i2 and wiki_L and (dy-wiki_L)<=2:
        if not has_ds: action="insert"
        else:
            ds_min=fl(r.get("intl_minutes")) or 0; w_min=fl(i2.get("intl2_minutes")) or 0
            youth_only=(lvl==1 and fl(i2.get("intl2_level")) and fl(i2.get("intl2_level"))>=2)
            # newer season (with a sample at least 60% of the old one, unless 2+ seasons newer), or a youth-only block replaced by a real pro season
            if youth_only or (wiki_L>ds_L and (w_min>=0.6*ds_min or wiki_L-ds_L>=2)): action="replace"
    if action in("insert","replace"):
        g=lambda k: fl(i2.get(k))
        new.update(intl_gp=g("intl2_gp"),intl_minutes=g("intl2_minutes"),intl_mpg=g("intl2_mpg"),intl_pts36=g("intl2_pts36"),intl_reb36=g("intl2_reb36"),intl_ast36=g("intl2_ast36"),
                   intl_stl36=g("intl2_stl36"),intl_blk36=g("intl2_blk36"),intl_ft_pct=g("intl2_ft_pct"),intl_fg3_pct=g("intl2_fg3_pct"),intl_age=g("intl2_age"),
                   intl_level=g("intl2_level"),intl_last_level=g("intl2_level"),intl_n_seasons=g("intl2_n_seasons"),intl_best_level=max(lvl or 0,g("intl2_career_best_level") or 0) or None)
        if g("intl2_el_gp"):
            new.update(intl_ts_pct=g("intl2_el_ts"),intl_efg_pct=g("intl2_el_efg"),intl_fg3ar=g("intl2_el_p3ar"),intl_ftar=g("intl2_el_ftr"),intl_orb_pct=g("intl2_el_orb_pct"),intl_drb_pct=g("intl2_el_drb_pct"),
                       intl_impact=(g("intl2_el_pir36") or 0)*(g("intl2_el_mpg") or 0)/36 if g("intl2_el_pir36") is not None else None); src=2
        else:
            for k in("intl_ts_pct","intl_efg_pct","intl_usg_pct","intl_ast_pct","intl_tov_pct","intl_orb_pct","intl_drb_pct","intl_fg3ar","intl_ftar","intl_impact"): new[k]=None
            src=1
        if g("intl2_youth_pts36") is not None and fl(r.get("intl_youth_pts36")) is None: new.update(intl_youth_pts36=g("intl2_youth_pts36"),intl_youth_n=g("intl2_youth_n"))
        strength=g("intl2_strength"); pts=g("intl2_pts36"); gap=dy-wiki_L
        new.update(intl_two_pts36=g("intl2_two_pts36"),intl_two_minutes=g("intl2_two_minutes"),intl_prev_pts36=g("intl2_prev_pts36"))
        stats[(sp,action)]+=1; rep.append((sp,dy,names.get(pid,pid),action,ds_L,wiki_L,ds_gp,new["intl_gp"],round(new["intl_pts36"] or 0,1),strength))
    else:
        src=0
        if has_ds:
            strength=LEVEL_STR.get(int(lvl),0.5) if lvl is not None else 0.5; pts=fl(r.get("intl_pts36")); gap=dy-ds_L
            if i2 and wiki_L==ds_L:  # same season on both sides: use the finer league strength + two-season context
                strength=fl(i2.get("intl2_strength")) or strength
                new.update(intl_two_pts36=fl(i2.get("intl2_two_pts36")),intl_two_minutes=fl(i2.get("intl2_two_minutes")),intl_prev_pts36=fl(i2.get("intl2_prev_pts36")))
            stats[(sp,"keep")]+=1
        else: strength=None; pts=None; gap=None
    if has_ds or new:
        new.update(intl_lg_strength=strength,intl_lg_adj_pts36=(pts*strength) if (pts is not None and strength is not None) else None,intl_season_gap=gap,intl_src=src)
        ipatch[sp].append(dict(pid=pid,**{k:(round(v,4) if isinstance(v,float) else v) for k,v in new.items()}))
    # ---- college basic fill
    if not has_col and i2 and i2.get("colw_gp") and fl(i2["colw_gp"])>=5 and int(float(i2["colw_season_end"]))>=dy-1:
        c=lambda k: fl(i2.get(k)); ce=int(float(i2["colw_season_end"]))
        cpatch[sp].append(dict(pid=pid,col_gp=c("colw_gp"),col_mpg=c("colw_mpg"),col_pts36=c("colw_pts36"),col_reb36=c("colw_reb36"),col_ast36=c("colw_ast36"),col_stl36=c("colw_stl36"),col_blk36=c("colw_blk36"),
                               col_ft_pct=c("colw_ft_pct"),col_fg3_pct=c("colw_fg3_pct"),col_n_seasons=c("colw_n_seasons"),col_final_is_current=float(ce==dy),col_age=(round(dage-(dy-ce)-0.15,2) if dage else None),col_basic_fill=1))
        stats[(sp,"college_fill")]+=1; rep.append((sp,dy,names.get(pid,pid),"college_fill",None,ce,None,c("colw_gp"),round(c("colw_pts36") or 0,1),None))
for sp in("train","test"):
    for nm,P in(("intl_patch",ipatch),("col_patch",cpatch)):
        cols=["pid"]+sorted({k for x in P[sp] for k in x if k!="pid"})
        with open(f"{D}/{nm}_{sp}.csv","w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); [w.writerow({k:("NA" if (k in x and x[k] is None) else x.get(k,"")) for k in cols}) for x in P[sp]]
print("stats:",dict(stats))
with open(f"{D}/patch_report_LOCAL.txt","w") as f:
    for x in sorted(rep,key=lambda x:(x[0],-x[1],x[2])): f.write("\t".join(str(v) for v in x)+"\n")
print("\nREPLACED / INSERTED / COLLEGE-FILLED (test classes):")
for x in sorted([x for x in rep if x[0]=="test"],key=lambda x:(-x[1],x[3],x[2])): print(f"  {x[1]} {x[2][:24]:24s} {x[3]:12s} ds_season {x[4]} -> wiki {x[5]}  gp {x[6]} -> {x[7]}  pts36 {x[8]}  strength {x[9]}")
print("\nREPLACED / INSERTED (train):",[(x[1],x[2]) for x in rep if x[0]=="train" and x[3]!="college_fill"])
print("college fills (train):",[(x[1],x[2]) for x in rep if x[0]=="train" and x[3]=="college_fill"])
w=[x for x in ipatch["test"] if x["pid"]=="P144ed94c77"]; print("\nWEMBY patch:",w)

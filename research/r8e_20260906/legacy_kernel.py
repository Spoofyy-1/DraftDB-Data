"""Model-only legacy reproduction. No vault, training loader, or test loader."""
import os,types
import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.stats import norm
_norm=norm
S=[f"y_s{i}_war" for i in range(1,6)]
HW={"uniform":[1]*5,"cum3":[1,1,1,0,0],"cum4":[1,1,1,1,0],"disc85":[.85**i for i in range(5)],"disc70":[.7**i for i in range(5)],"front":[1,.8,.6,.4,.2]}
THIN={"none":0.,"mild":.15,"strong":.35};ANCH={"none":0,"top1":1,"top3":3}
GLTB=[0.];GLS={};MU=[0.]*5;SD=[1.]*5

H_SOURCE='def audit_features(cols):\n    bad=[c for c in cols if c.startswith(BANNED_PREFIX) or c in BANNED_EXACT]\n    if bad: raise AssertionError(f"G1/G2 VIOLATION - leaked columns: {bad[:6]}")\n\ndef fit_prior(tr_raw):                                   # G4: priors from training rows only\n    return ({c:tr_raw[c].mean() for c in SHRINK},\n            tr_raw[COVER].notna().mean(axis=1).quantile([0.05,0.95]).values)\n\ndef build(d,prior,cq,opts):\n    d=d.copy()\n    if opts.get("shrink",True):\n        mins=pd.to_numeric(d.get("col_minutes_total"),errors="coerce")\n        gp=pd.to_numeric(d.get("col_gp"),errors="coerce"); mins=mins.fillna(gp*20.0)\n        r=(mins/(mins+opts.get("M",400.0))).clip(0,1).fillna(0.0); d["sample_reliability"]=r\n        for c in SHRINK: d["shr_"+c]=r*pd.to_numeric(d[c],errors="coerce").fillna(prior[c])+(1-r)*prior[c]\n    if opts.get("intl",False):\n        lv=pd.to_numeric(d.get("intl_level"),errors="coerce"); d["intl_strength"]=lv.map(LEVEL)\n        for c in INTL_VOL:\n            if c in d: d["adj_"+c]=pd.to_numeric(d[c],errors="coerce")*d["intl_strength"]\n    if opts.get("cov",False):\n        cov=d[COVER].notna().mean(axis=1); d["feat_coverage"]=((cov-cq[0])/(cq[1]-cq[0])).clip(0,1)\n    return d\n\ndef cols_for(opts):\n    c=list(FEATS)\n    if opts.get("shrink",True): c+=["sample_reliability"]+["shr_"+x for x in SHRINK]\n    if opts.get("intl",False):  c+=["intl_strength"]+["adj_"+x for x in INTL_VOL]\n    if opts.get("cov",False):   c+=["feat_coverage"]\n    if opts.get("el",False):    c+=EL_COLS\n    if opts.get("wk",False):    c+=WK_COLS\n    audit_features(c); return c\n\ndef predict(model,Xtr,ytr,Xte,cfg):\n    if model=="xgb":\n        kw=dict(XCFG); kw["monotone_constraints"]={"bio_age_at_draft":-1} if cfg.get("mono",True) else {}\n        if cfg.get("max_depth"): kw["max_depth"]=int(cfg["max_depth"])\n        if cfg.get("mono_extra"): kw["monotone_constraints"]={**kw["monotone_constraints"],**{c:1 for c in cfg["mono_extra"] if c in Xtr.columns}}\n        if cfg.get("q"): kw["objective"]="reg:quantileerror"; kw["quantile_alpha"]=float(cfg["q"])\n        if cfg.get("ixc"): kw["interaction_constraints"]=str(cfg["ixc"])\n        return np.mean([xgb.XGBRegressor(**kw,random_state=s).fit(Xtr,ytr,sample_weight=cfg.get("w")).predict(Xte)\n                        for s in cfg.get("seeds",(11,12,13))],axis=0)\n    if model=="xgbrank":\n        kw=dict(XCFG); kw.pop("objective",None); kw["monotone_constraints"]={"bio_age_at_draft":-1} if cfg.get("mono",True) else {}\n        q=np.asarray(cfg["qid"]); o=np.argsort(q,kind="stable"); Xs=Xtr.iloc[o]; ys=np.asarray(ytr)[o]; qs=q[o]; ws=None if cfg.get("w") is None else np.asarray(cfg["w"])[o]\n        return np.mean([xgb.XGBRanker(objective="rank:ndcg",lambdarank_pair_method="topk",lambdarank_num_pair_per_sample=8,**kw,random_state=s).fit(Xs,ys,qid=qs,sample_weight=ws).predict(Xte) for s in cfg.get("seeds",(11,12,13))],axis=0)\n    if model=="pair":                                     # pairwise within-class learner -> Borda score\n        q=np.asarray(cfg["qid"]); rng=np.random.default_rng(int(cfg.get("seeds",(11,))[0])); med=Xtr.median()\n        A=Xtr.fillna(med).fillna(0.0).values.astype(np.float32); Bq=Xte.fillna(med).fillna(0.0).values.astype(np.float32); y=np.asarray(ytr,float); per=int(cfg.get("pair_k",30))\n        P=[]; L=[]\n        for cls in np.unique(q):\n            ix=np.where(q==cls)[0]\n            if len(ix)<4: continue\n            for i in ix:\n                js=rng.choice(ix[ix!=i],size=min(per,len(ix)-1),replace=False); P.append(A[i][None,:]-A[js]); L.append((y[i]>y[js]).astype(int))\n        Xp=np.vstack(P); yp=np.concatenate(L)\n        m=xgb.XGBClassifier(max_depth=int(cfg.get("pair_depth",3)),learning_rate=0.05,n_estimators=int(cfg.get("pair_trees",300)),subsample=0.7,colsample_bytree=0.5,min_child_weight=10,reg_lambda=5.0,n_jobs=3,device=XDEV,tree_method="hist",random_state=int(cfg.get("seeds",(11,))[0])).fit(Xp,yp)\n        n=len(Bq); D=(Bq[:,None,:]-Bq[None,:,:]).reshape(n*n,-1); pr=m.predict_proba(D)[:,1].reshape(n,n); np.fill_diagonal(pr,0.5)\n        return (0.5*(pr+(1-pr.T))).mean(1)\n    if model=="tabicl":\n        from tabicl import TabICLRegressor\n        try: m=TabICLRegressor(device="cuda",n_estimators=int(cfg.get("icl_n",8)),**cfg.get("icl_kwargs",{}))\n        except TypeError: m=TabICLRegressor(device="cuda")\n        m.fit(Xtr.astype(float),ytr); return m.predict(Xte.astype(float))\n    if model=="et":\n        from sklearn.ensemble import ExtraTreesRegressor\n        med=Xtr.median(); A=Xtr.fillna(med).fillna(0.0); Bq=Xte.fillna(med).fillna(0.0)\n        return np.mean([ExtraTreesRegressor(n_estimators=500,min_samples_leaf=3,max_features=0.5,n_jobs=3,random_state=int(s_)).fit(A,ytr,sample_weight=cfg.get("w")).predict(Bq) for s_ in cfg.get("seeds",(11,12,13))],axis=0)\n    if model=="lgbm":\n        import lightgbm as lgb\n        mono=[(-1 if c=="bio_age_at_draft" else 0) for c in Xtr.columns] if cfg.get("mono",True) else None\n        ps=[]\n        for s_ in cfg.get("seeds",(11,12,13)):\n            m=lgb.LGBMRegressor(n_estimators=600,learning_rate=0.03,num_leaves=15,min_child_samples=10,subsample=0.8,subsample_freq=1,colsample_bytree=0.6,reg_lambda=5.0,n_jobs=3,verbose=-1,random_state=int(s_),monotone_constraints=mono)\n            m.fit(Xtr,ytr,sample_weight=cfg.get("w")); ps.append(m.predict(Xte))\n        return np.mean(ps,axis=0)\n    if model=="tabpfn":\n        from tabpfn import TabPFNRegressor\n        m=TabPFNRegressor(device="cuda"); m.fit(Xtr.astype(float),np.asarray(ytr)); return m.predict(Xte.astype(float))\n    if model=="knn":\n        from sklearn.neighbors import KNeighborsRegressor\n        mu=Xtr.mean(); sd=Xtr.std().replace(0,1.0); A=((Xtr-mu)/sd).fillna(0.0); Bq=((Xte-mu)/sd).fillna(0.0)\n        return KNeighborsRegressor(n_neighbors=int(cfg.get("knn_k",15)),weights="distance").fit(A,ytr).predict(Bq)\n    if model=="cat":\n        from catboost import CatBoostRegressor\n        ps=[]\n        for s_ in cfg.get("seeds",(11,)):\n            m=CatBoostRegressor(depth=4,iterations=300,learning_rate=0.06,l2_leaf_reg=5.0,random_seed=int(s_),verbose=0,thread_count=8,allow_writing_files=False)\n            m.fit(Xtr,ytr); ps.append(m.predict(Xte))\n        return np.mean(ps,axis=0)\n    if model=="spline":                                   # smooth non-linear: cubic splines per feature + ridge\n        from sklearn.preprocessing import SplineTransformer\n        from sklearn.linear_model import Ridge\n        mu=Xtr.mean(); sd=Xtr.std().replace(0,1.0); A=((Xtr-mu)/sd).fillna(0.0).clip(-4,4); Bq=((Xte-mu)/sd).fillna(0.0).clip(-4,4)\n        st=SplineTransformer(n_knots=int(cfg.get("spline_knots",5)),degree=3,include_bias=False).fit(A)\n        return Ridge(alpha=float(cfg.get("ridge_alpha",30.0))*3.0).fit(st.transform(A),ytr,sample_weight=cfg.get("w")).predict(st.transform(Bq))\n    if model=="ridge":\n        from sklearn.linear_model import Ridge\n        mu=Xtr.mean(); sd=Xtr.std().replace(0,1.0)\n        A=((Xtr-mu)/sd).fillna(0.0); Bq=((Xte-mu)/sd).fillna(0.0)\n        return Ridge(alpha=float(cfg.get("ridge_alpha",30.0))).fit(A,ytr).predict(Bq)\n    if model=="tabfm":\n        from tabfm import TabFMRegressor, tabfm_v1_0_0_pytorch as tfm\n        if _TFM[0] is None: _TFM[0]=tfm.load(model_type="regression",device="cuda")\n        m=TabFMRegressor(model=_TFM[0]); m.fit(Xtr.astype(float),ytr); return m.predict(Xte.astype(float))\n    if model.startswith("ens:"):\n        rs=[pd.Series(predict(p,Xtr,ytr,Xte,cfg)).rank().values for p in model[4:].split("+")]\n        return np.mean(rs,axis=0)\n    raise ValueError(model)'

def setup(feature_columns):
    global H
    ns=dict(np=np,pd=pd,xgb=xgb,os=os)
    ns.update(FEATS=feature_columns,
              COVER=[c for c in feature_columns if not c.startswith(("wp_","txt_","traj_","tv_","mock_","prog_","misc_","ts_","gt_","rsci_","cmb_","ctx_","f50_"))],
              BANNED_PREFIX=("y_",),BANNED_EXACT={"actual_pick","actual_round","pid","draft_year","was_drafted","declared_only","split","source_season"},
              SHRINK=[c for c in ["col_ts_pct","col_efg_pct","col_fg2_pct","col_fg3_pct","col_ft_pct","col_ast_pct","col_stl_pct","col_blk_pct","col_orb_pct","col_drb_pct","col_tov_pct","col_usg_pct","col_ortg","col_drtg","col_impact","col_pts36","col_reb36","col_ast36","col_stl36","col_blk36"] if c in feature_columns],
              LEVEL={4:1.45,3:1.20,2:.95,1:.60},INTL_VOL=["intl_pts36","intl_reb36","intl_ast36","intl_stl36","intl_blk36"],
              EL_COLS=[],WK_COLS=[],XDEV="cuda",_TFM=[None],
              XCFG=dict(objective="reg:squarederror",max_depth=3,learning_rate=.02,n_estimators=800,subsample=.7,device="cuda",tree_method="hist",colsample_bytree=.5,min_child_weight=8,reg_lambda=5.,reg_alpha=1.,n_jobs=3))
    exec(H_SOURCE,ns)
    H=types.SimpleNamespace(**ns)
    H.audit_features(feature_columns)

def label(df,spec,k=5):
    hw,norm_,clip,lab=spec; X=np.stack([df[S[i]].fillna(0).values for i in range(k)],1).astype(float)
    if norm_=="zseason": X=(X-np.array(MU[:k]))/np.array(SD[:k])
    v=np.sort(X,1)[:,-2:].mean(1) if hw=="top2" else (X*np.array(HW[hw][:k])).sum(1)
    if GLTB[0]>0 and GLS: v=v+GLTB[0]*np.array([sum(GLS.get(p,[0.0]*5)[:k]) for p in df.pid.values])
    if clip=="clip40": v=np.clip(v,-40,40)
    if clip=="log1p": v=np.sign(v)*np.log1p(np.abs(v))
    o=np.zeros(len(df))
    for y in df.draft_year.unique():
        m=(df.draft_year==y).values; r=pd.Series(v[m]).rank(pct=True).values
        o[m]=norm.ppf(np.clip((r*len(r)-0.5)/len(r),0.01,0.99)) if lab=="gaussrank" else r
    return o

def specs(g):
    own=(g["hw"],"none",g["clip"],g["label"]); out=[own]
    if g["labelmix"] in("mix2","mix3"): out.append(("uniform","none","none","rank"))
    if g["labelmix"]=="mix3": out.append(("uniform","zseason","none","gaussrank"))
    return out

def n_(d,c): return pd.to_numeric(d.get(c),errors="coerce")

def z_(s,mu,sd): return (s-mu)/(sd if sd and sd>0 else 1)

def stats_of(B): return {k:(float(n_(B,c).mean()),float(n_(B,c).std())) for k,c in [("ft","col_ft_pct"),("vol","col_fg3a_per40"),("proj","col_shot_proj_3p"),("age","bio_age_at_draft")]}

def add_feats(B,fx,st):
    B=B.copy(); ft,p3,vol,age,proj=n_(B,"col_ft_pct"),n_(B,"col_fg3_pct"),n_(B,"col_fg3a_per40"),n_(B,"bio_age_at_draft"),n_(B,"col_shot_proj_3p")
    if "shoot" in fx: B["x_ft_vol"]=ft*vol; B["x_proj_vol"]=proj*vol; B["x_ft_gap"]=ft-p3; B["x_shoot_score"]=z_(ft,*st["ft"])+z_(vol,*st["vol"])+z_(proj,*st["proj"])
    if "age" in fx: B["x_age_x_shoot"]=(-z_(age,*st["age"]))*(z_(ft,*st["ft"])+z_(vol,*st["vol"])); B["x_old_shooter"]=((age>=21.5)&(ft>=0.78)&(vol>=4)).astype(float)
    if "prod" in fx:
        ba,bc,usg,ts,blk,ht=n_(B,"col_bpm_pct_age"),n_(B,"col_bpm_pct_class"),n_(B,"col_usg_pct"),n_(B,"col_ts_pct"),n_(B,"col_blk_pct"),n_(B,"bio_height_in")
        B["x_prod_over_age"]=ba-bc; B["x_vol_eff"]=(usg-20)*(ts-54)/100; B["x_rim"]=blk*ht/80; B["x_young_prod"]=(21-age).clip(lower=0)*bc/100; B["x_old_prod"]=(age-21).clip(lower=0)*bc/100
    if "market" in fx:
        mock=n_(B,"cons_mock_consensus_rank"); bpm=n_(B,"col_bpm_pct_class").fillna(n_(B,"intl_lg_adj_pts36").rank(pct=True)*100)
        B["x_young_cons"]=(21-age).clip(lower=0)*(60-mock.clip(upper=60).fillna(60))/60; B["x_cons_vs_prod"]=(1-mock.fillna(75).rank(pct=True))-bpm.fillna(50)/100; B["x_cons_missing"]=mock.isna().astype(float)
    return B

def feat_tx(Btr,Bte,fx,trmeta,temeta,RATE):
    Btr,Bte=Btr.copy(),Bte.copy()
    if "eraz" in fx:
        for B,meta in((Btr,trmeta),(Bte,temeta)):
            gg=B[RATE].groupby(meta["draft_year"].values); B[RATE]=(B[RATE]-gg.transform("mean"))/(gg.transform("std").replace(0,np.nan))
    if "ctx" in fx:   # class-context means (inputs only): lets trees adjust for era drift in absolute stat levels
        for B,meta in((Btr,trmeta),(Bte,temeta)):
            for nm,c in(("fg3a","col_fg3a_per40"),("usg","col_usg_pct"),("age","bio_age_at_draft"),("height","bio_height_in"),("ts","col_ts_pct")):
                B["x_cls_"+nm]=pd.to_numeric(B[c],errors="coerce").groupby(meta["draft_year"].values).transform("mean") if c in B.columns else np.nan
    if "posz" in fx:
        ptr=trmeta["bio_pos_code"].fillna(-1).values; pte=temeta["bio_pos_code"].fillna(-1).values
        for p in np.unique(ptr):
            m=ptr==p; mu=Btr.loc[m,RATE].mean(); sd=Btr.loc[m,RATE].std().replace(0,np.nan); Btr.loc[m,RATE]=(Btr.loc[m,RATE]-mu)/sd
            mt=pte==p
            if mt.any(): Bte.loc[mt,RATE]=(Bte.loc[mt,RATE]-mu)/sd
    return Btr,Bte

def models_of(g): return ["xgb","tabicl"]+(["ridge"] if g["ridge"] else [])+(["knn"] if g.get("knn") else [])+(["cat"] if g.get("cat") else [])+(["et"] if g.get("et") else [])+(["lgbm"] if g.get("lgbm") else [])+(["tabpfn"] if g.get("tabpfn") else [])+(["pair"] if g.get("pair") else [])+(["spline"] if g.get("spline") else [])

def opts_of(g): return dict(shrink=True,intl=bool(g["intl"]),cov=True,M=g["M"],el=bool(g.get("el",0)),wk=bool(g.get("wk",0)))

def cols_of(g,base):
    c=base+(["x_ft_vol","x_proj_vol","x_ft_gap","x_shoot_score"] if "shoot" in g["fx"] else [])+(["x_age_x_shoot","x_old_shooter"] if "age" in g["fx"] else [])+(["x_prod_over_age","x_vol_eff","x_rim","x_young_prod","x_old_prod"] if "prod" in g["fx"] else [])+(["x_young_cons","x_cons_vs_prod","x_cons_missing"] if "market" in g["fx"] else [])+(["x_cls_fg3a","x_cls_usg","x_cls_age","x_cls_height","x_cls_ts"] if "ctx" in g["fx"] else [])
    if g.get("noscout"): c=[x for x in c if not x.startswith("scout_")]
    for _p in ("wp","txt","traj","tv","mock","prog","misc","ts","gt","rsci","cmb"):
        if not g.get(_p,0): c=[x for x in c if not x.startswith(_p+"_")]
    return c

def ixc_groups(cols):
    size=[i for i,c in enumerate(cols) if c.startswith(("bio_height","bio_weight","bio_combine","bio_bmi"))]
    prod=[i for i,c in enumerate(cols) if c.startswith(("col_","intl_","el_","wk_","x_","shr_","adj_"))]
    other=[i for i in range(len(cols)) if i not in size]
    return [sorted(set(size+prod)),sorted(set(other))]

def cfg_of(m,g,cols=None):
    c=dict(seeds=tuple(range(11+int(os.environ.get("SEED_SHIFT","0")),11+int(os.environ.get("SEED_SHIFT","0"))+g["bag"])),mono=(g["mono"]=="on" and "age" not in g["fx"]),icl_n=g["icl_n"],ridge_alpha=g.get("ridge_alpha",30.0),**({"q":0.25} if (m=="xgb" and g["risk"]=="q25") else ({"q":0.75} if (m=="xgb" and g["risk"]=="q75") else {})))
    if m=="xgb" and int(g.get("xgb_depth",3))!=3: c["max_depth"]=int(g["xgb_depth"])
    if m=="xgb" and g.get("mono_prod"): c["mono_extra"]=["col_bpm_pct_class","col_bpm_pct_age","col_impact","col_pts36","col_ts_pct","col_stl_pct","col_blk_pct","intl_pts36","intl_lg_adj_pts36"]
    if m=="xgb" and g.get("ixc") and cols is not None: c["ixc"]=ixc_groups(cols)
    if m=="tabicl":
        kw={"random_state":int(os.environ.get("SEED_SHIFT","0"))}
        if g.get("icl_norm","default")!="default": kw["norm_methods"]=g["icl_norm"]
        if g.get("icl_outlier",4.0)!=4.0: kw["outlier_threshold"]=float(g["icl_outlier"])
        if g.get("icl_shuffle","latin")!="latin": kw["feat_shuffle_method"]=g["icl_shuffle"]
        c["icl_kwargs"]=kw
    return c

def season_label(df,i,k):
    v=df[S[i]].fillna(0).values; o=np.zeros(len(df))
    for y in df.draft_year.unique():
        m=(df.draft_year==y).values; o[m]=pd.Series(v[m]).rank(pct=True).values
    return o

def market_z(df,g):
    """per-class gaussian rank of the market view (real pick for beatpick, final consensus for consres); 0 otherwise"""
    if g.get("beatpick"): base=-pd.to_numeric(df[["pid"]].merge(H.PICKS,on="pid",how="left")["actual_pick"],errors="coerce").fillna(75).values
    elif g.get("consres"): base=-n_(df,"cons_mock_consensus_rank").fillna(75).values
    else: return np.zeros(len(df))
    z=np.zeros(len(df)); yrs=n_(df,"draft_year").fillna(0).values
    for y in np.unique(yrs):
        m=yrs==y; r=pd.Series(base[m]).rank().values; z[m]=_norm.ppf((r-0.5)/m.sum())
    return z

def market_z_test(Bte):
    base=-n_(Bte,"cons_mock_consensus_rank"); r=base.rank().values; n=len(Bte); z=_norm.ppf((np.nan_to_num(r,nan=(n+1)/2)-0.5)/n); return np.where(base.isna().values,0.0,z)

def xgb_member(g,Btr,Bte,cols,yl,cfg,trdf):
    def one(cs,c2,y=yl):
        if g.get("xgb_obj","reg")=="ndcg":
            rel=np.floor(pd.Series(y).rank(pct=True).values*31.999).astype(int); c3=dict(c2); c3["qid"]=n_(trdf,"draft_year").fillna(0).values.astype(int); return H.predict("xgbrank",Btr[cs],rel,Bte[cs],c3)
        if g.get("risk")=="mix":
            a=dict(c2); a["q"]=0.25; b=dict(c2); b["q"]=0.75; return 0.5*(H.predict("xgb",Btr[cs],y,Bte[cs],a)+H.predict("xgb",Btr[cs],y,Bte[cs],b))
        return H.predict("xgb",Btr[cs],y,Bte[cs],c2)
    if g.get("subspace"):
        ps=[]
        for s in range(5):
            rs=np.random.default_rng(100+s); sub=list(rs.choice([c for c in cols if c!="bio_age_at_draft"],size=max(10,int(0.6*len(cols))),replace=False))+(["bio_age_at_draft"] if "bio_age_at_draft" in cols else [])
            ps.append(pd.Series(one(sub,cfg)).rank(pct=True).values)
        p=np.mean(ps,0)
    else: p=one(cols,cfg)
    if g.get("pathsplit"):
        trc=n_(trdf,"col_gp").notna().values; tec=n_(Bte,"col_gp").notna().values; ps=np.array(p,dtype=float)
        for mtr,mte in((trc,tec),(~trc,~tec)):
            if mtr.sum()>=60 and mte.sum()>0:
                c2=dict(cfg)
                if c2.get("w") is not None: c2["w"]=np.asarray(c2["w"])[mtr]
                sub=H.predict("xgb",Btr[cols][mtr],np.asarray(yl)[mtr],Bte[cols][mte],c2); ps[mte]=0.5*ps[mte]+0.5*pd.Series(sub).rank(pct=True).values*(np.nanmax(p)-np.nanmin(p))+np.nanmin(p)
        p=ps
    if g.get("tiersplit"):   # consensus top-15 specialist blended into the top-15 predictions
        trt=(n_(trdf,"cons_mock_consensus_rank").fillna(99).values<=15); tet=(n_(Bte,"cons_mock_consensus_rank").fillna(99).values<=15); ps=np.array(p,dtype=float)
        if trt.sum()>=60 and tet.sum()>0:
            c2=dict(cfg)
            if c2.get("w") is not None: c2["w"]=np.asarray(c2["w"])[trt]
            sub=H.predict("xgb",Btr[cols][trt],np.asarray(yl)[trt],Bte[cols][tet],c2); ps[tet]=0.5*ps[tet]+0.5*pd.Series(sub).rank(pct=True).values*(np.nanmax(p)-np.nanmin(p))+np.nanmin(p)
        p=ps
    return p

def xgb_cfg(g,cols,yl,trdf,Btr):
    cfg=cfg_of("xgb",g,cols); wv=np.ones(len(Btr))
    if g.get("topw",0): wv=wv*(1.0+float(g["topw"])*(pd.Series(yl).rank(pct=True).values**3))
    if g.get("recency",0): wv=wv*(1.0+float(g["recency"])*np.clip((n_(trdf,"draft_year").values-2010)/8.0,0,1))
    if float(g.get("undraft_w",1.0))<1.0: wv=np.where(pd.to_numeric(trdf[["pid"]].merge(H.PICKS,on="pid",how="left")["actual_pick"],errors="coerce").isna().values,float(g["undraft_w"])*wv,wv)
    if float(g.get("midw",0))>0:
        cr=n_(trdf,"cons_mock_consensus_rank").values.astype(float); pk=pd.to_numeric(trdf[["pid"]].merge(H.PICKS,on="pid",how="left")["actual_pick"],errors="coerce").values.astype(float)
        rr=np.where(np.isnan(cr),pk,cr); wv=wv*np.where((rr>=11)&(rr<=40),1.0+float(g["midw"]),1.0)
    if not np.allclose(wv,1.0): cfg["w"]=wv
    return cfg

def member_preds(g,Btr,Bte,cols,trdf,k):
    """dict model -> rank-averaged prediction over the genome's label set."""
    out={}; topk=None
    if g.get("icl_topk",0):
        import xgboost as xgb
        imp=xgb.XGBRegressor(max_depth=3,n_estimators=300,learning_rate=0.05,subsample=0.8,colsample_bytree=0.6,n_jobs=3,device=H.XDEV,tree_method="hist",random_state=11).fit(Btr[cols],label(trdf,specs(g)[0],k)).feature_importances_
        topk=[c for _,c in sorted(zip(imp,cols),reverse=True)[:int(g["icl_topk"])]]
    ctx=np.ones(len(Btr),bool)
    if g.get("icl_ctx","all")=="drafted" and "was_drafted" in trdf.columns: ctx=(pd.to_numeric(trdf["was_drafted"],errors="coerce").fillna(0).values==1)
    if g.get("icl_era"): ctx=ctx&(n_(trdf,"draft_year").values>=n_(trdf,"draft_year").max()-int(g["icl_era"])+1)
    if ctx.sum()<150: ctx=np.ones(len(Btr),bool)
    CI=np.where(ctx)[0]
    if int(g.get("icl_rec",0))>0:
        dyv=n_(trdf,"draft_year").values; rec=CI[dyv[CI]>=np.nanmax(dyv)-2]
        CI=np.concatenate([CI]+[rec]*int(g["icl_rec"]))
    cc=list(dict.fromkeys((topk or cols)+[c for c in cols if c.startswith("f50_")]))
    mz=market_z(trdf,g)
    def labels_for(spec):
        if g.get("pss"): return [(HW["disc85"][i],season_label(trdf,i,k)) for i in range(k)]
        return [(1.0,label(trdf,spec,k)-mz)]
    def icl_pred(yl): return H.predict("tabicl",Btr[cc].iloc[CI],np.asarray(yl)[CI],Bte[cc],cfg_of("tabicl",g,cols))
    for m in models_of(g):
        rs=[]
        for spec in specs(g):
            acc=np.zeros(len(Bte))
            for w,yl in labels_for(spec):
                if m=="tabicl": p=icl_pred(yl)
                elif m=="xgb" and g.get("resid"):
                    oof=np.zeros(len(Btr)); idx=np.arange(len(Btr)); np.random.default_rng(3).shuffle(idx)
                    for part in np.array_split(idx,3):
                        mask=np.zeros(len(Btr),bool); mask[part]=True
                        oof[mask]=H.predict("tabicl",Btr[cc][~mask],yl[~mask],Btr[cc][mask],cfg_of("tabicl",g,cols))
                    p=pd.Series(icl_pred(yl)).rank(pct=True).values+xgb_member(g,Btr,Bte,cols,pd.Series(yl).rank(pct=True).values-pd.Series(oof).rank(pct=True).values,xgb_cfg(g,cols,yl,trdf,Btr),trdf)
                else:
                    cfg=cfg_of(m,g,cols)
                    if m=="xgb": p=xgb_member(g,Btr,Bte,cols,yl,xgb_cfg(g,cols,yl,trdf,Btr),trdf)
                    elif m=="pair": p=H.predict("pair",Btr[cols],yl,Bte[cols],dict(cfg,qid=n_(trdf,"draft_year").values,pair_k=int(g.get("pair_k",30)),pair_depth=int(g.get("pair_depth",3))))
                    else: p=H.predict(m,Btr[cols],yl,Bte[cols],cfg)
                if g["hurdle"]:
                    import xgboost as xgb
                    MNc=[f"y_s{i}_minutes" for i in range(1,6)]; played=(trdf[MNc[:k]].apply(pd.to_numeric,errors="coerce").fillna(0).sum(axis=1)>=500).astype(int)
                    p=xgb.XGBClassifier(max_depth=3,learning_rate=0.03,n_estimators=500,subsample=0.7,colsample_bytree=0.5,min_child_weight=8,reg_lambda=5.0,n_jobs=3,device=H.XDEV,tree_method="hist",random_state=11).fit(Btr[cols],played).predict_proba(Bte[cols])[:,1]*pd.Series(p).rank(pct=True).values
                acc+=w*pd.Series(p).rank(pct=True).values
            rs.append(acc)
        out[m]=np.mean(rs,0)
    if float(g.get("star",0))>0:
        import xgboost as xgb
        yl0=label(trdf,specs(g)[0],k); top=(yl0>=np.quantile(yl0,float(g.get("star_q",0.85)))).astype(int)
        out["star"]=np.mean([xgb.XGBClassifier(max_depth=3,learning_rate=0.03,n_estimators=400,subsample=0.7,colsample_bytree=0.5,min_child_weight=5,reg_lambda=5.0,scale_pos_weight=3.0,n_jobs=3,device=H.XDEV,tree_method="hist",random_state=s).fit(Btr[cols],top).predict_proba(Bte[cols])[:,1] for s in (11,12,13)],0)
    return out

def stack(preds,Bte,g,wts):
    """wts: {'rich':(w...), 'thin':(w...)} per model order."""
    models=models_of(g); cov=n_(Bte,"feat_coverage").fillna(0).values; thin=cov<np.median(cov) if g["covw"] else np.zeros(len(cov),bool)
    r=np.zeros(len(cov))
    for i,m in enumerate(models): r+=np.where(thin,wts["thin"][i],wts["rich"][i])*preds[m]
    r=pd.Series(r).rank(pct=True).values
    if float(g.get("star",0))>0 and "star" in preds: r=(1-float(g["star"]))*r+float(g["star"])*pd.Series(preds["star"]).rank(pct=True).values
    if float(g.get("cons_unc",0))>0 and "xgb" in preds and "tabicl" in preds:
        dis=np.abs(preds["xgb"]-preds["tabicl"]); lam=float(g["cons_unc"]); mk=(-n_(Bte,"cons_mock_consensus_rank")).rank(pct=True).fillna(0.5).values; r=(1-lam*dis)*r+lam*dis*mk
    if g.get("beatpick") or g.get("consres"):
        zc=market_z_test(Bte); r=pd.Series(float(g.get("mkt_beta",1.0))*_norm.ppf(np.clip(r,1e-3,1-1e-3))+zc).rank(pct=True).values
    r=r-THIN[g["thin"]]*(1-cov)
    mock=n_(Bte,"cons_mock_consensus_rank"); rsci=n_(Bte,"hs_rsci_rank")
    if g["cons"]>0: r=(1-g["cons"])*r+g["cons"]*(-mock).rank(pct=True).fillna(0.5).values
    N=ANCH[g["anchor"]]
    if N: r=np.where(((mock<=N)&((rsci<=10)|(mock<=2))).fillna(False).values,np.maximum(r,0.88),r)
    return r

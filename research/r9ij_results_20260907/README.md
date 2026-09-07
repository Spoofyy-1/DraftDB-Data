# I/J saved-result verification and archive

Bothstudies pass independent saved-record validation, exact reference checks and deterministic replay. Originalstudy directories were mountedread-only, model-execution functions disabled, noGPUdevices mounted, and outputs written separately. No refits, new benchmark evaluation or2019+outcome reads occurred.

|Study|Frozenstudy/Hfiles|Taskrecords|Exactreferences|Savedrecipes/chunks|Rawarchive|
|---|---:|---:|---:|---:|---:|
|I|15/81|336|12|14256/108|24.90MB|
|J|15/81|48|12|2244/12|4.15MB|

Every task/configuration, recorded canonicaltie rule and saved score passed the existing validator. All savedrecipe compressed bytes, uncompressed hashes, individual lines and summaries exactly match a fresh arithmetic replay from saved predictions. Downloaded archives were independentlychecked against their allowlists, embeddedfrozen manifests, completedtask logs and chunk manifests.

|Registered result|Primaryfull meanseedcorrelation|Secondarysubset meanseedcorrelation|
|---|---:|---:|
|J50%TabICL+50%Ridge300|37.3788%|40.1873%|
|Jbest singlefamily:Ridge300|35.8372%|37.2329%|
|I40%TabICL+60%CatBoost,600trees|36.7951%|46.3786%|
|Ibest endpointcontrol:TabICL|35.5463%|37.6248%|
|Ibest standaloneCatBoost,600trees|33.3550%|46.7796%|

All listed winners use s2008_gap1_all_h1 and were ranked byfullpoolmean across allthree seeds and2012/13/14folds. These percentages are Spearman correlations, not percentages of correctly ordered players. The subset score issecondary and inherits selection/immature-label caveats. No modelis promoted.

TheI CatBoostsetting isMAE,depth3,learning_rate0.1,L2=100,bagging_temperature1,nan_modeMax. The originalmodel fit1200trees and these predictions use checkpoint600; fitting a new600-treemodel is a separately registered choice.

Fixed seed averaging is a differentpredictionrule from meanseedcorrelations. ForJ, within-familyseedrank averaging thenfamilyblending gives37.3701%full/40.5267%subset for its selectedstack. I first averages eachfamily rawprediction across3seeds andthenrank-blends:37.3290%full/48.2387%subset for its selectedblend. Thosefixedmodes are not averagedscores and mustnot be conflated.

Only the explicitwrapperallowlist may be published afterparentapproval. Archives contain savedI/J developmentoutputs and their frozen code/metadata; noKprivate outputs,input/labelNPZs,identitycrosswalks orkeys. Originalfrozen H/G input artifacts remain elsewhere and are not bundled.

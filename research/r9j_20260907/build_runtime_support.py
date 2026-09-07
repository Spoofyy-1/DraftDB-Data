"""Pin installed package code; no data/model access."""
from pathlib import Path
import importlib,hashlib,json
import sklearn,xgboost
ROOT=Path(__file__).resolve().parent
modules=['sklearn.pipeline','sklearn.impute._base','sklearn.preprocessing._data','sklearn.linear_model._ridge','sklearn.linear_model._base','xgboost.core','xgboost.sklearn']
sources={}
for name in modules:
 path=Path(importlib.import_module(name).__file__);key=str(path).replace('/home/ubuntu/nba/.venv','/opt/venv');sources[key]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
for path in (Path(xgboost.__file__).parent/'lib').glob('*.so'):
 sources[str(path).replace('/home/ubuntu/nba/.venv','/opt/venv')]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
payload={'versions':{'sklearn':sklearn.__version__,'xgboost':xgboost.__version__},'sources':sources}
path=ROOT/'runtime_support.json';assert not path.exists();path.write_text(json.dumps(payload,indent=2)+'\n');print(json.dumps({'versions':payload['versions'],'pinned_source_files':len(sources),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))

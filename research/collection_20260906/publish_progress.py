"""Keep source metadata in the user's data clone and dashboard; no git mutation."""
from pathlib import Path
import json,shutil,subprocess,time
root=Path(__file__).resolve().parent
dest=Path('/Users/kennakao/nba/datarebuild/research/collection_20260906')
for _ in range(8*60):
    try:
        states={p.name.removesuffix('_state.json'):json.loads(p.read_text()) for p in root.glob('*_state.json')}
        snapshot=root/'collection_state.json';snapshot.write_text(json.dumps(states,indent=2))
        shutil.copytree(root,dest,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.log','*.tmp','private'))
        subprocess.run(['scp','-q','-i','/Users/kennakao/.ssh/today.pem','-o','BatchMode=yes','-o','ConnectTimeout=10',str(snapshot),'ubuntu@209.20.157.130:/home/ubuntu/nba/handoff/collection_state.json'],timeout=30,check=True)
    except Exception as e:print(repr(e),flush=True)
    time.sleep(60)

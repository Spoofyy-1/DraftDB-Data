"""Publish only predictor/provenance files; preserve scientific manifests unchanged."""
from pathlib import Path
import gzip,hashlib,json,shutil,tarfile,os
R=Path(__file__).resolve().parent;O=R/'public_export'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def js(p):return json.loads(Path(p).read_text())
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def copy(src,dest,gz=False):
 src=R/src;dest=O/dest;dest.parent.mkdir(parents=True,exist_ok=True);data=src.read_bytes()
 if gz:
  dest.write_bytes(gzip.compress(data,compresslevel=9,mtime=0));assert gzip.decompress(dest.read_bytes())==data
 else:shutil.copyfile(src,dest)
 return {'source_path':str(src.relative_to(R)),'source_sha256':sha(src),'source_bytes':len(data),'public_sha256':sha(dest),'public_bytes':dest.stat().st_size,'compression':'gzip'if gz else None}
def main():
 os.umask(0o022);assert not O.exists();O.mkdir()
 manifest=js(R/'package/manifest.json');assert sha(R/'package/manifest.json')=='9ba8624cfe079fb1a91f80e0c10a662a0694f29ddafcf4f0e9bcfd3995c58225'
 verification=js(R/'verification.json');assert sha(R/'verification.json')=='7bd7e1a46d8abcd75c3dd6ffaa2822503764c3315c2e8680a4400eeaa479641e'
 assert verification['status']=='passed'and not verification['NBA_labels_or_scores_read']
 files={}
 for name,e in manifest['outputs'].items():
  src=R/'package'/name;assert sha(src)==e['sha256']
  assert e['columns']==(['pid','draft_year']+manifest['columns127']if name.startswith('features')else['pid','draft_year','was_drafted'])
  target='package/'+name+'.gz';files[target]=copy('package/'+name,target,True)
 for n in ['package/manifest.json','verification.json','source_downloads.json','build.py','fetch.py','verify.py']:
  files[n]=copy(n,n)
 for p in sorted((R/'source_code').glob('*.py')):
  n=str(p.relative_to(R));assert sha(p)==verification['source_code_sha256'][n];files[n]=copy(n,n)
 for n in ['source/local_pins.json','source/fifty_manifest.json','source/base_manifest.json','source/draft_dates.json']:
  files[n]=copy(n,n)
 for n in ['source/lineage.json','source/reference_game_team.csv','package/source_join_provenance.json']:
  target=n+'.gz';files[target]=copy(n,target,True)
 files['SCIENTIFIC_README.md']=copy('README.md','SCIENTIFIC_README.md')
 raw=[]
 for p in sorted((R/'raw').glob('*.bin')):
  rel=str(p.relative_to(R));entry=next((e for e in js(R/'source_downloads.json')if e['path']==rel),None)
  expected=entry['sha256']if entry else verification['support_file_sha256'][rel]
  assert sha(p)==expected
  raw.append({'path':rel,'sha256':expected,'bytes':p.stat().st_size,'already_gzip_compressed':p.read_bytes()[:2]==b'\x1f\x8b','url':entry['url']if entry else None,'retained_remote':str(p)})
 future_bytes=sum(e['bytes']for e in raw if '_2018.'not in e['path'])
 assert future_bytes>35*1024**2
 support=[]
 for p in sorted((R/'source').iterdir()):
  if not p.is_file():continue
  rel=str(p.relative_to(R))
  expected=js(R/'source/local_pins.json').get(rel)or verification['support_file_sha256'].get(rel)
  if expected:assert sha(p)==expected
  support.append({'path':rel,'sha256':sha(p),'bytes':p.stat().st_size,'retained_remote':str(p)})
 restore={'policy':'All16derived predictor/metadata tables are included losslessly as gzip. Original manifests remain byte-identical. Historical raw source archives remain on the GPU server due to the transfer cap. They never enter model-worker bundles.','remote_root':str(R),'raw_sources':raw,'support_sources':support,'future_raw_already_compressed_bytes':future_bytes,'raw_archive_included':False,'raw_exclusion_reason':'The14future files are alreadygzip and total morethan35MiB. No oversized raw archive is transferred.','restore_note':'Decompress .csv.gz and .json.gz files to recover original paths and hashes. Reproducible rebuild also requires listed raw/support files retained on server. OriginURLs may serve revisedbytes later; require matching SHA256 on restore.'}
 dump(O/'REMOTE_SOURCE_MANIFEST.json',restore)
 readme='''# 2019–2025 stack predictor inputs\n\nAll127 predictor columns for the frozen M/N stack are preserved in this package. The16 input/metadata CSVs use lossless gzip compression. Decompressing each file restores the exact SHA256 recorded in package/manifest.json. Predictor tables contain pid,draft_year,and127features; actualdraftmembership is stored separately. NoWARlabels,NBAoutcomes,benchmarkanswers,oractualdraftordercolumns are included.\n\nTwelve original M predictor matrices reproduced exactly. The same-source2018 control reproduced35game/team values andmissingcells for75players. Four invalid-game fixtures and all16 output-boundarychecks passed.\n\nAll14 newlyfetched2019–2025 rawgame/team sources werehashverified. These alreadycompressed archives exceed35MiB together, so they remain ontheGPUserver. REMOTE_SOURCE_MANIFEST.json provides paths,URLs,sizes,andhashes forrestoration. All derived predictor tables and source-join provenance are included here. Original annual source files also remain remote.\n\nRetrospectivepublicationvintages,schedulecompleteness,andoriginalpopulationconstruction remainunverified. This is a diagnostic predictor package. Rootcalendarbroker and modelworker isolation must enforce earliercohorttraining andcompleted-season labelcutoffs.\n\nSCIENTIFIC_README.md documents the unchanged scientific builder contract. PUBLIC_ALLOWLIST.json lists every publicfile with bytecount andSHA256.\n'''
 (O/'README.md').write_text(readme)
 dump(O/'COMPRESSION_MANIFEST.json',{'files':files,'scientific_manifest_unchanged':sha(O/'package/manifest.json')==sha(R/'package/manifest.json'),'label_files_included':False,'derived_tables_included':16})
 public={str(p.relative_to(O)):{'sha256':sha(p),'bytes':p.stat().st_size}for p in sorted(O.rglob('*'))if p.is_file()}
 assert sum(x['bytes']for x in public.values())<40*1024**2
 dump(O/'PUBLIC_ALLOWLIST.json',{'policy':'Copy onlythese listedfiles andthisallowlist. NoNBA WARlabels/outcomes,actualdraftorder,modelworkerinputbundles,orprivateOOFrecords.','files':public})
 with tarfile.open(R/'public_transfer.tar.gz','w:gz')as tar:
  for p in sorted(O.rglob('*')):
   if p.is_file():tar.add(p,arcname=str(p.relative_to(O)),recursive=False)
 assert (R/'public_transfer.tar.gz').stat().st_size<40*1024**2
 print(json.dumps({'public_files':len(public)+1,'public_bytes':sum(x['bytes']for x in public.values())+(O/'PUBLIC_ALLOWLIST.json').stat().st_size,'transfer_bytes':(R/'public_transfer.tar.gz').stat().st_size,'transfer_sha256':sha(R/'public_transfer.tar.gz'),'future_raw_bytes_retained':future_bytes,'allowlist_sha256':sha(O/'PUBLIC_ALLOWLIST.json')}))
if __name__=='__main__':main()

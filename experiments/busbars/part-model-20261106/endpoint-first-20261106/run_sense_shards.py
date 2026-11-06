"""External-process bounded, read-only exact source/candidate force-sense replay."""
import sys,json,subprocess,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import cec_force_sense_evidence as evidence
BASE=Path(__file__).parent/'vbus-shortcut-v6'
OUT=BASE/'sense-sharded-v1'
OUT.mkdir(exist_ok=False)
sources={'source':ROOT/'experiments/repack/bar-corridor-20261106/c9-corrective-v4/candidate/board.kicad_pcb','candidate':BASE/'candidate/board.kicad_pcb'}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(sources['source']) == 'b118546af6665d77b190a9ac8ce3132cde413d607cdb3d9b28ba620a3857be24'
assert sha(sources['candidate']) == '4b7457bd28a1a798b6c851b354a2807d02472b8c85b6f583ec48833dce616310'
ledger=[]
def run(label,stage,source,out,extra=()):
    args=['/usr/bin/python3',str(ROOT/'scripts/cec_force_sense_shards.py'),stage,'--source',str(source),'--board-hint','atx-24pin-rev3','--out',str(out),'--timeout-s','9.1',*extra]
    start=time.monotonic()
    try:
        r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=9.9)
        row=dict(label=label,stage=stage,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
    except subprocess.TimeoutExpired as exc:
        row=dict(label=label,stage=stage,external_timeout_s=9.9,stdout=str(exc.stdout),stderr=str(exc.stderr))
    row.update(elapsed_s=time.monotonic()-start,command=args,output=str(out),output_sha256=sha(out)if out.exists()else None)
    ledger.append(row);(OUT/'process-ledger.json').write_text(json.dumps(ledger,indent=2)+'\n')
    print(label,stage,row.get('returncode','TIMEOUT'),round(row['elapsed_s'],3),flush=True)
    return out.exists()and row.get('returncode')==0
complete={}
for label,source in sources.items():
    dest=OUT/label;dest.mkdir();manifest=dest/'manifest.json'
    if not run(label,'manifest',source,manifest):continue
    m=json.loads(manifest.read_text());legs=[];ok=True
    for i,row in enumerate(m['shard_inventory']['legs']):
        out=dest/f'leg-{i:02d}.json';legs.append(out)
        ok=run(label,'leg',source,out,['--manifest',str(manifest),'--input-ref',row['input_ref'],'--leg',row['leg']])and ok
    legacy=dest/'legacy.json';ok=run(label,'legacy',source,legacy,['--manifest',str(manifest)])and ok
    if ok:
        args=['--manifest',str(manifest),'--legacy-report',str(legacy)]
        for path in legs:args.extend(['--leg-report',str(path)])
        out=dest/'assembled.json'
        if run(label,'assemble',source,out,args):complete[label]=json.loads(out.read_text())
report=dict(scope='Read-only force/sense exact sharded replay; external9.9s subprocess bounds, no signals inside native runtime',sources={k:dict(path=str(v),sha256=sha(v))for k,v in sources.items()},assembled=list(complete))
if len(complete)==2:report['contact_preservation']=evidence.compare_contact_preservation(complete['source'],complete['candidate'])
(OUT/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)

"""Exact sharded read-only replay; each subprocess has a hard 10s deadline."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'experiments/busbars/coherent-mux-20261106/port-repaired-v1/sense-shards'
BOARDS = {
    'source': ROOT / 'experiments/busbars/part-model-20261106/endpoint-first-20261106/vbus-shortcut-v6/candidate/board.kicad_pcb',
    'candidate': ROOT / 'experiments/busbars/coherent-mux-20261106/port-repaired-v1/candidate/board.kicad_pcb',
}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(label, stage, target, extra=()):
    command = [sys.executable, 'scripts/cec_force_sense_shards.py', stage,
        '--source', str(BOARDS[label]), '--board-hint', 'atx-24pin-rev3',
        '--timeout-s', '9.1', '--out', str(target), *extra]
    try:
        result = subprocess.run(command, cwd=ROOT, timeout=10, capture_output=True, text=True)
        record = dict(label=label, stage=stage, output=str(target),
                      exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
    except subprocess.TimeoutExpired as error:
        record = dict(label=label, stage=stage, output=str(target), external_timeout_s=10,
                      stdout=str(error.stdout or ''), stderr=str(error.stderr or ''))
    (target.parent / (target.stem + '-process.json')).write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({k:v for k,v in record.items() if k not in ('stdout','stderr')}), flush=True)
    return target.exists() and record.get('exit_code') == 0


def main():
    if OUT.exists():
        raise ValueError('new_output_directory_required')
    before = {label:sha(path) for label,path in BOARDS.items()}
    for label in BOARDS:
        (OUT / label).mkdir(parents=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        manifests = {label:pool.submit(run,label,'manifest',OUT/label/'manifest.json') for label in BOARDS}
        if not all(f.result() for f in manifests.values()):
            raise ValueError('manifest_constituent_failed')
        jobs = []; reports = {}
        for label in BOARDS:
            folder=OUT/label; manifest=folder/'manifest.json'
            reports[label]=[]
            for index, leg in enumerate(read(manifest)['shard_inventory']['legs']):
                target=folder/f'leg-{index:03d}.json';reports[label].append(target)
                extra=['--manifest',str(manifest),'--input-ref',leg['input_ref'],'--leg',leg['leg']]
                jobs.append(pool.submit(run,label,'leg',target,extra))
            jobs.append(pool.submit(run,label,'legacy',folder/'legacy.json',['--manifest',str(manifest)]))
        if not all([f.result() for f in jobs]):
            raise ValueError('worker_constituent_failed')
        joins=[]
        for label in BOARDS:
            folder=OUT/label
            extra=['--manifest',str(folder/'manifest.json'),'--legacy-report',str(folder/'legacy.json')]
            for report in reports[label]:
                extra += ['--leg-report',str(report)]
            joins.append(pool.submit(run,label,'assemble',folder/'assembled.json',extra))
        if not all([f.result() for f in joins]):
            raise ValueError('assemble_constituent_failed')
    sys.path[:0]=[str(ROOT/'scripts')]
    import cec_force_sense_evidence as evidence
    import cec_force_current as force
    comparison=evidence.compare_contact_preservation(
        read(OUT/'source/assembled.json'),read(OUT/'candidate/assembled.json'))
    comparison.update(source_board_sha256=before['source'],candidate_board_sha256=before['candidate'],
        boards_unchanged=before=={label:sha(path) for label,path in BOARDS.items()},
        code_after=force._code_identity(),external_constituent_timeout_s=10,max_parallel_workers=4)
    (OUT/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
    print(json.dumps(comparison),flush=True)


if __name__=='__main__':
    main()

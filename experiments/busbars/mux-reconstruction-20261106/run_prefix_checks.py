"""Ten-second independent subprocesses; heavy exact replay runs alone."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[2]


def main():
    revision = sys.argv[1]
    assert revision and len(revision) <= 32 and all(c.isalnum() or c in '-_' for c in revision)
    out = WORK / 'output-prefix-v1' / ('checks-' + revision)
    assert not out.exists()
    out.mkdir()
    def run(name):
        cmd = [sys.executable, str(WORK / 'check_prefix.py'), name, revision]
        try:
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=10)
            row = dict(stage=name, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired as exc:
            row = dict(stage=name, timeout_s=10, stdout=str(exc.stdout or ''), stderr=str(exc.stderr or ''))
        target = out / (name + '.json')
        row['ok'] = row.get('returncode') == 0 and target.is_file() and json.loads(target.read_text())['ok']
        (out / (name + '-process.json')).write_text(json.dumps(row, indent=2) + '\n')
        print(json.dumps(dict(stage=name, ok=row['ok'])), flush=True)
        return row['ok']
    assert run('reflow'), 'exact_full_current_receiving_failed'
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(run, ['seat', 'ground', 'current', 'craft', 'pairs',
            'drc-source', 'drc-candidate', 'field-source', 'field-candidate']))
    assert all(result), 'independent_receiving_failed'


if __name__ == '__main__':
    main()

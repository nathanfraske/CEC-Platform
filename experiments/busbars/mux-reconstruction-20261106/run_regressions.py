"""One test per hard-ten-second process; bounded parallelism and raw results."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import time

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[2]


def main():
    label, *files = sys.argv[1:]
    assert label and files and all(c.isalnum() or c in '-_' for c in label)
    out = WORK / ('regression-' + label)
    assert not out.exists(); out.mkdir()
    collection = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', '-q', *files],
        cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert collection.returncode == 0, collection.stdout + collection.stderr
    nodes = [s.strip() for s in collection.stdout.splitlines() if s.startswith('tests/') and '::' in s]
    assert nodes and len(nodes) == len(set(nodes))
    def job(pair):
        n, node = pair; start = time.monotonic()
        xml = out / ('case-%04d.xml' % n)
        try:
            run = subprocess.run([sys.executable, '-m', 'pytest', '-q', node, '--junitxml', str(xml)],
                cwd=ROOT, capture_output=True, text=True, timeout=10)
            row = dict(node=node, returncode=run.returncode, stdout=run.stdout, stderr=run.stderr)
        except subprocess.TimeoutExpired as exc:
            row = dict(node=node, timeout_s=10, stdout=str(exc.stdout or ''), stderr=str(exc.stderr or ''))
        row.update(elapsed_s=time.monotonic()-start, ok=row.get('returncode') == 0)
        if not row['ok']:
            (out / ('failure-%04d.json' % n)).write_text(json.dumps(row, indent=2) + '\n')
            print(json.dumps(dict(node=node, ok=False, seconds=row['elapsed_s'])), flush=True)
        return {k: v for k, v in row.items() if k not in ('stdout', 'stderr')}
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(job, enumerate(nodes)))
    report = dict(total=len(rows), passed=sum(r['ok'] for r in rows), rows=rows,
                  each_test_external_timeout_s=10, maximum_parallel=2)
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}), flush=True)
    assert report['passed'] == report['total']


if __name__ == '__main__':
    main()

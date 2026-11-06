"""Complete receiver regressions split into small, externally bounded jobs."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent / 'vbus-shortcut-v6/regressions'
FILES = ['tests/test_full_current_planar_reflow.py', 'tests/test_force_sense_shards.py',
         'tests/test_native_drc_runner.py', 'tests/test_field_coupling.py',
         'tests/test_field_coupling_offsets.py']


def main():
    OUT.mkdir(exist_ok=False)
    collected = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', '-q', *FILES],
                               cwd=ROOT, capture_output=True, text=True, timeout=9.9)
    assert collected.returncode == 0, collected.stderr
    names = [line.strip() for line in collected.stdout.splitlines()
             if line.startswith('tests/') and '::' in line]
    assert names and len(names) == len(set(names))
    result = dict(ok=False, collected=len(names), tests=names, batches=[], timeout_s=9.9)
    for start in range(0, len(names), 10):
        chosen = names[start:start+10]
        began = time.monotonic()
        try:
            run = subprocess.run([sys.executable, '-m', 'pytest', '-q', *chosen,
                                  '--junitxml=' + str(OUT / f'batch-{start//10:02}.xml')],
                                 cwd=ROOT, capture_output=True, text=True, timeout=9.9)
            row = dict(tests=chosen, returncode=run.returncode, stdout=run.stdout, stderr=run.stderr)
        except subprocess.TimeoutExpired as exc:
            row = dict(tests=chosen, timeout=True, stdout=str(exc.stdout), stderr=str(exc.stderr))
        row['elapsed_s'] = time.monotonic()-began
        result['batches'].append(row)
        (OUT / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(dict(batch=start//10, ok=row.get('returncode') == 0,
                              tests=len(chosen), elapsed_s=row['elapsed_s'])), flush=True)
    result['ok'] = all(row.get('returncode') == 0 for row in result['batches'])
    (OUT / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(ok=result['ok'], tests=len(names))))


if __name__ == '__main__':
    main()

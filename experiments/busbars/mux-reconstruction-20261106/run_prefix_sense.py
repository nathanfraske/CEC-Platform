"""Fresh independent bounded per-leg copper-cut replay on this actual pair."""
import importlib.util
import json
from pathlib import Path
import sys

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[2]


def main():
    script = ROOT / 'experiments/busbars/coherent-mux-20261106/run_sense_shards_v1.py'
    spec = importlib.util.spec_from_file_location('prefix_sense_replay', script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    record = json.loads((WORK / 'output-prefix-construction.json').read_text())
    revision = sys.argv[1] if len(sys.argv) > 1 else 'baseline'
    assert revision and len(revision) <= 32 and all(c.isalnum() or c in '-_' for c in revision)
    module.OUT = WORK / 'output-prefix-v1' / ('sense-shards-' + revision)
    assert not module.OUT.exists(), 'fresh_observation_required'
    module.BOARDS = {k: Path(record[k]) for k in ('source', 'candidate')}
    module.main()


if __name__ == '__main__':
    main()

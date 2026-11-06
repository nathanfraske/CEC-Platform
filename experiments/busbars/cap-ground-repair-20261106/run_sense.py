"""Reuse bounded independent per-leg native replay on this exact pair."""
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
WORK=Path(__file__).resolve().parent


def main():
    script=ROOT/'experiments/busbars/coherent-mux-20261106/run_sense_shards_v1.py'
    spec=importlib.util.spec_from_file_location('cec_repack_sense_worker',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    record=json.loads((WORK/'construction.json').read_text())
    module.OUT=WORK/'sense-shards'
    module.BOARDS={key:Path(record[key])for key in ('source','candidate')}
    module.main()


if __name__=='__main__':main()

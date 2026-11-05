#!/usr/bin/env python3
"""One supervised route candidate with the ordinary oracle/checkpoint contract."""
import argparse
import json
import os
from pathlib import Path
import sys


def main(argv=None):
    import cec_operation_budget as budget
    diagnostic_handle = budget.arm_diagnostics()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.payload).read_text(encoding='utf-8'))
    import cec_full_pipeline
    budget.progress('route_candidate_dispatch', seed=payload['seed'])
    result = dict(cec_full_pipeline._route_candidate_worker(payload))
    result.setdefault('seed', int(payload['seed']))
    budget.write_json(args.report, result)
    budget.progress('route_candidate_complete', seed=payload['seed'], gate=result.get('gate'))
    return 0


if __name__ == '__main__':
    code = main()
    # Native SWIG teardown must not replace a fully serialized receipt with
    # an unrelated interpreter-shutdown fault. Exceptions still exit nonzero.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)

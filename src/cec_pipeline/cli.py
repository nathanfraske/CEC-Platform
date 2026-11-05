"""Canonical direct CLI and MCP stdio launch surface."""

from __future__ import annotations
import argparse, json, signal, sys
from pathlib import Path
from .legacy import ROOT, bootstrap

bootstrap()
import cec_suite_inspection as inspection
from . import geometry as design

from .identity import require
from .workbench import Workbench
from .protocol import TOOL_PARAMETERS, REQUIRED, DESCRIPTIONS, MAX_JSON, dispatch, serve
from .receivers import worker


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--validate-worker":
        from .execution import validate_worker

        signal.signal(
            signal.SIGALRM,
            lambda *_: (_ for _ in ()).throw(
                TimeoutError("finite_validation_watchdog")
            ),
        )
        signal.setitimer(signal.ITIMER_REAL, 245.0)
        validate_worker(sys.argv[2])
        return
    if len(sys.argv) == 5 and sys.argv[1] == "--worker":

        def expired(_signum, _frame):
            raise TimeoutError("bounded_independent_worker_watchdog")

        from .execution import WORKER_MAX_SECONDS

        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, WORKER_MAX_SECONDS)
        try:
            worker(*sys.argv[2:])
        except Exception as exc:
            data = json.loads(Path(sys.argv[2]).read_text())
            inspection.write_json(
                sys.argv[4],
                dict(
                    complete=False,
                    error=type(exc).__name__ + ":" + str(exc),
                    candidate_sha256=inspection.sha(data["candidate"]),
                    release_authority=False,
                ),
            )
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--call", choices=tuple(TOOL_PARAMETERS))
    parser.add_argument("--json", default="{}")
    parser.add_argument("--schemas", action="store_true")
    parser.add_argument(
        "--json-file",
        help="Explicit local request file for direct tools; not exposed over MCP",
    )
    parser.add_argument(
        "--checkpoint", help="Explicit verified portable or native review receipt"
    )
    parser.add_argument("--checkpoint-sha256", help="Exact identity for --checkpoint")
    args = parser.parse_args()
    if args.schemas:
        print(
            json.dumps(
                {
                    name: dict(
                        description=DESCRIPTIONS[name],
                        parameters=TOOL_PARAMETERS[name],
                        required=REQUIRED[name],
                    )
                    for name in TOOL_PARAMETERS
                }
            )
        )
        return
    workbench = Workbench(
        args.workspace,
        checkpoint=args.checkpoint,
        checkpoint_sha256=args.checkpoint_sha256,
    )
    if args.call:
        try:
            raw = Path(args.json_file).read_text() if args.json_file else args.json
            require(len(raw.encode()) <= MAX_JSON, "bounded_direct_request_required")
            value = dispatch(workbench, args.call, json.loads(raw))
        except Exception as exc:
            value = dict(
                ok=False,
                error=type(exc).__name__ + ":" + str(exc),
                release_authority=False,
            )
        print(json.dumps(value, separators=(",", ":"), allow_nan=False))
    else:
        serve(workbench)

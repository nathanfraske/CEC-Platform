"""Private exact-library mount correction; no tolerance waiver or promotion."""
import argparse
import json
from pathlib import Path

from cec_pipeline.native import _native
_native()
import cec_force_current as force
import cec_source_mount_stitch_reconcile as reconcile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--sha256', required=True)
    ap.add_argument('--mount-uuid', action='append', required=True)
    ap.add_argument('--board-hint', required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--assembly-instance', type=Path)
    ap.add_argument('--receive-candidate', type=Path)
    args = ap.parse_args()
    source = args.source.resolve(strict=True)
    if force._hash(source) != args.sha256:
        raise ValueError('exact_source_hash_required')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    proposal = reconcile.plan(source, board_hint=args.board_hint,
                              mount_uuids=args.mount_uuid, timeout_s=10.)
    force._write(out / 'plan.json', proposal)
    if args.receive_candidate:
        candidate = args.receive_candidate.resolve(strict=True)
    else:
        candidate = force._copy_family(source, out / 'candidate')
        force._write(out / 'construction.json', reconcile.construct_private(source, candidate, proposal))
    instance = json.loads(args.assembly_instance.read_text()) if args.assembly_instance else None
    receipt = reconcile.receive_full(source, candidate, out / 'receiving',
        board_hint=args.board_hint, mount_uuids=args.mount_uuid, assembly_instance=instance)
    print(json.dumps(dict(candidate=str(candidate), sha256=force._hash(candidate),
        ok=receipt['ok'], complete=receipt['complete'], gates=receipt['gates'],
        error=receipt.get('error'), release_authority=False)))


if __name__ == '__main__':
    main()

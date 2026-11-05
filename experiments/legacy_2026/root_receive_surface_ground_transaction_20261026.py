"""Add one existing public surface-Ground receiver to the frozen transaction.

The request contains only a Source land identity. No cuts, holes, current,
dimensions, callback or precomputed verdict enter this additional phase.
All original one-to-four-phase and whole-parent gates remain unchanged.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import cec_force_current as force
import cec_ground_component_join as ground
import root_receive_local_transaction_20261022 as base

KIND = 'source_surface_ground_join'
_VALIDATE = base.validate_phases
_RECEIVE = base.receive_phase
_DEPENDENCIES = base.annotation_dependencies


def validate_phases(phases):
    # Reuse only the existing exact UUID-schema/cardinality/order checks.
    # The co-owned electrical receiver is NOT used for this different role.
    projected = [dict(row, kind='coowned_input_control_ground')
        if type(row) is dict and row.get('kind') == KIND else row for row in phases] if type(phases) is list else phases
    _VALIDATE(projected)
    return [row['kind'] for row in phases]


def receive_phase(original, parent, row, hint, *, assembly_instance=None):
    if row.get('kind') != KIND:
        return _RECEIVE(original, parent, row, hint, assembly_instance=assembly_instance)
    validate_phases([row])
    parent = Path(parent).resolve(strict=True)
    child = Path(row['candidate']).resolve(strict=True)
    assert child != parent and force._hash(child) == row['candidate_sha256']
    # Both are actual independent saved native receivers, never the manual
    # request's geometry or the constructor's recorded success flag.
    proof = ground.receive(parent, child, board_hint=hint, timeout_s=10.)
    assert proof.get('ok') is True and proof.get('complete') is True, proof
    target = ground.receive_target(parent, child, board_hint=hint,
        pad_uuid=row['pad_uuid'], timeout_s=10.)
    assert target.get('ok') is True and target.get('complete') is True, target
    return child, dict(proof, requested_Source_target_receiving=target,
        source_surface_only_no_new_holes=True, release_authority=False)


def dependencies():
    return {**_DEPENDENCIES(), str(Path(__file__).resolve()): force._hash(Path(__file__)),
        str(Path(base.__file__).resolve()): force._hash(Path(base.__file__))}


@contextmanager
def installed():
    previous = base.validate_phases, base.receive_phase, base.annotation_dependencies
    base.validate_phases, base.receive_phase, base.annotation_dependencies = validate_phases, receive_phase, dependencies
    try:
        yield
    finally:
        base.validate_phases, base.receive_phase, base.annotation_dependencies = previous


def main():
    epoch = dependencies()
    args = sys.argv[1:]
    assert args.count('--out') == 1
    out = Path(args[args.index('--out')+1])
    with installed():
        status = base.main()
    assert epoch == dependencies(), 'surface_Ground_transaction_dispatcher_changed'
    path = out/'receiving.json'
    result = json.loads(path.read_text())
    result['inputs'].update(epoch)
    result['registered_saved_receiver'] = dict(kind=KIND, phase_dimensions_or_current_inputs=False,
        Source_roles_partitions_references_boundaries_and_target_recompiled=True,
        original_frozen_transaction=str(Path(base.__file__).resolve()),
        original_gates_or_phase_cap_changed=False, release_authority=False)
    force._write(path, result)
    return status


if __name__ == '__main__':
    raise SystemExit(main())

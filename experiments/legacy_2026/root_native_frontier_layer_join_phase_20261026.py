"""Identity-only typed native-frontier phase under all original root gates."""
from contextlib import contextmanager
from pathlib import Path
import json
import sys
import cec_force_current as force
import cec_distributed_supply_layer_join as join
import root_receive_local_transaction_20261022 as base

KIND = 'distributed_native_frontier_join'
_VALIDATE = base.validate_phases
_RECEIVE = base.receive_phase
_DEPENDENCIES = base.annotation_dependencies

def validate_phases(phases):
    old = base.KINDS
    try:
        base.KINDS = {**old, KIND:{'net', 'pad_uuids'}}
        result = _VALIDATE(phases)
    finally:
        base.KINDS = old
    for row in phases:
        if row['kind'] == KIND:
            if type(row['net']) is not str or not row['net']:
                raise ValueError('explicit_native_frontier_net_identity_required')
            join._ids(row['pad_uuids'])
    return result

def receive_phase(original, parent, row, hint, *, assembly_instance=None):
    if row.get('kind') != KIND:
        return _RECEIVE(original, parent, row, hint, assembly_instance=assembly_instance)
    validate_phases([row])
    parent = Path(parent).resolve(strict=True); child = Path(row['candidate']).resolve(strict=True)
    assert parent != child and force._hash(child) == row['candidate_sha256']
    result = join.receive_native_frontier(parent, child, board_hint=hint,
        net=row['net'], pad_uuids=row['pad_uuids'], timeout_s=10.)
    assert result.get('ok') is True and result.get('complete') is True, result
    return child, result

def dependencies():
    return {**_DEPENDENCIES(), **{str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))
        for m in (join, base)}, str(Path(__file__).resolve()):force._hash(Path(__file__))}

@contextmanager
def installed():
    previous = base.validate_phases, base.receive_phase, base.annotation_dependencies
    base.validate_phases, base.receive_phase, base.annotation_dependencies = validate_phases, receive_phase, dependencies
    try:
        yield
    finally:
        base.validate_phases, base.receive_phase, base.annotation_dependencies = previous

def main():
    epoch = dependencies(); args = sys.argv[1:]; assert args.count('--out') == 1
    out = Path(args[args.index('--out')+1])
    with installed():
        status = base.main()
    assert epoch == dependencies(), 'native_frontier_dispatcher_or_dependency_changed'
    path = out/'receiving.json'; result = json.loads(path.read_text())
    result['inputs'].update(epoch)
    result['registered_saved_receiver'] = dict(kind=KIND, identities_only=True,
        maximum_local_phases_unchanged=base.MAX_LOCAL_PHASES,
        all_original_parent_gates_retained=True, old_barrel_capacity_credited=False,
        constituent_limit_s=10, release_authority=False)
    force._write(path, result)
    return status

if __name__ == '__main__':
    raise SystemExit(main())

"""Identity-only stationary-address dispatch under every original root gate."""
from contextlib import contextmanager
from pathlib import Path
import json,sys
import cec_force_current as force
import cec_stationary_address_supply_join as address
import root_receive_local_transaction_20261022 as base

KIND='stationary_address_supply_join'
_VALIDATE=base.validate_phases
_RECEIVE=base.receive_phase
_DEPENDENCIES=base.annotation_dependencies


def validate_phases(phases):
    old=base.KINDS
    try:
        base.KINDS={**old,KIND:{'pad_uuid'}}
        result=_VALIDATE(phases)
    finally:base.KINDS=old
    seen=set()
    for row in phases:
        if row['kind']!=KIND:continue
        value=row['pad_uuid']
        if type(value)is not str or not value or value in seen:
            raise ValueError('distinct_explicit_stationary_address_land_identity_required')
        seen.add(value)
    return result


def receive_phase(original,parent,row,hint,*,assembly_instance=None):
    if row.get('kind')!=KIND:
        return _RECEIVE(original,parent,row,hint,assembly_instance=assembly_instance)
    validate_phases([row])
    parent=Path(parent).resolve(strict=True);child=Path(row['candidate']).resolve(strict=True)
    assert parent!=child and force._hash(child)==row['candidate_sha256']
    received=address.receive(parent,child,board_hint=hint,pad_uuid=row['pad_uuid'],timeout_s=10.)
    assert received.get('ok')is True and received.get('complete')is True,received
    return child,received


def dependencies():
    return {**_DEPENDENCIES(),**{str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))
        for m in(address,base)},str(Path(__file__).resolve()):force._hash(Path(__file__))}


@contextmanager
def installed():
    previous=base.validate_phases,base.receive_phase,base.annotation_dependencies
    base.validate_phases,base.receive_phase,base.annotation_dependencies=validate_phases,receive_phase,dependencies
    try:yield
    finally:base.validate_phases,base.receive_phase,base.annotation_dependencies=previous


def main():
    epoch=dependencies();args=sys.argv[1:];assert args.count('--out')==1
    out=Path(args[args.index('--out')+1])
    with installed():status=base.main()
    assert epoch==dependencies(),'stationary_address_dispatcher_or_dependency_changed'
    path=out/'receiving.json';result=json.loads(path.read_text())
    result['inputs'].update(epoch)
    result['registered_saved_receiver']=dict(kind=KIND,identities_only=True,
        maximum_local_phases_unchanged=base.MAX_LOCAL_PHASES,
        all_original_parent_gates_retained=True,constituent_limit_s=10,
        guessed_input_load=False,release_authority=False)
    force._write(path,result)
    return status


if __name__=='__main__':raise SystemExit(main())

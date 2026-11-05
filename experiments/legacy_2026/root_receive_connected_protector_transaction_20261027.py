"""Finite connected preclear + complete protector under all original gates.

Only two exact saved public receivers are registered. Base phase caps,
legacy eight-track ordinary cuts and every original-parent gate are intact.
No constructor callback or historical success record grants admission.
"""
from contextlib import contextmanager
from pathlib import Path
import json,sys
import cec_force_current as force
import cec_protector_cell_receiving as protector
import root_complete_protector_phase_20261026 as protector_phase
import root_connected_ordinary_phase_20261027 as connected_phase
import root_receive_local_transaction_20261022 as base


@contextmanager
def installed():
    restore_connected=connected_phase.install(base)
    previous=base.validate_phases,base.receive_phase,base.annotation_dependencies
    original_validate,original_receive,original_dependencies=previous
    def validate(phases):
        old=base.KINDS
        try:
            base.KINDS={**old,protector_phase.KIND:{'proposal'}}
            result=original_validate(phases)
        finally:base.KINDS=old
        if sum(row['kind']==protector_phase.KIND for row in phases)>1:
            raise ValueError('one_complete_protector_per_finite_local_transaction')
        return result
    def receive(original,parent,row,hint,*,assembly_instance=None):
        if row.get('kind')!=protector_phase.KIND:
            return original_receive(original,parent,row,hint,assembly_instance=assembly_instance)
        validate([row])
        proof=protector_phase.receive_phase(original,parent,row,hint,assembly_instance=assembly_instance)
        if proof.get('ok')is not True or proof.get('complete')is not True:
            raise ValueError('saved_complete_protector_phase_refused:'+str(proof))
        return Path(row['candidate']).resolve(strict=True),proof
    def dependencies():
        return {**original_dependencies(),**{str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))
            for m in(protector,protector_phase,connected_phase)},
            str(Path(__file__).resolve()):force._hash(Path(__file__))}
    base.validate_phases,base.receive_phase,base.annotation_dependencies=validate,receive,dependencies
    try:yield
    finally:
        base.validate_phases,base.receive_phase,base.annotation_dependencies=previous
        restore_connected()


def main():
    args=sys.argv[1:]
    if args.count('--out')!=1:raise ValueError('one_explicit_transaction_output_required')
    out=Path(args[args.index('--out')+1])
    with installed():
        epoch=base.annotation_dependencies()
        status=base.main()
        assert epoch==base.annotation_dependencies(),'connected_protector_dispatch_dependencies_changed'
    result=json.loads((out/'receiving.json').read_text())
    result['inputs'].update(epoch)
    result['registered_saved_receivers']=dict(kinds=[connected_phase.KIND,protector_phase.KIND],
        callbacks_or_constructor_proofs_accepted=False,legacy_ordinary_source_cap_unchanged=8,
        connected_chain_source_cap=16,maximum_local_phases_unchanged=base.MAX_LOCAL_PHASES,
        all_original_parent_gates_retained=True,constituent_limit_s=10.,release_authority=False)
    force._write(out/'receiving.json',result)
    return status


if __name__=='__main__':raise SystemExit(main())

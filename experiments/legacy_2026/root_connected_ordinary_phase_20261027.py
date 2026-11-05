"""Isolated fixed-bound typed adapter; base dispatcher/parent gates unchanged."""
from pathlib import Path
import re
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_ordinary_source_connected_reflow as connected

KIND='ordinary_source_connected_reflow'
FIELDS={'kind','candidate','candidate_sha256','net','retired_track_uuids','allow_locked_track_uuids'}

def validate_row(row):
    if type(row)is not dict or set(row)!=FIELDS or row['kind']!=KIND:
        raise ValueError('exact_connected_ordinary_phase_schema_required')
    connected._net(row['net'])
    cuts=ordinary._ids(row['retired_track_uuids'],'connected_ordinary_Source_tracks',16)
    locks=ordinary._ids(row['allow_locked_track_uuids'],'connected_ordinary_Source_locks',16)
    if (not cuts or not locks<=cuts or type(row['candidate'])is not str or not row['candidate']
        or type(row['candidate_sha256'])is not str or not re.fullmatch('[0-9a-f]{64}',row['candidate_sha256'])):
        raise ValueError('exact_connected_ordinary_phase_identity_and_scope_required')
    return row

def receive_phase(original,parent,row,hint,*,assembly_instance=None):
    validate_row(row)
    if type(hint)is not str or not hint:raise ValueError('explicit_connected_ordinary_phase_board_required')
    Path(original).resolve(strict=True)
    parent=Path(parent).resolve(strict=True);child=Path(row['candidate']).resolve(strict=True)
    if parent==child or force._hash(child)!=row['candidate_sha256']:
        raise ValueError('connected_ordinary_saved_phase_candidate_changed')
    return connected.receive(parent,child,board_hint=hint,net=row['net'],
        retired_track_uuids=row['retired_track_uuids'],allow_locked_track_uuids=row['allow_locked_track_uuids'],timeout_s=10.)

def install(base):
    """Install one exact tier, capturing the current composed dispatcher.

    The returned callable restores all captured functions. No base module
    bytes or legacy schema/cut bounds are modified.
    """
    previous=(base.validate_phases,base.receive_phase,base.annotation_dependencies)
    original_validate,original_receive,original_dependencies=previous
    def validate(phases):
        old=base.KINDS
        try:
            base.KINDS={**old,KIND:FIELDS-{'kind','candidate','candidate_sha256'}}
            result=original_validate(phases)
        finally:base.KINDS=old
        nets=set()
        net_kinds={'ordinary_join','ordinary_columns','can_endpoint_join','ordinary_reflow',
            'ordinary_source_reflow','distributed_supply_join',KIND}
        for row in phases:
            if row['kind']==KIND:validate_row(row)
            if row['kind']in net_kinds:
                if row['net']in nets:
                    raise ValueError('repeated_local_operator_requires_a_separate_transaction')
                nets.add(row['net'])
        return result
    def receive(original,parent,row,hint,*,assembly_instance=None):
        if row.get('kind')!=KIND:
            return original_receive(original,parent,row,hint,assembly_instance=assembly_instance)
        validate([row])
        proof=receive_phase(original,parent,row,hint,assembly_instance=assembly_instance)
        if proof.get('ok')is not True or proof.get('complete')is not True:
            raise ValueError('saved_connected_ordinary_phase_refused:'+str(proof))
        return Path(row['candidate']).resolve(strict=True),proof
    def dependencies():
        return {**original_dependencies(),**{str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))
            for m in(connected,ordinary)},str(Path(__file__).resolve()):force._hash(Path(__file__))}
    base.validate_phases,base.receive_phase,base.annotation_dependencies=validate,receive,dependencies
    def restore():
        base.validate_phases,base.receive_phase,base.annotation_dependencies=previous
    return restore

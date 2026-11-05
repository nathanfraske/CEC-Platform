"""Isolated typed phase adapter; does not replace any original-parent gate.

The shared base dispatcher is deliberately untouched. Its owner can register
this exact handler; callers still owe its four-phase/lineage/all-suite rules.
"""
import json
from pathlib import Path
import cec_force_current as force
import cec_protector_cell_receiving as protector

KIND='complete_protector_cell'


def receive_phase(original,parent,row,hint,*,assembly_instance=None):
    if (type(row) is not dict or set(row)!={'kind','candidate','candidate_sha256','proposal'}
            or row['kind']!=KIND or type(hint) is not str or not hint):
        raise ValueError('exact_typed_complete_protector_phase_required')
    parent=Path(parent).resolve(strict=True);child=Path(row['candidate']).resolve(strict=True)
    if parent==child or force._hash(child)!=row['candidate_sha256']:
        raise ValueError('complete_protector_saved_candidate_identity_changed')
    q=json.loads(Path(row['proposal']).resolve(strict=True).read_text())
    if (q.get('board_hint')!=hint or Path(q.get('source','')).resolve()!=parent
            or q.get('source_sha256')!=force._hash(parent)):
        raise ValueError('complete_protector_original_phase_source_changed')
    # Original is retained as root lineage context, never substituted with
    # the projection. The enclosing dispatcher replays original-parent gates.
    Path(original).resolve(strict=True)
    return protector.receive(parent,child,q,timeout_s=10.)

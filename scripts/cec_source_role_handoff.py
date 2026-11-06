"""Internal immutable Source-role handoff, never an admission certificate.

The private compiler continuation captures and rederives these observations
around a substantive phase boundary. No caller proof, stored fingerprint,
native-board copy, pose/copper authority or receiving acceptance is provided.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

import cec_cell_row_rebuild as row
import cec_control_gate_bias_placement as native
import cec_force_current as force
import cec_source_ground_leaf as canonical
from cec_native_items import _native_pointer

ROOT=Path(__file__).resolve().parents[1]


def _need(value,reason):
    if not value:raise ValueError(reason)


def _tick(deadline):
    _need(time.monotonic()<deadline,'source_role_handoff_deadline')


def _json(value):
    """Strict JSON values; reject coercive dict keys and nonfinite numbers."""
    def visit(item):
        if type(item)is dict:
            _need(all(type(k)is str for k in item),'source_role_handoff_JSON_string_keys_required')
            for v in item.values():visit(v)
        elif type(item)in(list,tuple):
            for v in item:visit(v)
        elif type(item)in(str,int,bool)or item is None:pass
        elif type(item)is float:_need(math.isfinite(item),'source_role_handoff_finite_JSON_required')
        else:raise ValueError('source_role_handoff_strict_JSON_required')
    visit(value)
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def _evidence(roles,deadline):
    """Observe declared Source proofs, never accept their alleged pass flags."""
    expected={};pending=[(roles,False)];count=0
    def add(name,digest):
        _need(type(name)is str and name and type(digest)is str
            and re.fullmatch('[0-9a-f]{64}',digest),'source_role_handoff_evidence_identity_required')
        path=Path(name);path=(ROOT/path if not path.is_absolute()else path).resolve(strict=True)
        key=str(path)
        _need(key not in expected or expected[key]==digest,'source_role_handoff_conflicting_evidence')
        _need(path.is_file()and force._hash(path)==digest,'source_role_handoff_declared_evidence_changed')
        expected[key]=digest
    while pending:
        _tick(deadline);item,in_proof=pending.pop();count+=1
        _need(count<=65536,'source_role_handoff_bounded_evidence_inventory_required')
        if type(item)is dict:
            if in_proof:
                for key in('evidence_files_sha256','schematic_files_sha256'):
                    if key in item:
                        _need(type(item[key])is dict,'source_role_handoff_evidence_map_required')
                        for name,digest in item[key].items():add(name,digest)
                if 'exporter'in item and type(item['exporter'])is str:
                    add(item['exporter'],item.get('exporter_sha256'))
                if 'datasheet'in item:add(item['datasheet'],item.get('datasheet_sha256'))
            pending.extend((v,in_proof or k=='source_proof')for k,v in item.items())
        elif type(item)in(list,tuple):pending.extend((v,in_proof)for v in item)
    return expected


def capture(board,poses,*,board_hint,roles,options,deadline):
    """Freshly fingerprint inputs for ONE wrapper-local continuation only."""
    now=time.monotonic()
    _need(type(deadline)in(int,float)and math.isfinite(deadline)and now<deadline<=now+10.,
        'bounded_source_role_handoff_deadline_required')
    _need(type(board_hint)is str and board_hint and type(poses)is dict and 1<=len(poses)<=8
        and type(roles)is dict and type(options)is dict,
        'literal_source_role_handoff_context_required')
    _need(all(type(ref)is str and ref and type(p)in(list,tuple)and len(p)==3
        and all(type(v)in(int,float)and math.isfinite(v)for v in p)for ref,p in poses.items()),
        'literal_source_role_handoff_poses_required')
    literal=dict(poses=_json(poses),roles=_json(roles),options=_json(options))
    _need(sum(map(len,literal.values()))<=16*1024*1024,'bounded_source_role_handoff_JSON_required')
    source=Path(board.GetFileName()).resolve(strict=True)
    environment=dict(os.environ);binding=row._source_binding(board)
    family=force._family(source,board_hint);epoch=force._code_identity()
    footprints={}
    for fp in board.GetFootprints():
        _tick(deadline);uid=force._uid(fp)
        _need(uid not in footprints,'source_role_handoff_unique_native_footprints_required')
        footprints[uid]=native._footprint(board,fp)
    _need(len(footprints)<=16384,'bounded_source_role_handoff_native_inventory_required')
    evidence=_evidence(roles,deadline)
    root=canonical.source_nc._root(board,board_hint);canonical_inputs=None
    if root is not None:
        root=Path(root).resolve(strict=True)
        files,hashes,_=canonical._hierarchy(root,deadline)
        import cec_toolchain as tc
        exporter=Path(tc.require_kicad_cli('Source role handoff')).resolve(strict=True)
        canonical_inputs=dict(root=str(root),hierarchy=hashes,
            exporter=str(exporter),exporter_sha256=force._hash(exporter),
            project_and_library_inputs=canonical._export_inputs(root,files))
    _tick(deadline)
    # Inputs are unchanged even while this fresh observation is assembled.
    _need(binding==row._source_binding(board)and environment==dict(os.environ)
        and family==force._family(source,board_hint)and epoch==force._code_identity()
        and source==Path(board.GetFileName()).resolve(), 'source_role_handoff_inputs_changed_during_capture')
    _need(_json(footprints)==_json({force._uid(fp):native._footprint(board,fp)
        for fp in board.GetFootprints()}),'source_role_handoff_native_metadata_changed_during_capture')
    _need(evidence==_evidence(roles,deadline),'source_role_handoff_evidence_changed_during_capture')
    if canonical_inputs is not None:
        current_root=canonical.source_nc._root(board,board_hint)
        _need(current_root is not None and Path(current_root).resolve()==root,
            'source_role_handoff_root_changed_during_capture')
        current_files,current_hashes,_=canonical._hierarchy(root,deadline)
        _need(current_hashes==canonical_inputs['hierarchy']
            and canonical._export_inputs(root,current_files)==canonical_inputs['project_and_library_inputs']
            and force._hash(exporter)==canonical_inputs['exporter_sha256'],
            'source_role_handoff_canonical_inputs_changed_during_capture')
    else:_need(canonical.source_nc._root(board,board_hint)is None,
        'source_role_handoff_root_changed_during_capture')
    payload=dict(schema=1,scope='private_Source_role_phase_input_identity',
        board_pointer=str(_native_pointer(board)),source=str(source),source_sha256=force._hash(source),
        board_hint=board_hint,source_native_binding=binding,native_footprints=footprints,
        family=family,code_epoch=epoch,environment=environment,canonical_inputs=canonical_inputs,
        role_evidence_files=evidence,**literal,admission_authority=False,motion_authority=False)
    encoded=_json(payload);_tick(deadline)
    return dict(payload=json.loads(encoded),sha256=hashlib.sha256(encoded.encode()).hexdigest())


def assert_same(snapshot,board,poses,*,board_hint,roles,options,deadline):
    """Rederive, do not validate a purported caller-owned certificate."""
    fresh=capture(board,poses,board_hint=board_hint,roles=roles,options=options,deadline=deadline)
    _need(_json(snapshot)==_json(fresh),'source_role_handoff_live_inputs_changed')
    return True

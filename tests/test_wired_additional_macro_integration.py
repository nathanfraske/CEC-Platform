"""Adversarial native wired-role integration, not production cut admission."""
import copy
import time

import pcbnew
import pytest
import cec_additional_aggregate_macro as op
import cec_wired_aggregate_ground_leaf as leaves
from cec_native_items import discard_items
from test_wired_aggregate_ground_leaf import fixture
from test_field_proposals import track


def context(tmp_path,monkeypatch,with_supply_boundary=False):
    source,root,parent,pad,ids,poses = fixture(tmp_path,monkeypatch)
    if with_supply_boundary:
        positive = parent.FindFootprintByReference('RENAMED_C').FindPadByNumber('1')
        edge = next(t for t in parent.GetTracks() if t.GetClass() == 'PCB_TRACK'
            and t.GetNetCode() == positive.GetNetCode()
            and positive.GetEffectiveShape(t.GetLayer()).Collide(t.GetEffectiveShape(),0))
        a,b = edge.GetStart(),edge.GetEnd()
        track(parent,positive.GetNetname(),(b.x/1e6,b.y/1e6),
            ((b.x+(b.x-a.x))/1e6,(b.y+(b.y-a.y))/1e6),width=.5)
        leaves.wired.cap.field._save_field_snapshot(parent,source)
        parent = pcbnew.LoadBoard(str(source)); pad = parent.FindFootprintByReference('RENAMED_C').FindPadByNumber('2')
    poses['RENAMED_C'][:2] = [14.,14.]
    roles = op.collect(parent,poses,board_hint=str(root),allow_linear_power_stage_reconstruction=True)
    proposal = dict(scope='source_typed_complete_cell_escape_proposal',poses=poses,board_hint=str(root),
        additional_aggregate_capacitors=roles,allow_linear_power_stage_reconstruction=True,
        allow_owned_locked_escapes=False,source_native_binding=leaves.native.row._source_binding(parent),
        retired_track_uuids=ids,row_plan={})
    child = pcbnew.LoadBoard(str(source)); fp = child.FindFootprintByReference('RENAMED_C')
    fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in poses['RENAMED_C'][:2])))
    discard_items(child,[t for t in child.GetTracks() if leaves.native.force._uid(t) in ids])
    return parent,child,proposal,pad,ids


@pytest.mark.parametrize('fault',['identity','false_flag','integer_flag','owner_pose','owner_pad','cap_pad','parent_dirty'])
def test_wired_context_requires_fresh_identity_exact_owner_and_real_source(tmp_path,monkeypatch,fault):
    parent,child,proposal,pad,ids = context(tmp_path,monkeypatch)
    if fault == 'identity':
        proposal['additional_aggregate_capacitors']['RENAMED_C']['source_wired_identity']['source_sha256'] = '0'*64
    elif fault == 'false_flag': proposal['allow_linear_power_stage_reconstruction'] = False
    elif fault == 'integer_flag': proposal['allow_owned_locked_escapes'] = 1
    elif fault == 'owner_pose': child.FindFootprintByReference('AMP73').Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'owner_pad': child.FindFootprintByReference('AMP73').FindPadByNumber('6').Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'cap_pad': child.FindFootprintByReference('RENAMED_C').FindPadByNumber('1').Move(pcbnew.VECTOR2I(1,0))
    else: parent.FindFootprintByReference('RENAMED_C').Move(pcbnew.VECTOR2I(1,0))
    with pytest.raises(ValueError): op.requests(parent,child,proposal)


def test_existing_wired_inventory_does_not_replace_independent_current_cut_proof(tmp_path,monkeypatch):
    parent,child,proposal,pad,ids = context(tmp_path,monkeypatch)
    positive = parent.FindFootprintByReference('RENAMED_C').FindPadByNumber('1')
    cuts = [t for t in parent.GetTracks() if t.GetClass() == 'PCB_TRACK'
        and t.GetNetCode() == positive.GetNetCode() and positive.GetEffectiveShape(t.GetLayer()).Collide(t.GetEffectiveShape(),0)]
    assert len(cuts) == 1
    uid = leaves.native.force._uid(cuts[0]); proposal['retired_track_uuids'].append(uid)
    discard_items(child,[t for t in child.GetTracks() if leaves.native.force._uid(t) == uid])
    # Refusal sentinel proves the established receiver is called for this
    # exact Source cut; it does NOT stub a successful retirement authority.
    calls = []
    def refuse(board,path,**kwargs):
        calls.append((board,path,kwargs)); raise ValueError('independent_current_cut_refused')
    monkeypatch.setattr(leaves.wired.cap.full,'plan',refuse)
    with pytest.raises(ValueError,match='independent_current_cut_refused'):
        op.requests(parent,child,proposal)
    assert len(calls) == 1 and calls[0][0] is parent
    assert calls[0][2]['retired_track_uuids'] == [uid]


def test_complete_leaf_required_and_immediate_ground_limit_not_inherited_from_old_tail(tmp_path,monkeypatch):
    parent,child,proposal,pad,ids = context(tmp_path,monkeypatch)
    demands = op.requests(parent,child,proposal)
    ground = demands['ground:'+leaves.native.force._uid(pad)]
    assert ground['reach_mm'] == .8
    assert ground['width_nm'] >= 200000
    assert proposal['additional_aggregate_capacitors']['RENAMED_C']['source_Ground_leaf']['source_length_mm'] > .8
    # Existing Source return does not qualify the moved cap's immediate gate.
    moved = child.FindFootprintByReference('RENAMED_C').FindPadByNumber('2')
    assert leaves.wired.cap.cells._existing_return(child,moved,.8,allow_native_track_body=True) is None
    leaf_ids = proposal['additional_aggregate_capacitors']['RENAMED_C']['source_Ground_leaf']['track_uuids']
    proposal['retired_track_uuids'] = [u for u in ids if u != leaf_ids[-1]]
    child = pcbnew.LoadBoard(parent.GetFileName())
    child.FindFootprintByReference('RENAMED_C').SetPosition(pcbnew.VECTOR2I_MM(14,14))
    discard_items(child,[t for t in child.GetTracks()
        if leaves.native.force._uid(t) in proposal['retired_track_uuids']])
    with pytest.raises(ValueError,match='complete_independently_owned_Ground_leaf'):
        op.requests(parent,child,proposal)


def test_real_row_owned_current_cut_gets_explicit_full_width_native_boundary(tmp_path,monkeypatch):
    parent,child,proposal,pad,ids = context(tmp_path,monkeypatch,with_supply_boundary=True)
    positive = parent.FindFootprintByReference('RENAMED_C').FindPadByNumber('1')
    edge = next(t for t in parent.GetTracks() if t.GetClass() == 'PCB_TRACK'
        and t.GetNetCode() == positive.GetNetCode()
        and positive.GetEffectiveShape(t.GetLayer()).Collide(t.GetEffectiveShape(),0))
    uid = leaves.native.force._uid(edge)
    # Actual row-owned retirement, not transport's extra-edge branch.
    proposal['row_plan']['retired_track_uuids'] = [uid]
    discard_items(child,[t for t in child.GetTracks() if leaves.native.force._uid(t) == uid])
    demands = op.requests(parent,child,proposal)
    boundaries = [r for k,r in demands.items() if k.startswith('aggregate_incident_cut:')]
    assert len(boundaries) == 1
    request = boundaries[0]
    assert request['kind'] == 'source_boundary' and request['width_nm'] == 500000
    assert request['source_full_current_incident_cut_plan']['retired_track_uuids'] == [uid]
    assert request['b']['native_uuids'] and uid not in request['b']['native_uuids']
    assert request['every_surviving_source_component_port_mandatory']
    cap = leaves.wired.cap; source = parent.GetFileName()
    with pytest.raises(ValueError):
        cap.ports.full_width_connection(parent,child,source,request,proposal['board_hint'],time.monotonic()+2.)
    a,b = request['a']['at_nm'],request['b']['at_nm']
    track(child,request['net'],tuple(v/1e6 for v in a),tuple(v/1e6 for v in b),width=.5)
    observed = cap.ports.full_width_connection(parent,child,source,request,proposal['board_hint'],time.monotonic()+2.)
    assert observed['all_named_contacts_connected'] and observed['all_used_strokes_meet_source_and_aggregate_width']


@pytest.mark.parametrize('fault',['moved_boundary','co_cut_boundary','thin_restore'])
def test_current_boundary_projection_cannot_borrow_unproved_motion_cut_or_thin_copper(tmp_path,monkeypatch,fault):
    parent,child,proposal,pad,ids = context(tmp_path,monkeypatch,with_supply_boundary=True)
    positive = parent.FindFootprintByReference('RENAMED_C').FindPadByNumber('1')
    edge = next(t for t in parent.GetTracks() if t.GetClass() == 'PCB_TRACK'
        and t.GetNetCode() == positive.GetNetCode()
        and positive.GetEffectiveShape(t.GetLayer()).Collide(t.GetEffectiveShape(),0))
    uid = leaves.native.force._uid(edge); proposal['row_plan']['retired_track_uuids'] = [uid]
    discard_items(child,[t for t in child.GetTracks() if leaves.native.force._uid(t) == uid])
    demands = op.requests(parent,child,proposal)
    request, = [r for k,r in demands.items() if k.startswith('aggregate_incident_cut:')]
    retained_uid, = request['b']['native_uuids']
    retained = next(t for t in child.GetTracks() if leaves.native.force._uid(t) == retained_uid)
    if fault == 'moved_boundary':
        retained.Move(pcbnew.VECTOR2I(1,0))
        with pytest.raises(ValueError,match='conductor_motion_needs_typed_projection'):
            op.requests(parent,child,proposal)
    elif fault == 'co_cut_boundary':
        discard_items(child,[retained])
        with pytest.raises(ValueError,match='co_cut_needs_separate_projection'):
            op.requests(parent,child,proposal)
    else:
        a,b = request['a']['at_nm'],request['b']['at_nm']
        track(child,request['net'],tuple(v/1e6 for v in a),tuple(v/1e6 for v in b),width=.2)
        with pytest.raises(ValueError):
            leaves.wired.cap.ports.full_width_connection(parent,child,parent.GetFileName(),request,
                proposal['board_hint'],time.monotonic()+2.)

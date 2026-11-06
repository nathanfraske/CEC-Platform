"""Real canonical/native wired reservoir leaf; no supply ownership inferred."""
from pathlib import Path
import copy
import time

import pcbnew
import pytest
import cec_wired_aggregate_ground_leaf as op
from test_aggregate_cap_ground_leaf import fixture as ground_fixture, save
from test_field_proposals import track


def fixture(tmp_path, monkeypatch, quarter=0, back=False):
    source,root,board,pad,ids,peer = ground_fixture(tmp_path,monkeypatch,quarter)
    fp = pad.GetParentFootprint(); positive = fp.FindPadByNumber('1')
    at = positive.GetPosition(); other = pad.GetPosition()
    track(board,positive.GetNetname(),(at.x/1e6,at.y/1e6),
        ((at.x+(at.x-other.x))/1e6,(at.y+(at.y-other.y))/1e6),width=.5)
    if back:
        for f in board.GetFootprints(): f.Flip(pcbnew.VECTOR2I(0,0),True)
        for t in board.GetTracks(): t.Flip(pcbnew.VECTOR2I(0,0),True)
        for z in board.Zones(): z.Flip(pcbnew.VECTOR2I(0,0),True)
    board = save(board,source); fp = board.FindFootprintByReference('RENAMED_C')
    pad = fp.FindPadByNumber('2')
    poses = {ref:[f.GetPosition().x/1e6,f.GetPosition().y/1e6,f.GetOrientationDegrees()]
        for ref in ('RENAMED_C','AMP73') for f in [board.FindFootprintByReference(ref)]}
    poses['RENAMED_C'][0] += .1
    return source,root,board,pad,ids,poses


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_positive_wired_identity_native_leaf_and_fresh_replay(tmp_path,monkeypatch,quarter,back):
    source,root,board,pad,ids,poses = fixture(tmp_path,monkeypatch,quarter,back)
    before = op.native.row._source_binding(board); raw = source.read_bytes()
    proof = op.plan(board,op.native.force._uid(pad),poses,board_hint=str(root))
    assert proof['scope'] == op.SCOPE and proof['track_uuids'] == ids
    assert proof['wired_identity']['source_terminal_contacts']
    assert proof['boundary_uuids'] and proof['maximum_new_Ground_return_mm'] == .8
    assert proof['no_selected_bypass_alias'] and proof['native_partition_receiving_required']
    assert not proof['supply_trace_retirement_authority']
    assert not proof['new_barrel_authority'] and not proof['current_authority']
    assert op.replay(board,proof) == proof
    assert source.read_bytes() == raw and op.native.row._source_binding(board) == before


def test_locks_are_reported_only_under_explicit_policy_without_mutation(tmp_path,monkeypatch):
    source,root,board,pad,ids,poses = fixture(tmp_path,monkeypatch)
    edge = next(t for t in board.GetTracks() if op.native.force._uid(t) == ids[0])
    edge.SetLocked(True); board = save(board,source)
    uid = op.native.force._uid(pad); before = op.native.row._source_binding(board)
    with pytest.raises(ValueError): op.plan(board,uid,poses,board_hint=str(root))
    proof = op.plan(board,uid,poses,board_hint=str(root),allow_owned_locked_escapes=True)
    assert proof['locked_owned_track_uuids'] == [ids[0]]
    assert proof['exact_locked_uuid_consent_required']
    assert proof['source_edges'][0]['locked'] is True
    assert op.native.row._source_binding(board) == before


@pytest.mark.parametrize('fault',['strictbool','group','interior','missing_owner','forged','dirty'])
def test_no_membership_or_inventory_waiver(tmp_path,monkeypatch,fault):
    source,root,board,pad,ids,poses = fixture(tmp_path,monkeypatch)
    uid = op.native.force._uid(pad); opts = {}
    if fault == 'strictbool': opts['allow_owned_locked_escapes'] = 1
    elif fault == 'missing_owner': poses.pop('AMP73')
    elif fault == 'dirty': pad.Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'forged':
        proof = op.plan(board,uid,poses,board_hint=str(root)); proof = copy.deepcopy(proof)
        proof['maximum_new_Ground_return_mm'] = 1.35
        with pytest.raises(ValueError): op.replay(board,proof)
        return
    else:
        edge = next(t for t in board.GetTracks() if op.native.force._uid(t) == ids[0])
        if fault == 'group':
            g = pcbnew.PCB_GROUP(board); board.Add(g); g.AddItem(edge)
        else:
            a,b = edge.GetStart(),edge.GetEnd(); xy = ((a.x+b.x)/2e6,(a.y+b.y)/2e6)
            track(board,'GND',(xy[0]-1,xy[1]),(xy[0]+1,xy[1]),width=.5)
        board = save(board,source)
    with pytest.raises(ValueError): op.plan(board,uid,poses,board_hint=str(root),**opts)


@pytest.mark.parametrize('case',['exact','offset','drilled_away','interior_through'])
def test_exact_drilled_annulus_endpoint_is_not_a_proximity_waiver(case):
    board = pcbnew.BOARD()
    edge = track(board,'GND',(5,5),(7,5),width=.2)
    fp = pcbnew.FOOTPRINT(board); fp.SetReference('UNNAMED'); board.Add(fp)
    pad = pcbnew.PAD(fp); pad.SetNumber('2'); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
    mask = pcbnew.LSET(); mask.AddLayer(pcbnew.F_Cu); pad.SetLayerSet(mask); pad.SetNet(edge.GetNet())
    fp.Add(pad); pad.SetPosition(pcbnew.VECTOR2I_MM(5,5))
    via = pcbnew.PCB_VIA(board); via.SetNet(edge.GetNet()); via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetWidth(200000 if case == 'drilled_away' else 500000); via.SetDrill(300000)
    via.SetPosition(pcbnew.VECTOR2I_MM(7 if case in ('exact','drilled_away') else 6.7 if case == 'offset' else 6,5))
    board.Add(via)
    if case == 'exact':
        proof = op._walk(board,pad,200000,pcbnew.F_Cu,time.monotonic()+2.)
        assert proof['track_uuids'] == [op.native.force._uid(edge)]
        assert proof['boundary_uuids'] == [op.native.force._uid(via)]
        assert proof['actual_contact_ledger'][0]['actual_lower_contact_nm2'] > 0
    else:
        with pytest.raises(ValueError): op._walk(board,pad,200000,pcbnew.F_Cu,time.monotonic()+2.)


def test_fresh_distinct_single_edge_dispatch_cannot_alias_isolated_role(tmp_path,monkeypatch):
    import cec_additional_aggregate_macro as aggregate
    source,root,board,pad,ids,poses = fixture(tmp_path,monkeypatch)
    roles = aggregate.collect(board,poses,board_hint=str(root),allow_linear_power_stage_reconstruction=True)
    proposal = dict(scope='source_typed_complete_cell_escape_proposal',poses=poses,board_hint=str(root),
        source_native_binding=op.native.row._source_binding(board),additional_aggregate_capacitors=roles,
        allow_linear_power_stage_reconstruction=True,allow_owned_locked_escapes=False)
    rows = op.single_edge_ownerships(board,proposal,ids,deadline=time.monotonic()+8.)
    assert len(rows) == len(ids) and all(op.authority_label(r['authority']) for r in rows)
    assert all(not op.native.authority_label(r['authority']) for r in rows)
    for field in ('scope','return','current','supply','root'):
        bad = copy.deepcopy(rows[0]['authority']); leaf = bad['source_wired_aggregate_Ground_leaf']
        if field == 'scope': leaf['scope'] = op.native.SCOPE
        elif field == 'return': leaf['maximum_new_Ground_return_mm'] = 1.35
        elif field == 'current': leaf['current_authority'] = True
        elif field == 'supply': leaf['supply_trace_retirement_authority'] = True
        else: bad['source_Ground_root']['selected_bypass'] = True
        assert not op.authority_label(bad)
    proposal['additional_aggregate_capacitors']['RENAMED_C']['source_Ground_leaf']['width_nm'] -= 1
    with pytest.raises(ValueError):
        op.single_edge_ownerships(board,proposal,ids,deadline=time.monotonic()+8.)

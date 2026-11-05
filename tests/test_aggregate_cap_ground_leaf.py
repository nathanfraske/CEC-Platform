"""Canonical additional-cap Ground leaf: distinct role, native actual metal.

Only the existing aggregate-current model is fixture-stubbed. Canonical
schematic exports, selected minima, saved geometry and Ground class are real.
"""
import copy
import json
import time

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest

import cec_aggregate_cap_ground_leaf as op
import cec_additional_aggregate_macro as aggregate
import cec_source_aggregate_capacitor_cell as cap
from cec_native_items import discard_items
from test_source_aggregate_capacitor_cell import fixture as canonical_fixture
from test_field_proposals import track


def fixture(tmp_path, monkeypatch, quarter=0):
    source, root, _ = canonical_fixture(tmp_path, monkeypatch)
    board = pcbnew.LoadBoard(str(source)); fp = board.FindFootprintByReference('RENAMED_C')
    ground = fp.FindPadByNumber('2'); peer = board.FindFootprintByReference('EXISTING_FEED').FindPadByNumber('2')
    a = tuple(v/1e6 for v in ground.GetPosition()); z = tuple(v/1e6 for v in peer.GetPosition())
    points = [a, (a[0]+2, z[1]-3), (z[0], z[1]-3), z]
    ids = []
    for first, last in zip(points, points[1:]):
        edge = track(board, 'GND', first, last, width=.5); ids.append(cap.force._uid(edge))
    if quarter:
        origin = pcbnew.VECTOR2I_MM(15,15); angle = pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(), *board.GetTracks(), *board.Zones()]: item.Rotate(origin, angle)
    cap.field._save_field_snapshot(board, source)
    project = source.with_suffix('.kicad_pro'); data = json.loads(project.read_text())
    data.setdefault('net_settings', {}).setdefault('classes', []).append(dict(name='EXACT_RETURN',
        track_width=.5, clearance=.2, via_diameter=.9, via_drill=.4))
    data['net_settings']['netclass_assignments'] = data['net_settings'].get('netclass_assignments') or {}
    data['net_settings']['netclass_assignments']['GND'] = 'EXACT_RETURN'
    project.write_text(json.dumps(data))
    board = pcbnew.LoadBoard(str(source)); fp = board.FindFootprintByReference('RENAMED_C')
    return source, root, board, fp.FindPadByNumber('2'), ids, cap.force._uid(peer)


def save(board, source):
    cap.field._save_field_snapshot(board, source)
    return pcbnew.LoadBoard(str(source))


@pytest.mark.parametrize('quarter', range(4))
def test_renamed_rotated_positive_canonical_additional_leaf(tmp_path, monkeypatch, quarter):
    source, root, board, pad, ids, peer = fixture(tmp_path, monkeypatch, quarter)
    raw = source.read_bytes(); before = cap.row._source_binding(board)
    proof = op.plan(board, cap.force._uid(pad), board_hint=str(root))
    assert proof['scope'] == op.SCOPE and proof['track_uuids'] == ids
    assert proof['boundary_uuids'] == [peer]
    assert proof['width_nm'] == 500000 and proof['source_length_mm'] <= 12
    assert proof['unchanged_selected_bypass_assignments']['AMP73:6:100n'] == 'EXISTING_FEED'
    assert proof['canonical_source']['symbol_kind'] == 'C'
    assert proof['maximum_new_Ground_return_mm'] == .8
    assert proof['every_retained_boundary_and_Source_partition_mandatory']
    assert proof['retained_barrel_uuids'] and not set(proof['retained_barrel_uuids']) & set(ids)
    assert proof['no_selected_bypass_alias'] and not proof['Ground_current_or_ampacity_credit']
    assert not proof['current_authority'] and not proof['new_barrel_authority'] and not proof['release_authority']
    assert source.read_bytes() == raw and before == cap.row._source_binding(board)


@pytest.mark.parametrize('fault', ['native_move','wrong_pin','wrong_class','foreign_root','foreign_interior',
    'Ground_interior','root_barrel','grouped','locked_root','locked_successor','unknown_fill',
    'missing_boundary','supply_attached','missing_minimum'])
def test_unknown_or_shared_actual_material_never_borrows_additional_cap_authority(tmp_path, monkeypatch, fault):
    source, root, board, pad, ids, peer = fixture(tmp_path, monkeypatch)
    tracks = {cap.force._uid(t):t for t in board.GetTracks()}; first = tracks[ids[0]]
    pad_uuid = cap.force._uid(pad)
    if fault == 'native_move': pad.Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'wrong_pin': pad_uuid = cap.force._uid(pad.GetParentFootprint().FindPadByNumber('1'))
    elif fault == 'wrong_class':
        data=json.loads(source.with_suffix('.kicad_pro').read_text())
        data['net_settings']['classes'][-1]['track_width']=.6
        source.with_suffix('.kicad_pro').write_text(json.dumps(data))
    elif fault in ('foreign_root','foreign_interior','Ground_interior'):
        at=pad.GetPosition() if fault=='foreign_root' else pcbnew.VECTOR2I(
            (first.GetStart().x+first.GetEnd().x)//2,(first.GetStart().y+first.GetEnd().y)//2)
        xy=tuple(v/1e6 for v in at)
        track(board, 'GND' if fault=='Ground_interior' else '/ALPHA',
            (xy[0]-1,xy[1]),(xy[0]+1,xy[1]),width=.5)
        if fault.startswith('foreign'):
            # KiCad's loader can normalize a floating shorted foreign track.
            # Exercise this native material refusal without saving that fault;
            # dirty-parent rejection is independently tested above.
            with pytest.raises(ValueError,match='foreign'):
                op._walk(board,pad,500000,pcbnew.F_Cu,time.monotonic()+2.)
            return
        board=save(board,source)
    elif fault == 'root_barrel':
        via=next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA')
        via.SetPosition(pad.GetPosition());board=save(board,source)
    elif fault == 'grouped':
        group=pcbnew.PCB_GROUP(board);board.Add(group);group.AddItem(first);board=save(board,source)
    elif fault.startswith('locked'):
        tracks[ids[0]if fault=='locked_root'else ids[1]].SetLocked(True);board=save(board,source)
    elif fault == 'unknown_fill':
        z=pcbnew.ZONE(board);z.SetNet(pad.GetNet());z.SetLayer(pcbnew.F_Cu)
        poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
        for xy in ((10,7),(13,7),(13,10),(10,10)):poly.Append(round(xy[0]*1e6),round(xy[1]*1e6))
        z.Outline().Append(poly);board.Add(z);board=save(board,source)
    elif fault == 'missing_boundary':
        # A changed class successor is retained, not silently consumed. Here
        # remove only the final leaf edge, leaving the first two dangling.
        discard_items(board,[tracks[ids[-1]]]);board=save(board,source)
    elif fault == 'supply_attached':
        p=pad.GetParentFootprint().FindPadByNumber('1');at=tuple(v/1e6 for v in p.GetPosition())
        track(board,'/ALPHA',at,(at[0]-1,at[1]),width=.5);board=save(board,source)
    else:
        board.FindFootprintByReference('EXISTING_FEED').Move(pcbnew.VECTOR2I_MM(10,0));board=save(board,source)
    before=cap.row._source_binding(board)
    with pytest.raises(ValueError):op.plan(board,pad_uuid,board_hint=str(root))
    assert before==cap.row._source_binding(board)


def test_actual_retained_barrel_and_branch_are_boundary_not_retired(tmp_path, monkeypatch):
    source, root, board, pad, ids, _ = fixture(tmp_path, monkeypatch)
    last=next(t for t in board.GetTracks()if cap.force._uid(t)==ids[1]);at=last.GetEnd()
    via=next(t for t in board.GetTracks()if t.GetClass()=='PCB_VIA');via.SetPosition(at)
    board=save(board,source);proof=op.plan(board,cap.force._uid(pad),board_hint=str(root))
    assert proof['track_uuids']==ids[:2]
    assert cap.force._uid(via) in proof['boundary_uuids']
    assert ids[-1] in proof['boundary_uuids'] and ids[-1] not in proof['track_uuids']


def test_macro_only_retires_complete_fresh_leaf_not_arbitrary_incident_metal(tmp_path, monkeypatch):
    source,root,parent,pad,ids,_=fixture(tmp_path,monkeypatch)
    fp=pad.GetParentFootprint();owner=parent.FindFootprintByReference('AMP73')
    poses={fp.GetReference():[14,14,fp.GetOrientationDegrees()],
        owner.GetReference():[owner.GetPosition().x/1e6,owner.GetPosition().y/1e6,owner.GetOrientationDegrees()]}
    roles=aggregate.collect(parent,poses,board_hint=str(root))
    assert roles['RENAMED_C']['source_Ground_leaf']['track_uuids']==ids
    assert roles['RENAMED_C']['no_Source_copper_retirement'] is False
    assert roles['RENAMED_C']['Source_Ground_leaf_retirement_requires_fresh_independent_ownership'] is True
    proposal=dict(poses=poses,board_hint=str(root),additional_aggregate_capacitors=roles,
        reference_group_uuids=[],retired_track_uuids=[],row_plan={},
        source_native_binding=cap.row._source_binding(parent),scope='source_typed_complete_cell_escape_proposal')
    child=pcbnew.LoadBoard(str(source));child.FindFootprintByReference('RENAMED_C').SetPosition(pcbnew.VECTOR2I_MM(14,14))
    with pytest.raises(ValueError):aggregate.requests(parent,child,proposal)
    proposal['retired_track_uuids']=ids
    discard_items(child,[t for t in child.GetTracks()if cap.force._uid(t)in ids])
    demands=aggregate.requests(parent,child,proposal)
    assert demands['ground:'+cap.force._uid(pad)]['reach_mm']==.8
    authorities=op.single_edge_ownerships(parent,proposal,ids,deadline=time.monotonic()+8.)
    assert len(authorities)==len(ids) and all(op.authority_label(r['authority'])for r in authorities)
    assert all(r['authority']['kind']==op.KIND for r in authorities)
    for fault in ('kind','width','root_role','root_current','leaf_current','partition','return','boundary'):
        forged=copy.deepcopy(authorities[0]['authority'])
        if fault=='kind':forged['kind']='positive_existing_low_power_ground_boundary'
        elif fault=='width':forged['source_width_nm']-=1
        elif fault=='root_role':forged['source_Ground_root']['role']='ground'
        elif fault=='root_current':forged['source_Ground_root']['current_authority']=True
        elif fault=='leaf_current':forged['source_aggregate_cap_Ground_leaf']['current_authority']=True
        elif fault=='partition':forged['source_aggregate_cap_Ground_leaf']['native_partition_receiving_required']=False
        elif fault=='return':forged['source_aggregate_cap_Ground_leaf']['maximum_new_Ground_return_mm']=.81
        else:forged['source_aggregate_cap_Ground_leaf']['boundary_uuids']=[]
        assert not op.authority_label(forged)
    proposal['additional_aggregate_capacitors']['RENAMED_C']['source_Ground_leaf']['width_nm']=499999
    with pytest.raises(ValueError):op.single_edge_ownerships(parent,proposal,ids,deadline=time.monotonic()+8.)


@pytest.mark.parametrize('fault',['missing_current','changed_current','incomplete_domain'])
def test_positive_full_rail_model_is_mandatory_never_a_Ground_ampacity_budget(tmp_path,monkeypatch,fault):
    source,root,board,pad,_,_=fixture(tmp_path,monkeypatch)
    original=cap.full._model
    if fault=='missing_current':monkeypatch.setattr(cap.cells,'_supply_current_widths',lambda *a:None)
    elif fault=='changed_current':monkeypatch.setattr(cap.cells,'_supply_current_widths',lambda *a:dict(current_authority={}))
    else:
        def incomplete(*args):
            kind,domain,contract=original(*args);domain['complete']=False;return kind,domain,contract
        monkeypatch.setattr(cap.full,'_model',incomplete)
    with pytest.raises(ValueError):op.plan(board,cap.force._uid(pad),board_hint=str(root))

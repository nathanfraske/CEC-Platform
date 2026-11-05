"""Existing address entries use the shared real via-throat classifier.

The generated matching schematic/netlist comes from the canonical fixture;
native geometry, manufacturer roles, process and endpoint verdicts are real.
No routing or receiving success is mocked.
"""
import copy
import json
import math
from pathlib import Path

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_macro_new_ground_dogbone as op
from test_retained_address_ground import fixture as canonical_fixture


def fixture(tmp_path,monkeypatch,quarter=0,back=False):
    facts=canonical_fixture(tmp_path,monkeypatch,turn=0,back=back)
    parent,unused,unused_proposal,unused_requests,uid,vid,tid,gid,*_=facts
    source=Path(parent.GetFileName())
    pad=next(p for f in parent.GetFootprints()for p in f.Pads()if force._uid(p)==uid)
    # The canonical fixture serializes pin centres in a row. Put the long
    # land perpendicular to that row, like a real fine-pitch package row.
    pad.SetSize(pcbnew.VECTOR2I_MM(1.45,.3));pad.SetOrientationDegrees(90)
    at=tuple(pad.GetPosition());face=next(iter(pad.GetLayerSet().CuStack()))
    track=next(t for t in parent.GetTracks()if force._uid(t)==tid)
    track.SetStart(pcbnew.VECTOR2I(at[0],at[1]-715000))
    track.SetEnd(pcbnew.VECTOR2I(at[0],at[1]-1050000));track.SetWidth(200000)
    via=next(t for t in parent.GetTracks()if force._uid(t)==vid)
    next(g for g in parent.Groups()if force._uid(g)==gid).RemoveItem(via)
    via.SetPosition(pcbnew.VECTOR2I(at[0],at[1]-1400000))
    group=pcbnew.PCB_GROUP(parent);group.SetName(fr.ENDPOINT_NECKDOWN_GROUP)
    parent.Add(group);group.AddItem(track)
    field._save_field_snapshot(parent,source)
    project=source.with_suffix('.kicad_pro')
    data=(json.loads(project.read_text())if project.is_file()else dict(
        board=dict(design_settings=dict(rules={})),net_settings=dict(classes=[dict(
            name='Default',track_width=.2,clearance=.2,via_diameter=.9,via_drill=.5)])))
    ground=copy.deepcopy(data['net_settings']['classes'][0]);ground.update(
        name='SYNTHETIC_PREFERRED_GROUND',track_width=.5,clearance=.2)
    data['net_settings']['classes'].append(ground)
    data['net_settings']['netclass_assignments']=dict(data['net_settings'].get('netclass_assignments')or{})
    data['net_settings']['netclass_assignments']['GND']=ground['name']
    data['board']['design_settings']['rules']['min_track_width']=.2
    project.write_text(json.dumps(data))
    additive.bind_local_endpoint_rule(parent,source)
    parent=pcbnew.LoadBoard(str(source));child=pcbnew.LoadBoard(str(source))
    owner=next(f for f in child.GetFootprints()if any(force._uid(p)==uid for p in f.Pads()))
    pose=[owner.GetPosition().x/1e6+8,owner.GetPosition().y/1e6+4,
          owner.GetOrientationDegrees()+90*quarter]
    owner.SetPosition(pcbnew.VECTOR2I_MM(*pose[:2]));owner.SetOrientationDegrees(pose[2])
    pad=next(p for p in owner.Pads()if force._uid(p)==uid)
    angle=math.radians(pad.GetOrientationDegrees())
    # Leave a real 1um interior margin to the unchanged .335mm Source limit;
    # do not relax it to absorb the native last-inside lattice boundary.
    vector=[round(1059000*math.cos(angle)),round(-1059000*math.sin(angle))]
    menu=op.fab.local_pofv_geometry_candidates(op.fab.get_profile(op.fab.board_profile_name(parent)),board=parent)
    index=min((i for i,g in enumerate(menu)if tuple(round(v*1e6)for v in
        op.fab.board_legal_through_via_geometry(parent,*g)[:2])==tuple(round(v*1e6)for v in g)
        and round(g[0]*1e6)>=500000),key=lambda i:menu[i][0])
    request=dict(owner_pad_uuid=uid,geometry_index=index,
        position_nm=[pad.GetPosition().x+vector[0],pad.GetPosition().y+vector[1]])
    proposal=dict(source_native_binding=row._source_binding(parent),
        board_hint=str(source),poses={owner.GetReference():pose})
    return source,parent,child,proposal,pad,request


def materialize(board,pad,ops):
    items=[]
    for value in ops:
        if value[0]=='via':item=op._column(board,pad,value[1],round(value[3]*1e6),round(value[2]*1e6))
        else:
            item=pcbnew.PCB_TRACK(board);item.SetNet(pad.GetNet());item.SetLayer(value[4])
            item.SetStart(pcbnew.VECTOR2I(*value[1]));item.SetEnd(pcbnew.VECTOR2I(*value[2]));item.SetWidth(value[3])
        board.Add(item);items.append(item)
    return {force._uid(i)for i in items}


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_source_entry_and_saved_via_throat_all_cardinal_faces(tmp_path,monkeypatch,quarter,back):
    source,parent,child,proposal,pad,request=fixture(tmp_path,monkeypatch,quarter,back)
    geometry=op.fab.local_pofv_geometry_candidates(op.fab.get_profile(op.fab.board_profile_name(parent)),board=parent)[request['geometry_index']]
    column=op._column(child,pad,request['position_nm'],round(geometry[0]*1e6),round(geometry[1]*1e6))
    assert not pad.GetEffectiveShape(next(iter(pad.GetLayerSet().CuStack()))).Collide(
        column.GetEffectiveShape(next(iter(pad.GetLayerSet().CuStack()))),0),dict(
            geometry=geometry,pad_at=list(pad.GetPosition()),via=request['position_nm'],
            pad_size=list(pad.GetSize()),pad_angle=pad.GetOrientationDegrees(),
            bbox=[pad.GetBoundingBox().GetX(),pad.GetBoundingBox().GetY(),
                pad.GetBoundingBox().GetWidth(),pad.GetBoundingBox().GetHeight()])
    excluded=fr._via_pad_excluded(child,column.GetPosition(),round(geometry[0]*1e6),
        round(geometry[1]*1e6),pad.GetNetCode())
    assert excluded is None,dict(excluded=str(excluded),geometry=geometry,
        ref=excluded.GetParentFootprint().GetReference(),pin=excluded.GetNumber(),
        at=list(excluded.GetPosition()),net=excluded.GetNetname(),
        owner_positions=[(f.GetReference(),list(f.GetPosition()))for f in child.GetFootprints()])
    raw=source.read_bytes();before=[row._source_binding(b)for b in(parent,child)]
    proofs,_=op.plan(parent,child,proposal,[request]);proof=proofs[0]
    assert proof['source_device_attachment']['manufacturer_role']=='address'
    assert proof['width_nm']==500000
    assert proof['source_address_entry']['entry_width_nm']==200000
    assert proof['maximum_surface_path_mm']==pytest.approx(.335,abs=1e-9)
    assert proof['source_return_mm']==pytest.approx(.335,abs=1e-9)
    op.rederive(child,proof)
    offer,detail=op.entry_ops(child,proof)
    assert offer and detail['found'],detail
    assert {o[3]for o in offer if o[0]=='trk'}=={200000}
    assert detail['source_address_entry_native_geometry']['full_class_native_via_throat_received']
    assert before==[row._source_binding(b)for b in(parent,child)] and source.read_bytes()==raw
    incoming=materialize(child,pad,offer)
    observed=op.receive(child,proofs,incoming)
    assert observed[0]['source_address_entry_native_geometry']['shared_native_endpoint_classifier']
    assert not observed[0]['literal_incoming_full_class_surface_stub_received']
    assert observed[0]['incoming_native_surface_path_mm']<=proof['maximum_surface_path_mm']
    assert not observed[0]['current_qualified'] and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['missing_group','wrong_group','wrong_width','functional_ground','small_barrel'])
def test_no_new_generic_ground_narrowing_or_smaller_throat(tmp_path,monkeypatch,fault):
    source,parent,child,proposal,pad,request=fixture(tmp_path,monkeypatch)
    original=next(p for f in parent.GetFootprints()for p in f.Pads()if force._uid(p)==force._uid(pad))
    device=op._device_attachment(parent,original,proposal)
    width=500000;escape=(200000,1175000);diameter=600000
    group=next(g for g in parent.Groups()if g.GetName()==fr.ENDPOINT_NECKDOWN_GROUP)
    if fault=='missing_group':
        for item in list(group.GetItems()):group.RemoveItem(item)
    elif fault=='wrong_group':group.SetName('not_source_endpoint_ownership')
    elif fault=='wrong_width':next(iter(group.GetItems())).SetWidth(199999)
    elif fault=='functional_ground':
        pin=next(p for p in original.GetParentFootprint().Pads()if p.GetNumber()=='7')
        assert op.roles.footprint_contract(pin.GetParentFootprint())['pins']['7']=='ground'
        device=dict(device,manufacturer_role='ground');original=pin
    else:diameter=499999
    assert op._source_address_entry(parent,original,device,width,escape,diameter,
        op.time.monotonic()+2.)is None


@pytest.mark.parametrize('fault',['width','source_width','manufacturer_role','source_track','class_width'])
def test_rederive_rejects_forged_entry_records(tmp_path,monkeypatch,fault):
    source,parent,child,proposal,pad,request=fixture(tmp_path,monkeypatch)
    proofs,_=op.plan(parent,child,proposal,[request]);proof=copy.deepcopy(proofs[0])
    entry=proof['source_address_entry']
    if fault=='width':proof['endpoint_escape'][0]-=1
    elif fault=='source_width':entry['entry_width_nm']-=1
    elif fault=='manufacturer_role':entry['manufacturer_role_unchanged']='ground'
    elif fault=='source_track':entry['source_tracks'][0]['width_nm']-=1
    else:proof['width_nm']-=1
    with pytest.raises(ValueError):op.rederive(child,proof)


def test_saved_shared_geometry_is_not_an_inherited_positive_flag(tmp_path,monkeypatch):
    source,parent,child,proposal,pad,request=fixture(tmp_path,monkeypatch)
    proofs,_=op.plan(parent,child,proposal,[request]);proof=proofs[0]
    ops,_=op.entry_ops(child,proof);assert ops
    incoming=materialize(child,pad,ops)
    # Native copper still connects, but a changed barrel cannot borrow the
    # old positive flag or supply the promised complete class-width throat.
    via=next(t for t in child.GetTracks()if force._uid(t)in incoming and t.GetClass()=='PCB_VIA')
    via.SetWidth(proof['width_nm']-1)
    with pytest.raises(ValueError):op.receive(child,proofs,incoming)


def test_serialized_saved_entry_and_exact_source_are_reobserved(tmp_path,monkeypatch):
    source,parent,child,proposal,pad,request=fixture(tmp_path,monkeypatch)
    proofs,_=op.plan(parent,child,proposal,[request]);proof=proofs[0]
    ops,_=op.entry_ops(child,proof);assert ops
    incoming=materialize(child,pad,ops)
    group=next(g for g in child.Groups()if g.GetName()==fr.ENDPOINT_NECKDOWN_GROUP)
    for item in child.GetTracks():
        if force._uid(item)in incoming and item.GetClass()=='PCB_TRACK':group.AddItem(item)
    candidate=force._copy_family(source,tmp_path/'actual-saved-entry')
    field._save_field_snapshot(child,candidate)
    loaded=pcbnew.LoadBoard(str(candidate))
    result=op.receive(loaded,json.loads(json.dumps(proofs)),incoming)
    assert result[0]['source_address_entry_native_geometry']['shared_native_endpoint_classifier']
    assert result[0]['incoming_native_surface_path_mm']<=.335
    source.write_bytes(source.read_bytes()+b'\n')
    with pytest.raises(ValueError):op.receive(loaded,proofs,incoming)


def test_forged_receiving_width_cannot_retype_actual_source_class(tmp_path,monkeypatch):
    source,parent,child,proposal,pad,request=fixture(tmp_path,monkeypatch)
    proofs,_=op.plan(parent,child,proposal,[request]);proof=proofs[0]
    ops,_=op.entry_ops(child,proof);assert ops
    incoming=materialize(child,pad,ops)
    forged=copy.deepcopy(proofs)
    forged[0]['width_nm']-=1
    forged[0]['source_address_entry']['preferred_class_width_nm']-=1
    with pytest.raises(ValueError):op.receive(child,forged,incoming)

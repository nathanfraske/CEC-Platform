"""A reconstructed Ground cut owes exact endpoints, not an echo trace."""
import copy
import time
from pathlib import Path

import pcbnew
import pytest
import cec_complete_cell_receiving as saved
import cec_source_ground_boundary_connection as observer
import cec_field_coupling as field
from cec_native_items import discard_items
from test_source_ground_boundary_connection import fixture as base_fixture


def fixture(tmp_path,monkeypatch,quarter=0,back=False):
    parent,unused,old,unused_requests,proposal=base_fixture(tmp_path,monkeypatch,quarter,back)
    # Keep the fixture's original one-reference Source contract. A fixed
    # Source fragment is a reconstruction debt unless it has both reference
    # entries. This tests connectivity, not whole-board reference qualification.
    for z in list(parent.Zones()):
        if z.GetLayer()==pcbnew.In4_Cu:parent.Remove(z)
    source=Path(parent.GetFileName());field._save_field_snapshot(parent,source)
    parent=pcbnew.LoadBoard(str(source))
    proposal=observer.escape.prepare(parent,proposal['poses'],board_hint='opaque')
    board=pcbnew.LoadBoard(str(source));observer.escape.apply_private(board,proposal)
    requests=observer.escape.obligations(parent,board,proposal)
    cuts={k:r for k,r in requests.items()if r['kind']=='ground_boundary'}
    assert len(cuts)==1
    key,request=next(iter(cuts.items()))
    points={tuple(r['a']['at_nm'])for r in requests.values()if r['kind']=='ground'}
    for point in points:
        via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet('GND'));via.SetPosition(pcbnew.VECTOR2I(*point))
        via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    return parent,board,key,request,requests,proposal


def observe(parent,board,key,requests,proposal):
    return observer.observe_many(parent,board,requests,board_hint='opaque',source_proposal=proposal)[key]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_source_recompile_and_filled_island_reconnect_without_surface_echo(tmp_path,monkeypatch,quarter,back):
    parent,board,key,request,requests,proposal=fixture(tmp_path,monkeypatch,quarter,back)
    before=[observer.row._source_binding(b)for b in(parent,board)]
    proof=observe(parent,board,key,requests,proposal)
    assert proof and proof['all_named_contacts_connected']
    assert proof['actual_native_filled_island_connectivity_proved']and not proof['whole_zone_uuid_connectivity_credit']
    assert proof['independently_received_local_ground_returns']
    assert proof['new_copper']==proof['new_holes']==0 and not proof['routing_admitted']
    assert not proof['current_qualified']and not proof['release_authority']
    assert before==[observer.row._source_binding(b)for b in(parent,board)]


@pytest.mark.parametrize('fault',['point','source_binding','cut_identity','class_width','missing_ground',
    'changed_pad','changed_role','removed_fixed_via','no_fills','custom_pad','foreign_via'])
def test_forged_source_or_unconnected_named_contact_refuses(tmp_path,monkeypatch,fault):
    parent,board,key,request,requests,proposal=fixture(tmp_path,monkeypatch)
    uid=request['a']['pad_uuid'];pad=next(p for f in board.GetFootprints()for p in f.Pads()if observer.force._uid(p)==uid)
    if fault=='point':request['b']['at_nm'][0]+=1
    elif fault=='source_binding':request['retained_source_ground_fragment']['source_native_binding']='forged'
    elif fault=='cut_identity':request['retained_source_ground_fragment']['retired_ground_track_uuids']=['unknown']
    elif fault=='class_width':request['width_nm']-=1
    elif fault=='missing_ground':del requests['ground:'+request['a']['pad_uuid']]
    elif fault=='changed_pad':pad.SetSize(pcbnew.VECTOR2I(400001,400000))
    elif fault=='changed_role':pad.SetNet(board.FindNet('OUT'))
    elif fault=='custom_pad':pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    elif fault=='no_fills':
        for z in board.Zones():z.UnFill()
    else:
        vias=[t for t in board.GetTracks()if t.GetClass()=='PCB_VIA'and list(t.GetPosition())==request['b']['at_nm']]
        assert vias
        if fault=='foreign_via':
            for v in vias:v.SetNet(board.FindNet('OUT'))
        else:discard_items(board,vias)
    if fault=='no_fills':
        with pytest.raises(ValueError,match='filled_faces_required'):
            observe(parent,board,key,requests,proposal)
    else:assert observe(parent,board,key,requests,proposal)is None


def test_same_zone_uuid_does_not_connect_two_separate_filled_islands(tmp_path,monkeypatch):
    parent,board,key,request,requests,proposal=fixture(tmp_path,monkeypatch)
    assert observe(parent,board,key,requests,proposal)
    poly=pcbnew.SHAPE_POLY_SET()
    for x,y in(request['a']['at_nm'],request['b']['at_nm']):
        poly.NewOutline()
        for dx,dy in((-200000,-200000),(200000,-200000),(200000,200000),(-200000,200000)):
            poly.Outline(poly.OutlineCount()-1).Append(x+dx,y+dy)
    for z in board.Zones():z.SetFilledPolysList(z.GetLayer(),poly);z.SetIsFilled(True)
    assert observe(parent,board,key,requests,proposal)is None


def test_saved_receiving_requires_its_own_source_and_exact_cut_endpoint_witness(tmp_path,monkeypatch):
    parent,board,key,request,requests,proposal=fixture(tmp_path,monkeypatch)
    selected={k:r for k,r in requests.items()if r['kind']in('ground','ground_boundary')}
    proof=saved._receive_paths(parent,board,selected,set(),'opaque',time.monotonic()+10.,
        allow_retained_no_additions=True,source_proposal=proposal)
    assert any(p.get('source_recompiled_ground_cut',{}).get('all_named_contacts_connected')for p in proof)
    with pytest.raises(ValueError,match='source_recompile_required'):
        saved._receive_paths(parent,board,selected,set(),'opaque',time.monotonic()+10.,allow_retained_no_additions=True)
    selected=copy.deepcopy(selected);selected[key]['b']['at_nm'][0]+=1
    with pytest.raises(ValueError,match='exact_endpoints_not_connected'):
        saved._receive_paths(parent,board,selected,set(),'opaque',time.monotonic()+10.,
            allow_retained_no_additions=True,source_proposal=proposal)


def test_empty_offer_is_only_a_conditional_proposal_and_keeps_staged_receiving(tmp_path,monkeypatch):
    parent,board,key,request,requests,proposal=fixture(tmp_path,monkeypatch)
    class Captured(Exception):pass
    detail={}
    def append(ops):
        assert ops==[]and detail['conditional_source_ground_cut_requires_staged_receiving']
        raise Captured
    with pytest.raises(Captured):
        observer.escape._connection_menu(board,request,board_hint='opaque',deadline=time.monotonic()+10.,
            layers=[pcbnew.F_Cu,pcbnew.B_Cu],append=append,detail=detail)

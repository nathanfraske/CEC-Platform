"""Literal connected boundary ports need no new spur to another same-net site."""
import copy
import time
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_force_current as force
from test_retained_native_bypass_connection import native
import cec_complete_cell_receiving as saved


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_existing_native_pad_to_exact_track_port_is_observed_without_additions(monkeypatch,quarter,back):
    b,request,t=native(monkeypatch,quarter,back)
    request['kind']='source_boundary'
    request['b']=dict(native_uuids=[force._uid(t)],at_nm=list(t.GetEnd()),layers=[int(t.GetLayer())])
    before=escape.row._source_binding(b)
    proof=escape.retained_native_boundary_connection(b,request)
    assert proof and proof['all_named_contacts_connected'] and proof['zone_and_foreign_net_edges_excluded']
    assert proof['new_copper']==0 and not proof['current_qualified']
    assert before==escape.row._source_binding(b)


@pytest.mark.parametrize('fault',['gap','forged_point','forged_uuid','foreign_net','one_open_port','ground','duplicate'])
def test_every_native_named_contact_and_material_connection_is_required(monkeypatch,fault):
    b,request,t=native(monkeypatch);request['kind']='source_boundary'
    request['b']=dict(native_uuids=[force._uid(t)],at_nm=list(t.GetEnd()),layers=[int(t.GetLayer())])
    if fault=='gap':
        request['a'],request['b']=copy.deepcopy(request['a']),copy.deepcopy(request['b'])
        owner=b.FindFootprintByReference('opaque_0_owner');owner.Move(pcbnew.VECTOR2I_MM(-1,0))
        request['a']['at_nm'][0]-=1000000
    elif fault=='forged_point':request['b']['at_nm'][1]+=200000
    elif fault=='forged_uuid':request['b']['native_uuids']=['unknown']
    elif fault=='foreign_net':request['net']='OUT'
    elif fault=='ground':request['net']='GND'
    elif fault=='duplicate':request['b']['native_uuids']*=2
    else:
        isolated=pcbnew.PCB_TRACK(b);isolated.SetNet(t.GetNet());isolated.SetLayer(t.GetLayer())
        isolated.SetStart(t.GetEnd()+pcbnew.VECTOR2I_MM(0,2));isolated.SetEnd(t.GetEnd()+pcbnew.VECTOR2I_MM(1,2))
        isolated.SetWidth(200000);b.Add(isolated);request['b']['native_uuids'].append(force._uid(isolated))
    assert escape.retained_native_boundary_connection(b,request) is None


def test_no_additions_need_explicit_mode_and_each_saved_terminal_proof(monkeypatch):
    b,request,t=native(monkeypatch)
    with pytest.raises(ValueError,match='bounded_native_cell_conductor'):
        saved._receive_paths(b,b,{'supply':request},set(),'opaque',time.monotonic()+2.)
    proof=saved._receive_paths(b,b,{'supply':request},set(),'opaque',time.monotonic()+2.,allow_retained_no_additions=True)
    assert proof[0]['saved_path_mm']==.5
    boundary=copy.deepcopy(request);boundary['kind']='source_boundary'
    boundary['b']=dict(native_uuids=[force._uid(t)],at_nm=list(t.GetEnd()),layers=[int(t.GetLayer())])
    proof=saved._receive_paths(b,b,{'supply':request,'old_contact':boundary},set(),'opaque',
        time.monotonic()+2.,allow_retained_no_additions=True)
    assert len(proof)==2 and proof[1]['retained_native_boundary']['new_copper']==0
    t.SetEnd(t.GetStart()+pcbnew.VECTOR2I_MM(.1,0))
    with pytest.raises(ValueError):
        saved._receive_paths(b,b,{'supply':request,'old_contact':boundary},set(),'opaque',
            time.monotonic()+2.,allow_retained_no_additions=True)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_typed_ground_cut_reuses_actual_explicit_copper_not_nm_echo(monkeypatch,quarter,back):
    b,request,t=native(monkeypatch,quarter,back)
    ground=pcbnew.NETINFO_ITEM(b,'GND');b.Add(ground)
    old_net=t.GetNetname()
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname()==old_net:p.SetNet(ground)
    for item in b.GetTracks():
        if item.GetNetname()==old_net:item.SetNet(ground)
    request.update(kind='ground_boundary',net='GND',retained_source_ground_fragment=dict(
        actual_fixed_source_contacts_not_same_net_proximity=True,
        whole_original_current_plane_and_saved_partition_receiving_required=True))
    # The real pad contact is not required to share a rounded route axis.
    request['b']=dict(native_uuids=[force._uid(t)],at_nm=list(t.GetEnd()),layers=[int(t.GetLayer())])
    before=escape.row._source_binding(b)
    proof=escape.retained_native_boundary_connection(b,request)
    assert proof and proof['typed_source_ground_fragment']and proof['all_named_contacts_connected']
    assert proof['physical_return_and_original_current_receiving_still_required']
    assert not proof['current_qualified']and proof['new_copper']==proof['new_holes']==0
    assert escape.row._source_binding(b)==before
    request['retained_source_ground_fragment'].pop('actual_fixed_source_contacts_not_same_net_proximity')
    assert escape.retained_native_boundary_connection(b,request)is None


def test_typed_ground_cut_does_not_infer_connection_from_shared_net(monkeypatch):
    b,request,t=native(monkeypatch)
    request.update(kind='ground_boundary',net='GND',retained_source_ground_fragment=dict(
        actual_fixed_source_contacts_not_same_net_proximity=True,
        whole_original_current_plane_and_saved_partition_receiving_required=True))
    assert escape.retained_native_boundary_connection(b,request)is None

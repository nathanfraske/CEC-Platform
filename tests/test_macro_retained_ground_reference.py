"""No redundant Ground trace when real retained plated entries already connect."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_complete_macro_cell as macro
import cec_force_current as force
import cec_field_coupling as field
from test_complete_macro_cell import fixture


def case(tmp_path,monkeypatch,quarter=0,back=False,*,ground_class_width_mm=None):
    source,parent,private,packet=fixture(tmp_path,monkeypatch,quarter=quarter,back=back,extra_ground_boundary=True,
        ground_class_width_mm=ground_class_width_mm)
    requests=[(k,r) for k,r in packet['requests'].items() if r['net']=='GND' and r['kind']=='source_boundary'
        and r.get('exact_additional_macro_component_source_ownership')]
    assert len(requests)==1
    return source,parent,private,packet,*requests[0]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_retained_reference_connectivity_needs_no_echo_trace_and_one_complete_trial(tmp_path,monkeypatch,quarter,back):
    source,parent,private,packet,key,request=case(tmp_path,monkeypatch,quarter,back)
    before=row._source_binding(private);raw=source.read_bytes()
    evidence=escape.retained_ground_reference_connection(private,request)
    assert evidence and evidence['actual_native_retained_connectivity_proved']
    assert evidence['new_copper']==evidence['new_holes']==0
    result=macro.screen(source,private,packet,board_hint='opaque')
    assert result['complete'],result['errors']
    assert result['selection']['selected'][key]['ops']==[]
    assert result['selection']['complete_selections_checked']<10
    assert len(result['complete_selection_trace_craft_trials'])<10
    assert row._source_binding(private)==before and source.read_bytes()==raw
    escape.construct_private(private,result['packet'],result['selection']);additive._ground_refill(private)
    child=force._copy_family(source,tmp_path/'reference-reuse-child');field._save_field_snapshot(private,child)
    received=macro.receive(source,child,board_hint='opaque')
    assert received['ok'] and received['complete'],received['errors']
    assert received['retained_native_ground_reference_connections'][key]==evidence
    assert received['all_original_physical_ground_returns']['ok'] and not received['release_authority']


@pytest.mark.parametrize('fault',['not_ground','untyped','arbitrary_kind','not_mandatory','fake_axis',
    'missing_via','smd_endpoint','unfilled','missing_plane','net','factory','faces'])
def test_net_names_and_plane_proximity_do_not_substitute_for_physical_reference_entries(tmp_path,monkeypatch,fault):
    source,parent,private,packet,key,request=case(tmp_path,monkeypatch);request=copy.deepcopy(request)
    live={force._uid(t):t for t in private.GetTracks()};via=live[request['a']['native_uuids'][0]]
    if fault=='not_ground':request['net']='RAIL'
    elif fault=='untyped':request['exact_additional_macro_component_source_ownership']=[dict(kind='same_net')]
    elif fault=='arbitrary_kind':request['kind']='ground'
    elif fault=='not_mandatory':request['every_surviving_source_component_port_mandatory']=False
    elif fault=='fake_axis':request['a']['at_nm'][0]+=1
    elif fault=='missing_via':request['a']['native_uuids']=['missing']
    elif fault=='smd_endpoint':request['a']['pad_uuid']='a_surface_pad_is_not_a_barrel'
    elif fault=='unfilled':next(iter(private.Zones())).UnFill()
    elif fault=='missing_plane':private.Remove(next(iter(private.Zones())))
    elif fault=='net':via.SetNet(private.FindNet('RAIL'))
    elif fault=='factory':
        evidence=escape.retained_ground_reference_connection(private,request)
        live[evidence['entries'][0]['uuid']].SetDrill(900000)
    else:request['a']['layers']=[100]
    before=row._source_binding(private)
    assert escape.retained_ground_reference_connection(private,request) is None
    assert row._source_binding(private)==before


@pytest.mark.parametrize('back',[False,True])
def test_two_disconnected_islands_of_the_same_zone_do_not_prove_a_reference_link(tmp_path,monkeypatch,back):
    import cec_ground_return_shortcut as reference
    source,parent,private,packet,key,request=case(tmp_path,monkeypatch,back=back)
    original=escape.retained_ground_reference_connection(private,request);assert original
    live={force._uid(t):t for t in private.GetTracks()};poly=pcbnew.SHAPE_POLY_SET()
    for entry in original['entries']:
        x,y=live[entry['uuid']].GetPosition();poly.NewOutline()
        for dx,dy in ((-400000,-400000),(400000,-400000),(400000,400000),(-400000,400000)):
            poly.Outline(poly.OutlineCount()-1).Append(x+dx,y+dy)
    for zone in private.Zones():
        zone.SetFilledPolysList(zone.GetLayer(),poly);zone.SetIsFilled(True)
    assert all(reference._reference_contacts(private,live[q['uuid']]) for q in original['entries'])
    assert escape.retained_ground_reference_connection(private,request) is None


@pytest.mark.parametrize('declared',[False,True])
def test_factory_pickup_port_resolves_only_its_exact_source_owned_barrel_axis(tmp_path,monkeypatch,declared):
    source,parent,private,packet,key,request=case(tmp_path,monkeypatch);request=copy.deepcopy(request)
    live={force._uid(t):t for t in private.GetTracks()};authority=request['exact_additional_macro_component_source_ownership']
    uid=next(q['via_uuid'] for a in authority for q in a['source_owned_barrel_roots'])
    via=live[uid]
    edge=next(t for t in private.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND'
        and tuple(via.GetPosition()) in (tuple(t.GetStart()),tuple(t.GetEnd())))
    other=next(p for p in (request['a'],request['b']) if uid not in p['native_uuids']
        and live[p['native_uuids'][0]].GetClass()=='PCB_VIA')
    request['a']=dict(native_uuids=[force._uid(edge)],at_nm=list(via.GetPosition()),layers=[int(edge.GetLayer())])
    request['b']=other
    if not declared:
        for a in authority:a['source_owned_barrel_roots']=[]
    result=escape.retained_ground_reference_connection(private,request)
    if declared:
        assert result and result['entries'][0]['uuid']==uid
        assert result['entries'][0]['native_port_uuid']==force._uid(edge)
    else:assert result is None

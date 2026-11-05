"""Actual retained track-to-reference connectivity needs no echo loop."""
import copy
import time
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_retained_ground_component as ground
from test_macro_retained_ground_reference import case


def fixture(tmp_path,monkeypatch,quarter=0,back=False):
    source,parent,board,packet,key,request=case(tmp_path,monkeypatch,quarter,back)
    request=copy.deepcopy(request);live={force._uid(t):t for t in board.GetTracks()}
    initial=escape.retained_ground_reference_connection(board,request)
    roots=ground._scope(request)
    if initial['entries'][0]['uuid']in roots:
        request['a'],request['b']=request['b'],request['a']
    original=live[request['a']['native_uuids'][0]];at=pcbnew.VECTOR2I(*request['a']['at_nm'])
    endpoint=pcbnew.VECTOR2I(at.x+1000000,at.y)
    edge=pcbnew.PCB_TRACK(board);edge.SetNet(original.GetNet());edge.SetWidth(request['width_nm'])
    edge.SetStart(at);edge.SetEnd(endpoint);edge.SetLayer(pcbnew.In2_Cu);board.Add(edge)
    request['a']=dict(native_uuids=[force._uid(edge)],at_nm=list(endpoint),layers=[pcbnew.In2_Cu])
    return board,request,edge


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_source_track_and_owned_reference_entry_share_real_filled_component(tmp_path,monkeypatch,quarter,back):
    board,request,edge=fixture(tmp_path,monkeypatch,quarter,back)
    assert escape.retained_ground_reference_connection(board,request)is None
    before=row._source_binding(board);proof=ground.observe(board,request)
    assert proof and proof['all_named_contacts_connected']and proof['actual_native_retained_connectivity_proved']
    assert proof['whole_zone_uuid_connectivity_credit']is False
    assert proof['remote_smd_return_not_inferred']and not proof['current_qualified']
    assert proof['new_copper']==proof['new_holes']==0
    assert row._source_binding(board)==before
    offered=[];detail={}
    escape._connection_menu(board,request,board_hint='opaque',deadline=time.monotonic()+5.,
        layers=[pcbnew.In2_Cu,pcbnew.B_Cu],append=offered.append,detail=detail)
    assert offered==[[]]and detail['retained_native_ground_reference_connection']==proof
    assert row._source_binding(board)==before


@pytest.mark.parametrize('fault',['not_ground','not_mandatory','untyped','unknown_kind','width',
    'no_owned_entry','smd_endpoint','foreign_track','unknown_face','unfilled','factory'])
def test_names_and_scope_claims_do_not_replace_literal_native_reference_material(tmp_path,monkeypatch,fault):
    board,request,edge=fixture(tmp_path,monkeypatch)
    if fault=='not_ground':request['net']='RAIL'
    elif fault=='not_mandatory':request['every_surviving_source_component_port_mandatory']=False
    elif fault=='untyped':request['exact_additional_macro_component_source_ownership'][0]['kind']='same_net'
    elif fault=='unknown_kind':request['kind']='ground'
    elif fault=='width':request['width_nm']+=1
    elif fault=='no_owned_entry':
        for a in request['exact_additional_macro_component_source_ownership']:a['source_owned_barrel_roots']=[]
    elif fault=='smd_endpoint':request['a']['pad_uuid']='not-a-plated-native-port'
    elif fault=='foreign_track':edge.SetNet(board.FindNet('RAIL'))
    elif fault=='unknown_face':request['a']['layers']=[100]
    elif fault=='unfilled':
        for zone in board.Zones():zone.UnFill()
    elif fault=='factory':
        live={force._uid(t):t for t in board.GetTracks()}
        for root in ground._scope(request):live[root].SetDrill(900000)
    before=row._source_binding(board)
    assert ground.observe(board,request)is None
    assert row._source_binding(board)==before


def test_one_zone_uuid_cannot_join_separate_real_filled_islands(tmp_path,monkeypatch):
    board,request,edge=fixture(tmp_path,monkeypatch)
    assert ground.observe(board,request)
    b_at=pcbnew.VECTOR2I(*request['b']['at_nm'])
    # A's actual retained track and its old barrel share one island; B's
    # actual owned reference barrel contacts another on every reference face.
    poly=pcbnew.SHAPE_POLY_SET()
    for x,y in(edge.GetStart(),b_at):
        poly.NewOutline()
        for dx,dy in((-300000,-300000),(300000,-300000),(300000,300000),(-300000,300000)):
            poly.Outline(poly.OutlineCount()-1).Append(x+dx,y+dy)
    for zone in board.Zones():
        zone.SetFilledPolysList(zone.GetLayer(),poly);zone.SetIsFilled(True)
    assert ground.observe(board,request)is None
    # A foreign authored net physically spanning the islands is not a bridge.
    other=pcbnew.PCB_TRACK(board);other.SetNet(board.FindNet('RAIL'));other.SetWidth(200000)
    other.SetLayer(pcbnew.In4_Cu);other.SetStart(edge.GetStart());other.SetEnd(b_at);board.Add(other)
    assert ground.observe(board,request)is None


@pytest.mark.parametrize('timeout',[True,0,-1,10.1,float('nan'),float('inf')])
def test_observation_budget_is_independent_and_bounded(timeout):
    with pytest.raises(ValueError):ground.observe(None,{},timeout_s=timeout)

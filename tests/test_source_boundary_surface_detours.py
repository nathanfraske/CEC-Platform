"""Named scalar ports get a real bounded surface maze before new holes."""
import math
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
from test_local_supply_native_detours import source,menu


def force_fallback(monkeypatch,producer=None):
    original=escape.fr._guarded_profiled_lastmile_legs;guard=escape.fr._tap_foreign_clear
    active=[]
    def route(*args,**kwargs):
        active.append(kwargs)
        return (producer or original)(*args,**kwargs)
    monkeypatch.setattr(escape.fr,'_guarded_profiled_lastmile_legs',route)
    monkeypatch.setattr(escape.fr,'_tap_foreign_clear',lambda *a,**k:bool(active) and guard(*a,**k))
    # This fixture deliberately has current authority on its ONE surface.
    # Other layer/port bridge behavior is covered by its own native tests;
    # do not invent additional layer authority to exercise this fallback.
    monkeypatch.setattr(escape.fr,'_lastmile_bridge',lambda *a,**k:None)
    return active


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_named_ports_receive_actual_native_full_width_same_face_search(monkeypatch,turn,back):
    board,request,obstacle,contract=source(monkeypatch,turn,back);request['kind']='source_boundary'
    before=row._source_binding(board);calls=force_fallback(monkeypatch)
    choices,detail=menu(board,request,seconds=3.)
    trials=detail['source_boundary_surface_trials']
    assert calls and trials and any(q['found'] for q in trials),detail
    surface=[ops for ops in choices if ops and all(op[0]=='trk' for op in ops)]
    assert surface
    for ops in surface:
        assert all(op[3]==250000 and op[4]==request['a']['layers'][0] for op in ops)
        assert tuple(ops[0][1])==tuple(request['a']['at_nm']) and tuple(ops[-1][2])==tuple(request['b']['at_nm'])
        assert sum(math.dist(op[1],op[2]) for op in ops)/1e6<=trials[-1]['max_length_mm']
    assert row._source_binding(board)==before and not any(q['no_path_proof'] for q in trials)


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_source_typed_low_power_ground_cut_can_take_a_same_face_maze(monkeypatch,turn,back):
    board,request,obstacle,contract=source(monkeypatch,turn,back)
    old=board.GetNetcodeFromNetname(request['net']);ground=pcbnew.NETINFO_ITEM(board,'GND');board.Add(ground)
    for item in [*board.GetTracks(),*(p for f in board.GetFootprints() for p in f.Pads())]:
        if item.GetNetCode()==old:item.SetNet(ground)
    request.update(kind='ground_boundary',net='GND',width_nm=250000,retained_source_ground_fragment=dict(
        actual_fixed_source_contacts_not_same_net_proximity=True,
        whole_original_current_plane_and_saved_partition_receiving_required=True))
    request.pop('unchanged_full_rail_current_contract',None)
    before=row._source_binding(board);force_fallback(monkeypatch)
    choices,detail=menu(board,request,seconds=3.)
    assert choices and any(q['found'] for q in detail['source_boundary_surface_trials'])
    assert all(op[0]=='trk' and op[3]==250000 and op[4]==request['a']['layers'][0]
        for ops in choices for op in ops)
    assert row._source_binding(board)==before and detail['unchanged_current_contract'] is None


@pytest.mark.parametrize('fault',['too_long','thin','start','end','disconnected','non45'])
def test_surface_candidate_cannot_bypass_width_ports_octilinearity_or_length(monkeypatch,fault):
    board,request,obstacle,contract=source(monkeypatch);request['kind']='source_boundary'
    a=pcbnew.VECTOR2I(*request['a']['at_nm']);b=pcbnew.VECTOR2I(*request['b']['at_nm'])
    legs=[(a,b,250000)]
    if fault=='too_long':
        p=pcbnew.VECTOR2I(a.x,a.y+15000000);q=pcbnew.VECTOR2I(b.x,p.y)
        legs=[(a,p,250000),(p,q,250000),(q,b,250000)]
    elif fault=='thin':legs=[(a,b,100000)]
    elif fault=='start':legs=[(pcbnew.VECTOR2I(a.x+1,a.y),b,250000)]
    elif fault=='end':legs=[(a,pcbnew.VECTOR2I(b.x+1,b.y),250000)]
    elif fault=='disconnected':legs=[(a,pcbnew.VECTOR2I(a.x+100000,a.y),250000),
        (pcbnew.VECTOR2I(a.x+200000,a.y),b,250000)]
    else:
        p=pcbnew.VECTOR2I(a.x+1000000,a.y+200000);legs=[(a,p,250000),(p,b,250000)]
    force_fallback(monkeypatch,lambda *a,**k:legs)
    choices,detail=menu(board,request,seconds=2.)
    assert not detail['source_boundary_surface_trials'][-1]['found']


@pytest.mark.parametrize('fault',['changed_current','missing_layer'])
def test_surface_search_cannot_invent_source_current_or_layer_authority(monkeypatch,fault):
    board,request,obstacle,contract=source(monkeypatch);request['kind']='source_boundary'
    if fault=='changed_current':request['unchanged_full_rail_current_contract']['current_authority']['amps']=.1
    else:contract['required_by_layer_nm']={};request['unchanged_full_rail_current_contract']=contract
    force_fallback(monkeypatch)
    with pytest.raises(ValueError):menu(board,request)

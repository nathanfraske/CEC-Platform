"""Actual endpoint clearance, unchanged whole-current floors, no fake ports."""
import ast
import copy
import math
import time
from pathlib import Path
import pcbnew
import pytest
import cec_decoupler_cell as cell
import cec_fr as fr
from cec_route_dimensions import current_trace_widths


def fixture(*,back=False,turn=0,board_min=250000):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6);b.GetDesignSettings().m_TrackMinWidth=board_min
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    own=pcbnew.NETINFO_ITEM(b,'/renamed/WHOLE_SOURCE');foreign=pcbnew.NETINFO_ITEM(b,'FOREIGN');b.Add(own);b.Add(foreign)
    layer=pcbnew.B_Cu if back else pcbnew.F_Cu
    def point(x,y):
        for _ in range(turn):x,y=20-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    pads=[]
    for ref,at in [('RENAMED_SUPPLY_PIN',(8.6,10)),('RENAMED_BYPASS_PIN',(13,10))]:
        f=pcbnew.FOOTPRINT(b);f.SetReference(ref);f.SetPosition(point(*at));b.Add(f)
        p=pcbnew.PAD(f);p.SetNumber('6');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetNet(own)
        p.SetSize(pcbnew.VECTOR2I_MM(.3,.3));p.SetShape(pcbnew.PAD_SHAPE_RECT)
        mask=pcbnew.LSET();mask.AddLayer(layer);p.SetLayerSet(mask);p.SetPosition(point(*at));f.Add(p);pads.append(p)
    t=pcbnew.PCB_TRACK(b);t.SetNet(foreign);t.SetLayer(layer);t.SetWidth(200000)
    t.SetStart(point(8.15,9));t.SetEnd(point(8.15,11));b.Add(t)
    for a,z in [((0,0),(20,0)),((20,0),(20,20)),((20,20),(0,20)),((0,20),(0,0))]:
        edge=pcbnew.PCB_SHAPE();edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts);edge.SetStart(point(*a));edge.SetEnd(point(*z));b.Add(edge)
    authority=dict(amps=1.1,geometry_margin=1.25,margin_included=False,source='positive native fixture')
    widths=current_trace_widths(authority,tuple(b.GetLayerName(l)for l in b.GetEnabledLayers().CuStack()),'jlcpcb_6l_pofv_signal',rise_c=30.)
    current=dict(current_authority=authority,profile='jlcpcb_6l_pofv_signal',required_by_layer_nm={b.GetLayerID(n):math.ceil(w*1e6)for n,w in widths.items()})
    return b,pads,own,layer,current,t


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('class_width',[500000,1000000])
def test_native_full_class_blocked_but_whole_current_pad_escape_clears(back,turn,class_width):
    b,pads,net,layer,current,foreign=fixture(back=back,turn=turn)
    a,z=[p.GetPosition()for p in pads];floor=max(b.GetDesignSettings().m_TrackMinWidth,current['required_by_layer_nm'][layer])
    assert not fr._tap_foreign_clear(b,a,z,class_width,layer,200000,{net.GetNetCode()},foreign_cache={})
    result=cell._canonical_whole_rail_surface(b,a,z,[layer],net_code=net.GetNetCode(),class_width_nm=class_width,
        clearance_nm=200000,current_widths=current,deadline_monotonic=time.monotonic()+2,max_length_nm=8000000,foreign_cache={},endpoint_pads=pads)
    assert result is not None
    legs,face,width=result
    assert face==layer and width==class_width and any(w<class_width for s,t,w in legs)
    assert all(w>=floor and fr._tap_foreign_clear(b,s,t,w,layer,200000,{net.GetNetCode()},foreign_cache={})for s,t,w in legs)
    assert tuple(legs[0][0])==tuple(a)and tuple(legs[-1][1])==tuple(z)


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',range(4))
def test_native_guarded_maze_handoff_preserves_endpoint_budget(back,turn):
    b,pads,net,layer,current,foreign=fixture(back=back,turn=turn);a,z=[p.GetPosition()for p in pads]
    escapes=cell._whole_current_endpoint_escapes(b,pads,net_code=net.GetNetCode(),layer=layer,
        class_width_nm=1000000,clearance_nm=200000,current_widths=current)
    report={};floor=max(b.GetDesignSettings().m_TrackMinWidth,current['required_by_layer_nm'][layer])
    legs=fr._guarded_profiled_lastmile_legs(b,a,z,1000000,layer,200000,net.GetNetCode(),
        lambda s,t,h:fr._edge_leg_clear(b,s,t,h+200000),allow_maze=True,
        start_escape=escapes[0],end_escape=escapes[1],foreign_cache={},deadline_monotonic=time.monotonic()+2,
        max_length_nm=8000000,search_diagnostics=report)
    assert legs and all(w>=floor for s,t,w in legs)
    assert all(fr._tap_foreign_clear(b,s,t,w,layer,200000,{net.GetNetCode()},foreign_cache={})for s,t,w in legs)


def test_literal_native_endpoint_none_never_acquires_pad_allowance():
    b,pads,net,layer,current,_=fixture()
    result=cell._whole_current_endpoint_escapes(b,[pads[0],None],net_code=net.GetNetCode(),layer=layer,
        class_width_nm=1000000,clearance_nm=200000,current_widths=current)
    assert result[0]and result[1]is None


@pytest.mark.parametrize('fault',['net','layer','no_current','no_authority'])
def test_invalid_source_context_is_fail_closed(fault):
    b,pads,net,layer,current,_=fixture();code=net.GetNetCode()
    if fault=='net':code=0
    elif fault=='layer':layer=pcbnew.In2_Cu
    elif fault=='no_current':current=None
    else:current.pop('current_authority')
    with pytest.raises(ValueError):cell._whole_current_endpoint_escapes(b,pads,net_code=code,layer=layer,
        class_width_nm=1000000,clearance_nm=200000,current_widths=current)


def test_canonical_never_emits_below_board_minimum_even_without_local_allowance():
    b,pads,net,layer,current,foreign=fixture(board_min=600000)
    # Remove only the synthetic foreign obstruction: test the floor itself,
    # not a mocked geometric admission or an intentionally impossible route.
    from cec_native_items import discard_items
    discard_items(b,[foreign])
    result=cell._canonical_whole_rail_surface(b,pads[0].GetPosition(),pads[1].GetPosition(),[layer],
        net_code=net.GetNetCode(),class_width_nm=500000,clearance_nm=200000,current_widths=current,
        deadline_monotonic=time.monotonic()+2,max_length_nm=8000000,foreign_cache={},endpoint_pads=pads)
    assert result is None or all(w>=600000 for s,t,w in result[0])


def test_joint_menu_forwards_both_budgets_to_guarded_search():
    import cec_cell_escape_replan as escape
    tree=ast.parse(Path(escape.__file__).read_text())
    menu=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='_connection_menu')
    calls=[n.value for n in ast.walk(menu)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='legs'for t in n.targets)
        and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Attribute)
        and n.value.func.attr=='_guarded_profiled_lastmile_legs']
    assert len(calls)==2 and all({'start_escape','end_escape'}<={k.arg for k in c.keywords}for c in calls)

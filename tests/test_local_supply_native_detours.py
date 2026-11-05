"""Bounded native owner/cap detours cannot borrow widths, vias or locality."""
import copy
import math
import time

import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_force_current as force


def source(monkeypatch, turn=0, back=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    settings=board.GetDesignSettings();settings.m_TrackMinWidth=200000
    settings.m_MinClearance=200000
    nets={}
    for name in ('local_rail','foreign_material'):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);nets[name]=net
    def pad(ref,net,at,size):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);board.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(nets[net])
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(*size))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
        fp.Add(p);p.SetPosition(pcbnew.VECTOR2I_MM(*at));return p
    a=pad('arbitrary_owner','local_rail',(10,10),(.6,.6))
    b=pad('unrelated_cap_name','local_rail',(12,10),(.6,.6))
    obstacle=pad('native_obstacle','foreign_material',(11,10),(.4,.5))
    if back:
        for fp in board.GetFootprints():fp.Flip(pcbnew.VECTOR2I_MM(15,15),False)
    if turn:
        for fp in board.GetFootprints():
            fp.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(90*turn,pcbnew.DEGREES_T))
    # Explicit synthetic contract tests propagation; these are not board load
    # estimates or a substitute for source-derived production budgets.
    face=int(list(a.GetLayerSet().CuStack())[0])
    contract=dict(required_by_layer_nm={face:250000},
        current_authority=dict(source='synthetic_fixture_only',amps=.3,margin_included=True))
    monkeypatch.setattr(escape.cell,'_supply_current_widths',lambda *args:copy.deepcopy(contract))
    monkeypatch.setattr(escape.cell,'_netclass',lambda *args:dict(width=200000,clearance=200000))
    def end(p):return dict(pad_uuid=force._uid(p),at_nm=list(p.GetPosition()),
        layers=[int(layer) for layer in p.GetLayerSet().CuStack()])
    request=dict(kind='local_supply',net='local_rail',a=end(a),b=end(b),width_nm=200000,
        unchanged_full_rail_current_contract=copy.deepcopy(contract))
    return board,request,obstacle,contract


def menu(board,request,*,seconds=2.):
    choices=[];detail={}
    escape._connection_menu(board,request,board_hint='opaque_fixture',
        deadline=time.monotonic()+seconds,layers=[pcbnew.In2_Cu,pcbnew.B_Cu],
        append=lambda ops:choices.append(ops),detail=detail)
    return choices,detail


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_throat_detour_is_short_full_width_same_face_and_nonmutating(monkeypatch,turn,back):
    board,request,obstacle,contract=source(monkeypatch,turn,back)
    before=row._source_binding(board)
    choices,detail=menu(board,request)
    trials=detail['local_supply_surface_trials']
    assert trials and any(t['found'] for t in trials),detail
    # The old fixed rectangles either hit the real land or exceed the strict
    # locality bound. The accepted new path goes around its native contour.
    assert choices and len(choices)==1,choices
    path=choices[0];layer=request['a']['layers'][0]
    assert all(op[0]=='trk' and op[3]==250000 and op[4]==layer for op in path)
    assert tuple(path[0][1])==tuple(request['a']['at_nm'])
    assert tuple(path[-1][2])==tuple(request['b']['at_nm'])
    assert sum(math.dist(op[1],op[2]) for op in path)/1e6<=trials[-1]['max_length_mm']
    assert all(not (dx and dy) or abs(dx)==abs(dy) for op in path
        for dx,dy in [(op[2][0]-op[1][0],op[2][1]-op[1][1])])
    assert row._source_binding(board)==before
    assert all(not t['no_path_proof'] for t in trials)


@pytest.mark.parametrize('fault',['too_long','thin','wrong_start','wrong_end','disconnected'])
def test_producer_cannot_bypass_local_length_width_or_real_terminal_anchors(monkeypatch,fault):
    board,request,obstacle,contract=source(monkeypatch)
    a=pcbnew.VECTOR2I(*request['a']['at_nm']);b=pcbnew.VECTOR2I(*request['b']['at_nm'])
    center=pcbnew.VECTOR2I(a.x,a.y+2000000)
    legs=[(a,center,250000),(center,b,250000)]
    if fault=='thin':legs=[(a,b,100000)]
    if fault=='wrong_start':legs=[(pcbnew.VECTOR2I(a.x+1,a.y),b,250000)]
    if fault=='wrong_end':legs=[(a,pcbnew.VECTOR2I(b.x+1,b.y),250000)]
    if fault=='disconnected':legs=[(a,pcbnew.VECTOR2I(a.x+100000,a.y),250000),
        (pcbnew.VECTOR2I(a.x+200000,a.y),b,250000)]
    monkeypatch.setattr(escape.fr,'_guarded_profiled_lastmile_legs',lambda *args,**kw:legs)
    choices,detail=menu(board,request)
    assert not choices and not detail['local_supply_surface_trials'][-1]['found']


@pytest.mark.parametrize('fault',['unknown_current','changed_current','missing_layer'])
def test_detour_does_not_invent_current_or_layer_authority(monkeypatch,fault):
    board,request,obstacle,contract=source(monkeypatch)
    if fault=='unknown_current':
        def unknown(*args):raise ValueError('unknown_fixture_current')
        monkeypatch.setattr(escape.cell,'_supply_current_widths',unknown)
    elif fault=='changed_current':request['unchanged_full_rail_current_contract']['current_authority']['amps']=.1
    else:
        contract['required_by_layer_nm']={}
        request['unchanged_full_rail_current_contract']=copy.deepcopy(contract)
    with pytest.raises(ValueError):menu(board,request)


def test_no_common_face_cannot_create_a_hidden_layer_jump(monkeypatch):
    board,request,obstacle,contract=source(monkeypatch)
    request['b']['layers']=[pcbnew.B_Cu]
    called=[]
    monkeypatch.setattr(escape.fr,'_guarded_profiled_lastmile_legs',lambda *a,**kw:called.append(kw))
    choices,detail=menu(board,request)
    assert not called and not choices and detail['local_supply_surface_trials']==[]


def test_expired_lease_does_not_start_a_new_surface_search(monkeypatch):
    board,request,obstacle,contract=source(monkeypatch)
    called=[]
    monkeypatch.setattr(escape.fr,'_guarded_profiled_lastmile_legs',lambda *a,**kw:called.append(kw))
    choices,detail=menu(board,request,seconds=-1.)
    assert not called and not choices and detail['local_supply_surface_trials']==[]

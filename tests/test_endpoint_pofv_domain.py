"""Loaded native endpoint/process/rollback tests, with renamed rotated cells.

The downstream coupled-route and return-field calls are stubbed in these unit
tests; the actual pad, barrel, clearance and profile predicates are not.
"""
import time
import json
from unittest.mock import patch

import pcbnew
import pytest

import cec_fab_profile as fab
import cec_precision_route as route


def fixture(tmp_path, *, quarter=0, back=False, narrow=.30, blocker=False):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    # The fixture models an explicitly fine native process. A profile name
    # alone is not permission to bypass the stock board's absolute minima.
    settings=board.GetDesignSettings()
    settings.m_ViasMinSize=300000
    settings.m_MinThroughDrill=200000
    settings.m_ViasMinAnnularWidth=50000
    props = board.GetProperties()
    props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    board.SetProperties(props)
    for net in ('A_NEW', 'B_NEW', 'UNCHANGED'):
        board.Add(pcbnew.NETINFO_ITEM(board, net))
    def pose(x, y):
        for _ in range(quarter):
            x, y = -y, x
        return 30+x, 30+y
    # The wide .8 mm lands must have a legal .2 mm gap. At .75 mm pitch
    # they overlapped, and the preferred .35 mm via correctly failed the
    # foreign-pad guard before reaching the intended narrow endpoint.
    raw = [(0,0), (10,0), (0,1.), (10,1.)]
    endpoints = tuple(pose(*xy) for xy in raw)
    for index, point in enumerate(endpoints):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference('RENAMED_'+str(index)); board.Add(fp)
        pad = pcbnew.PAD(fp); pad.SetNumber('x')
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(narrow if index in (1,3) else .8, .8))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*point))
        pad.SetOrientationDegrees(90*quarter)
        pad.SetNet(board.FindNet('A_NEW' if index < 2 else 'B_NEW'))
        layers = pcbnew.PAD.SMDMask()
        if back:
            layers.FlipStandardLayers()
        pad.SetLayerSet(layers)
        fp.Add(pad)
    # Unrelated authored copper plus group must survive every failed attempt.
    track = pcbnew.PCB_TRACK(board); track.SetNet(board.FindNet('UNCHANGED'))
    a, b = (pose(9,-1), pose(11,1)) if blocker else (pose(-4,-4),pose(-3,-4))
    track.SetStart(pcbnew.VECTOR2I_MM(*a)); track.SetEnd(pcbnew.VECTOR2I_MM(*b))
    track.SetWidth(pcbnew.FromMM(.2)); track.SetLayer(board.GetLayerID('In2.Cu'))
    track.SetLocked(True); board.Add(track)
    group = pcbnew.PCB_GROUP(board); group.SetName('inherited'); board.Add(group); group.AddItem(track)
    path = tmp_path/'fixture.kicad_pcb'; pcbnew.SaveBoard(str(path),board,True)
    # Native minima live in the project, not the PCB serialization. Bind the
    # exact saved family so LoadBoard does not restore stock .5/.3/.1 floors.
    path.with_suffix('.kicad_pro').write_text(json.dumps({'board':{'design_settings':{'rules':{
        'min_via_diameter':.3,'min_through_hole_diameter':.2,
        'min_via_annular_width':.05,'min_clearance':.2}}}}))
    return path, endpoints, dict(name='arbitrary_bus',kind='usb',p='A_NEW',n='B_NEW',width=.2,gap=.25)


def ids(board):
    return sorted(item.m_Uuid.AsString() for item in board.GetTracks())


def solve(board, pair, endpoints, *, old=False, **kwargs):
    with patch.object(route, 'route_coupled_pair', return_value=dict(route_mode='unit-test')) as coupled, \
         patch.object(route, '_add_pair_transition_returns', return_value=([], 'covered')) as returns:
        if old:
            result = route._route_coupled_endpoint_pofv_geometry(board,pair,endpoints,
                target_layer='In2.Cu',geometry=(.35,.25),**kwargs)
        else:
            result = route._route_coupled_endpoint_pofv(board,pair,endpoints,
                target_layer='In2.Cu',**kwargs)
    return result, coupled.call_count, returns.call_count


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False,True])
def test_loaded_narrow_lands_use_existing_process_floor_without_altering_source(tmp_path,quarter,back):
    path,ends,pair = fixture(tmp_path,quarter=quarter,back=back)
    original = path.read_bytes()
    old = pcbnew.LoadBoard(str(path)); inherited = ids(old)
    refused, calls, returns = solve(old,pair,ends,old=True)
    assert refused['refusal_kind']=='endpoint_pofv_geometry'
    assert ids(old)==inherited and calls==returns==0
    board = pcbnew.LoadBoard(str(path))
    result,calls,returns = solve(board,pair,ends)
    assert not result.get('refused'), result
    assert calls==1 and returns==2
    attempts = result['pofv_geometry_search']['attempts']
    assert len(attempts)==2 and attempts[0]['qualification']['pad_containment_ok'] is False
    vias = [t for t in board.GetTracks() if t.GetClass()=='PCB_VIA']
    assert len(vias)==4
    assert all(t.GetWidth()==pcbnew.FromMM(.3) and t.GetDrillValue()==pcbnew.FromMM(.2) for t in vias)
    assert all(fab.local_pofv_via_decision(board,t)[0] for t in vias)
    assert all(board.FindFootprintByReference('RENAMED_'+str(i)) is not None for i in range(4))
    assert set(inherited)<=set(ids(board))
    assert len(list(board.Groups()))==1 and len(list(next(iter(board.Groups())).GetItems()))==1
    output=tmp_path/'result.kicad_pcb';pcbnew.SaveBoard(str(output),board,True)
    reloaded=pcbnew.LoadBoard(str(output))
    assert ids(board)==ids(reloaded)
    assert path.read_bytes()==original


def test_preferred_geometry_is_retained_when_it_fits(tmp_path):
    path,ends,pair=fixture(tmp_path,narrow=.8)
    board=pcbnew.LoadBoard(str(path));result,_,_=solve(board,pair,ends)
    assert not result.get('refused')
    assert len(result['pofv_geometry_search']['attempts'])==1
    assert all(t.GetWidth()==pcbnew.FromMM(.35) for t in board.GetTracks() if t.GetClass()=='PCB_VIA')


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_native_constructor_requests_board_legal_endpoint_menu(tmp_path, quarter, back):
    path, ends, pair = fixture(tmp_path, quarter=quarter, back=back, narrow=.8)
    board = pcbnew.LoadBoard(str(path))
    settings = board.GetDesignSettings()
    settings.m_ViasMinSize = pcbnew.FromMM(.5)
    settings.m_MinThroughDrill = pcbnew.FromMM(.2)
    settings.m_ViasMinAnnularWidth = pcbnew.FromMM(.1)
    inherited = set(ids(board))
    result, calls, returns = solve(board, pair, ends)
    assert not result.get('refused'), result
    assert calls == 1 and returns == 2
    attempts = result['pofv_geometry_search']['attempts']
    assert len(attempts) == 1 and attempts[0]['diameter_mm'] == .5
    vias = [t for t in board.GetTracks() if t.GetClass() == 'PCB_VIA']
    assert len(vias) == 4
    assert all(t.GetWidth() >= settings.m_ViasMinSize for t in vias)
    assert all(t.GetDrillValue() >= settings.m_MinThroughDrill for t in vias)
    assert all(t.GetWidth()-t.GetDrillValue() >= 2*settings.m_ViasMinAnnularWidth
               for t in vias)
    assert all(fab.local_pofv_via_decision(board, t)[0] for t in vias)
    assert inherited <= set(ids(board))


def test_native_menu_enlargement_still_refuses_lands_that_do_not_contain_it(tmp_path):
    path, ends, pair = fixture(tmp_path, narrow=.45)
    board = pcbnew.LoadBoard(str(path))
    board.GetDesignSettings().m_ViasMinSize = pcbnew.FromMM(.5)
    before = ids(board)
    result, calls, returns = solve(board, pair, ends)
    assert result['refusal_kind'] == 'endpoint_pofv_geometry'
    assert calls == returns == 0 and ids(board) == before
    assert all(attempt['diameter_mm'] >= .5
               for attempt in result['pofv_geometry_search']['attempts'])


@pytest.mark.parametrize('kwargs', [dict(narrow=.29),dict(blocker=True)])
def test_minimum_still_requires_full_land_and_all_layer_clearance(tmp_path,kwargs):
    path,ends,pair=fixture(tmp_path,**kwargs)
    board=pcbnew.LoadBoard(str(path));before=ids(board)
    result,calls,returns=solve(board,pair,ends)
    assert result['refusal_kind']=='endpoint_pofv_geometry'
    assert ids(board)==before and calls==returns==0
    assert len(result['pofv_geometry_search']['attempts'])==2
    if kwargs.get('blocker'):
        evidence=result['endpoint_qualification']['via_spot']
        assert evidence['reason']=='foreign copper excludes via land'
        assert evidence['blockers']


def test_unavailable_profile_and_expired_deadline_do_not_emit_copper(tmp_path):
    path,ends,pair=fixture(tmp_path)
    for mode in ('profile','deadline'):
        board=pcbnew.LoadBoard(str(path));before=ids(board)
        if mode=='profile':
            props=board.GetProperties();props['CEC_FAB_PROFILE']='unknown';board.SetProperties(props)
        result,calls,returns=solve(board,pair,ends,deadline=time.monotonic()-1 if mode=='deadline' else None)
        assert result.get('refused') and ids(board)==before and calls==returns==0


def test_actual_route_failure_is_not_retried_with_smaller_barrels(tmp_path):
    path,ends,pair=fixture(tmp_path,narrow=.8)
    board=pcbnew.LoadBoard(str(path));before=ids(board)
    with patch.object(route,'route_coupled_pair',return_value=dict(refused='synthetic downstream refusal')) as coupled:
        result=route._route_coupled_endpoint_pofv(board,pair,ends,target_layer='In2.Cu')
    assert result['refused']=='qualified endpoint POFV route refused'
    assert len(result['pofv_geometry_search']['attempts'])==1 and coupled.call_count==1
    assert ids(board)==before


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('accepted',[True,False])
def test_native_plated_terminal_face_routes_without_redundant_signal_vias(tmp_path,quarter,accepted):
    path,ends,pair=fixture(tmp_path,quarter=quarter,narrow=.8)
    b=pcbnew.LoadBoard(str(path))
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
            pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    before=ids(b)
    def proposed(board,_pair,**kwargs):
        t=pcbnew.PCB_TRACK(board);t.SetNet(board.FindNet(pair['p']))
        t.SetStart(pcbnew.VECTOR2I_MM(*ends[0]));t.SetEnd(pcbnew.VECTOR2I_MM(*ends[1]))
        t.SetLayer(board.GetLayerID('In2.Cu'));t.SetWidth(200000);board.Add(t)
        return dict(route_mode='unit-native-face')
    with patch.object(route,'route_coupled_pair',side_effect=proposed) as coupled, \
         patch('cec_pth_pair_returns.synthesize',return_value=dict(ok=accepted)) as returns:
        r=route._route_coupled_endpoint_pofv(b,pair,ends,target_layer='In2.Cu')
    assert coupled.call_count==returns.call_count==1
    assert coupled.call_args.kwargs['prefer_grid'] is True
    assert coupled.call_args.kwargs['allow_layer_transitions'] is False
    assert not any(t.GetClass()=='PCB_VIA' for t in b.GetTracks())
    assert r['new_signal_transition_count']==0 and r['native_terminal_access']
    if accepted:
        assert not r.get('refused') and len(ids(b))==len(before)+1
    else:
        assert r.get('refused') and ids(b)==before


@pytest.mark.parametrize('kind',['nonplated','undrilled'])
@pytest.mark.parametrize('quarter',[0,1])
def test_layer_mask_alone_does_not_invent_a_plated_terminal(tmp_path,kind,quarter):
    path,ends,pair=fixture(tmp_path,quarter=quarter,narrow=.8)
    b=pcbnew.LoadBoard(str(path));before=ids(b)
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH if kind=='nonplated' else pcbnew.PAD_ATTRIB_PTH)
            pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3) if kind=='nonplated' else pcbnew.VECTOR2I(0,0))
            pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    with patch.object(route,'route_coupled_pair') as coupled:
        r=route._route_coupled_endpoint_pofv(b,pair,ends,target_layer='In2.Cu')
    # KiCad itself removes the electrical net from NPTH lands. Undrilled
    # PTH still carries a net, so it reaches the explicit physical-access guard.
    expected=('start endpoint has no exact owning pad' if kind=='nonplated'
              else 'endpoint has no physical native terminal access')
    assert r['refused']==expected
    assert not coupled.called and ids(b)==before


def test_deadline_is_shared_and_never_renewed_between_geometries(tmp_path):
    path,ends,pair=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(path));before=ids(board)
    with patch.object(route,'_deadline_expired',side_effect=[False,True,True]), \
         patch.object(route,'_route_coupled_endpoint_pofv_geometry',return_value=dict(
             refused='geometry refused',refusal_kind='endpoint_pofv_geometry')) as attempt:
        result=route._route_coupled_endpoint_pofv(board,pair,ends,target_layer='In2.Cu',deadline=123.5)
    assert attempt.call_count==1 and attempt.call_args.kwargs['deadline']==123.5
    assert result['pofv_geometry_search']['deadline_exhausted']
    assert ids(board)==before


def test_inherited_endpoint_barrel_is_reused_not_resized_or_duplicated(tmp_path):
    path,ends,pair=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(path))
    via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet(pair['p']))
    via.SetPosition(pcbnew.VECTOR2I_MM(*ends[0]));via.SetWidth(pcbnew.FromMM(.35))
    via.SetDrill(pcbnew.FromMM(.25));via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetLocked(True);board.Add(via)
    uid=via.m_Uuid.AsString()
    result,_,_=solve(board,pair,ends)
    assert not result.get('refused'),result
    vias=[item for item in board.GetTracks() if item.GetClass()=='PCB_VIA']
    assert len(vias)==4
    retained=next(item for item in vias if item.m_Uuid.AsString()==uid)
    assert retained.IsLocked() and retained.GetWidth()==pcbnew.FromMM(.35)
    assert retained.GetDrillValue()==pcbnew.FromMM(.25)
    assert len(result['pofv']['reused_barrels'])==1

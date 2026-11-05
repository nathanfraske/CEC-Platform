"""Loaded-native true pad contact; no route-generator or coordinate recipe."""
import math
import pcbnew
import pytest
from cec_kelvin_departure import audit_pad_departures
from cec_local_copper_cell import copper_inventory
from test_kelvin_discipline import _fp,_pad_smd,_trk


def native(tmp_path,angle,back,segments,*,width=.25,pad_size=(2.,4.)):
    board=pcbnew.CreateEmptyBoard()
    net=pcbnew.NETINFO_ITEM(board,'ARBITRARY');board.Add(net)
    fp=_fp(board,'ELEMENT_Q','anonymous')
    _pad_smd(fp,'A',net,10,10,*pad_size)
    _pad_smd(fp,'B',net,16,10,*pad_size)
    for a,b in segments:_trk(board,net,a,b,wmm=width)
    # Rigidly transform both copper and physical pads; rotate arbitrary names.
    for item in [*board.GetFootprints(),*board.GetTracks()]:
        if back:item.Flip(pcbnew.VECTOR2I(0,0),False)
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    path=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    board=pcbnew.LoadBoard(str(path));fp=next(iter(board.GetFootprints()))
    pads={p.GetNumber():p for p in fp.Pads()}
    return board,pads


@pytest.mark.parametrize('angle',[0,45,90,180,270])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_native_inner_exit_is_storage_direction_and_face_invariant(tmp_path,angle,back,reverse):
    segments=[((10.88,10),(12.,10)),((12.,10),(12.,14.))]
    if reverse:segments=[(b,a) for a,b in segments]
    board,pads=native(tmp_path,angle,back,segments);before=copper_inventory(board)
    result=audit_pad_departures(pads['A'],pads['B'].GetPosition(),board.GetTracks())
    assert result['ok'] and result['departure_count']==1,result
    assert result['departures'][0]['inner_projection_mm']>1.
    assert copper_inventory(board)==before


@pytest.mark.parametrize('segments,reason',[
    ([((10.88,10),(6,10))],'departure_not_on_inner_face'),
    ([((10.88,10),(10.88,15))],'departure_not_perpendicular_inward'),
    ([((7,10),(13,10))],'thin_track_crosses_source_pad_without_terminal'),
    ([((10.88,10),(13,11))],'departure_not_perpendicular_inward')])
@pytest.mark.parametrize('angle',[0,90])
def test_inner_endpoint_does_not_prove_correct_departure(tmp_path,segments,reason,angle):
    board,pads=native(tmp_path,angle,False,segments)
    result=audit_pad_departures(pads['A'],pads['B'].GetPosition(),board.GetTracks())
    assert result['applicable'] and not result['ok']
    assert any(row['reason']==reason for row in result['issues'])


def test_close_but_not_touching_is_not_contact(tmp_path):
    board,pads=native(tmp_path,0,False,[((11.3,10),(13,10))])
    result=audit_pad_departures(pads['A'],pads['B'].GetPosition(),board.GetTracks())
    assert not result['applicable'] and not result['ok']
    assert result['reason']=='no_native_pad_contact'


def test_cap_overlap_at_authored_pad_edge_is_contact(tmp_path):
    board,pads=native(tmp_path,0,False,[((11.05,10),(13,10))])
    assert audit_pad_departures(pads['A'],pads['B'].GetPosition(),board.GetTracks())['ok']


def test_internal_segments_and_valid_branches_are_preserved(tmp_path):
    segments=[((10,10),(10.88,10)),((10.88,10),(12,10)),
              ((12,10),(12,13)),((12,10),(14,10))]
    board,pads=native(tmp_path,90,True,segments)
    result=audit_pad_departures(pads['A'],pads['B'].GetPosition(),board.GetTracks())
    assert result['ok'] and result['internal_count']==1,result


def test_an_additional_outer_contact_cannot_hide_behind_good_branch(tmp_path):
    board,pads=native(tmp_path,0,False,[((10.88,10),(12,10)),((9.12,10),(6,10))])
    result=audit_pad_departures(pads['A'],pads['B'].GetPosition(),board.GetTracks())
    assert not result['ok'] and result['departure_count']==2


def test_contact_on_other_copper_layer_is_not_connected(tmp_path):
    board,pads=native(tmp_path,0,False,[((10.88,10),(12,10))])
    next(iter(board.GetTracks())).SetLayer(pcbnew.B_Cu)
    assert not audit_pad_departures(pads['A'],pads['B'].GetPosition(),board.GetTracks())['applicable']


def with_input(board,x,y,number='INPUT',size=(.3,.3)):
    fp=_fp(board,'OTHER_'+number,'anonymous')
    net=board.FindNet('ARBITRARY')
    _pad_smd(fp,number,net,x,y,*size)
    return next(iter(fp.Pads()))


def test_separate_voltage_branch_does_not_inherit_kelvin_rule(tmp_path):
    board,pads=native(tmp_path,0,False,[((10.88,10),(13,10)),((10.88,10),(10.88,15))])
    target=with_input(board,13,10)
    voltage=with_input(board,10.88,15,'VOLTAGE')
    result=audit_pad_departures(pads['A'],pads['B'].GetPosition(),board.GetTracks(),
        target_pads=[target],connectivity_pads=[target,voltage,pads['A']])
    assert result['ok'] and result['departure_count']==1,result
    assert len(result['non_sense_departures'])==1


def test_voltage_branch_rejoining_outside_source_remains_kelvin(tmp_path):
    board,pads=native(tmp_path,0,False,[((10.88,10),(13,10)),((10.88,10),(10.88,15)),
        ((10.88,15),(13,15)),((13,15),(13,10))])
    target=with_input(board,13,10)
    result=audit_pad_departures(pads['A'],pads['B'].GetPosition(),board.GetTracks(),target_pads=[target])
    assert not result['ok'] and result['departure_count']==2,result
    assert result['issues'][0]['reason']=='departure_not_perpendicular_inward'


def test_real_pad_copper_can_bridge_pieces_outside_source(tmp_path):
    board,pads=native(tmp_path,0,False,[((10.88,10),(10.88,15)),
        ((11.2,15),(13,15))])
    target=with_input(board,13,15)
    voltage=with_input(board,11.04,15,'VOLTAGE',size=(.6,.6))
    result=audit_pad_departures(pads['A'],pads['B'].GetPosition(),board.GetTracks(),
        target_pads=[target],connectivity_pads=[voltage])
    assert not result['ok'] and result['departure_count']==1,result
    assert result['issues'][0]['reason']=='departure_not_perpendicular_inward'


def test_near_input_is_not_a_connection_and_every_input_must_be_reached(tmp_path):
    board,pads=native(tmp_path,0,False,[((10.88,10),(13,10))])
    target=with_input(board,13,10)
    missed=with_input(board,13,10.5,'MISSED')
    result=audit_pad_departures(pads['A'],pads['B'].GetPosition(),board.GetTracks(),target_pads=[target,missed])
    assert not result['ok'] and result['departure_count']==1,result
    assert result['unreachable_input_pad_uuids']==[missed.m_Uuid.AsString()]


def test_overlapping_pad_cannot_reintroduce_cut_force_node(tmp_path):
    board,pads=native(tmp_path,0,False,[((10.88,10),(13,10))])
    target=with_input(board,13,10)
    bridge=with_input(board,10,10,'BRIDGE')
    result=audit_pad_departures(pads['A'],pads['B'].GetPosition(),board.GetTracks(),
        target_pads=[target],connectivity_pads=[bridge])
    assert not result['ok']
    assert result['issues'][0]['reason']=='connectivity_pad_overlaps_source_cut'


def test_offset_pad_is_not_silently_assumed_centred(tmp_path):
    board,pads=native(tmp_path,0,False,[((10.88,10),(13,10))])
    pads['A'].SetOffset(pcbnew.VECTOR2I(100000,0))
    result=audit_pad_departures(pads['A'],pads['B'].GetPosition(),board.GetTracks())
    assert not result['ok']
    assert result['issues'][0]['reason']=='unsupported_native_departure_shape'


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_production_checker_retains_good_branching_and_transforms(angle,back):
    from test_kelvin_discipline import _Board
    from cec_constraints import _chk_kelvin_inner
    fixture=_Board();fixture.synth()
    for item in [*fixture.b.GetFootprints(),*fixture.b.GetTracks()]:
        if back:item.Flip(pcbnew.VECTOR2I(0,0),False)
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    result=_chk_kelvin_inner(fixture.b,'',{})
    assert result[0] is True,result


@pytest.mark.parametrize('bad_origin',[True,False])
def test_production_checker_rejects_wrong_exit_or_near_miss_input(bad_origin):
    from test_kelvin_discipline import _Board
    from cec_constraints import _chk_kelvin_inner
    fixture=_Board()
    if bad_origin:hi=[(10.78,10),(5,10),(5,6),(13,6)]
    else:hi=[(10.78,10),(12,10),(12,5.3),(13,5.3)]
    lo=[(15.22,10),(14,10),(14,13.5),(13,13.5)]
    for net,points in [(fixture.hi,hi),(fixture.lo,lo)]:
        for a,b in zip(points,points[1:]):_trk(fixture.b,net,a,b)
    result=_chk_kelvin_inner(fixture.b,'',{})
    assert result[0] is False,result
    expected='departure_not_on_inner_face' if bad_origin else 'input_not_reached_from_source'
    assert expected in result[1]
    assert result[2][0]['native_departure']['contact_count']==1


@pytest.mark.parametrize('connected_leg',[None,'hi','lo'])
def test_routed_board_with_missing_source_contact_never_reports_kelvin_pass(connected_leg):
    from test_kelvin_discipline import _Board
    from cec_constraints import _chk_kelvin_inner
    fixture=_Board();fixture.locked_trunk()
    points={'hi':[(10.78,10),(12,10),(12,6),(13,6)],
            'lo':[(15.22,10),(14,10),(14,13.5),(13,13.5)]}
    if connected_leg:
        for a,b in zip(points[connected_leg],points[connected_leg][1:]):
            _trk(fixture.b,getattr(fixture,connected_leg),a,b)
    result=_chk_kelvin_inner(fixture.b,'',{})
    assert result[0] is False,result
    missing=[p for p in result[2] if p['native_departure']['contact_count']==0]
    assert len(missing)==(2 if connected_leg is None else 1)
    assert all(p['why']=='no_native_pad_contact' for p in missing)
    assert all(p['native_departure']['unreachable_input_pad_uuids'] for p in missing)


def test_wholly_unrouted_floorplan_retains_explicit_route_time_state():
    from test_kelvin_discipline import _Board
    from cec_constraints import _chk_kelvin_inner
    assert _chk_kelvin_inner(_Board().b,'',{})==(None,'floorplan (route-time)')


@pytest.mark.parametrize('kwargs',[{'inner_min_mm':-1},{'inner_min_mm':float('nan')},
    {'heading_tolerance_nm':-1},{'heading_tolerance_nm':1.5}])
def test_invalid_policy_is_not_a_waiver(tmp_path,kwargs):
    board,pads=native(tmp_path,0,False,[])
    with pytest.raises(ValueError):audit_pad_departures(pads['A'],pads['B'].GetPosition(),[],**kwargs)

"""One generic predicate protects every Kelvin synthesis branch."""
from unittest.mock import patch
import pcbnew
import pytest
import cec_fr as fr
import cec_route_quality as quality
from cec_local_copper_cell import copper_inventory
from test_kelvin_discipline import _Board,_trk,_fp,_pad_smd,HI,LO,PAIR


def point(x,y):return pcbnew.VECTOR2I_MM(x,y)


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_loaded_unlocked_outward_target_cannot_escape_back_through_force_pad(tmp_path,angle,back):
    world=_Board()
    world.p10.SetPosition(point(6,6))  # canonical target-inward test refuses
    for fp in world.b.GetFootprints():
        if back:fp.Flip(point(0,0),False)
        fp.Rotate(point(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    path=tmp_path/'anonymous.kicad_pcb';pcbnew.SaveBoard(str(path),world.b,True)
    board=pcbnew.LoadBoard(str(path))
    result=fr.synthesize_kelvin_taps(board,kelvin_pairs=PAIR)
    assert result['refused'].get(HI),result
    assert not result['by_net'].get(HI)
    assert any(w['kind']=='kelvin_launch' for row in result['refused_details']
               if row['net']==HI for w in row['blocker_details'])
    geometric=quality.analyze_board(board,critical_nets={HI,LO})
    assert geometric['geometry_ok'],geometric
    assert all(t.GetClass()=='PCB_TRACK' and t.GetLayer()==(pcbnew.B_Cu if back else pcbnew.F_Cu)
               for t in board.GetTracks())
    assert not any(t.GetNetname()==HI for t in board.GetTracks())


@pytest.mark.parametrize('kind',['pad','track','via','zone'])
def test_existing_partner_sense_copper_is_not_exempt(tmp_path,kind):
    world=_Board();board=world.b
    a,b=point(5,3),point(17,3)
    if kind=='pad':_pad_smd(_fp(board,'OTHER','foreign sense'), '1',world.lo,11,3,.8,.8)
    if kind=='track':_trk(board,world.lo,(11,2),(11,4),locked=True)
    if kind=='via':
        via=pcbnew.PCB_VIA(board);via.SetPosition(point(11,3))
        via.SetWidth(pcbnew.FromMM(.6));via.SetDrill(pcbnew.FromMM(.3))
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(world.lo);board.Add(via)
    if kind=='zone':
        zone=pcbnew.ZONE(board);zone.SetLayer(pcbnew.F_Cu);zone.SetNet(world.lo)
        zone.SetZoneName(fr.PIPELINE_POUR_PREFIXES[0]+'synthetic')
        poly=zone.Outline();poly.NewOutline()
        for x,y in ((10,2),(12,2),(12,4),(10,4)):poly.Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
        board.Add(zone)
    path=tmp_path/'foreign.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    board=pcbnew.LoadBoard(str(path));before=copper_inventory(board)
    hi,lo=(board.GetNetcodeFromNetname(net) for net in (HI,LO))
    assert fr._tap_foreign_clear(board,a,b,pcbnew.FromMM(.25),pcbnew.F_Cu,pcbnew.FromMM(.2),{hi,lo})
    assert not fr._tap_candidate_clear(board,[a,b],pcbnew.FromMM(.25),pcbnew.F_Cu,
        pcbnew.FromMM(.2),hi,own_net=HI)
    assert copper_inventory(board)==before
    certificate=fr._tap_path_refusal_certificate(board,[a,b],pcbnew.FromMM(.25),
        pcbnew.F_Cu,pcbnew.FromMM(.2),{hi},hi,path_kind='direct',own_net=HI)
    assert any(row['net']==LO for row in certificate['blocked_legs'])


def test_raw_heading_refusal_is_witnessed_before_mutation():
    world=_Board();before=copper_inventory(world.b)
    path=[point(4,3),point(9,6)];code=world.hi.GetNetCode()
    assert not fr._tap_candidate_clear(world.b,path,pcbnew.FromMM(.25),pcbnew.F_Cu,
        pcbnew.FromMM(.2),code,own_net=HI)
    report=fr._tap_path_refusal_certificate(world.b,path,pcbnew.FromMM(.25),pcbnew.F_Cu,
        pcbnew.FromMM(.2),{code},code,path_kind='straight',own_net=HI)
    witness=next(row for row in report['blocked_legs'] if row['kind']=='route_geometry')
    assert witness['leg_start_mm']==[4.,3.] and witness['leg_end_mm']==[9.,6.]
    assert not witness['ok'] and copper_inventory(world.b)==before


def test_every_emission_branch_including_vbus_obeys_shared_guard():
    world=_Board();before=copper_inventory(world.b)
    with patch.object(fr,'_tap_candidate_clear',return_value=False) as guard:
        report=world.synth()
    assert guard.call_count>1 and report['taps']==0
    assert copper_inventory(world.b)==before


def test_legal_45_degree_direct_and_pending_reservation_checks_remain():
    world=_Board();board=world.b;code=world.hi.GetNetCode();a,b=point(3,3),point(5,5)
    args=(board,[a,b],pcbnew.FromMM(.25),pcbnew.F_Cu,pcbnew.FromMM(.2),code)
    assert fr._tap_candidate_clear(*args,own_net=HI)
    pending=[([point(3,5),point(5,3)],world.lo.GetNetCode(),LO,'foreign',pcbnew.F_Cu)]
    assert not fr._tap_candidate_clear(*args,own_net=HI,pending=pending)
    reserved=[dict(net=LO,layer='F.Cu',x0=3.8,y0=3.8,x1=4.2,y1=4.2)]
    assert not fr._tap_candidate_clear(*args,own_net=HI,reservations=reserved)

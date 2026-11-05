"""Native fixture: intersect a pin aperture, bypass disk and return-via domain."""
from copy import deepcopy
import math

import pcbnew
import pytest

import cec_certificate_repair as repair
import cec_fab_profile as fab
import cec_fr as fr
import cec_pad_face_launch as faces
import cec_support_motion as motion
import cec_support_pin_aperture as aperture


def fixture(quarter=0,back=False):
    board=pcbnew.CreateEmptyBoard(); board.SetCopperLayerCount(6)
    props=board.GetProperties(); props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    board.GetDesignSettings().m_MinClearance=200000
    board.GetDesignSettings().m_TrackMinWidth=100000
    board.GetDesignSettings().m_HoleToHoleMin=200000
    board.GetDesignSettings().m_ViasMinSize=300000
    board.GetDesignSettings().m_MinThroughDrill=200000
    board.GetDesignSettings().m_ViasMinAnnularWidth=50000
    layer=pcbnew.B_Cu if back else pcbnew.F_Cu
    nets={}
    for name in ('/RENAMED_SIGNAL','/SUPPLY','GND'):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);nets[name]=net
    def point(x,y):
        for _ in range(quarter):x,y=-y,x
        return [x+80.,y+90.]
    def footprint(ref,centre,rows):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(*point(*centre)));fp.SetLayer(layer);board.Add(fp)
        pads=[]
        for number,net,at,size in rows:
            p=pcbnew.PAD(fp);p.SetNumber(number);p.SetNet(nets[net]);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetPosition(pcbnew.VECTOR2I_MM(*point(*at)))
            p.SetSize(pcbnew.VECTOR2I_MM(*size));p.SetOrientationDegrees(quarter*90)
            layers=pcbnew.LSET();layers.AddLayer(layer);p.SetLayerSet(layers);fp.Add(p);pads.append(p)
        return fp,pads
    owner,pins=footprint('OWNER_X',(0,0),[
        ('1','/RENAMED_SIGNAL',(.25,1.15),(.2,.6)),
        ('2','GND',(-.25,1.15),(.2,.6)),
        ('3','/SUPPLY',(.675,.375),(.2,.6))])
    cap,pads=footprint('BYPASS_Y',(.999,2.275),[
        ('1','/SUPPLY',(1.775,2.275),(.9,.95)),('2','GND',(.225,2.275),(.9,.95))])
    for at in ((.225,2.275),(-.272704,1.627297)):
        via=pcbnew.PCB_VIA(board);via.SetNet(nets['GND']);via.SetPosition(pcbnew.VECTOR2I_MM(*point(*at)))
        via.SetWidth(350000);via.SetDrill(250000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetLocked(True);board.Add(via)
    detail=dict(cap_ref='BYPASS_Y',owner_ref='OWNER_X',owner_pin='3',rail='/SUPPLY',status='assigned',
        return_gate_mode='absolute_ground_distance',owner_supply_position_mm=point(.675,.375),
        cap_supply_position_mm=point(1.775,2.275),owner_ground_position_mm=point(-.25,1.15),
        cap_ground_position_mm=point(.225,2.275),owner_ground_positions_mm=[dict(pin='2',position=point(-.25,1.15))],
        ground_distance_mm=math.hypot(.475,1.125),return_limit_mm=2.5,supply_excess_limit_mm=.25,
        tangent_target=dict(best_loop=dict(supply_mm=2.,loop_proxy_mm=3.231363)))
    target=dict(ref='BYPASS_Y',target_net='/RENAMED_SIGNAL',endpoint_ref='OWNER_X',endpoint_pad='1',
        endpoint_x_mm=point(.25,1.15)[0],endpoint_y_mm=point(.25,1.15)[1],
        motion='away_from_endpoint',companion_refs=[])
    return board,cap,pins[0],target,[detail],layer


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_aperture_and_alternative_pad_launch_are_affine_and_immutable(quarter,back):
    board,cap,pin,target,details,layer=fixture(quarter,back)
    before=(tuple(cap.GetPosition()),[(p.m_Uuid.AsString(),tuple(p.GetPosition())) for fp in board.GetFootprints() for p in fp.Pads()])
    original=deepcopy((target,details))
    candidates=aperture.proposals(board,target,details,support_limits=motion.limits())
    assert candidates
    assert (tuple(cap.GetPosition()),[(p.m_Uuid.AsString(),tuple(p.GetPosition())) for fp in board.GetFootprints() for p in fp.Pads()])==before
    assert (target,details)==original
    chosen=candidates[0]
    assert math.hypot(chosen['dx_mm'],chosen['dy_mm'])<.3
    assert not chosen['pin_aperture']['release_authority']
    cap.Move(pcbnew.VECTOR2I_MM(chosen['dx_mm'],chosen['dy_mm']))
    common=dict(profile=fab.PROFILES['jlcpcb_6l_pofv_signal'],leg_ok=lambda *a:True,limit=1,
        offsets_mm=fr._dogbone_offset_ladder_mm(),angles_deg=((90+quarter*90)%360,),foreign_cache={})
    old=fr._local_pofv_dogbone_seats(board,pin.GetPosition(),layer,200000,pin.GetNetCode(),200000,**common)
    assert not old
    common['foreign_cache']={}
    found=fr._local_pofv_dogbone_seats(board,pin.GetPosition(),layer,200000,pin.GetNetCode(),200000,
        **common,allow_face_launch=True)
    assert found and found[0][1][0][1]!=pin.GetPosition()
    repair._lay_ops(board,found[0][1],pin.GetNetCode(),lock=False)
    via=next(v for v in board.GetTracks() if v.GetClass()=='PCB_VIA' and v.GetNetCode()==pin.GetNetCode())
    assert fab.local_pofv_via_decision(board,via)[0]


@pytest.mark.parametrize('fault',['locked','fixed','short_motion','no_profile','unassigned','foreign_inner'])
def test_aperture_does_not_waive_existing_domains(fault):
    board,cap,pin,target,details,layer=fixture()
    limits=motion.limits()
    if fault=='locked':cap.SetLocked(True)
    if fault=='fixed':limits['immutable_refs']=['BYPASS_Y']
    if fault=='short_motion':limits['max_shift_mm']=.05
    if fault=='no_profile':
        props=board.GetProperties();props['CEC_FAB_PROFILE']='';board.SetProperties(props)
    if fault=='unassigned':details[0]['status']='missing'
    if fault=='foreign_inner':
        track=pcbnew.PCB_TRACK(board);track.SetNet(board.FindNet('GND'));track.SetLayer(pcbnew.In2_Cu)
        track.SetWidth(1500000);track.SetStart(pcbnew.VECTOR2I_MM(77,91.6));track.SetEnd(pcbnew.VECTOR2I_MM(83,91.6));board.Add(track)
    assert not aperture.proposals(board,target,details,support_limits=limits)


@pytest.mark.parametrize('kwargs',[{'max_candidates':0},{'max_launches':0},{'max_candidates':True}])
def test_aperture_search_is_explicitly_bounded(kwargs):
    board,cap,pin,target,details,layer=fixture()
    with pytest.raises(ValueError):aperture.proposals(board,target,details,**kwargs)


def test_face_fallback_retains_edge_and_length_guards():
    board,cap,pin,target,details,layer=fixture()
    rows=aperture.proposals(board,target,details,support_limits=motion.limits())
    cap.Move(pcbnew.VECTOR2I_MM(rows[0]['dx_mm'],rows[0]['dy_mm']))
    for policy in (dict(leg_ok=lambda *a:False),dict(leg_ok=lambda *a:True,max_length_nm=1000)):
        assert not fr._local_pofv_dogbone_seats(board,pin.GetPosition(),layer,200000,pin.GetNetCode(),200000,
            profile=fab.PROFILES['jlcpcb_6l_pofv_signal'],limit=1,offsets_mm=fr._dogbone_offset_ladder_mm(),
            angles_deg=(0,90,180,270),foreign_cache={},allow_face_launch=True,**policy)

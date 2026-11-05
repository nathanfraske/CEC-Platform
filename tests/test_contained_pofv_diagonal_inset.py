"""Non-square native lands need canonical inset rays, not bbox corners."""
import math
import time

import pcbnew
import pytest

import cec_fab_profile as fab
import cec_fr as fr
import cec_local_copper_cell as copper


def fixture(quarter=0,back=False,*,line_sum=21.05,pad_width=.9):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    settings=b.GetDesignSettings()
    settings.m_ViasMinSize=pcbnew.FromMM(.5)
    settings.m_MinThroughDrill=pcbnew.FromMM(.2)
    settings.m_ViasMinAnnularWidth=pcbnew.FromMM(.1)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for name in ('unrelated_control','unrelated_current_bus'):
        b.Add(pcbnew.NETINFO_ITEM(b,name))
    f=pcbnew.FOOTPRINT(b);f.SetReference('RANDOMIZED_OWNER')
    p=pcbnew.PAD(f);p.SetNumber('arbitrary_pin');p.SetNet(b.FindNet('unrelated_control'))
    p.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);p.SetRoundRectRadiusRatio(.15)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
    p.SetSize(pcbnew.VECTOR2I_MM(pad_width,.95));f.Add(p)
    f.SetPosition(pcbnew.VECTOR2I_MM(10,10));f.SetOrientationDegrees(quarter*90);b.Add(f)
    if back:f.Flip(f.GetPosition(),False)
    def transform(x,y):
        if back:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    t=pcbnew.PCB_TRACK(b);t.SetStart(transform(9,line_sum-9))
    t.SetEnd(transform(line_sum-9,9));t.SetWidth(pcbnew.FromMM(1.))
    t.SetLayer(pcbnew.In2_Cu);t.SetNet(b.FindNet('unrelated_current_bus'));t.SetLocked(True);b.Add(t)
    return b,p


def seats(b,p,**kwargs):
    return fr._local_pofv_inset_seats(b,p.GetPosition(),p.GetLayerSet().CuStack()[0],
        200000,p.GetNetCode(),200000,
        profile=fab.get_profile(fab.board_profile_name(b)),leg_ok=lambda *_:True,**kwargs)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_rectangular_corner_only_escape_is_native_guarded_and_canonical(quarter,back):
    b,p=fixture(quarter,back);before=copper.copper_inventory(b)
    assert not fr._via_spot_clear(b,p.GetPosition(),500000,200000,{p.GetNetCode()},
        drill_nm=250000,net_code=p.GetNetCode())
    found=seats(b,p);assert found
    for xy,ops in found:
        dx,dy=xy[0]-p.GetPosition().x,xy[1]-p.GetPosition().y
        assert dx and dy and abs(dx)==abs(dy)
        at=pcbnew.VECTOR2I(*xy);_,_,drill,diameter=ops[-1]
        assert fab.via_pad_decision(b,p,at,pcbnew.FromMM(diameter),
            pcbnew.FromMM(drill),p.GetNetCode())[0]
        assert pcbnew.FromMM(diameter)>=b.GetDesignSettings().m_ViasMinSize
        assert fr._via_spot_clear(b,at,pcbnew.FromMM(diameter),200000,{p.GetNetCode()},
            drill_nm=pcbnew.FromMM(drill),net_code=p.GetNetCode())
        assert math.hypot(dx,dy)<400000
    assert before==copper.copper_inventory(b)


@pytest.mark.parametrize('cause',['too_small','buried_blocker','ambiguous','expired','length','edge'])
def test_new_diagonal_sampler_never_waives_existing_guards(cause):
    b,p=fixture(pad_width=.49 if cause=='too_small' else .9,
        line_sum=20.9 if cause=='buried_blocker' else 21.05)
    kwargs={}
    if cause=='ambiguous':
        clone=pcbnew.PAD(p.GetParentFootprint());clone.SetNumber('duplicate')
        clone.SetNet(p.GetNet());clone.SetPosition(p.GetPosition());clone.SetSize(p.GetSize())
        clone.SetShape(p.GetShape());clone.SetAttribute(p.GetAttribute());clone.SetLayerSet(p.GetLayerSet())
        p.GetParentFootprint().Add(clone)
    if cause=='expired':kwargs['deadline_monotonic']=time.monotonic()-1
    if cause=='length':kwargs['max_length_nm']=1000
    if cause=='edge':
        assert not fr._local_pofv_inset_seats(b,p.GetPosition(),pcbnew.F_Cu,200000,
            p.GetNetCode(),200000,profile=fab.get_profile(fab.board_profile_name(b)),
            leg_ok=lambda *_:False)
    else:assert not seats(b,p,**kwargs)


def test_absent_profile_is_not_diagonal_creation_authority():
    b,p=fixture()
    assert not fr._local_pofv_inset_seats(b,p.GetPosition(),pcbnew.F_Cu,200000,
        p.GetNetCode(),200000,profile=None,leg_ok=lambda *_:True)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('accept',[True,False])
def test_native_bridge_reuses_real_barrel_and_receives_diagonal_surface_launch(quarter,back,accept):
    b,p=fixture(quarter,back)
    x,y=7.,7.
    if back:x=20-x
    for _ in range(quarter):x,y=20-y,x
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(x,y))
    via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(p.GetNet());b.Add(via)
    before=copper.copper_inventory(b)
    face=p.GetLayerSet().CuStack()[0]
    ops=fr._lastmile_bridge(b,via.GetPosition(),{face,pcbnew.In2_Cu},p.GetPosition(),{face},
        200000,p.GetNetCode(),[pcbnew.In2_Cu],200000,seat_limit=4,allow_maze=False,
        allow_lattice=False,deadline_monotonic=time.monotonic()+2,
        canonical_turns_only=True,endpoint_handoffs=False,ops_ok=lambda _:accept)
    assert bool(ops)==accept
    if accept:
        incoming=[op for op in ops if op[0]=='via'];assert len(incoming)==1
        at=incoming[0][1];dx,dy=at.x-p.GetPosition().x,at.y-p.GetPosition().y
        assert dx and dy and abs(dx)==abs(dy)
        assert fab.via_pad_decision(b,p,at,pcbnew.FromMM(incoming[0][3]),
            pcbnew.FromMM(incoming[0][2]),p.GetNetCode())[0]
        assert any(op[0]=='trk' and op[4]==pcbnew.In2_Cu for op in ops)
    assert before==copper.copper_inventory(b)

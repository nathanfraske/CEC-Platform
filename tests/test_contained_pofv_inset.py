"""Native land-area escape with preserved process and all-layer guards."""
import time
import pytest
import pcbnew
import cec_fr as fr
import cec_fab_profile as fab
import cec_local_copper_cell as copper


def fixture(*,quarter=0,back=False,width=.8):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    settings=b.GetDesignSettings()
    settings.m_ViasMinSize=pcbnew.FromMM(.3)
    settings.m_MinThroughDrill=pcbnew.FromMM(.2)
    settings.m_ViasMinAnnularWidth=pcbnew.FromMM(.05)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    for name in ('renamed_endpoint','buried_foreign'):b.Add(pcbnew.NETINFO_ITEM(b,name))
    f=pcbnew.FOOTPRINT(b);f.SetReference('UNRELATED_OWNER');f.SetValue('arbitrary_part')
    p=pcbnew.PAD(f);p.SetNumber('unrelated_pin');p.SetNet(b.FindNet('renamed_endpoint'))
    p.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);p.SetRoundRectRadiusRatio(.15)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
    p.SetSize(pcbnew.VECTOR2I_MM(width,width));f.Add(p)
    f.SetPosition(pcbnew.VECTOR2I_MM(10,10));f.SetOrientationDegrees(quarter*90);b.Add(f)
    if back:f.Flip(f.GetPosition(),False)
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(10.25,9))
    t.SetEnd(pcbnew.VECTOR2I_MM(10.25,11));t.SetWidth(pcbnew.FromMM(.2))
    t.SetLayer(pcbnew.In2_Cu);t.SetNet(b.FindNet('buried_foreign'));t.SetLocked(True);b.Add(t)
    return b,p


def seats(b,p,**kwargs):
    return fr._local_pofv_inset_seats(b,p.GetPosition(),p.GetLayerSet().CuStack()[0],
        pcbnew.FromMM(.2),p.GetNetCode(),pcbnew.FromMM(.2),
        profile=fab.get_profile(fab.board_profile_name(b)),leg_ok=lambda *_:True,**kwargs)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_contained_off_center_barrel_clears_buried_obstacle_without_mutation(quarter,back):
    b,p=fixture(quarter=quarter,back=back);before=copper.copper_inventory(b)
    assert not fr._via_spot_clear(b,p.GetPosition(),pcbnew.FromMM(.35),pcbnew.FromMM(.2),
        {p.GetNetCode()},drill_nm=pcbnew.FromMM(.25),net_code=p.GetNetCode())
    found=seats(b,p);assert 0<len(found)<=4
    for xy,ops in found:
        at=pcbnew.VECTOR2I(*xy);_,_,drill,dia=ops[-1]
        assert xy!=tuple(p.GetPosition())
        assert fab.via_pad_decision(b,p,at,pcbnew.FromMM(dia),pcbnew.FromMM(drill),p.GetNetCode())[0]
        assert fr._via_spot_clear(b,at,pcbnew.FromMM(dia),pcbnew.FromMM(.2),{p.GetNetCode()},
            drill_nm=pcbnew.FromMM(drill),net_code=p.GetNetCode())
        a,c=ops[0][1:3];assert a.x==c.x or a.y==c.y or abs(a.x-c.x)==abs(a.y-c.y)
    assert before==copper.copper_inventory(b)


def test_guard_budget_and_too_small_land_never_become_a_waiver():
    b,p=fixture();assert not seats(b,p,deadline_monotonic=time.monotonic()-1)
    assert not seats(b,p,max_length_nm=1000)
    assert not seats(b,p,limit=0)
    assert not fr._local_pofv_inset_seats(b,p.GetPosition(),pcbnew.F_Cu,200000,p.GetNetCode(),200000,
        profile=fab.get_profile(fab.board_profile_name(b)),leg_ok=lambda *_:False)
    b,p=fixture(width=.29);assert not seats(b,p)


def test_ambiguous_owner_or_absent_process_is_not_small_via_authority():
    b,p=fixture();clone=pcbnew.PAD(p.GetParentFootprint());clone.SetNumber('duplicate')
    clone.SetNet(b.FindNet('renamed_endpoint'));clone.SetPosition(p.GetPosition())
    clone.SetSize(p.GetSize());clone.SetLayerSet(p.GetLayerSet());clone.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.GetParentFootprint().Add(clone);assert not seats(b,p)
    b,p=fixture();props=b.GetProperties();props['CEC_FAB_PROFILE']='unknown';b.SetProperties(props)
    assert not fr._local_pofv_inset_seats(b,p.GetPosition(),pcbnew.F_Cu,200000,p.GetNetCode(),200000,
        profile=None,leg_ok=lambda *_:True)


@pytest.mark.parametrize('accept',[True,False])
def test_real_bridge_uses_contained_seat_but_transaction_receiver_can_refuse(accept):
    b,p=fixture();f=pcbnew.FOOTPRINT(b);f.SetReference('OTHER_RENAMED_ENDPOINT')
    other=pcbnew.PAD(f);other.SetNumber('other');other.SetNet(b.FindNet('renamed_endpoint'))
    other.SetShape(pcbnew.PAD_SHAPE_RECT);other.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    other.SetSize(pcbnew.VECTOR2I_MM(.8,.8));other.SetLayerSet(pcbnew.PAD.SMDMask())
    f.Add(other);f.SetPosition(pcbnew.VECTOR2I_MM(8,10));b.Add(f)
    before=copper.copper_inventory(b)
    ops=fr._lastmile_bridge(b,p.GetPosition(),{pcbnew.F_Cu},other.GetPosition(),{pcbnew.F_Cu},
        200000,p.GetNetCode(),[pcbnew.In2_Cu],200000,seat_limit=4,allow_maze=False,
        allow_lattice=False,deadline_monotonic=time.monotonic()+3,ops_ok=lambda _:accept)
    assert bool(ops)==accept
    if accept:
        barrels=[op for op in ops if op[0]=='via'];assert len(barrels)==2
        assert any(tuple(op[1])!=tuple(p.GetPosition()) and
            fab.via_pad_decision(b,p,op[1],pcbnew.FromMM(op[3]),pcbnew.FromMM(op[2]),p.GetNetCode())[0]
            for op in barrels),ops
    assert before==copper.copper_inventory(b)


def test_local_width_aware_geometry_keeps_drills_and_the_historical_default():
    profile=fab.get_profile('jlcpcb_6l_pofv_high_current')
    assert tuple(tuple(round(v*1e6) for v in row) for row in fab.local_pofv_geometry_candidates(profile))==((350000,250000),(300000,200000))
    assert fab.local_pofv_geometry_candidates(profile,minimum_web_nm=200000)==((.45,.25),(.4,.2))
    assert not fab.local_pofv_geometry_candidates(None,minimum_web_nm=200000)
    for dia,drill in fab.local_pofv_geometry_candidates(profile,minimum_web_nm=477370):
        assert round((dia-drill)*1e6)>=477370
        assert fab.pofv_dimensions(profile,dia,drill)[0]


@pytest.mark.parametrize('web',[True,-1,2000001,.2,float('inf')])
def test_local_width_menu_requires_a_bounded_exact_conductor_width(web):
    with pytest.raises(ValueError):
        fab.local_pofv_geometry_candidates(fab.get_profile('jlcpcb_6l_pofv_high_current'),minimum_web_nm=web)


@pytest.mark.parametrize('web,grid',[(True,None),(-1,None),(2000001,None),(0,True),(0,.09),(0,.751),(0,float('nan'))])
def test_bridge_refuses_invalid_local_web_or_middle_resolution(web,grid):
    b,p=fixture()
    with pytest.raises(ValueError):
        fr._lastmile_bridge(b,p.GetPosition(),{pcbnew.F_Cu},pcbnew.VECTOR2I_MM(8,10),{pcbnew.F_Cu},
            200000,p.GetNetCode(),[pcbnew.In2_Cu],200000,deadline_monotonic=time.monotonic()+2,
            minimum_local_via_web_nm=web,middle_grid_mm=grid)


@pytest.mark.parametrize('quarter,back',[(0,False),(1,False),(2,True),(3,True)])
def test_real_explicit_fine_middle_reuses_native_contained_seats_and_finite_capture(quarter,back):
    b,p=fixture(quarter=quarter,back=back,width=1.2)
    f=pcbnew.FOOTPRINT(b);f.SetReference('RENAMED_FINE_PEER')
    other=pcbnew.PAD(f);other.SetNumber('arbitrary_peer_pin');other.SetNet(b.FindNet('renamed_endpoint'))
    other.SetShape(pcbnew.PAD_SHAPE_RECT);other.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    other.SetSize(pcbnew.VECTOR2I_MM(1.2,1.2));other.SetLayerSet(pcbnew.PAD.SMDMask())
    f.Add(other);f.SetPosition(pcbnew.VECTOR2I_MM(8,10));b.Add(f)
    if back:f.Flip(f.GetPosition(),False)
    face=p.GetLayerSet().CuStack()[0]
    fence=pcbnew.PCB_TRACK(b);fence.SetNet(b.FindNet('buried_foreign'));fence.SetLayer(face)
    fence.SetStart(pcbnew.VECTOR2I_MM(9,0));fence.SetEnd(pcbnew.VECTOR2I_MM(9,20))
    fence.SetWidth(200000);b.Add(fence)
    before=copper.copper_inventory(b);diagnostics={}
    ops=fr._lastmile_bridge(b,p.GetPosition(),{face},other.GetPosition(),{face},200000,
        p.GetNetCode(),[pcbnew.F_Cu,pcbnew.In2_Cu,pcbnew.B_Cu],200000,
        seat_limit=4,allow_maze=True,allow_lattice=False,deadline_monotonic=time.monotonic()+3,
        middle_grid_mm=.1,minimum_local_via_web_nm=200000,
        _multilayer_only=True,_multilayer_pair_limit=2,diagnostics=diagnostics)
    assert ops,diagnostics
    assert all(op[0]!='via' or round((op[3]-op[2])*1e6)>=200000 for op in ops)
    found=[r for r in diagnostics['middle_searches'] if r['stop']=='found']
    assert found and all(r['heuristic_weight']==3. and r['terminal_capture_mm']==1.
        and r['neutral_state_dominance_active'] and not r['shortest_path_qualified'] for r in found)
    assert any(op[0]=='via' and tuple(op[1])!=tuple(p.GetPosition())
        and fab.via_pad_decision(b,p,op[1],pcbnew.FromMM(op[3]),pcbnew.FromMM(op[2]),p.GetNetCode())[0] for op in ops)
    assert before==copper.copper_inventory(b)

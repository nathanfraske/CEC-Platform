"""A retained ordinary barrel is not a via-on-pad or reference-plane waiver."""
import math,time
import pcbnew
import pytest
import cec_cell_escape_replan as op
import cec_additive_route_receiving as additive
import cec_ground_return_shortcut as shortcut
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
from cec_native_items import discard_items
from test_native_ground_terminal_branch import fixture as source_fixture
from test_field_proposals import track


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu,offset=(.6,.4)):
    b,source,ids,ports,owner,cap,old=source_fixture(tmp_path,quarter=quarter,mirror=mirror,layer=layer)
    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    pad=cap.FindPadByNumber('2');pad.SetSize(pcbnew.VECTOR2I_MM(.56,.62))
    pad.SetOrientationDegrees(quarter*90)
    via=pcbnew.PCB_VIA(b);via.SetNet(b.FindNet('GND'));via.SetPosition(point(9.5+offset[0],8+offset[1]))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetLocked(True);b.Add(via);additive._ground_refill(b);field._save_field_snapshot(b,source)
    return b,source,pad,via,point


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_two_leg_immediate_return_keeps_real_barrel_and_actual_saved_reference_planes(tmp_path,quarter,mirror,layer):
    b,source,pad,via,_=fixture(tmp_path,quarter,mirror,layer);before=op.row._source_binding(b);raw=source.read_bytes()
    choices=op.retained_ground_barrel_ops(b,pad,deadline=time.monotonic()+10.)
    assert len(choices)==2 and all(len(c)==2 for c in choices)
    assert op.row._source_binding(b)==before and source.read_bytes()==raw
    assert len(shortcut._reference_contacts(b,via))==2
    blocked,_=fab.via_at_pad_conflicts(b,via.GetPosition(),600000,300000,pad.GetNetCode())
    assert blocked is None
    for choice in choices:
        assert choice[0][1]==tuple(pad.GetPosition()) and choice[-1][2]==tuple(via.GetPosition())
        assert sum(math.dist(a,z) for _,a,z,_,_ in choice)/1e6==pytest.approx(.2+.4*math.sqrt(2))
        assert all(kind=='trk' and width>=200000 and face==layer and
            (a[0]==z[0] or a[1]==z[1] or abs(a[0]-z[0])==abs(a[1]-z[1]))
            for kind,a,z,width,face in choice)
        a,z=choice[0][1:3];other=choice[1][2]
        assert (z[0]-a[0])*(other[0]-z[0])+(z[1]-a[1])*(other[1]-z[1])>0
        added=[]
        try:
            for _,a,z,width,face in choice:
                added.append(track(b,'GND',[v/1e6 for v in a],[v/1e6 for v in z],width=width/1e6,layer=face))
            witness=op.cell._existing_return(b,pad,.8,allow_native_track_body=True)
            # The witness can start at an intermediate point already inside
            # the real land; path budgeting still charges both full strokes.
            assert witness and 0<witness[0]<=.2+.4*math.sqrt(2)+1e-9
            assert force._uid(witness[1])==force._uid(via)
        finally:discard_items(b,added)
        assert op.row._source_binding(b)==before


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_literal_full_class_source_body_needs_no_overlapping_new_ground_stroke(tmp_path,quarter,mirror,layer):
    b,source,pad,via,point=fixture(tmp_path,quarter,mirror,layer,offset=(.6,0))
    start,end=point(9.,8.),via.GetPosition()
    old=track(b,'GND',[v/1e6 for v in start],[v/1e6 for v in end],width=.2,layer=layer)
    before=op.row._source_binding(b);raw=source.read_bytes()
    assert op.retained_ground_barrel_ops(b,pad,deadline=time.monotonic()+10.)==[[]]
    assert old.GetWidth()==200000 and op.row._source_binding(b)==before and source.read_bytes()==raw


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_body_observer_minimizes_against_a_still_live_old_endpoint_even_inside_longer_lease(
        tmp_path,quarter,mirror,layer):
    b,source,pad,via,point=fixture(tmp_path,quarter,mirror,layer,offset=(.6,0))
    track(b,'GND',[v/1e6 for v in point(9.5,8.)],[v/1e6 for v in via.GetPosition()],width=.2,layer=layer)
    pad.SetPosition(point(9.65,8.));before=op.row._source_binding(b)
    old=op.cell._existing_return(b,pad,16.,allow_native_track_body=False)
    actual=op.cell._existing_return(b,pad,16.,allow_native_track_body=True)
    tight=op.cell._existing_return(b,pad,.8,allow_native_track_body=True)
    assert old and actual and tight
    # Exact queried-pad-centre seeding now observes the retained stroke's
    # real interior at9.65mm; neither observer must detour via its9.5mm end.
    assert old[0]==pytest.approx(.45) and actual[0]==pytest.approx(.45)
    assert actual[0]==tight[0] and force._uid(actual[1])==force._uid(via)
    assert op.row._source_binding(b)==before


@pytest.mark.parametrize('fault',['narrow','off_axis','clipped_pad','gap'])
def test_a_thin_partial_off_axis_or_gapped_body_is_not_zero_emission_authority(tmp_path,fault):
    b,source,pad,via,point=fixture(tmp_path,offset=(.6,0))
    old=track(b,'GND',(9.,8.),(10.1,8.),width=.2)
    if fault=='narrow':old.SetWidth(199999)
    elif fault=='off_axis':pad.Move(pcbnew.VECTOR2I(0,1))
    elif fault=='clipped_pad':pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
    else:
        old.SetEnd(point(9.7,8.))
        track(b,'GND',(9.702,8.),(10.1,8.),width=.2)
    before=op.row._source_binding(b)
    assert [] not in op.retained_ground_barrel_ops(b,pad,deadline=time.monotonic()+10.)
    assert op.row._source_binding(b)==before


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_ordinary_dimensions_do_not_waive_partial_same_net_smd_overlap(tmp_path,layer):
    b,source,pad,via,_=fixture(tmp_path,layer=layer,offset=(.375,.375));before=op.row._source_binding(b)
    assert fab.board_legal_through_via_geometry(b,.6,.3)[:2]==(.6,.3)
    assert fab.via_at_pad_conflicts(b,via.GetPosition(),600000,300000,pad.GetNetCode())[0] is not None
    assert not op.retained_ground_barrel_ops(b,pad,deadline=time.monotonic()+10.)
    assert op.row._source_binding(b)==before


def test_actual_octilinear_length_not_euclidean_distance_owns_the_reach_budget(tmp_path):
    b,source,pad,via,_=fixture(tmp_path,offset=(.7,.3));before=op.row._source_binding(b)
    assert math.dist(tuple(pad.GetPosition()),tuple(via.GetPosition()))<800000
    assert .4+.3*math.sqrt(2)>.8
    assert not op.retained_ground_barrel_ops(b,pad,deadline=time.monotonic()+10.)
    assert op.row._source_binding(b)==before


@pytest.mark.parametrize('fault',['unfilled_plane','missing_plane','no_profile','blind','foreign_via',
    'unknown_dimensions','foreign_land','foreign_copper','outside','expired'])
def test_real_saved_planes_through_process_surface_clearance_and_time_are_required(tmp_path,fault):
    b,source,pad,via,point=fixture(tmp_path)
    if fault=='unfilled_plane':next(iter(b.Zones())).UnFill()
    elif fault=='missing_plane':discard_items(b,[next(iter(b.Zones()))])
    elif fault=='no_profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='';b.SetProperties(props)
    elif fault=='blind':via.SetViaType(pcbnew.VIATYPE_BLIND);via.SetLayerPair(pcbnew.F_Cu,pcbnew.In1_Cu)
    elif fault=='foreign_via':via.SetNet(b.FindNet('+3V3'))
    elif fault=='unknown_dimensions':via.SetWidth(100000);via.SetDrill(50000)
    elif fault=='foreign_land':
        other=next(p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()=='+3V3')
        other.SetPosition(via.GetPosition())
    elif fault=='foreign_copper':track(b,'+3V3',(9.8,7.7),(9.8,8.6),width=.2)
    elif fault=='outside':
        delta=pcbnew.VECTOR2I_MM(-9.5,0);pad.Move(delta);via.Move(delta)
    before=op.row._source_binding(b);deadline=time.monotonic()+10. if fault!='expired' else time.monotonic()-1.
    assert not op.retained_ground_barrel_ops(b,pad,deadline=deadline)
    assert op.row._source_binding(b)==before


def test_a_fully_contained_qualified_source_barrel_needs_no_decorative_spoke(tmp_path):
    b,source,pad,via,_=fixture(tmp_path,offset=(.025,0));pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    assert fab.local_pofv_via_decision(b,via)[0]
    assert op.cell._existing_return(b,pad,.8,allow_native_track_body=True)[0]==0.
    before=op.row._source_binding(b)
    assert not op.retained_ground_barrel_ops(b,pad,deadline=time.monotonic()+10.)
    assert op.row._source_binding(b)==before


def test_local_pofv_is_reproved_from_actual_proposed_stroke_without_changing_the_barrel(tmp_path):
    b,source,pad,via,_=fixture(tmp_path,offset=(.6,0));via.SetWidth(350000);via.SetDrill(250000)
    assert not fab.local_pofv_via_decision(b,via)[0]
    before=op.row._source_binding(b)
    choices=op.retained_ground_barrel_ops(b,pad,deadline=time.monotonic()+10.)
    assert len(choices)==1 and len(choices[0])==1
    assert via.GetWidth(via.TopLayer())==350000 and via.GetDrillValue()==250000
    assert op.row._source_binding(b)==before


def test_native_process_exception_cannot_leave_temporary_copper_in_the_proposal_board(tmp_path,monkeypatch):
    b,source,pad,via,_=fixture(tmp_path,offset=(.6,0));via.SetWidth(350000);via.SetDrill(250000)
    before=op.row._source_binding(b)
    def refuse(*a,**kw):raise ValueError('hostile_native_process_lookup')
    monkeypatch.setattr(fab,'local_pofv_via_decision',refuse)
    with pytest.raises(ValueError,match='hostile_native_process_lookup'):
        op.retained_ground_barrel_ops(b,pad,deadline=time.monotonic()+10.)
    assert op.row._source_binding(b)==before


@pytest.mark.parametrize('value',[0,-1,True,.800001,float('nan'),float('inf')])
def test_reach_is_finite_and_never_silently_expanded(tmp_path,value):
    b,source,pad,*_=fixture(tmp_path);before=op.row._source_binding(b)
    with pytest.raises(ValueError):op.retained_ground_barrel_ops(b,pad,deadline=time.monotonic()+10.,reach_mm=value)
    assert op.row._source_binding(b)==before


@pytest.mark.parametrize('value',[True,float('nan'),float('inf'),None])
def test_unknown_deadline_is_not_permission_for_unbounded_search(tmp_path,value):
    b,source,pad,*_=fixture(tmp_path);before=op.row._source_binding(b)
    with pytest.raises(ValueError):op.retained_ground_barrel_ops(b,pad,deadline=value)
    assert op.row._source_binding(b)==before

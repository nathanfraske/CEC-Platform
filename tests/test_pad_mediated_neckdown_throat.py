"""A real convex SMD land may connect an escape to its qualified in-pad via."""
import pcbnew
import pytest
import cec_fr as fr
import cec_force_current as force


def fixture(*, quarter=0, back=False, fault=None):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    net=pcbnew.NETINFO_ITEM(board,'/opaque_supply');board.Add(net)
    other=pcbnew.NETINFO_ITEM(board,'/foreign');board.Add(other)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('arbitrary_'+str(quarter));board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('input');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.5))
    pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetPosition(pcbnew.VECTOR2I_MM(10,10));pad.SetNet(net);fp.Add(pad)
    if fault=='nonconvex_shape':pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    if fault=='overlong_pad_path':pad.SetSize(pcbnew.VECTOR2I_MM(.8,6))
    prefix=pcbnew.PCB_TRACK(board);prefix.SetStart(pcbnew.VECTOR2I_MM(9.6,10))
    prefix.SetEnd(pcbnew.VECTOR2I_MM(9.8,10));prefix.SetWidth(200000);prefix.SetLayer(pcbnew.F_Cu)
    prefix.SetNet(net);board.Add(prefix)
    if fault=='branch':
        for end in ((9.7,9.9),(9.7,10.1)):
            track=pcbnew.PCB_TRACK(board);track.SetStart(prefix.GetStart());track.SetEnd(pcbnew.VECTOR2I_MM(*end))
            track.SetWidth(200000);track.SetLayer(pcbnew.F_Cu);track.SetNet(net);board.Add(track)
    via=pcbnew.PCB_VIA(board);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetWidth(350000);via.SetDrill(250000)
    via.SetPosition(pcbnew.VECTOR2I_MM(10.3 if fault=='partial_overlap' else 10.1,
        12 if fault=='overlong_pad_path' else 10));via.SetNet(other if fault=='foreign_via' else net);board.Add(via)
    if fault=='bad_dimensions':via.SetWidth(260000)
    if fault=='blind':via.SetViaType(pcbnew.VIATYPE_BLIND)
    group=pcbnew.PCB_GROUP(board);group.SetName('not the factory group' if fault=='wrong_group' else fr.LOCAL_POFV_SIGNAL_VIA_GROUP)
    board.Add(group);group.AddItem(via);via.SetLocked(True)
    if fault=='wrong_profile':
        props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l';board.SetProperties(props)
    throat=pcbnew.PCB_TRACK(board);throat.SetStart(via.GetPosition())
    throat.SetEnd(via.GetPosition()+pcbnew.VECTOR2I_MM(0,1));throat.SetWidth(500000 if fault=='narrow_throat' else 1000000)
    throat.SetLayer(pcbnew.F_Cu if fault=='same_face_throat' else pcbnew.B_Cu)
    throat.SetNet(other if fault=='foreign_throat' else net);board.Add(throat)
    if fault=='disconnected_throat':
        throat.Move(pcbnew.VECTOR2I_MM(.8,0))
    origin=pcbnew.VECTOR2I_MM(10,10);angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
    fp.Rotate(origin,angle)
    for track in board.GetTracks():track.Rotate(origin,angle)
    if back:
        fp.SetLayer(pcbnew.B_Cu);layers=pcbnew.LSET()
        for layer in (pcbnew.B_Cu,pcbnew.B_Mask,pcbnew.B_Paste):layers.AddLayer(layer)
        pad.SetLayerSet(layers);prefix.SetLayer(pcbnew.B_Cu)
        throat.SetLayer(pcbnew.B_Cu if fault=='same_face_throat' else pcbnew.F_Cu)
        for track in board.GetTracks():
            if track not in (prefix,throat) and track.GetClass()=='PCB_TRACK':track.SetLayer(pcbnew.B_Cu)
    return board,prefix


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_convex_land_and_qualified_full_width_other_face_feed_are_sufficient(quarter,back):
    b,prefix=fixture(quarter=quarter,back=back)
    before=[(force._uid(t),tuple(t.GetStart()),tuple(t.GetEnd()),t.IsLocked()) for t in b.GetTracks()]
    qualified,rejected=fr._qualified_endpoint_neckdown_tracks(b,[prefix],1000000,required_clearance=150000)
    assert [force._uid(t) for t in qualified]==[force._uid(prefix)] and not rejected
    assert before==[(force._uid(t),tuple(t.GetStart()),tuple(t.GetEnd()),t.IsLocked()) for t in b.GetTracks()]


@pytest.mark.parametrize('fault',['nonconvex_shape','overlong_pad_path','partial_overlap',
    'foreign_via','bad_dimensions','blind','wrong_group','wrong_profile','narrow_throat',
    'foreign_throat','disconnected_throat','branch'])
def test_group_membership_nearby_via_or_narrow_continuation_cannot_qualify(fault):
    b,prefix=fixture(fault=fault)
    cohort=[t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.F_Cu and t.GetWidth()<1000000]
    qualified,rejected=fr._qualified_endpoint_neckdown_tracks(b,cohort,1000000,required_clearance=150000)
    assert not qualified and rejected

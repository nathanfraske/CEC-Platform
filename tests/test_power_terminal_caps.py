"""Wide terminal visibility is native geometry, never current/contact credit."""
import pcbnew
import pytest
import cec_field_coupling as field
import cec_power_contours as contours
import cec_rectilinear_copper as owner
from test_power_contours import board,track


def fixture(angle=0,mirror=False,face=pcbnew.F_Cu):
    b,n=board();b.SetCopperLayerCount(6)
    def at(x,y):
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return (round((x+35)*1e6),round((y+35)*1e6))
    t=track(b,n,at(0,0),at(20,0),2000000);t.SetLayer(face)
    return b,n,t


def audit(b,**kwargs):
    return contours.audit_board(b,include_terminal_caps=True,timeout_s=10.,**kwargs)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_long_actual_native_caps_are_observed_in_every_pose_and_face_without_mutation(angle,mirror,face):
    b,n,t=fixture(angle,mirror,face);before=field._field_snapshot_inventory(b)
    assert contours.audit_board(b)['finding_count']==0  # old scoped audit is unchanged
    result=audit(b)
    assert result['complete'] and result['terminal_cap_review_complete']
    assert result['finding_count']==2 and result['types']=={'wide_exposed_terminal_cap':2}
    assert {tuple(f['at_mm']) for f in result['findings']}=={
        tuple(v/1e6 for v in t.GetStart()),tuple(v/1e6 for v in t.GetEnd())}
    assert all(f['track_uuids']==[t.m_Uuid.AsString()] and not f['ordinary_neckdown_allowed'] for f in result['findings'])
    assert not result['replacement_authorized'] and field._field_snapshot_inventory(b)==before


def pad(b,n,point,face,*,plated=False):
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);p=pcbnew.PAD(fp);fp.Add(p);p.SetNet(n)
    p.SetPosition(point);p.SetSize(pcbnew.VECTOR2I_MM(4,4));p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH if plated else pcbnew.PAD_ATTRIB_SMD)
    layers=pcbnew.LSET.AllCuMask() if plated else pcbnew.LSET()
    if not plated:layers.AddLayer(face)
    else:p.SetDrillSize(pcbnew.VECTOR2I_MM(.6,.6))
    p.SetLayerSet(layers);return p


@pytest.mark.parametrize('plated',[False,True])
def test_literal_same_face_pad_can_hide_terminal_visually_but_grants_no_current_or_contact_authority(plated):
    b,n,t=fixture()
    for p in (t.GetStart(),t.GetEnd()):pad(b,n,p,pcbnew.F_Cu,plated=plated)
    result=audit(b)
    assert result['complete'] and result['finding_count']==0 and not result['replacement_authorized']
    assert not result['native_copper_mutated']


@pytest.mark.parametrize('fault',['foreign_net','other_face','tiny','oval_bbox','npth'])
def test_native_pad_identity_face_and_actual_shape_matter_not_bounding_box(fault):
    b,n,t=fixture();p=pad(b,n,t.GetStart(),pcbnew.F_Cu)
    if fault=='foreign_net':
        other=pcbnew.NETINFO_ITEM(b,'different/rail');b.Add(other);p.SetNet(other)
    elif fault=='other_face':
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);p.SetLayerSet(layers)
    elif fault=='tiny':p.SetSize(pcbnew.VECTOR2I_MM(.1,.1))
    elif fault=='oval_bbox':
        p.SetShape(pcbnew.PAD_SHAPE_OVAL);p.SetSize(pcbnew.VECTOR2I_MM(8,.4));p.SetOrientationDegrees(45)
    else:p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH);p.SetDrillSize(pcbnew.VECTOR2I_MM(4,4))
    result=audit(b);assert result['complete'] and result['finding_count']==2


def test_actual_forward_native_continuation_is_not_an_exposed_terminal():
    b,n,t=fixture();first=t.GetEnd();last=first+pcbnew.VECTOR2I_MM(10,0)
    u=track(b,n,list(first),list(last),t.GetWidth())
    result=audit(b)
    assert result['complete'] and result['finding_count']==2
    assert {tuple(f['at_mm']) for f in result['findings']}=={
        tuple(v/1e6 for v in t.GetStart()),tuple(v/1e6 for v in u.GetEnd())}
    scoped=audit(b,track_uuid_scope=[t.m_Uuid.AsString()])
    assert scoped['complete'] and scoped['finding_count']==1
    assert audit(b,track_uuid_scope=[])['finding_count']==0


def test_coincident_ending_tracks_cannot_launder_a_round_terminal():
    b,n,t=fixture();p=t.GetEnd()
    track(b,n,list(p-pcbnew.VECTOR2I_MM(5,0)),list(p),t.GetWidth())
    result=audit(b)
    assert result['complete']
    assert len([f for f in result['findings'] if f['at_mm']==[p.x/1e6,p.y/1e6]])==2


@pytest.mark.parametrize('fault',[None,'unfilled','hole','wrong_name','other_face'])
def test_only_actual_canonical_purposeful_fill_can_hide_a_partial_terminal(fault):
    b,n,t=fixture();p=t.GetStart();x,y=p.x,p.y
    z=pcbnew.ZONE(b);z.SetNet(n);z.SetLayer(pcbnew.F_Cu);z.SetZoneName(owner.ZONE_NAME);b.Add(z)
    profile=owner._poly([(x-1100000,y-1100000),(x+1100000,y-1100000),
        (x+1100000,y+1100000),(x-1100000,y+1100000)])
    z.Outline().Append(profile);filled=profile.CloneDropTriangulation()
    if fault=='hole':
        filled.BooleanSubtract(owner._poly([(x-100000,y-100000),(x+100000,y-100000),
            (x+100000,y+100000),(x-100000,y+100000)]))
    z.SetFilledPolysList(pcbnew.F_Cu,filled);z.SetIsFilled(fault!='unfilled')
    if fault=='wrong_name':
        z.SetZoneName('unqualified-circular-filler')
        # Names no longer pretend to be geometry. Retain this negative case
        # by making the actual outer edge noncanonical at native resolution.
        ring=z.Outline().Outline(0);q=ring.CPoint(0)
        ring.SetPoint(0,pcbnew.VECTOR2I(q.x+1,q.y))
    if fault=='other_face':z.SetLayer(pcbnew.B_Cu)
    before=field._field_snapshot_inventory(b);result=audit(b)
    assert result['complete'] and result['finding_count']==(1 if fault is None else 2),result
    assert field._field_snapshot_inventory(b)==before


def test_finding_requests_expose_literal_long_source_tracks_without_cut_authority():
    b,n,t=fixture();old=contours.finding_requests(b,timeout_s=10.)
    result=contours.finding_requests(b,include_terminal_caps=True,timeout_s=10.)
    assert old['complete'] and old['requests']==[]
    assert result['complete'] and result['source_finding_count']==2 and len(result['requests'])==1
    assert result['requests'][0]['source_tracks'][0]['uuid']==t.m_Uuid.AsString()
    assert result['requests'][0]['finding_types']==['wide_exposed_terminal_cap']
    assert not result['replacement_authorized'] and not result['new_current_authority']


def test_exhausted_terminal_review_is_unknown_not_clean():
    b,n,t=fixture();result=contours.audit_board(b,include_terminal_caps=True,timeout_s=0)
    assert not result['complete'] and not result['terminal_cap_review_complete']
    limited=audit(b,max_findings=1)
    assert not limited['complete'] and not limited['terminal_cap_review_complete']


@pytest.mark.parametrize('bad',[None,0,1,'true',[]])
def test_invalid_terminal_policy_is_never_silently_enabled(bad):
    b,n,t=fixture()
    with pytest.raises(ValueError):contours.audit_board(b,include_terminal_caps=bad)
    with pytest.raises(ValueError):contours.finding_requests(b,include_terminal_caps=bad)

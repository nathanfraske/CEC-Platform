"""A blocked preferred chamfer is not a proof that its legal domain is empty."""
import math
import pcbnew
import pytest
import cec_octilinear_corner as corners
import cec_fr as fr
import cec_field_coupling as field
from test_full_current_corner_finish import fixture


@pytest.mark.parametrize('vectors',[((10000000,0),(0,10000000)),((10000000,10000000),(-10000000,10000000))])
@pytest.mark.parametrize('maximum,minimum',[(2000000,50000),(200000,50000),(150000,150000),(2000000000,1)])
def test_integer_portfolio_keeps_all_original_physical_and_leg_bounds(vectors,maximum,minimum):
    values=corners.coordinate_insets(*vectors,maximum_nm=maximum,minimum_nm=minimum)
    preferred=corners.coordinate_inset(*vectors,maximum_nm=maximum,minimum_nm=minimum)
    scale=2 if corners.kind(*vectors)=='diagonal' else 1
    if preferred is None:
        # Equal physical bounds need not contain a representable diagonal
        # retreat on the integer-nanometre lattice. Refusing that empty domain
        # is required; rounding up would exceed maximum, down would violate
        # minimum. This fixture's legs do not impose the limiting bound.
        assert math.isqrt(maximum**2//scale)**2*scale<minimum**2
        assert values==[]
        return
    assert 1<=len(values)<=8 and values==sorted(set(values),reverse=True)
    assert values[0]==preferred
    assert all(minimum**2<=n*n*scale<=maximum**2 for n in values)
    assert all(n<=min(2*max(abs(x),abs(y))//5 for x,y in vectors) for n in values)
    assert (values[-1]-1)**2*scale<minimum**2


@pytest.mark.parametrize('limit',[1,2,4,8])
def test_positive_work_bound_retains_preferred_and_minimum_when_capacity_allows(limit):
    values=corners.coordinate_insets((10000000,0),(0,10000000),
        maximum_nm=2000000,minimum_nm=50000,max_candidates=limit)
    assert 1<=len(values)<=limit
    assert values[0]==2000000
    assert values==sorted(set(values),reverse=True)
    assert all(50000<=value<=2000000 for value in values)
    if limit>1:assert values[-1]==50000


@pytest.mark.parametrize('limit',[0,9,True,None])
def test_work_bound_is_never_implicitly_unlimited(limit):
    with pytest.raises(ValueError):corners.coordinate_insets((100,0),(0,100),maximum_nm=50,minimum_nm=1,max_candidates=limit)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_obstacle_blocks_large_miter_but_a_smaller_full_width_miter_is_clear(tmp_path,monkeypatch,quarter,mirror,face):
    source,net,domains,contract=fixture(tmp_path,monkeypatch,quarter=quarter,mirror=mirror,face=face,width=.6)
    b=pcbnew.LoadBoard(str(source));tracks=list(b.GetTracks());shared=set(map(tuple,(tracks[0].GetStart(),tracks[0].GetEnd())))&set(map(tuple,(tracks[1].GetStart(),tracks[1].GetEnd())))
    at=next(iter(shared));far=[]
    for t in tracks:
        p=t.GetEnd() if tuple(t.GetStart())==at else t.GetStart();far.append(tuple(p))
    directions=[((p[0]-at[0])//max(abs(p[i]-at[i]) for i in (0,1)),(p[1]-at[1])//max(abs(p[i]-at[i]) for i in (0,1))) for p in far]
    position=pcbnew.VECTOR2I(*(at[i]+1000000*sum(d[i] for d in directions) for i in (0,1)))
    n=pcbnew.NETINFO_ITEM(b,'/actual/foreign');b.Add(n);fp=pcbnew.FOOTPRINT(b);fp.SetReference('FOREIGN');b.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(.1,.1));pad.SetPosition(position);pad.SetNet(n);layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers);fp.Add(pad)
    old=field._field_snapshot_inventory(b);ids=[t.m_Uuid.AsString() for t in tracks]
    made=fr.chamfer_unlocked_right_angles(b,max_chamfer_mm=2.,min_chamfer_mm=.05,max_width_mm=1.,allow_locked_track_uuids=ids,timeout_s=10.)
    assert made['chamfered']==1 and made['cutback_samples_tested']>=2
    trials=made['cutback_trials'];assert not trials[0]['accepted'] and trials[-1]['accepted']
    assert .05<=made['detail'][0]['chamfer_mm']<2.
    assert all(t.GetWidth()==600000 and t.GetLayer()==face for t in b.GetTracks())
    assert len(list(b.GetTracks()))==3 and pad.GetPosition()==position
    assert old!=field._field_snapshot_inventory(b)


def test_unroutable_domain_still_returns_no_change_without_lowering_minimum(tmp_path,monkeypatch):
    source,net,domains,contract=fixture(tmp_path,monkeypatch,width=.6);b=pcbnew.LoadBoard(str(source))
    ids=[t.m_Uuid.AsString() for t in b.GetTracks()];before=field._field_snapshot_inventory(b)
    monkeypatch.setattr(fr,'_tap_foreign_clear',lambda *a,**k:False)
    made=fr.chamfer_unlocked_right_angles(b,max_chamfer_mm=2.,min_chamfer_mm=.15,allow_locked_track_uuids=ids,timeout_s=10.)
    assert made['chamfered']==0 and 1<=made['cutback_samples_tested']<=8
    assert min(q['coordinate_inset_nm'] for q in made['cutback_trials'])==150000
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('reason',['same_net_side_contact_lost','nearby_same_net_zone_fill_unknown',
    'contact_inventory_bound','contact_deadline'])
def test_native_contact_ownership_refusal_is_not_a_license_to_try_smaller_cuts(tmp_path,monkeypatch,reason):
    import cec_route_corner_contacts as contacts
    source,net,domains,contract=fixture(tmp_path,monkeypatch,width=.6)
    b=pcbnew.LoadBoard(str(source));ids=[t.m_Uuid.AsString() for t in b.GetTracks()]
    before=field._field_snapshot_inventory(b);calls=[]
    def refuse(*args,**kwargs):
        calls.append(kwargs)
        return dict(ok=False,reason=reason,examined=1,lost_contacts=['source-native-contact'])
    monkeypatch.setattr(fr,'_tap_foreign_clear',lambda *a,**k:True)
    monkeypatch.setattr(contacts,'preserve_contacts',refuse)
    made=fr.chamfer_unlocked_right_angles(b,max_chamfer_mm=2.,min_chamfer_mm=.05,
        allow_locked_track_uuids=ids,timeout_s=10.)
    assert made['chamfered']==0 and made['skipped']['native_contact']==1
    assert made['cutback_samples_tested']==1 and len(calls)==1
    assert made['native_contact_refusals'][0]['reason']==reason
    assert made['cutback_trials'][0]['further_cutbacks_refused']=='source_native_contact_scope_requires_owner_reconstruction'
    assert before==field._field_snapshot_inventory(b)

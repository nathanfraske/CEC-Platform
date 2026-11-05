"""Real native finite-width pad entries, not bounding-box permissions."""
import time
import pcbnew
import pytest
import cec_fab_profile as fab
import cec_native_pad_octilinear_entry as entry


def fixture(*,quarter=0,mirror=False,back=False):
    board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);board.Add(fp);centre=[20000000,20000000]
    fp.SetPosition(pcbnew.VECTOR2I(*centre));pad=pcbnew.PAD(fp);pad.SetNumber('renamed')
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
    pad.SetRoundRectRadiusRatio(.1);pad.SetSize(pcbnew.VECTOR2I(800000,400000));pad.SetPosition(pcbnew.VECTOR2I(*centre))
    layers=pcbnew.LSET()
    for l in((pcbnew.B_Cu,pcbnew.B_Mask,pcbnew.B_Paste)if back else(pcbnew.F_Cu,pcbnew.F_Mask,pcbnew.F_Paste)):layers.AddLayer(l)
    pad.SetLayerSet(layers);pad.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);fp.Add(pad)
    dx,dy=-1127400,820601
    if mirror:dx=-dx
    for _ in range(quarter):dx,dy=dy,-dx
    fp.Rotate(pcbnew.VECTOR2I(*centre),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    return board,fp,pad,[centre[0]+dx,centre[1]+dy]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',(False,True))
@pytest.mark.parametrize('back',(False,True))
def test_off_centre_full_disk_native_entry_is_canonical_in_all_frames(quarter,mirror,back):
    board,fp,pad,axis=fixture(quarter=quarter,mirror=mirror,back=back)
    before=(tuple(pad.GetPosition()),tuple(pad.GetSize()),pad.GetOrientationDegrees(),tuple(pad.GetLayerSet().CuStack()))
    q=entry.choose(pad,axis,width_nm=250000)
    assert q==entry.choose(pad,axis,width_nm=250000)
    assert q['actual_native_start_disk_contained']and q['containment_tolerance_nm']==0
    assert fab._pad_contains_circle(pad,pcbnew.VECTOR2I(*q['start_nm']),125000,tolerance_nm=0)
    delta=[q['start_nm'][i]-axis[i]for i in(0,1)]
    assert delta[0]==0 or delta[1]==0 or abs(delta[0])==abs(delta[1])
    assert 0<sum(d*d for d in delta)<=1500000**2
    assert q['start_nm']!=q['source_pad_centre_nm']and q['width_nm']==250000
    assert not any(q[k]for k in('electrical_scope','routing_admitted','release_authority'))
    assert before==(tuple(pad.GetPosition()),tuple(pad.GetSize()),pad.GetOrientationDegrees(),tuple(pad.GetLayerSet().CuStack()))


@pytest.mark.parametrize('fault',('tht','hole','DNP','two_faces','no_copper'))
def test_ineligible_or_unmanufactured_land_cannot_become_a_start(fault):
    board,fp,pad,axis=fixture()
    if fault=='tht':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='hole':pad.SetDrillSize(pcbnew.VECTOR2I(200000,200000))
    elif fault=='DNP':fp.SetDNP(True)
    elif fault=='two_faces':layers=pad.GetLayerSet();layers.AddLayer(pcbnew.B_Cu);pad.SetLayerSet(layers)
    else:pad.SetLayerSet(pcbnew.LSET())
    with pytest.raises(ValueError):entry.choose(pad,axis,width_nm=250000)


@pytest.mark.parametrize('bad',(True,0,-1,1000001,float('nan')))
def test_full_width_is_not_a_boolean_or_missing_dimension(bad):
    board,fp,pad,axis=fixture()
    with pytest.raises(ValueError):entry.choose(pad,axis,width_nm=bad)


@pytest.mark.parametrize('bad',(True,0,-1,1500001,float('inf')))
def test_exposed_reach_is_never_extended_or_reset(bad):
    board,fp,pad,axis=fixture()
    with pytest.raises(ValueError):entry.choose(pad,axis,width_nm=250000,maximum_leg_nm=bad)


def test_actual_native_shape_rejects_a_falsely_generous_bbox(monkeypatch):
    board,fp,pad,axis=fixture();generous=pad.GetBoundingBox();pad.SetSize(pcbnew.VECTOR2I(100000,100000))
    monkeypatch.setattr(pad,'GetBoundingBox',lambda:generous)
    with pytest.raises(ValueError,match='no_full_width_native_pad_entry'):entry.choose(pad,axis,width_nm=250000)


def test_exhausted_native_candidate_check_cannot_return_a_late_positive(monkeypatch):
    board,fp,pad,axis=fixture();clock=[100.]
    from types import SimpleNamespace
    monkeypatch.setattr(entry,'time',SimpleNamespace(monotonic=lambda:clock[0]));original=fab._pad_contains_circle
    def delayed(*a,**kw):
        result=original(*a,**kw);clock[0]=200.;return result
    monkeypatch.setattr(fab,'_pad_contains_circle',delayed)
    with pytest.raises(ValueError,match='deadline'):entry.choose(pad,axis,width_nm=250000,deadline=101.)

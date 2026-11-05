"""Proposed-only interval normalization preserves literal native copper."""
import copy
import pcbnew
import pytest
import cec_proposed_collinear_copper as proposed
import cec_field_coupling as field


def polygon(ops,layer):
    union=pcbnew.SHAPE_POLY_SET()
    for op in ops:
        if op[0]!='trk' or op[4]!=layer:continue
        track=pcbnew.PCB_TRACK(None);track.SetStart(pcbnew.VECTOR2I(*op[1]));track.SetEnd(pcbnew.VECTOR2I(*op[2]))
        track.SetWidth(op[3]);track.SetLayer(layer)
        body=pcbnew.SHAPE_POLY_SET()
        track.GetEffectiveShape(layer).TransformToPolygon(body,1,pcbnew.ERROR_INSIDE)
        union.BooleanAdd(body)
    return union


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('direction',[(1,0),(1,1),(0,1),(-1,0)])
def test_native_capsule_union_exact_for_reversed_overlapping_and_touching_strokes(face,direction):
    def at(n):return (10000000+direction[0]*n*1000000,10000000+direction[1]*n*1000000)
    ops=[('trk',at(0),at(4),500000,face),('trk',at(6),at(2),500000,face),
         ('trk',at(6),at(8),500000,face),('trk',at(1),at(3),500000,face)]
    original=copy.deepcopy(ops);merged,proof=proposed.normalize(ops)
    assert len(merged)==1 and ops==original
    # Native circular capsule geometry is exact; tessellating separate 45°
    # capsules can introduce different integer polygonization slivers. Prove
    # their native centerline interval union and equal actual capsule width
    # without treating a tessellation tolerance as physical permission.
    native=[pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*o[1]),pcbnew.VECTOR2I(*o[2]),o[3])for o in ops]
    final=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*merged[0][1]),pcbnew.VECTOR2I(*merged[0][2]),merged[0][3])
    assert all(s.GetWidth()==final.GetWidth() and s.GetSeg().Collinear(final.GetSeg())for s in native)
    project=lambda p:p.x*direction[0]+p.y*direction[1]
    spans=sorted(sorted((project(s.GetSeg().A),project(s.GetSeg().B)))for s in native)
    low,high=spans[0]
    for a,z in spans[1:]:assert a<=high;high=max(high,z)
    assert [low,high]==sorted((project(final.GetSeg().A),project(final.GetSeg().B)))
    if 0 in direction:
        a=polygon(ops,face);b=polygon(merged,face)
        x=a.CloneDropTriangulation();x.BooleanSubtract(b)
        y=b.CloneDropTriangulation();y.BooleanSubtract(a)
        assert x.OutlineCount()==0 and y.OutlineCount()==0
    assert proof['exact_equal_width_collinear_capsule_union_preserved']
    assert not proof['source_items_inspected_or_mutated'] and not proof['current_qualified'] and not proof['release_authority']


@pytest.mark.parametrize('fault',['width','layer','positive_gap','parallel_offset'])
def test_nonidentical_scope_is_never_merged(fault):
    a=('trk',(0,0),(1000000,0),500000,pcbnew.F_Cu)
    b=['trk',(500000,0),(2000000,0),500000,pcbnew.F_Cu]
    if fault=='width':b[3]=500001
    elif fault=='layer':b[4]=pcbnew.B_Cu
    elif fault=='positive_gap':b[1]=(1000001,0)
    else:b[1]=(500000,1);b[2]=(2000000,1)
    out,proof=proposed.normalize([a,b]);assert len(out)==2


def test_no_native_source_uuid_or_source_board_is_in_scope_and_vias_stay_literal():
    board=pcbnew.BOARD();old=pcbnew.PCB_TRACK(board)
    old.SetStart(pcbnew.VECTOR2I(0,0));old.SetEnd(pcbnew.VECTOR2I(1000000,0));old.SetWidth(500000);board.Add(old)
    before=field._field_snapshot_inventory(board)
    via=('via',(1000000,0),.5,.9)
    ops=[('trk',(1000000,0),(2000000,0),500000,pcbnew.F_Cu),via,via]
    out,proof=proposed.normalize(ops)
    assert len(out)==3 and out[-2:]==[via,via]
    assert out[0][1:3]==((1000000,0),(2000000,0))
    assert field._field_snapshot_inventory(board)==before
    assert proof['via_geometry_unchanged'] and not proof['source_items_inspected_or_mutated']
    with pytest.raises(ValueError):proposed.normalize([(*ops[0],old.m_Uuid.AsString())])


@pytest.mark.parametrize('ops',[[],None,{},[('trk',(0,0),(0,0),1,0)],
    [('trk',(0,0),(1,2),1,0)],[('trk',(0,0),(1,0),True,0)],
    [('trk',(0.,0),(1,0),1,0)],[('unknown',)],
    [('trk',(0,0),(1,0),1,0)]*145])
def test_invalid_or_unbounded_packet_refuses(ops):
    with pytest.raises((ValueError,TypeError)):proposed.normalize(ops)

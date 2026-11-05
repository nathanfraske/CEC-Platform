"""Reuse exact old centreline cover without copying or editing Source copper."""
import math
import pcbnew
import pytest
import cec_additive_portal_compaction as cover
import cec_certificate_repair as repair
import cec_force_current as force
import cec_field_coupling as field
import cec_ordinary_signal_completion as ordinary
import cec_route_quality as quality
import cec_additive_pair_repair as additive
from test_ordinary_native_portals import fixture


def track(board,a,b,*,width=220000,layer=pcbnew.F_Cu,net='ordinary'):
    if board.FindNet(net)is None:board.Add(pcbnew.NETINFO_ITEM(board,net))
    t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b))
    t.SetWidth(width);t.SetLayer(layer);t.SetNet(board.FindNet(net));return t


@pytest.mark.parametrize('heading',range(8))
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('case',['prefix','tails','middle','one_nm_gap','touching_union'])
def test_native_integer_interval_complement_preserves_every_gap(heading,layer,case):
    b=pcbnew.BOARD();vectors=[(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1)]
    v=vectors[heading]
    def at(n):return (10000000+v[0]*n,10000000+v[1]*n)
    target=track(b,at(0),at(10000000),layer=layer)
    old,expected={
        'prefix':([(0,2000000)],[(2000000,10000000)]),
        'tails':([(0,1000000),(8000000,10000000)],[(1000000,8000000)]),
        'middle':([(3000000,6000000)],[(0,3000000),(6000000,10000000)]),
        'one_nm_gap':([(0,5000000),(5000001,10000000)],[(5000000,5000001)]),
        'touching_union':([(0,5000000),(5000000,10000000)],[])}[case]
    retained=[track(b,at(lo),at(hi),layer=layer,width=300000)for lo,hi in old]
    before=[(force._uid(t),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth())for t in retained]
    r=cover.uncovered_collinear_segments(target,retained)
    assert r['segments_nm']==[[list(at(lo)),list(at(hi))]for lo,hi in expected]
    assert not r['original_conductors_edited']and not r['current_authority']
    assert before==[(force._uid(t),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth())for t in retained]


@pytest.mark.parametrize('fault',['different_net','different_face','underwidth','one_nm_offset'])
def test_overlap_or_proximity_cannot_supply_existing_cover(fault):
    b=pcbnew.BOARD();a=(10000000,10000000);z=(20000000,10000000)
    target=track(b,a,z);old=track(b,a,z)
    if fault=='different_net':b.Add(pcbnew.NETINFO_ITEM(b,'foreign'));old.SetNet(b.FindNet('foreign'))
    elif fault=='different_face':old.SetLayer(pcbnew.B_Cu)
    elif fault=='underwidth':old.SetWidth(target.GetWidth()-1)
    else:old.Move(pcbnew.VECTOR2I(0,1))
    assert cover.uncovered_collinear_segments(target,[old])['segments_nm']==[[list(a),list(z)]]


def test_failed_fragment_or_heading_validation_does_not_partially_materialize():
    b=pcbnew.BOARD();t=track(b,(0,0),(1000000,0));b.Add(t);before=[force._uid(x)for x in b.GetTracks()]
    ops=[('trk',pcbnew.VECTOR2I(1000000,0),pcbnew.VECTOR2I(2000000,0),220000,pcbnew.F_Cu),
        ('trk',pcbnew.VECTOR2I(2000000,0),pcbnew.VECTOR2I(2500000,1000000),220000,pcbnew.F_Cu)]
    with pytest.raises(ValueError,match='exact_octilinear_collinear_projection'):
        repair._lay_ops(b,ops,t.GetNetCode(),reuse_existing_collinear=True)
    assert before==[force._uid(x)for x in b.GetTracks()]
    pieces=[track(b,(300000,0),(400000,0)),track(b,(600000,0),(700000,0))]
    with pytest.raises(ValueError,match='bounded_missing_collinear_fragment'):
        cover.uncovered_collinear_segments(t,pieces,max_parts=1)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_saved_native_extension_is_not_a_source_overdraw_or_backtrack(tmp_path,quarter,back):
    source,b,net=fixture(tmp_path,quarter=quarter,back=back)
    q=ordinary.plan(b,source,board_hint='synthetic',net=net);ends=ordinary._pads(b,q['request'])
    a,z=[tuple(p.GetPosition())for p in ends]
    prefix=tuple(a[k]+(z[k]-a[k])//10 for k in(0,1));face=next(iter(ends[0].GetLayerSet().CuStack()))
    t=track(b,a,prefix,net=net,layer=face);t.SetLocked(True);b.Add(t)
    field._save_field_snapshot(b,source);original=source.read_bytes()
    child=force._copy_family(source,tmp_path/'child');saved=pcbnew.LoadBoard(str(child));before=quality.analyze_board(saved)
    old={force._uid(t)for t in saved.GetTracks()};native=next(t for t in saved.GetTracks()if force._uid(t)in old)
    material=field._field_snapshot_inventory(saved);uid=force._uid(native)
    laid=repair._lay_ops(saved,[('trk',pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),220000,face)],
        saved.GetNetcodeFromNetname(net),reuse_existing_collinear=True)
    assert laid['tracks']==1 and laid['collinear_reuse'][0]['segments_nm']==[[list(prefix),list(z)]]
    assert field._field_snapshot_inventory(saved)[('track',uid)]==material[('track',uid)]
    assert next(t for t in saved.GetTracks()if force._uid(t)==uid).IsLocked()
    after=quality.analyze_board(saved)
    assert before['issue_count']==after['issue_count']==0
    additive.save_native_additions(child,saved,{},old)
    proof=ordinary.receive(source,child,board_hint='synthetic',net=net)
    assert proof['ok']and proof['complete'],proof
    assert source.read_bytes()==original

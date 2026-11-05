"""Native 45-degree tees, rotated geometry and original full-current guards."""
import json,time
from pathlib import Path
from unittest.mock import patch
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_terminal_trim as frozen
import cec_octilinear_terminal_trim as tips
import cec_native_tee_corridor_reflow as corridor
import cec_full_current_planar_reflow as full
from test_full_current_terminal_trim import authority
from test_field_proposals import track
from test_lastmile import _board

def fixture(tmp_path,quarter=0,mirror=False,face=pcbnew.F_Cu,backtrack=False,net='/test/unnamed_source_current'):
    def pose(p):
        x,y=p[0]-20,p[1]-20
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return x+20,y+20
    far=(20,18) if backtrack else (20,22)
    b=_board([(*pose(p),net) for p in ((18,18),far)],edge=(0,0,40,40));b.SetCopperLayerCount(6)
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
    for a,z in [((18,18),(20.6,20.6)),((20,20),far)]:
        track(b,net,pose(a),pose(z),layer=face,width=.2).SetLocked(True)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    return source,net

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_nonperpendicular_tip_has_native_source_current_receiving(tmp_path,quarter,mirror,face):
    source,net=fixture(tmp_path,quarter,mirror,face);before=source.read_bytes()
    with authority(net,face):
        b=pcbnew.LoadBoard(str(source))
        assert not frozen._geometry(b,source,True,time.monotonic()+10.)
        d=tips.discover(b,source,board_hint='synthetic',allow_locked_source=True)
        assert len(d['requests'])==1,d
        q=tips.plan(b,source,d['requests'][0],board_hint='synthetic',allow_locked_source=True)
        tips.materialize(b,source,q,board_hint='synthetic')
        child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
        received=tips.receive(source,child,q,board_hint='synthetic')
        assert received['ok'] and received['complete'],received
        assert received['saved_trace_length_mm']==pytest.approx(.6*2**.5)
    assert source.read_bytes()==before

@pytest.mark.parametrize('fault',['missing_current','incomplete','below_floor','locked','group','mask','ground','extra_tip_contact'])
def test_positive_current_and_real_contact_guards_remain(tmp_path,fault):
    source,net=fixture(tmp_path,net='GND' if fault=='ground' else '/test/unnamed_source_current');b=pcbnew.LoadBoard(str(source));old=max(b.GetTracks(),key=lambda t:t.GetLength())
    if fault=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(old)
    if fault=='mask':old.SetHasSolderMask(True)
    if fault=='extra_tip_contact':track(b,net,(20.6,20.6),(21.6,20.6))
    field._save_field_snapshot(b,source)
    with authority(net,incomplete=fault=='incomplete',floor=.3 if fault=='below_floor' else .1,missing=fault=='missing_current'):
        d=tips.discover(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',allow_locked_source=fault!='locked')
    assert not d['requests'],d

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_trim_alone_does_not_waive_a_new_backtrack(tmp_path,quarter,mirror):
    source,net=fixture(tmp_path,quarter,mirror,backtrack=True)
    with authority(net):
        b=pcbnew.LoadBoard(str(source));d=tips.discover(b,source,board_hint='synthetic',allow_locked_source=True)
        assert len(d['requests'])==1
        q=tips.plan(b,source,d['requests'][0],board_hint='synthetic',allow_locked_source=True)
        tips.materialize(b,source,q,board_hint='synthetic');child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
        received=tips.receive(source,child,q,board_hint='synthetic')
    assert not received['ok'] and 'full_current_planar_canonical_craft_refused' in str(received['errors'])

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_atomic_source_corridor_removes_tip_and_backtracking_together(tmp_path,quarter,mirror):
    def pose(p):
        x,y=p[0]-20,p[1]-20
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return x+20,y+20
    net='/another/source_current'
    b=_board([(*pose(p),net) for p in ((8,20),(24,24.2))],edge=(0,0,40,40));b.SetCopperLayerCount(6)
    points=[(8,20),(10,20),(18,20),(18.2,19.8),(18.2,19.5)]
    segments=list(zip(points,points[1:]))+[((18.1,19.4),(18.8,20.1)),((18.8,20.1),(18.8,21)),((18.8,21),(22,24.2)),((22,24.2),(24,24.2))]
    for a,z in segments:track(b,net,pose(a),pose(z),width=.2).SetLocked(True)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source);before=source.read_bytes()
    b=pcbnew.LoadBoard(str(source))
    with authority(net):
        menu=corridor.discover(b,source,board_hint='synthetic');assert menu['offers'],menu
        offer=menu['offers'][0];ids=offer['retired_track_uuids'];live={force._uid(t):t for t in b.GetTracks()}
        prototype=live[ids[0]].Duplicate()
        from cec_native_items import discard_items
        for a,z in zip(offer['points_nm'],offer['points_nm'][1:]):
            t=prototype.Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));b.Add(t)
        discard_items(b,[live[u] for u in ids]);additive=corridor.additive;additive._ground_refill(b)
        child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
        received=full.receive(source,child,board_hint='synthetic',retired_track_uuids=ids)
    assert received['ok'] and received['complete'],received
    assert len(offer['points_nm'])-1<len(ids) and source.read_bytes()==before

def test_frozen_owner_not_monkeypatched():
    assert frozen._geometry is not tips._ns._geometry
    assert 'd[0]*pv[0]+d[1]*pv[1]!=0' in Path(frozen.__file__).read_text()

@pytest.mark.parametrize('maximum',[True,0,1,9,100])
def test_work_bound_is_not_current_or_contact_authority(maximum):
    with pytest.raises(ValueError):corridor.windows(None,{},max_tracks=maximum)

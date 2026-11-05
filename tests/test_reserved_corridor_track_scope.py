"""Old crossings must be scoped, not merely avoided by future emissions."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_reserved_corridor_track_scope as scope
from test_field_proposals import track


def fixture(tmp_path,turn=0,mirror=False,mode=None):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    crossing=track(b,'RENAMED_CONTROL',(10,5),(10,15));crossing.SetLocked(True)
    separate=track(b,'RENAMED_CONTROL',(20,5),(20,15))
    track(b,'GND',(10,25),(20,25))
    if mode=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('EXISTING_SOURCE_OWNER');b.Add(g);g.AddItem(crossing)
    for t in b.GetTracks():
        if mirror:t.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        t.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(turn*90,pcbnew.DEGREES_T))
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    parent,candidate=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    lookup={force._uid(t):t for t in candidate.GetTracks()}
    t=lookup[force._uid(crossing)];s,z=t.GetStart(),t.GetEnd()
    middle=pcbnew.VECTOR2I((s.x+z.x)//2,(s.y+z.y)//2)
    if mode=='barrel':
        ghost=pcbnew.PCB_VIA(candidate);ghost.SetPosition(middle);ghost.SetWidth(1000000);ghost.SetDrill(300000)
        ghost.SetViaType(pcbnew.VIATYPE_THROUGH);ghost.SetLayerPair(0,2)
        candidate.Add(pcbnew.NETINFO_ITEM(candidate,'PRIORITY_DOMAIN'));ghost.SetNet(candidate.FindNet('PRIORITY_DOMAIN'))
        candidate.Add(ghost)
    else:
        dx,dy=z.x-s.x,z.y-s.y
        ghost=track(candidate,'PRIORITY_DOMAIN',((middle.x-dy/5)/1e6,(middle.y+dx/5)/1e6),
            ((middle.x+dy/5)/1e6,(middle.y-dx/5)/1e6),layer=int(t.GetLayer()),width=1.)
    if mode=='different_face':ghost.SetLayer(2 if t.GetLayer()==0 else 0)
    if mode=='same_net':ghost.SetNet(t.GetNet())
    if mode=='changed':t.Move(pcbnew.VECTOR2I(1,0))
    return parent,candidate,t,ghost,path


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_retained_crossing_is_proposed_without_changing_any_native_copper(tmp_path,turn,mirror):
    p,b,t,g,path=fixture(tmp_path,turn,mirror)
    before=field._field_snapshot_inventory(b);saved=path.read_bytes()
    result=scope.plan(p,b,[g],source_path=path,board_hint='synthetic',clearance_for=lambda _:200000)
    assert [r['uuid'] for r in result['additional_source_ordinary_tracks']]==[force._uid(t)]
    row=result['additional_source_ordinary_tracks'][0]
    assert row['width_nm']==200000 and row['source_locked'] and row['witnesses']
    assert result['all_foreign_track_obstructions_scoped'] and not result['automatic_retirement_authorized']
    assert not result['current_or_pair_or_ground_authority'] and not result['release_authority']
    assert field._field_snapshot_inventory(b)==before and path.read_bytes()==saved


@pytest.mark.parametrize('mode',['group','changed'])
def test_group_and_changed_source_cannot_hide_inside_ordinary_label(tmp_path,mode):
    p,b,t,g,path=fixture(tmp_path,mode=mode)
    result=scope.plan(p,b,[g],source_path=path,board_hint='synthetic',clearance_for=lambda _:200000)
    assert not result['additional_source_ordinary_tracks'] and not result['all_foreign_track_obstructions_scoped']


@pytest.mark.parametrize('mode',['same_net','different_face'])
def test_no_physical_foreign_same_face_crossing_means_no_scope(tmp_path,mode):
    p,b,t,g,path=fixture(tmp_path,mode=mode)
    result=scope.plan(p,b,[g],source_path=path,board_hint='synthetic',clearance_for=lambda _:200000)
    assert not result['additional_source_ordinary_tracks'] and result['all_foreign_track_obstructions_scoped']


def test_real_through_reservation_covers_other_actual_faces(tmp_path):
    p,b,t,g,path=fixture(tmp_path,mirror=True,mode='barrel')
    result=scope.plan(p,b,[g],source_path=path,board_hint='synthetic',clearance_for=lambda _:200000)
    assert [r['uuid'] for r in result['additional_source_ordinary_tracks']]==[force._uid(t)]


def test_already_pending_crossing_is_not_counted_or_cut_twice(tmp_path):
    p,b,t,g,path=fixture(tmp_path)
    result=scope.plan(p,b,[g],source_path=path,board_hint='synthetic',clearance_for=lambda _:200000,
        already_pending_uuids=[force._uid(t)])
    assert not result['additional_source_ordinary_tracks'] and len(result['already_scheduled_contacts'])==1


def test_nonordinary_track_is_an_explicit_blocker_not_new_scope(tmp_path,monkeypatch):
    p,b,t,g,path=fixture(tmp_path)
    monkeypatch.setattr(scope.ordinary,'eligible_nets',lambda *a:set())
    result=scope.plan(p,b,[g],source_path=path,board_hint='synthetic',clearance_for=lambda _:200000)
    assert not result['additional_source_ordinary_tracks'] and not result['all_foreign_track_obstructions_scoped']
    assert result['unscoped_foreign_track_obstructions'][0]['reason']=='not_positive_source_ordinary_track'


@pytest.mark.parametrize('value',[0,65,True])
def test_union_bound_is_not_copper_or_current_authority(tmp_path,value):
    p,b,t,g,path=fixture(tmp_path)
    with pytest.raises(ValueError):scope.plan(p,b,[g],source_path=path,board_hint='synthetic',
        clearance_for=lambda _:200000,maximum_tracks=value)

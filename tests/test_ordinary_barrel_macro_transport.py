"""Source-owned cross-face roots survive contact-type and frame changes."""
import pcbnew
import pytest
import cec_ordinary_barrel_macro_transport as transport
import cec_field_coupling as field
import cec_force_current as force
from test_macro_ordinary_barrel_scope import fixture
from test_field_proposals import track


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_endpoint_kernels_keep_barrel_identity_geometry_and_incident_faces(tmp_path,turn,mirror):
    a,b,path,uid,obstacles=fixture(tmp_path,turn,mirror)
    via=next(t for t in b.GetTracks() if force._uid(t)==uid)
    target=[via.GetPosition().x+750000,via.GetPosition().y+750000]
    before=field._field_snapshot_inventory(a)
    proof=transport.apply(a,b,[dict(uuid=uid,position_nm=target)],source_path=path,
        board_hint='synthetic',obstructing_items=obstacles,clearance_nm=200000,allow_locked_via_uuids=[uid])
    assert list(via.GetPosition())==target and via.GetDrillValue()==300000
    assert all(via.GetWidth(l)==600000 for l in b.GetEnabledLayers().CuStack())
    assert len(proof['source_contact_track_uuids'])==2 and not proof['generated_transient_track_uuids']
    assert proof['source_barrel_identity_count_padstack_and_groups_preserved']
    assert not proof['source_current_or_clearance_or_release_qualified']
    for t in b.GetTracks():
        if t.GetClass()=='PCB_TRACK':assert target in [list(t.GetStart()),list(t.GetEnd())]
    assert field._field_snapshot_inventory(a)==before


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_interior_source_contact_splits_both_limbs_instead_of_tearing_a_tee(tmp_path,turn,mirror):
    a,b,path,uid,obstacles=fixture(tmp_path,turn,mirror)
    for board in (a,b):
        v=next(t for t in board.GetTracks() if force._uid(t)==uid)
        t=next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.F_Cu)
        s,e=t.GetStart(),t.GetEnd()
        t.SetEnd(pcbnew.VECTOR2I(2*e.x-s.x,2*e.y-s.y))
    before=field._field_snapshot_inventory(a)
    via=next(t for t in b.GetTracks() if force._uid(t)==uid)
    target=[via.GetPosition().x+750000,via.GetPosition().y+750000]
    proof=transport.apply(a,b,[dict(uuid=uid,position_nm=target)],source_path=path,
        board_hint='synthetic',obstructing_items=obstacles,clearance_nm=200000,allow_locked_via_uuids=[uid])
    assert len(proof['generated_transient_track_uuids'])==1
    assert sum(r['actual_body_contact_split'] for r in proof['kernel_changes'])==1
    tracks=[t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK']
    assert len(tracks)==3 and all(target in [list(t.GetStart()),list(t.GetEnd())] for t in tracks)
    assert field._field_snapshot_inventory(a)==before


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_rim_endpoint_contact_is_not_mistaken_for_an_interior_tee(tmp_path,turn,mirror):
    a,b,path,uid,obstacles=fixture(tmp_path,turn,mirror)
    for board in (a,b):
        t=next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.F_Cu)
        s,e=t.GetStart(),t.GetEnd()
        offset=pcbnew.VECTOR2I(-(e.y-s.y)*3//40,(e.x-s.x)*3//40)
        t.Move(offset)
    via=next(t for t in b.GetTracks() if force._uid(t)==uid)
    target=[via.GetPosition().x+750000,via.GetPosition().y+750000]
    proof=transport.apply(a,b,[dict(uuid=uid,position_nm=target)],source_path=path,
        board_hint='synthetic',obstructing_items=obstacles,clearance_nm=200000,allow_locked_via_uuids=[uid])
    assert not proof['generated_transient_track_uuids']
    assert all(not r['actual_body_contact_split'] for r in proof['kernel_changes'])
    assert proof['source_contact_witness_is_not_full_width_or_capacity_credit']
    assert len([t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK'])==2


@pytest.mark.parametrize('fault',['protected','source_group','candidate_group','track_width','track_lock',
    'same_seat','far','bad_point','bad_motion','bad_schema','missing_track'])
def test_invalid_scope_or_source_change_is_refused_without_partial_writes(tmp_path,fault):
    a,b,path,uid,obstacles=fixture(tmp_path)
    via=next(t for t in b.GetTracks() if force._uid(t)==uid)
    target=[via.GetPosition().x+750000,via.GetPosition().y+750000]
    q=dict(uuid=uid,position_nm=target);limit=2.
    if fault=='protected':
        for board in (a,b):
            n=pcbnew.NETINFO_ITEM(board,'/USB_D_P');board.Add(n)
            for t in board.GetTracks():t.SetNet(n)
    elif fault=='source_group':
        v=next(t for t in a.GetTracks() if force._uid(t)==uid)
        g=pcbnew.PCB_GROUP(a);g.SetName('OTHER_OWNER');g.AddItem(v);a.Add(g)
    elif fault=='candidate_group':
        g=pcbnew.PCB_GROUP(b);g.SetName('NEW_OWNER');g.AddItem(via);b.Add(g)
    elif fault in ('track_width','track_lock','missing_track'):
        t=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
        if fault=='track_width':t.SetWidth(250000)
        elif fault=='track_lock':t.SetLocked(not t.IsLocked())
        else:b.Remove(t)
    elif fault=='same_seat':q['position_nm']=list(via.GetPosition())
    elif fault=='far':q['position_nm'][0]+=5000000
    elif fault=='bad_point':q['position_nm'][0]=True
    elif fault=='bad_motion':limit=True
    elif fault=='bad_schema':q['current_a']=1
    before=field._field_snapshot_inventory(b);original=field._field_snapshot_inventory(a)
    with pytest.raises(ValueError):
        transport.apply(a,b,[q],source_path=path,board_hint='synthetic',obstructing_items=obstacles,
            clearance_nm=200000,allow_locked_via_uuids=[uid],maximum_shift_mm=limit)
    assert field._field_snapshot_inventory(b)==before and field._field_snapshot_inventory(a)==original

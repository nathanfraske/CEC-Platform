"""Explicit 45-degree native SMD poses preserve real lands and process scope."""
import json

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_cell_row_rebuild as row
import cec_complete_macro_cell as complete
import cec_field_coupling as field
import cec_force_current as force
import cec_smd_macro_transport as transport
from test_cell_row_rebuild import fixture as row_fixture
from test_complete_macro_cell import fixture as complete_fixture
from test_smd_macro_transport import pair,cardinal_pair,inventory


@pytest.mark.parametrize('turn',[45,135,225,315])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('offset',[(0,0),(.625,0)])
def test_native_octilinear_pose_transports_exact_existing_barrels_and_dogbone(tmp_path,turn,back,offset):
    parent,private,uid,tail=cardinal_pair(tmp_path,back=back,offset=offset)
    owner=force._uid(next(iter(parent.GetFootprints())))
    before=inventory(parent)
    old=next(f for f in parent.GetFootprints() if force._uid(f)==owner)
    fp=next(f for f in private.GetFootprints() if force._uid(f)==owner)
    delta=pcbnew.VECTOR2I_MM(.8,-.6)
    expected=next(t for t in parent.GetTracks() if force._uid(t)==uid).Duplicate()
    expected.Rotate(old.GetPosition(),pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    expected.Move(delta)
    fp.SetOrientationDegrees(old.GetOrientationDegrees()+turn)
    fp.Move(delta)
    proof=transport.apply(parent,private,allow_octilinear_rotations=True)
    actual=next(t for t in private.GetTracks() if force._uid(t)==uid)
    assert tuple(actual.GetPosition())==tuple(expected.GetPosition())
    assert actual.GetWidth(actual.TopLayer())==expected.GetWidth(expected.TopLayer())
    assert actual.GetDrillValue()==expected.GetDrillValue()
    assert proof['new_barrels_created']==0 and len(proof['source_process_barrel_motion'])==2
    if offset!=(0,0):
        assert tail in proof['transient_rebuild_required_uuids']
        dogbone=next(t for t in parent.GetTracks() if t.GetClass()=='PCB_TRACK' and force._uid(t)!=tail)
        after=next(t for t in private.GetTracks() if force._uid(t)==force._uid(dogbone))
        assert abs(after.GetLength()-dogbone.GetLength())<=1
        assert force._uid(dogbone) not in proof['transient_rebuild_required_uuids']
    assert proof['source_owner_octilinear_transforms'][owner]['octilinear_turn_deg']==turn
    assert inventory(parent)==before and not proof['saved_candidate_authorized']


@pytest.mark.parametrize('turn',[15,30,44,46,89,135.01])
def test_octilinear_permission_does_not_allow_arbitrary_angles_or_change_conductors(tmp_path,turn):
    parent,private,owner,uid=pair(tmp_path)
    fp=next(iter(private.GetFootprints()));fp.SetOrientationDegrees(turn)
    before=inventory(private)
    with pytest.raises(ValueError):transport.apply(parent,private,allow_octilinear_rotations=True)
    assert inventory(private)==before


@pytest.mark.parametrize('value',[None,1,0,'yes',{}])
def test_octilinear_permission_is_an_explicit_boolean(tmp_path,value):
    parent,private,owner,uid=pair(tmp_path)
    next(iter(private.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.5,.5))
    before=inventory(private)
    with pytest.raises(ValueError):transport.apply(parent,private,allow_octilinear_rotations=value)
    assert inventory(private)==before


def test_default_surface_policy_still_refuses_diagonal_rotation(tmp_path):
    parent,private,owner,uid=pair(tmp_path)
    next(iter(private.GetFootprints())).SetOrientationDegrees(45)
    before=inventory(private)
    with pytest.raises(ValueError):transport.apply(parent,private,allow_cardinal_rotations=True)
    assert inventory(private)==before


@pytest.mark.parametrize('turn',[45,135,225,315])
def test_source_row_plan_roundtrip_rederives_native_diagonal_land(turn):
    board,poses,cells,tracks=row_fixture()
    target={'BYPASS':[12.,13.,float(turn)]}
    before=row._source_binding(board)
    plan=row.plan(board,target,{},allow_owned_locked=True,allow_octilinear_rotations=True)
    assert row._source_binding(board)==before
    saved=json.loads(json.dumps(plan))
    row.apply(board,saved)
    assert board.FindFootprintByReference('BYPASS').GetOrientationDegrees()==turn or (
        board.FindFootprintByReference('BYPASS').GetOrientationDegrees()-turn)%360==0
    assert not saved['routing_admitted']


@pytest.mark.parametrize('back',[False,True])
def test_complete_saved_macro_rederives_diagonal_capacitor_pose_and_all_returns(tmp_path,monkeypatch,back):
    source,parent,unused,seed=complete_fixture(tmp_path,monkeypatch,back=back)
    poses=seed['source_plan']['poses']
    cap=next(iter(seed['source_plan']['selected_bypasses']))
    poses[cap][2]+=45.
    raw=source.read_bytes()
    private,packet=compiler.compile(source,poses,board_hint='opaque',allow_octilinear_rotations=True)
    assert packet['explicit_native_macro_options']['allow_octilinear_rotations'] is True
    additive._ground_refill(private)
    proof=complete.screen(source,private,packet,board_hint='opaque')
    assert proof['complete'],(proof['errors'],proof.get('empty_obligations'))
    escape.construct_private(private,proof['packet'],proof['selection'])
    additive._ground_refill(private)
    child=force._copy_family(source,tmp_path/'UNADMITTED-octilinear-cell')
    field._save_field_snapshot(private,child)
    received=complete.receive(source,child,board_hint='opaque',allow_octilinear_rotations=True)
    assert received['ok'] and received['complete'],received['errors']
    assert received['all_original_surviving_native_partitions_preserved']
    assert received['all_original_physical_ground_returns']['ok']
    assert not complete.receive(source,child,board_hint='opaque')['ok']
    assert source.read_bytes()==raw and not received['release_authority']

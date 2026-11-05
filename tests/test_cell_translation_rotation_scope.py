"""Pose events derive the rotated source cut, not stationary ownership."""
import math
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_escape_pose_frontier as frontier
import cec_field_coupling as field
import cec_force_current as force
import cec_cell_row_rebuild as row
from test_cell_escape_replan import fixture


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('delta',[(0.,0.),(.6,-.4)])
def test_real_owned_escape_is_cut_before_exactly_once_rotated_event_query(
        monkeypatch,tmp_path,rotation,mirror,delta):
    board,_,owner,cap=fixture(monkeypatch,prefix='independent_rotated_cell')
    pad=owner.FindPadByNumber('2');start=pad.GetPosition()
    departure=pcbnew.PCB_TRACK(board);departure.SetNet(pad.GetNet())
    departure.SetStart(start);departure.SetEnd(start+pcbnew.VECTOR2I_MM(0,3))
    departure.SetWidth(200000);departure.SetLayer(pcbnew.F_Cu)
    departure.SetLocked(True);board.Add(departure)
    barrel=pcbnew.PCB_VIA(board);barrel.SetNet(pad.GetNet())
    barrel.SetPosition(departure.GetEnd());barrel.SetWidth(600000)
    barrel.SetDrill(300000);barrel.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(barrel)
    foreign=pcbnew.PCB_TRACK(board);foreign.SetNet(board.FindNet('INPUT_N'))
    foreign.SetStart(pcbnew.VECTOR2I_MM(18,18));foreign.SetEnd(pcbnew.VECTOR2I_MM(22,18))
    foreign.SetWidth(2000000);foreign.SetLayer(pcbnew.In3_Cu);foreign.SetLocked(True);board.Add(foreign)
    if mirror:
        for item in [*board.GetFootprints(),*board.GetTracks()]:
            item.Flip(pcbnew.VECTOR2I_MM(20,20),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    parent=pcbnew.LoadBoard(str(source));before=row._source_binding(parent)
    sha=force._hash(source);refs=[owner.GetReference(),cap.GetReference()]
    expected=frontier.rigid_poses(parent,refs,refs[0],delta,rotation)
    expected_scope=escape.prepare(parent,expected,board_hint='opaque',max_shift_mm=16.)
    own_id=force._uid(departure);foreign_id=force._uid(foreign);barrel_id=force._uid(barrel)
    assert (own_id in expected_scope['retired_track_uuids']) is bool(rotation or any(delta))
    monkeypatch.setattr(force,'_family',lambda *_a,**_k:('immutable',sha))
    monkeypatch.setattr(force,'_code_identity',lambda:'stable-test-epoch')
    calls=[]
    def projected(private,owners,**kw):
        calls.append(kw)
        assert kw['rotation_deg']==0
        assert set(kw['selected_refs'])==set(refs)
        for ref,target in expected.items():
            fp=private.FindFootprintByReference(ref)
            assert tuple(fp.GetPosition())==tuple(round(v*1e6) for v in target[:2])
            assert math.remainder(fp.GetOrientationDegrees()-target[2],360)==pytest.approx(0.)
        ids={force._uid(t) for t in private.GetTracks()}
        assert (own_id not in ids) is bool(rotation or any(delta))
        assert {barrel_id,foreign_id}<=ids
        return dict(deltas_mm=[[.3,-.4]],rotation_deg=0,routing_admitted=False,
            release_authority=False,no_path_proof=False)
    monkeypatch.setattr(frontier,'assembly_translation_events',projected)
    report=frontier.cell_translation_events(source,[refs[0]],board_hint='opaque',
        seed_delta_mm=delta,rotation_deg=rotation,radius_mm=4.)
    assert len(calls)==1 and report['rotation_deg']==rotation
    assert report['private_projector_rotation_deg']==0
    assert report['proposed_source_rotation_applied_exactly_once']
    assert report['source_owned_retired_track_uuids']==expected_scope['retired_track_uuids']
    assert report['deltas_from_source_mm']==[[delta[0]+.3,delta[1]-.4]]
    assert report['fresh_source_plan_for_each_final_pose_required']
    assert not report['routing_admitted'] and not report['release_authority']
    assert row._source_binding(pcbnew.LoadBoard(str(source)))==before and force._hash(source)==sha


def test_unknown_rotating_device_is_not_an_event_cut_authority(monkeypatch,tmp_path):
    board,_,owner,_=fixture(monkeypatch,prefix='unsupported_device')
    owner.SetValue('unqualified_device');source=tmp_path/'source.kicad_pcb'
    field._save_field_snapshot(board,source);sha=force._hash(source)
    monkeypatch.setattr(force,'_family',lambda *_a,**_k:('immutable',sha))
    monkeypatch.setattr(force,'_code_identity',lambda:'stable-test-epoch')
    def unexpected(*_a,**_k):raise AssertionError('unproved cut reached projector')
    monkeypatch.setattr(frontier,'assembly_translation_events',unexpected)
    with pytest.raises(ValueError,match='positive_complete_low_power_device_pin_contract_required'):
        frontier.cell_translation_events(source,[owner.GetReference()],board_hint='opaque',
            seed_delta_mm=(0.,0.),rotation_deg=180)
    assert force._hash(source)==sha

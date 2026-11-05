"""Native geometry, finite budgets and normal placement-generator integration."""
import pytest
import pcbnew

import cec_certificate_repair as repair
import cec_fixed_pofv_mobility as mobility
import cec_fab_profile as fab
from test_fixed_pofv_mobility import fixture, pose


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('offset,ref', [((0, 0), 'SUPPORT'), ((17, -9), 'RENAMED')])
def test_actual_fixed_anchor_rotations_preserve_barrel(back, offset, ref):
    board, fp, pad, via = fixture(back=back, offset=offset, ref=ref)
    before = (tuple(pad.GetPosition()), tuple(via.GetPosition()), fp.GetOrientationDegrees())
    rows = mobility.proposals(board, dict(ref=ref), reach_fractions=(0,))
    assert len(rows) == 3
    assert {row['rotation_delta_deg'] for row in rows} == {90, 180, -90}
    original_position = fp.GetPosition()
    original_angle = fp.GetOrientationDegrees()
    for row in rows:
        assert row['fixed_anchor']['via_uuid'] == via.m_Uuid.AsString()
        assert mobility.evaluate(board, dict(ref=ref), row)['ok']
        fp.SetPosition(original_position + pcbnew.VECTOR2I_MM(row['dx_mm'], row['dy_mm']))
        fp.SetOrientationDegrees(original_angle + row['rotation_delta_deg'])
        assert tuple(pad.GetPosition()) == tuple(via.GetPosition())
        assert fab.local_pofv_via_decision(board, via)[0]
        fp.SetPosition(original_position)
        fp.SetOrientationDegrees(original_angle)
    assert before == (tuple(pad.GetPosition()), tuple(via.GetPosition()), fp.GetOrientationDegrees())


def test_budget_determinism_and_noop_are_not_mutations():
    board, fp, pad, via = fixture()
    target = dict(ref=fp.GetReference())
    rows = mobility.proposals(board, target)
    assert 3 < len(rows) < 512
    assert rows == mobility.proposals(board, target)
    assert rows[:2] == mobility.proposals(board, target, max_candidates=2)
    assert all(mobility.evaluate(board, target, row)['ok'] for row in rows)
    assert all((row['dx_mm'], row['dy_mm'], row['rotation_delta_deg']) != (0, 0, 0) for row in rows)
    assert mobility.proposals(board, target, generated_locked_uuids=(via.m_Uuid.AsString(),)) == []
    fp.SetLocked(True)
    assert mobility.proposals(board, target) == []


@pytest.mark.parametrize('kwargs', [
    {'max_candidates': 0}, {'max_candidates': True}, {'max_candidates': 4097},
    {'max_anchors': 0}, {'max_anchors': 1.5}, {'max_anchors': 65},
    {'rotations': (45,)}, {'rotations': (float('nan'),)}, {'rotations': ()},
    {'reach_fractions': (1.1,)}, {'reach_fractions': (-0.1,)},
    {'reach_fractions': (float('inf'),)}, {'reach_fractions': ()}])
def test_invalid_search_parameters_fail_closed(kwargs):
    board, fp, pad, via = fixture()
    with pytest.raises(ValueError):
        mobility.proposals(board, dict(ref=fp.GetReference()), **kwargs)


@pytest.mark.parametrize('back', [False, True])
def test_dependency_survives_a_native_short_dogbone(back):
    board, fp, pad, via = fixture(back=back)
    fp.SetPosition(fp.GetPosition() + pcbnew.VECTOR2I_MM(1, 0))
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pad.GetPosition()); track.SetEnd(via.GetPosition())
    track.SetWidth(200000)
    track.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu)
    track.SetNet(via.GetNet()); board.Add(track)
    assert fab.local_pofv_via_decision(board, via)[0]
    records = mobility.constraints(board, {fp.GetReference()})
    assert len(records) == 1 and records[0]['owner_kind'] == 'live_dogbone'
    assert not mobility.evaluate(board, dict(ref=fp.GetReference()), pose(3))['ok']
    rows = mobility.proposals(board, dict(ref=fp.GetReference()), reach_fractions=(0,))
    assert rows and all(row['fixed_anchor']['owner_kind'] == 'live_dogbone' for row in rows)


def test_nearby_same_net_pad_is_not_an_owner_and_duplicate_numbers_are_not_lost():
    board, fp, pad, via = fixture()
    other = pcbnew.PAD(fp)
    other.SetNumber(pad.GetNumber())
    other.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    other.SetShape(pcbnew.PAD_SHAPE_RECT)
    other.SetSize(pcbnew.VECTOR2I_MM(.6, .4))
    other.SetPosition(pad.GetPosition() + pcbnew.VECTOR2I_MM(.9, 0))
    other.SetLayerSet(pad.GetLayerSet()); other.SetNet(pad.GetNet())
    fp.Add(other)
    records = mobility.constraints(board, {fp.GetReference()})
    assert len(records) == 1
    assert tuple(records[0]['owner'].GetPosition()) == tuple(pad.GetPosition())


def test_multiple_fixed_owner_domains_are_intersected():
    board, fp, pad, via = fixture()
    second = pcbnew.PAD(fp)
    second.SetNumber('OTHER')
    second.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    second.SetShape(pcbnew.PAD_SHAPE_RECT)
    second.SetSize(pcbnew.VECTOR2I_MM(.6, .4))
    second.SetPosition(pad.GetPosition() + pcbnew.VECTOR2I_MM(4, 0))
    second.SetLayerSet(pad.GetLayerSet()); second.SetNet(pad.GetNet()); fp.Add(second)
    second_via = pcbnew.PCB_VIA(board)
    second_via.SetPosition(second.GetPosition()); second_via.SetWidth(350000)
    second_via.SetDrill(250000); second_via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    second_via.SetNet(via.GetNet()); second_via.SetLocked(True); board.Add(second_via)
    rows = mobility.proposals(board, dict(ref=fp.GetReference()))
    assert rows and all(row['rotation_delta_deg'] == 0 for row in rows)
    assert all(mobility.evaluate(board, dict(ref=fp.GetReference()), row)['checked'] == 2 for row in rows)


def test_normal_occupancy_ranks_valid_anchor_poses_before_top_k(tmp_path):
    board, fp, pad, via = fixture()
    for a, b in (((0, 0), (60, 0)), ((60, 0), (60, 60)),
                 ((60, 60), (0, 60)), ((0, 60), (0, 0))):
        edge = pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts); edge.SetWidth(50000); board.Add(edge)
    signal = pcbnew.NETINFO_ITEM(board, '/OPEN'); board.Add(signal)
    output = pcbnew.PAD(fp)
    output.SetNumber('signal'); output.SetNet(signal)
    output.SetAttribute(pcbnew.PAD_ATTRIB_SMD); output.SetShape(pcbnew.PAD_SHAPE_RECT)
    output.SetSize(pcbnew.VECTOR2I_MM(.6, .4)); output.SetLayerSet(pad.GetLayerSet())
    output.SetPosition(fp.GetPosition() - pcbnew.VECTOR2I_MM(.775, 0)); fp.Add(output)
    source = tmp_path / 'native.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    before = source.read_bytes()
    target = repair.asdict(repair.FootprintRepairTarget(ref=fp.GetReference(),
        target_net='/OPEN', endpoint_ref='PEER', endpoint_pad='1',
        endpoint_x_mm=2, endpoint_y_mm=3, hit_count=1, distance_mm=30,
        priority=(0,), motion='toward_endpoint'))
    rows = repair._occupancy_relocation_candidates(str(source), target, limit=1)
    assert len(rows) == 1 and rows[0]['generator'] == 'fixed_local_via_domain'
    assert mobility.evaluate(board, target, rows[0])['ok']
    assert rows[0]['occupancy_score']['outside_mm2'] == 0
    assert source.read_bytes() == before

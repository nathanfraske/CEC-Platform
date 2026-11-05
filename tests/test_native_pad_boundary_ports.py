"""Contacts share a port only by an unchanged connected native SMD land."""
import copy
import math
import pcbnew
import pytest
import cec_native_pad_boundary_ports as ports
import cec_field_coupling as field
import cec_force_current as force
from test_field_refill_proposals import ground_fixture
from test_field_proposals import track


def fixture(tmp_path, angle=0, mirror=1):
    _, board = ground_fixture(tmp_path)
    def xy(p):
        a = math.radians(angle); x, y = p[0]*mirror, p[1]
        return (round(15+x*math.cos(a)-y*math.sin(a), 6),
                round(12+x*math.sin(a)+y*math.cos(a), 6))
    pads = []
    for i, point in enumerate(((-3, 0), (3, 0))):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference('OWNER'+str(i)); board.Add(fp)
        pad = pcbnew.PAD(fp); fp.Add(pad); pad.SetNumber('1')
        pad.SetNetCode(board.GetNetcodeFromNetname('/CONTROL'))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*xy(point))); pad.SetSize(pcbnew.VECTOR2I_MM(1, 1))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        mask = pcbnew.LSET(); mask.AddLayer(pcbnew.F_Cu); pad.SetLayerSet(mask); pads.append(pad)
    old = track(board, '/CONTROL', xy((-3, 0)), xy((3, 0)))
    anchors = [list(pcbnew.VECTOR2I_MM(*xy(p))) for p in
               ((-3, 0), (2.8, -.1), (3, 0), (3.2, .2))]
    row = dict(net='/CONTROL', layer='F.Cu', external_boundary_count=4, anchors_nm=anchors)
    return board, pads, old, [row], xy


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('mirror', [1, -1])
def test_rotated_mirrored_multiple_contacts_keep_one_actual_pad_port(tmp_path, angle, mirror):
    board, pads, old, rows, _ = fixture(tmp_path, angle, mirror)
    before = field._field_snapshot_inventory(board)
    proof = ports.plan(board, rows, retired_track_uuids=[force._uid(old)])
    assert proof['endpoints_nm'] == sorted([list(p.GetPosition()) for p in pads])
    assert sorted(len(p['source_anchor_points_nm']) for p in proof['ports']) == [1, 3]
    assert proof['independently_restore_every_original_anchor_required']
    assert not proof['current_or_barrel_capacity_credited']
    assert before == field._field_snapshot_inventory(board)


@pytest.mark.parametrize('fault', ['wrong_count', 'wrong_net', 'wrong_face', 'floating',
    'duplicate', 'foreign_cut', 'tht', 'npth', 'overlapping_pad', 'custom', 'missing_cut'])
def test_no_coordinate_or_net_alias_can_merge_unproved_source_contacts(tmp_path, fault):
    board, pads, old, rows, xy = fixture(tmp_path)
    if fault == 'wrong_count': rows[0]['external_boundary_count'] = 2
    elif fault == 'wrong_net': rows[0]['net'] = 'GND'
    elif fault == 'wrong_face': rows[0]['layer'] = 'B.Cu'
    elif fault == 'floating': rows[0]['anchors_nm'][1] = [25000000, 15000000]
    elif fault == 'duplicate': rows[0]['anchors_nm'][1] = rows[0]['anchors_nm'][2]
    elif fault == 'foreign_cut': old.SetNetCode(board.GetNetcodeFromNetname('GND'))
    elif fault in ('tht', 'npth'):
        pads[1].SetAttribute(pcbnew.PAD_ATTRIB_PTH if fault == 'tht' else pcbnew.PAD_ATTRIB_NPTH)
        pads[1].SetDrillSize(pcbnew.VECTOR2I_MM(.3, .3))
    elif fault == 'overlapping_pad':
        fp = pcbnew.FOOTPRINT(board); board.Add(fp); pad = pcbnew.PAD(pads[1]); fp.Add(pad)
    elif fault == 'custom': pads[1].SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    ids = [] if fault == 'missing_cut' else [force._uid(old)]
    before = field._field_snapshot_inventory(board)
    with pytest.raises(ValueError): ports.plan(board, rows, retired_track_uuids=ids)
    assert before == field._field_snapshot_inventory(board)


@pytest.mark.parametrize('budget', [0, 11, True, float('nan'), float('inf')])
def test_finite_boundary_proposal_lease_required(tmp_path, budget):
    board, _, old, rows, _ = fixture(tmp_path)
    with pytest.raises(ValueError): ports.plan(board, rows, retired_track_uuids=[force._uid(old)], timeout_s=budget)

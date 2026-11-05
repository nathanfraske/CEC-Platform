"""Optical placement must not ignore native mechanical permissions."""
import json

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest

import cec_field_coupling as field
import cec_native_rule_areas as rules
import cec_route_checkpoint as checkpoint
import cec_synth_pipeline as synth
from test_fiducial_edge_policy import TestFiducialEdgePolicy as FiducialFixture


def fixture(*, permission='footprints', layer=pcbnew.F_Cu, embedded=False):
    board = FiducialFixture._board()
    for fp in board.GetFootprints():
        fp.SetFPID(pcbnew.LIB_ID('cec-Fiducial', 'Fiducial_1mm_Mask2mm'))
    fp = board.FindFootprintByReference('FID3')
    fp.SetPosition(pcbnew.VECTOR2I_MM(45, 5))
    parent = board
    if embedded:
        parent = pcbnew.FOOTPRINT(board)
        parent.SetReference('UNRELATED_MECHANICAL_OWNER')
        board.Add(parent)
    area = pcbnew.ZONE(parent)
    area.SetLayer(layer)
    area.SetIsRuleArea(True)
    area.SetZoneName('renamed native mechanical boundary')
    area.SetDoNotAllowPads(permission == 'pads')
    area.SetDoNotAllowFootprints(permission == 'footprints')
    area.SetDoNotAllowTracks(True)
    area.Outline().NewOutline()
    for x, y in ((42, 2), (49, 2), (49, 8), (42, 8)):
        area.Outline().Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    parent.Add(area)
    return board, area


@pytest.mark.parametrize('permission', ['pads', 'footprints'])
@pytest.mark.parametrize('embedded', [False, True])
def test_both_native_owners_and_permissions_reseat_mark(tmp_path, permission, embedded):
    board, area = fixture(permission=permission, embedded=embedded)
    path = tmp_path/'board.kicad_pcb'
    field._save_field_snapshot(board, path)
    before = synth._oracle_fiducials(str(path), expect=True)
    assert not before['ok'] and any(v[0] == 'native_keepout' for v in before['violations'])
    report = synth.repair_fiducials_to_edge_band(str(path), allow_existing_copper=True)
    assert report['ok'] and [r['ref'] for r in report['moved']] == ['FID3']
    assert synth._oracle_fiducials(str(path), expect=True)['ok']
    saved = pcbnew.LoadBoard(str(path))
    assert len(rules.optical_areas(saved, pcbnew.F_Cu)) == 1


@pytest.mark.parametrize('permission,layer', [('tracks', pcbnew.F_Cu), ('pads', pcbnew.B_Cu)])
def test_unrelated_permission_or_opposite_face_does_not_block_mark(tmp_path, permission, layer):
    board, _ = fixture(permission=permission, layer=layer)
    path = tmp_path/'board.kicad_pcb'
    field._save_field_snapshot(board, path)
    assert synth._oracle_fiducials(str(path), expect=True)['ok']
    assert not synth.repair_fiducials_to_edge_band(str(path), allow_existing_copper=True)['changed']


def test_native_hole_is_not_replaced_with_aabb():
    board, area = fixture()
    area.Outline().NewHole(0)
    for x, y in ((43, 3), (43, 7), (47, 7), (47, 3)):
        area.Outline().Append(pcbnew.FromMM(x), pcbnew.FromMM(y), 0, 0)
    shape = rules.optical_areas(board, pcbnew.F_Cu)[0]['shape']
    assert not shape.Collide(pcbnew.VECTOR2I_MM(45, 5), pcbnew.FromMM(1.5))
    assert shape.Collide(pcbnew.VECTOR2I_MM(42.5, 5), pcbnew.FromMM(.1))


@pytest.mark.parametrize('fault', ['none', 'functional', 'pad', 'copper', 'rule', 'authority', 'rotation'])
def test_optical_receiving_permits_only_exact_unconnected_translation(tmp_path, fault):
    board, area = fixture()
    source, child = tmp_path/'before.kicad_pcb', tmp_path/'after.kicad_pcb'
    field._save_field_snapshot(board, source)
    state = dict(placement_scope='complete', placements={'FID3': [45, 5, 0]},
                 report={'untouched': 'electrical debt'})
    source.with_suffix('.pourfirst-state.json').write_text(json.dumps(state))
    fp = board.FindFootprintByReference('FID3')
    fp.SetPosition(pcbnew.VECTOR2I_MM(45, 12))
    if fault == 'functional':
        fp.SetFPID(pcbnew.LIB_ID('Connector', 'Not_a_mark'))
    elif fault == 'pad':
        pad = pcbnew.PAD(fp); pad.SetNumber('1'); pad.SetSize(pcbnew.VECTOR2I_MM(1, 1)); fp.Add(pad)
    elif fault == 'copper':
        track = pcbnew.PCB_TRACK(board); track.SetStart(pcbnew.VECTOR2I_MM(20, 20))
        track.SetEnd(pcbnew.VECTOR2I_MM(25, 20)); track.SetWidth(pcbnew.FromMM(.2)); board.Add(track)
    elif fault == 'rule': area.SetDoNotAllowPads(True)
    elif fault == 'rotation': fp.SetOrientationDegrees(90)
    field._save_field_snapshot(board, child)
    state['placements']['FID3'] = [45, 12, 0]
    if fault == 'authority': state['report'] = {'invented': 'qualified'}
    child.with_suffix('.pourfirst-state.json').write_text(json.dumps(state))
    received = checkpoint.optical_preservation(source, child)
    assert received['ok'] is (fault == 'none'), received
    assert received['complete'] is (fault == 'none')
    assert not received['release_authority'] and not received['grants_local_copper_ownership']

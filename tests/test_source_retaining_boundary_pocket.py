"""Literal source retention and changed-region policy, never source qualification."""
import copy
from pathlib import Path
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_rectilinear_copper as native
import cec_regional_fill as regional
import cec_source_retaining_boundary_pocket as pocket
from test_lastmile import _board

def fixture(tmp_path, legacy=False):
    b = _board([(3, 3, 'SYNTH_POCKET'), (7, 3, 'SYNTH_POCKET')], edge=(0, 0, 12, 10))
    b.SetCopperLayerCount(6)
    points = [[2000000, 2000000], [8000000, 2000000], [8000000, 6000000], [6000000, 6000000],
        [6000000, 5800000], [4000000, 5800000], [4000000, 6000000], [2000000, 6000000]]
    def zone(points, priority):
        z = pcbnew.ZONE(b); z.SetNet(next(iter(b.GetPads())).GetNet()); z.SetLayer(pcbnew.F_Cu)
        z.SetZoneName(native.ZONE_NAME); z.SetAssignedPriority(priority); z.SetLocalClearance(200000)
        z.SetMinThickness(100000); z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL); z.SetCornerSmoothingType(0)
        z.Outline().Append(native._poly(points)); z.SetFilledPolysList(pcbnew.F_Cu, native._poly(points)); z.SetIsFilled(True)
        b.Add(z); return z
    owner = zone(points, 0)
    if legacy:
        # A pre-existing stronger region's unfilled middle is already covered
        # by the old lower owner. The new pocket is elsewhere. This is frozen
        # test debt, NOT an assertion that such overlap is factory-qualified.
        stronger = zone([[4500000, 2500000], [5500000, 2500000], [5500000, 3500000], [4500000, 3500000]], 10)
        partial = native._poly([[4500000, 2500000], [4600000, 2500000], [4600000, 3500000], [4500000, 3500000]])
        stronger.SetFilledPolysList(pcbnew.F_Cu, partial)
    path = tmp_path/'source'/'board.kicad_pcb'; path.parent.mkdir()
    field._save_field_snapshot(b, path)
    return path, force._uid(owner)

@pytest.mark.parametrize('legacy', [False, True])
def test_native_addition_keeps_every_source_record_and_never_extends_stronger_void_intrusion(tmp_path, legacy):
    source, uid = fixture(tmp_path, legacy)
    proposal = pocket.plan(source, board_hint='synthetic_not_hardware', zone_uuid=uid)
    before = pcbnew.LoadBoard(str(source)); after = pocket.construct(source, proposal)
    old = next(z for z in before.Zones() if force._uid(z) == uid).GetFilledPolysList(pcbnew.F_Cu)
    new = next(z for z in after.Zones() if force._uid(z) == uid).GetFilledPolysList(pcbnew.F_Cu)
    assert regional.exact_source_contour_present(new, old, time.monotonic()+10.)
    assert not proposal['current_or_barrel_qualified'] and not proposal['inherited_regional_intrusion_qualified']
    added = new.CloneDropTriangulation(); added.BooleanSubtract(old)
    if legacy:
        assert proposal['regional_combination_contract']['regional_fill_binding']['protected_regions']
        strong = next(z for z in before.Zones() if z.GetAssignedPriority() == 10)
        void = strong.Outline().CloneDropTriangulation(); void.BooleanSubtract(strong.GetFilledPolysList(pcbnew.F_Cu))
        old_intrusion = old.CloneDropTriangulation(); old_intrusion.BooleanIntersection(void)
        assert old_intrusion.OutlineCount()
        intrusion = added.CloneDropTriangulation(); intrusion.BooleanIntersection(void)
        assert not intrusion.OutlineCount()

@pytest.mark.parametrize('fault', ['source', 'clearance', 'profile', 'regional_binding', 'mirror_geometry'])
def test_source_snapshot_process_or_geometry_cannot_be_forged(tmp_path, fault):
    source, uid = fixture(tmp_path)
    proposal = pocket.plan(source, board_hint='synthetic_not_hardware', zone_uuid=uid)
    bad = copy.deepcopy(proposal)
    if fault == 'source': bad['source_sha256'] = '0'*64
    elif fault == 'clearance': bad['source_configuration']['clearance_nm'] = 0
    elif fault == 'profile': bad['selected_pocket']['points_nm'][0][0] += 1
    elif fault == 'regional_binding': bad['regional_combination_contract']['min_thickness_nm'] = 1
    elif fault == 'mirror_geometry': bad['selected_pocket']['replacement_path_nm'].reverse()
    with pytest.raises(ValueError, match='stale_or_forged'): pocket.construct(source, bad)

@pytest.mark.parametrize('fault', ['field', 'extra_copper'])
def test_saved_child_cannot_smuggle_unowned_artwork_or_copper(tmp_path, fault):
    source, uid = fixture(tmp_path)
    proposal = pocket.plan(source, board_hint='synthetic_not_hardware', zone_uuid=uid)
    child = force._copy_family(source, tmp_path/'child')
    board = pocket.construct(source, proposal)
    if fault == 'field': next(iter(board.GetFootprints())).SetReference('FORGED')
    else:
        track = pcbnew.PCB_TRACK(board); track.SetNet(next(iter(board.GetPads())).GetNet())
        track.SetLayer(pcbnew.F_Cu); track.SetWidth(200000)
        track.SetStart(pcbnew.VECTOR2I(3000000,3000000));track.SetEnd(pcbnew.VECTOR2I(4000000,3000000))
        board.Add(track)
    field._save_field_snapshot(board, child)
    proof = pocket.receive(source, child, proposal, board_hint='synthetic_not_hardware')
    assert not proof['ok'] and not proof['complete']
    assert any('changed_unowned_saved_native_evidence' in error for error in proof['errors'])

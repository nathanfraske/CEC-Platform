"""Mount stitch proposals keep mounting datums and contact envelopes fixed."""
import math
from pathlib import Path

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
from cec_mounting_contract import (repair_radial_drill_field,
    repair_declared_radial_fields, repair_native_mount_fields)
import cec_fab_check as fab
import cec_fab_native_geometry as native


def fixture(angle=0, shift=(20, 30), flip=False, bore=2.2, land=4.4, radius=1.65, count=8):
    b = pcbnew.CreateEmptyBoard(); b.SetCopperLayerCount(6)
    net = pcbnew.NETINFO_ITEM(b, 'arbitrary_ground'); b.Add(net)
    fp = pcbnew.FOOTPRINT(b); fp.SetReference('RENAMED_MOUNT'); b.Add(fp)
    pads = []
    for i in range(count+1):
        p = pcbnew.PAD(fp); p.SetNumber('42'); p.SetNet(net)
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH); p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_CIRCLE)
        p.SetLayerSet(pcbnew.LSET.AllCuMask())
        diameter, drill = (land, bore) if i == 0 else (.7, .4)
        p.SetSize(pcbnew.VECTOR2I_MM(diameter, diameter))
        p.SetDrillSize(pcbnew.VECTOR2I_MM(drill, drill))
        pos = (0, 0) if i == 0 else (radius*math.cos(2*math.pi*(i-1)/count),
                                      radius*math.sin(2*math.pi*(i-1)/count))
        p.SetPosition(pcbnew.VECTOR2I_MM(*pos)); fp.Add(p); pads.append(p)
    fp.SetPosition(pcbnew.VECTOR2I_MM(*shift)); fp.SetOrientationDegrees(angle)
    if flip: fp.Flip(fp.GetPosition(), False)
    return b, fp, pads


def rules():
    return fab.profile_rules(fab.PROFILES['jlcpcb'], 1., 'jlcpcb_6l_pofv_signal')


@pytest.mark.parametrize('angle,shift,flip', [(0, (20, 30), False), (45, (-13, 42), False),
                                            (90, (5, -20), True), (137, (99, 12), True)])
@pytest.mark.parametrize('bore,land,radius,count', [(2.2, 4.4, 1.65, 8), (3.2, 6., 2.1, 8),
                                                  (2.2, 4.4, 1.65, 4)])
def test_repair_without_screw_or_contact_growth(angle, shift, flip, bore, land, radius, count):
    b, fp, pads = fixture(angle, shift, flip, bore, land, radius, count)
    before = [(p.GetSize(), p.GetDrillSize(), p.GetNetCode(), p.GetNumber(), p.GetPosition()) for p in pads]
    pose = (fp.GetPosition(), fp.GetOrientationDegrees(), fp.IsFlipped())
    result = repair_radial_drill_field(fp, .45)
    assert result['complete'] and result['applied_count'] == count, result
    assert pose == (fp.GetPosition(), fp.GetOrientationDegrees(), fp.IsFlipped())
    assert before[0] == (pads[0].GetSize(), pads[0].GetDrillSize(), pads[0].GetNetCode(),
                        pads[0].GetNumber(), pads[0].GetPosition())
    for p, old in zip(pads, before):
        assert old[:4] == (p.GetSize(), p.GetDrillSize(), p.GetNetCode(), p.GetNumber())
    for i, p in enumerate(pads):
        for q in pads[i+1:]:
            assert not p.GetEffectiveHoleShape().Collide(q.GetEffectiveHoleShape(), 450000)
    proof = native.audit_holes(b, rules())
    # A reversed full-through primary span is the same physical bore. Partial,
    # backdrilled and postmachined spans remain independently unsupported.
    assert proof['complete'] and not proof['findings'], proof
    assert repair_radial_drill_field(fp, .45)['applied_count'] == 0


def test_immutable_ring_refuses_growth():
    b, fp, pads = fixture(land=4.)
    before = [p.GetPosition() for p in pads]
    result = repair_radial_drill_field(fp, .45)
    assert not result['complete'] and result['applied_count'] == 0
    assert before == [p.GetPosition() for p in pads]


def test_foreign_terminal_refused():
    b, fp, pads = fixture(); pads[-1].SetNumber('different')
    before = [p.GetPosition() for p in pads]
    assert not repair_radial_drill_field(fp, .45)['complete']
    assert before == [p.GetPosition() for p in pads]


@pytest.mark.parametrize('floor', [True, float('nan'), float('inf'), -.1, 0.])
def test_invalid_authority_never_moves_pad(floor):
    b, fp, pads = fixture(); before = [p.GetPosition() for p in pads]
    assert not repair_radial_drill_field(fp, floor)['complete']
    assert before == [p.GetPosition() for p in pads]


def declare(fp):
    fp.SetFPID(pcbnew.LIB_ID('arbitrary_vendor', 'MountingHole_Declared'))
    fp.SetAttributes(pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)


def test_native_entry_uses_role_not_reference_and_keeps_already_compliant_mounts():
    b, fp, pads = fixture(); declare(fp)
    result = repair_native_mount_fields(b, rules())
    assert result['complete'] and result['applied_count'] == 8, result
    assert result['minimum_gap_mm'] == .45
    assert repair_native_mount_fields(b, rules())['applied_count'] == 0
    b, fp, pads = fixture(radius=1.76); declare(fp)
    before = [p.GetPosition() for p in pads]
    assert repair_native_mount_fields(b, rules())['applied_count'] == 0
    assert before == [p.GetPosition() for p in pads]


def test_terminal_and_unmarked_footprints_are_never_inferred_as_mounts():
    b, fp, pads = fixture(); before = [p.GetPosition() for p in pads]
    fp.SetFPID(pcbnew.LIB_ID('arbitrary_vendor', 'Connector_Terminal'))
    fp.SetAttributes(pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    assert repair_native_mount_fields(b, rules())['applied_count'] == 0
    fp.SetFPID(pcbnew.LIB_ID('arbitrary_vendor', 'MountingHole_Declared'))
    fp.SetAttributes(0)
    assert repair_native_mount_fields(b, rules())['applied_count'] == 0
    assert before == [p.GetPosition() for p in pads]


def test_locked_or_changed_declaration_requires_authority():
    b, fp, pads = fixture(); declare(fp); fp.SetLocked(True)
    declarations = {fp.GetReference(): fp.GetFPIDAsString()}
    assert not repair_declared_radial_fields(b, declarations, .45)['complete']
    assert not repair_declared_radial_fields(b, {fp.GetReference(): 'different'}, .45,
        allow_locked_footprint_uuids=[fp.m_Uuid.AsString()])['complete']
    assert repair_native_mount_fields(b, rules(),
        allow_locked_footprint_uuids=[fp.m_Uuid.AsString()])['applied_count'] == 8


def test_source_dru_strengthens_floor_and_cannot_force_envelope_growth(tmp_path):
    b, fp, pads = fixture(); declare(fp)
    path = tmp_path / 'arbitrary.kicad_pcb'
    path.with_suffix('.kicad_dru').write_text('(version 1) (rule "strict" (constraint hole_to_hole (min 0.6mm)))')
    before = [p.GetPosition() for p in pads]
    result = repair_native_mount_fields(b, rules(), board_path=path)
    assert not result['complete'] and result['minimum_gap_mm'] == .6
    assert before == [p.GetPosition() for p in pads]


def test_production_fab_repair_entry_routes_to_generic_mount_function(tmp_path, monkeypatch):
    import cec_fab_profile
    import cec_fab_repair
    b, fp, pads = fixture(); declare(fp)
    path = str(tmp_path / 'arbitrary.kicad_pcb'); pcbnew.SaveBoard(path, b)
    monkeypatch.setattr(cec_fab_profile, 'active_profile_name', lambda *a, **k: 'jlcpcb_6l_pofv_signal')
    result = cec_fab_repair.repair(path, apply=False, do_legend=False,
        do_priority=False, do_island=False, do_starved=False, do_acute=False,
        do_octilinear=False, do_backtrack=False)
    assert result['mounting_stitch']['applied_count'] == 8, result
    unchanged = pcbnew.LoadBoard(path)
    mount = unchanged.FindFootprintByReference('RENAMED_MOUNT')
    assert repair_radial_drill_field(mount, .45)['applied_count'] == 8  # dry run did not save


def test_vendored_slim_mount_already_meets_factory_floor():
    path = Path(__file__).resolve().parents[1] / 'lib/vendor/MountingHole.pretty'
    fp = pcbnew.FootprintLoad(str(path), 'MountingHole_2.2mm_M2_Pad_Via_Slim_6mm_Hardware')
    assert repair_radial_drill_field(fp, .45)['applied_count'] == 0
    assert min(p.GetDrillSize().x for p in fp.Pads()) == 400000


def test_vendored_standard_mount_does_not_reintroduce_underspaced_stitches():
    path = Path(__file__).resolve().parents[1] / 'lib/vendor/MountingHole.pretty'
    fp = pcbnew.FootprintLoad(str(path), 'MountingHole_2.2mm_M2_Pad_Via')
    result = repair_radial_drill_field(fp, .45)
    assert result['complete'] and result['applied_count'] == 0, result
    centre = max(fp.Pads(), key=lambda pad: pad.GetDrillSize().x)
    assert centre.GetDrillSize().x == 2200000 and centre.GetSize().x == 4400000

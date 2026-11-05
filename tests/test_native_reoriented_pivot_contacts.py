"""Fixed-centre contact proofs use native material, not identical rectangles."""
import time
import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_native_placement_context as motion
import cec_native_pivot_contacts as contacts
import cec_pose_additive_reconstruction as receiving
from test_native_local_cell_rotation import fixed_supply_setup


def fixture(*, face=pcbnew.F_Cu, orientation=0):
    b, fp, fixed, ground, via, dogbone, trunk, rail = fixed_supply_setup(layer=face)
    fp.SetReference('REORIENTED_UNRELATED_PACKAGE')
    if orientation:
        at = fixed.GetPosition()
        angle = pcbnew.EDA_ANGLE(orientation, pcbnew.DEGREES_T)
        fp.Rotate(at, angle)
        for item in (via, dogbone, trunk):
            item.Rotate(at, angle)
    return b, fp, fixed, ground, via, dogbone, trunk, rail


@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize('orientation', [0, 90, 180, 270])
@pytest.mark.parametrize('turn', [90, 270])
def test_reoriented_rectangle_keeps_real_trunk_and_rigid_private_return(face, orientation, turn):
    b, fp, fixed, ground, via, dogbone, trunk, _ = fixture(face=face, orientation=orientation)
    original = (tuple(trunk.GetStart()), tuple(trunk.GetEnd()), trunk.GetWidth(), tuple(fixed.GetPosition()))
    ids = {force._uid(item) for item in b.GetTracks()}
    with pytest.raises(ValueError, match='not_exactly_stationary'):
        motion.rotate_isolated_local_cells(b, {fp.GetReference(): turn},
            pivot_pad_uuids={fp.GetReference(): force._uid(fixed)})
    result = motion.rotate_isolated_local_cells(b, {fp.GetReference(): turn},
        pivot_pad_uuids={fp.GetReference(): force._uid(fixed)}, allow_reoriented_pivot_contacts=True)
    assert original == (tuple(trunk.GetStart()), tuple(trunk.GetEnd()), trunk.GetWidth(), tuple(fixed.GetPosition()))
    assert ids == {force._uid(item) for item in b.GetTracks()}
    assert tuple(ground.GetPosition()) == tuple(dogbone.GetStart())
    assert tuple(via.GetPosition()) == tuple(dogbone.GetEnd())
    proof = result['source_reoriented_pivot_contact_replay'][fp.GetReference()]
    assert proof['all_source_native_contacts_preserved'] and not proof['pad_copper_identical']
    assert force._uid(trunk) in {q['uuid'] for q in proof['original_native_contacts']}
    assert not result['exact_stationary_pivot_land_replay']
    assert not result['source_items_retired'] and not proof['release_authority']


@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize('turn', [90, 270])
def test_saved_receiving_independently_replays_reorientation_without_source_mutation(tmp_path, face, turn):
    b, fp, fixed, _, _, _, _, _ = fixture(face=face)
    for s, e in [((0, 0), (40, 0)), ((40, 0), (40, 40)), ((40, 40), (0, 40)), ((0, 40), (0, 0))]:
        item = pcbnew.PCB_SHAPE(b); item.SetShape(pcbnew.SHAPE_T_SEGMENT); item.SetLayer(pcbnew.Edge_Cuts)
        item.SetStart(pcbnew.VECTOR2I_MM(*s)); item.SetEnd(pcbnew.VECTOR2I_MM(*e)); item.SetWidth(50000); b.Add(item)
    source = tmp_path / 'source.kicad_pcb'; field._save_field_snapshot(b, source)
    uid, pad_uid = force._uid(fp), force._uid(fixed)
    target = force._copy_family(source, tmp_path / 'candidate')
    child = pcbnew.LoadBoard(str(target))
    motion.rotate_isolated_local_cells(child, {fp.GetReference(): turn},
        pivot_pad_uuids={fp.GetReference(): pad_uid}, allow_reoriented_pivot_contacts=True)
    additive._ground_refill(child); field._save_field_snapshot(child, target)
    source_bytes = source.read_bytes()
    denied = receiving.receive(source, target, selected_footprint_uuids=[uid], board_hint='unrelated',
        selected_pivot_pad_uuids={uid: pad_uid}, max_shift_mm=6.)
    assert not denied['ok'] and denied['errors']
    proof = receiving.receive(source, target, selected_footprint_uuids=[uid], board_hint='unrelated',
        selected_pivot_pad_uuids={uid: pad_uid}, max_shift_mm=6., allow_reoriented_pivot_contacts=True)
    assert proof['ok'] and proof['complete'], proof
    assert proof['all_original_terminal_and_copper_partitions_preserved']
    assert source.read_bytes() == source_bytes and not proof['release_authority']


@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_small_old_side_contact_cannot_be_hidden_by_a_new_rectangle(face):
    b, fp, fixed, _, via, _, _, rail = fixture(face=face)
    tiny = pcbnew.PCB_TRACK(b); tiny.SetLayer(face); tiny.SetNet(rail); tiny.SetWidth(10000)
    tiny.SetStart(pcbnew.VECTOR2I_MM(20.28, 18)); tiny.SetEnd(pcbnew.VECTOR2I_MM(20.28, 18.05)); b.Add(tiny)
    before = (tuple(fp.GetPosition()), fp.GetOrientationDegrees(), tuple(via.GetPosition()))
    with pytest.raises(ValueError, match='source_pivot_native_contact_lost'):
        motion.rotate_isolated_local_cells(b, {fp.GetReference(): 90},
            pivot_pad_uuids={fp.GetReference(): force._uid(fixed)}, allow_reoriented_pivot_contacts=True)
    assert before == (tuple(fp.GetPosition()), fp.GetOrientationDegrees(), tuple(via.GetPosition()))


def test_native_drilled_hole_is_not_fictional_pivot_copper():
    b, fp, fixed, _, _, _, trunk, rail = fixture()
    via = pcbnew.PCB_VIA(b); via.SetPosition(fixed.GetPosition()); via.SetNet(rail)
    via.SetWidth(1200000); via.SetDrill(1000000); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(via)
    clone = fp.Clone(); projected = pcbnew.Cast_to_FOOTPRINT(pcbnew.Cast_to_BOARD_ITEM(clone))
    projected.Rotate(fixed.GetPosition(), pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T))
    after = projected.FindPadByNumber(fixed.GetNumber())
    proof = contacts.preserve(b, fixed, after, deadline_monotonic=time.monotonic() + 2.)
    assert force._uid(trunk) in {q['uuid'] for q in proof['original_native_contacts']}
    assert force._uid(via) not in {q['uuid'] for q in proof['original_native_contacts']}


def test_unknown_same_net_fill_refuses_before_motion():
    b, fp, fixed, _, via, _, _, rail = fixture()
    zone = pcbnew.ZONE(b); zone.SetNet(rail); zone.SetLayer(pcbnew.F_Cu)
    zone.Outline().NewOutline()
    for x, y in [(19.5, 17.5), (20.5, 17.5), (20.5, 18.5), (19.5, 18.5)]:
        zone.Outline().Append(round(x * 1e6), round(y * 1e6))
    b.Add(zone)
    before = (fp.GetOrientationDegrees(), tuple(via.GetPosition()))
    with pytest.raises(ValueError, match='same_net_fill_unknown'):
        motion.rotate_isolated_local_cells(b, {fp.GetReference(): 90},
            pivot_pad_uuids={fp.GetReference(): force._uid(fixed)}, allow_reoriented_pivot_contacts=True)
    assert before == (fp.GetOrientationDegrees(), tuple(via.GetPosition()))


def test_contact_inventory_uses_actual_fill_not_the_authored_zone_outline():
    b, fp, fixed, _, _, _, trunk, rail = fixture()
    zone = pcbnew.ZONE(b); zone.SetNet(rail); zone.SetLayer(pcbnew.F_Cu)
    zone.Outline().NewOutline()
    for x, y in [(19.5, 17.5), (20.5, 17.5), (20.5, 18.5), (19.5, 18.5)]:
        zone.Outline().Append(round(x * 1e6), round(y * 1e6))
    fill = pcbnew.SHAPE_POLY_SET(); fill.NewOutline()
    for x, y in [(24, 22), (25, 22), (25, 23), (24, 23)]:
        fill.Append(round(x * 1e6), round(y * 1e6))
    zone.SetFilledPolysList(pcbnew.F_Cu, fill); zone.SetIsFilled(True); b.Add(zone)
    proof = motion.rotate_isolated_local_cells(b, {fp.GetReference(): 90},
        pivot_pad_uuids={fp.GetReference(): force._uid(fixed)}, allow_reoriented_pivot_contacts=True)
    ids = {q['uuid'] for q in proof['source_reoriented_pivot_contact_replay'][fp.GetReference()]['original_native_contacts']}
    assert force._uid(trunk) in ids and force._uid(zone) not in ids


def test_far_complex_parts_are_rejection_screened_not_polygonized_as_contacts():
    b, fp, fixed, _, _, _, _, rail = fixture()
    for index in range(128):
        other = pcbnew.FOOTPRINT(b); other.SetReference('FAR_' + str(index)); b.Add(other)
        pad = pcbnew.PAD(other); other.Add(pad); pad.SetNet(rail); pad.SetNumber('1')
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(1, 1.45)); pad.SetRoundRectRadiusRatio(.25)
        pad.SetPosition(pcbnew.VECTOR2I_MM(30 + index, 30)); pad.SetLayerSet(fixed.GetLayerSet())
    proof = motion.rotate_isolated_local_cells(b, {fp.GetReference(): 90},
        pivot_pad_uuids={fp.GetReference(): force._uid(fixed)}, allow_reoriented_pivot_contacts=True,
        timeout_s=2.)
    actual = proof['source_reoriented_pivot_contact_replay'][fp.GetReference()]['original_native_contacts']
    assert len(actual) == 1


@pytest.mark.parametrize('bad', [1, 'yes', None, [], float('nan')])
def test_new_contact_mode_is_explicit_boolean_not_a_truthy_waiver(bad):
    b, fp, fixed, _, _, _, _, _ = fixture()
    with pytest.raises(ValueError, match='bounded_explicit_cardinal'):
        motion.rotate_isolated_local_cells(b, {fp.GetReference(): 90},
            pivot_pad_uuids={fp.GetReference(): force._uid(fixed)}, allow_reoriented_pivot_contacts=bad)

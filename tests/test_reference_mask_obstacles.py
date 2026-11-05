"""Mask-art openings are native obstacles even without a pad, net or model."""
import copy
from pathlib import Path
import pcbnew
import pytest
import cec_dense_reference_mapping as mapping
import cec_reference_mask_obstacles as masks
import cec_field_coupling as field
import cec_force_current as force
from test_dense_reference_mapping import fixture


def proposal(tmp_path, *, back=False, quarter=0):
    source, grade, uid = fixture(tmp_path, back=back, quarter=quarter)
    plan = mapping.plan(source, grade=grade, board_hint='explicit_synthetic_mask_test', maximum_components=1)
    return source, plan, uid


def opening(source, plan, uid, *, child=False, opposite=False):
    board = pcbnew.LoadBoard(str(source))
    parent = next(fp for fp in board.GetFootprints() if force._uid(fp) == uid) if child else board
    x, y = plan['records'][0]['text_xy_mm']
    item = pcbnew.PCB_SHAPE(parent); item.SetShape(pcbnew.SHAPE_T_RECT)
    layer = pcbnew.B_Mask if plan['target_layer_id'] == pcbnew.B_SilkS else pcbnew.F_Mask
    if opposite: layer = pcbnew.F_Mask if layer == pcbnew.B_Mask else pcbnew.B_Mask
    item.SetLayer(layer); item.SetFilled(True); item.SetWidth(100000)
    item.SetStart(pcbnew.VECTOR2I(round((x-.15)*1e6), round((y-.15)*1e6)))
    item.SetEnd(pcbnew.VECTOR2I(round((x+.15)*1e6), round((y+.15)*1e6))); parent.Add(item)
    field._save_field_snapshot(board, source)
    # This fixture deliberately refreshes only this filter's Source witness.
    # No synthetic discovery-grade result is claimed to be real native DRC.
    plan['binding']['source_sha256'] = force._hash(source)
    return force._uid(item)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('child', [False, True])
def test_same_face_mask_artwork_rejects_proposed_reverse_ink(tmp_path, quarter, back, child):
    source, plan, uid = proposal(tmp_path, quarter=quarter, back=back)
    opening(source, plan, uid, child=child)
    proof = masks.observe(source, plan)
    assert not proof['ok'] and any('actual_native_mask_artwork' in e for e in proof['errors'])
    assert not proof['release_authority']


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('child', [False, True])
def test_mask_artwork_on_other_surface_is_not_an_invented_obstacle(tmp_path, back, child):
    source, plan, uid = proposal(tmp_path, back=back)
    opening(source, plan, uid, child=child, opposite=True)
    proof = masks.observe(source, plan)
    assert proof['ok'] and proof['complete'] and not proof['native_mask_artwork']


@pytest.mark.parametrize('fault', ['source_hash', 'invalid_layer'])
def test_mask_preflight_requires_actual_source_and_target_face(tmp_path, fault):
    source, plan, _ = proposal(tmp_path)
    bad = copy.deepcopy(plan)
    if fault == 'source_hash': bad['binding']['source_sha256'] = '0'*64
    else: bad['target_layer_id'] = pcbnew.F_Cu
    assert not masks.observe(source, bad)['ok']


def test_mask_filter_does_not_mutate_source_or_override_native_and_release_gates(tmp_path):
    source, plan, _ = proposal(tmp_path)
    before = source.read_bytes(); proof = masks.observe(source, plan)
    assert proof['ok'] and proof['native_drc_still_required']
    assert not proof['fab_ready'] and not proof['release_authority']
    assert before == source.read_bytes()


def test_chart_frame_title_and_leader_are_not_exempt_from_mask_artwork_checks(tmp_path):
    source, grade, uid = fixture(tmp_path, roomy=True)
    plan = mapping.plan(source, grade=grade, board_hint='explicit_synthetic_chart_mask', maximum_components=1)
    assert plan['mode'] == 'nearby_front_mapping_chart'
    board = pcbnew.LoadBoard(str(source)); fp = next(iter(board.GetFootprints()))
    items, _, _ = mapping.chart_decoration(board, plan['records'], [(fp, mapping.court(fp))],
        plan['target_layer_id'], plan['binding']['factory_legend'])
    title = next(t for t in items if t.GetClass() == 'PCB_TEXT')
    item = pcbnew.PCB_SHAPE(board); item.SetShape(pcbnew.SHAPE_T_RECT)
    item.SetLayer(pcbnew.F_Mask); item.SetFilled(True); item.SetWidth(100000)
    at = title.GetPosition()
    item.SetStart(pcbnew.VECTOR2I(at.x-150000, at.y-150000))
    item.SetEnd(pcbnew.VECTOR2I(at.x+150000, at.y+150000)); board.Add(item)
    field._save_field_snapshot(board, source)
    plan['binding']['source_sha256'] = force._hash(source)
    proof = masks.observe(source, plan)
    assert not proof['ok'] and 'chart_decoration' in str(proof['errors'])

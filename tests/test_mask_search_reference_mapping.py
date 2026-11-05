"""Mask search fixtures are geometry tests, not real hardware DRC grades."""
import copy
from pathlib import Path
import pcbnew
import pytest
import cec_dense_reference_mapping as original
import cec_mask_search_reference_mapping as search
import cec_reference_mask_obstacles as masks
import cec_force_current as force
import cec_field_coupling as field
from test_dense_reference_mapping import fixture
from test_reference_mask_obstacles import opening


def refresh_grade(source, grade):
    import json
    data = json.loads(grade.read_text())
    row = data['boards']['candidate']
    row['sha256'] = force._hash(source)
    row['native_producer']['source_files'][str(source)] = row['sha256']
    force._write(grade, data)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_mask_is_an_obstacle_during_search_not_only_a_late_filter(tmp_path, quarter, back):
    source, grade, uid = fixture(tmp_path, quarter=quarter, back=back)
    prior = original.plan(source, grade=grade, board_hint='explicit_mask_search_fixture',
        maximum_components=1)
    opening(source, prior, uid)
    refresh_grade(source, grade)
    unchanged = source.read_bytes()
    assert not masks.observe(source, prior)['ok']
    proposal = search.plan(source, grade=grade, board_hint='explicit_mask_search_fixture',
        maximum_components=1)
    assert proposal['records'][0]['text_xy_mm'] != prior['records'][0]['text_xy_mm']
    assert masks.observe(source, proposal)['ok']
    board, manifest = search.construct(source, proposal)
    child = force._copy_family(source, tmp_path/'candidate')
    field._save_field_snapshot(board, child)
    proof = search.receive(source, child, proposal)
    assert proof['ok'] and proof['complete'], proof
    assert proof['actual_native_mask_artwork_in_search_and_replayed']
    assert proof['all_copper_parts_pads_poses_outlines_models_bom_values_mpns_and_rules_exact']
    assert proof['whole_saved_second_native_roundtrip_stable']
    assert not proof['fab_ready'] and not proof['release_authority']
    assert source.read_bytes() == unchanged
    assert manifest['reverse_annotations_are_native_footprint_children']


@pytest.mark.parametrize('fault', ['owner_hash', 'mask_hash', 'policy', 'glyph', 'pose', 'omit_binding'])
def test_mask_search_plan_and_dependencies_cannot_be_forged(tmp_path, fault):
    source, grade, uid = fixture(tmp_path)
    proposal = search.plan(source, grade=grade, board_hint='explicit_mask_search_fixture',
        maximum_components=1)
    bad = copy.deepcopy(proposal)
    if fault in ('owner_hash', 'mask_hash'):
        module = search if fault == 'owner_hash' else masks
        bad['mask_search_binding']['input_sha256'][str(Path(module.__file__).resolve())] = '0'*64
    elif fault == 'policy':
        bad['mask_search_binding']['policy'] = 'anything'
    elif fault == 'glyph':
        bad['records'][0]['text_xy_mm'][0] += .000001
    elif fault == 'pose':
        bad['records'][0]['courtyard_xy_mm'][0][0] += .000001
    else:
        del bad['mask_search_binding']
    with pytest.raises(ValueError):
        search.construct(source, bad)


@pytest.mark.parametrize('back', [False, True])
def test_unrelated_surface_mask_does_not_change_selected_seat(tmp_path, back):
    source, grade, uid = fixture(tmp_path, back=back)
    prior = original.plan(source, grade=grade, board_hint='explicit_mask_search_fixture',
        maximum_components=1)
    opening(source, prior, uid, opposite=True)
    refresh_grade(source, grade)
    proposal = search.plan(source, grade=grade, board_hint='explicit_mask_search_fixture',
        maximum_components=1)
    assert proposal['records'] == prior['records']
    assert not masks.observe(source, proposal)['native_mask_artwork']


def test_no_global_patch_and_original_annotation_owner_remains_exact(tmp_path):
    source, grade, uid = fixture(tmp_path)
    before = original.plan(source, grade=grade, board_hint='explicit_mask_search_fixture',
        maximum_components=1)
    search.plan(source, grade=grade, board_hint='explicit_mask_search_fixture',
        maximum_components=1)
    after = original.plan(source, grade=grade, board_hint='explicit_mask_search_fixture',
        maximum_components=1)
    assert before == after and 'mask_search_binding' not in after
    assert original.obstacles is not search._private.obstacles


def test_actual_transformed_worker_compiles_and_keeps_all_original_native_gates():
    import root_run_mask_search_reference_mapping_20261020 as worker
    code = worker.source_code()
    compile(code, str(Path(worker.__file__)), 'exec')
    for gate in ('timeout_s=10.', "not produced['native_inventory']['potentially_truncated']",
            "saved_guard == guarded", "not fresh and not after['unconnected_items']"):
        assert gate in code
    assert "proposal['mask_search_binding']['input_sha256']" in code


@pytest.mark.parametrize('fault', ['copper', 'pad', 'silk', 'source_visible'])
def test_saved_child_must_still_match_the_entire_original_reconstruction(tmp_path, fault):
    source, grade, uid = fixture(tmp_path)
    proposal = search.plan(source, grade=grade, board_hint='explicit_mask_search_fixture',
        maximum_components=1)
    board, _ = search.construct(source, proposal)
    fp = next(fp for fp in board.GetFootprints() if force._uid(fp)==uid)
    if fault == 'copper':
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(pcbnew.VECTOR2I_MM(18, 18)); item.SetEnd(pcbnew.VECTOR2I_MM(19, 18))
        item.SetWidth(200000); board.Add(item)
    elif fault == 'pad':
        next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'silk':
        next(t for t in fp.GraphicalItems() if t.GetClass()=='PCB_TEXT'
            and t.GetLayer()==proposal['target_layer_id']).SetText('WRONG')
    else:
        fp.Reference().SetVisible(True)
    child = force._copy_family(source, tmp_path/'candidate')
    field._save_field_snapshot(board, child)
    assert not search.receive(source, child, proposal)['ok']

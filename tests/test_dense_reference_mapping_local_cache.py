"""Invocation-local map reuse must retain both independent native comparisons."""
import copy
import json
from pathlib import Path
import uuid

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest
import cec_dense_reference_mapping as op
import cec_mask_search_reference_mapping as masked
import cec_field_coupling as field
import cec_force_current as force
from test_dense_reference_mapping import fixture, saved as attached_saved
from test_mask_search_reference_mapping import refresh_grade


def rigid_saved(tmp_path, **kwargs):
    source, grade, uid = fixture(tmp_path, **kwargs)
    proposal = op.plan(source, grade=grade, board_hint='synthetic_local_map_reuse',
        maximum_components=1, reverse_ownership='rigid_root_group_per_component')
    candidate = force._copy_family(source, tmp_path/'rigid-child')
    manifest = op.write_private(source, candidate, json.loads(json.dumps(proposal)))
    return source, candidate, proposal, uid, manifest


def mutation(board, fault):
    fp = next(iter(board.GetFootprints()))
    if fault == 'copper':
        track = pcbnew.PCB_TRACK(board); track.SetLayer(pcbnew.F_Cu)
        track.SetStart(pcbnew.VECTOR2I_MM(18, 18)); track.SetEnd(pcbnew.VECTOR2I_MM(19, 18))
        track.SetWidth(200000); board.Add(track)
    elif fault == 'pad':
        next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'guide':
        next(g for g in board.GetDrawings() if g.GetClass() == 'PCB_SHAPE').Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'group':
        next(iter(board.Groups())).SetName('changed-rigid-owner')
    elif fault == 'text':
        next(g for g in board.GetDrawings() if g.GetClass() == 'PCB_TEXT').SetText('different-owner')
    elif fault == 'metadata':
        fp.SetValue('different-part-metadata')
    else:
        raise AssertionError(fault)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_expected_tree_is_invocation_local_and_both_native_child_saves_remain(tmp_path, monkeypatch, quarter, back):
    source, candidate, proposal, _, _ = rigid_saved(tmp_path, quarter=quarter, back=back)
    original_nodes = op.additive._nodes; original_plan = op.plan
    original_save = field._save_field_snapshot; original_freeze = op.syntax._freeze
    parsing = []; saves = []; planning = [False]; frozen_roots = []; depth = [0]
    def nodes(path):
        parsing.append((str(path), planning[0]))
        return original_nodes(path)
    def plan(*args, **kwargs):
        planning[0] = True
        try: return original_plan(*args, **kwargs)
        finally: planning[0] = False
    def save(board, path):
        saves.append(Path(path).name)
        return original_save(board, path)
    def freeze(tree):
        if depth[0] == 0 and tree and tree[0] == 'kicad_pcb': frozen_roots.append(tree)
        depth[0] += 1
        try: return original_freeze(tree)
        finally: depth[0] -= 1
    monkeypatch.setattr(op.additive, '_nodes', nodes)
    monkeypatch.setattr(op, 'plan', plan)
    monkeypatch.setattr(field, '_save_field_snapshot', save)
    monkeypatch.setattr(op.syntax, '_freeze', freeze)
    before = [p.read_bytes() for p in (source, candidate)]
    result = op.receive(source, candidate, proposal)
    assert result['ok'] and result['complete'], result
    assert [p.read_bytes() for p in (source, candidate)] == before
    assert saves == ['board.kicad_pcb', 'normalized-candidate.kicad_pcb', 'second-save.kicad_pcb']
    source_calls = [inside for path, inside in parsing if Path(path) == source]
    # Full fresh planning retains its own raw ownership parse. This same
    # invocation's independently unchanged Source inventory also supplies
    # construction collision checks; no second Source parse or verdict cache.
    assert source_calls == [True]
    native_paths = [Path(path).name for path, _ in parsing if Path(path).parent != source.parent]
    assert native_paths == ['board.kicad_pcb', 'normalized-candidate.kicad_pcb', 'second-save.kicad_pcb']
    assert len(frozen_roots) == 3  # expected once; independent first/second child once each


@pytest.mark.parametrize('save_name,reason', [
    ('normalized-candidate.kicad_pcb', 'reference_mapping_changed_unowned_board_evidence'),
    ('second-save.kicad_pcb', 'reference_mapping_is_not_stable_under_a_second_native_save'),
])
@pytest.mark.parametrize('fault', ['copper', 'pad', 'guide', 'group', 'text', 'metadata'])
def test_either_independent_native_projection_mutation_still_refuses(tmp_path, monkeypatch, save_name, reason, fault):
    source, candidate, proposal, _, _ = rigid_saved(tmp_path)
    original_save = field._save_field_snapshot; observed = []
    def save(board, path):
        observed.append(Path(path).name)
        if Path(path).name == save_name: mutation(board, fault)
        return original_save(board, path)
    monkeypatch.setattr(field, '_save_field_snapshot', save)
    before = [p.read_bytes() for p in (source, candidate)]
    result = op.receive(source, candidate, proposal)
    assert not result['ok'] and reason in result['errors'][0], result
    assert observed.count(save_name) == 1
    assert ('second-save.kicad_pcb' in observed) is (save_name == 'second-save.kicad_pcb')
    assert [p.read_bytes() for p in (source, candidate)] == before


@pytest.mark.parametrize('rigid', [False, True])
def test_no_cross_invocation_expected_or_source_inventory_cache(tmp_path, rigid):
    for index in range(2):
        root = tmp_path/str(index); root.mkdir()
        source, candidate, proposal, _, _ = (rigid_saved(root) if rigid else attached_saved(root))
        result = op.receive(source, candidate, proposal)
        assert result['ok'] and result['complete'], result
        native = pcbnew.LoadBoard(str(candidate)); fp = next(iter(native.GetFootprints()))
        fp.SetValue('different-on-later-invocation'); field._save_field_snapshot(native, candidate)
        assert not op.receive(source, candidate, proposal)['ok']


@pytest.mark.parametrize('kind', ['source_root_collision', 'fresh_generated_collision'])
def test_complete_source_root_and_fresh_generated_identity_collisions_refuse(tmp_path, monkeypatch, kind):
    source, grade, uid = fixture(tmp_path)
    proposal = op.plan(source, grade=grade, board_hint='synthetic_local_map_reuse',
        maximum_components=1, reverse_ownership='rigid_root_group_per_component')
    real = uuid.uuid5
    repeated = uuid.UUID('2790a280-46f4-45be-8196-599efb0e1099')
    def identifier(namespace, name):
        if kind == 'fresh_generated_collision': return repeated
        if ':record-' in name: return uuid.UUID(uid)
        return real(namespace, name)
    monkeypatch.setattr(op.uuid, 'uuid5', identifier)
    before = source.read_bytes()
    with pytest.raises(ValueError, match='legend_generated_uuid_collision'):
        op.construct(source, proposal)
    assert source.read_bytes() == before


def test_source_uuid_collision_inventory_is_once_for_multiple_generated_root_groups(tmp_path, monkeypatch):
    source, grade, uid = fixture(tmp_path, roomy=True)
    board = pcbnew.LoadBoard(str(source)); first = next(iter(board.GetFootprints()))
    body = op.court(first); x0, y0, x1, y1 = body.bounds
    library = Path(__file__).resolve().parents[1]/'lib/vendor/Package_SO.pretty'
    second = pcbnew.FootprintLoad(str(library), 'SOIC-8_3.9x4.9mm_P1.27mm'); board.Add(second)
    second.SetReference('OTHER78'); second.SetPosition(pcbnew.VECTOR2I_MM(20, 20+(y1-y0)+1.))
    second.Value().SetLayer(pcbnew.F_Fab); second.Reference().SetLayer(pcbnew.F_SilkS)
    second.Reference().SetTextSize(pcbnew.VECTOR2I_MM(1, 1)); second.Reference().SetTextThickness(150000)
    # An actually unknown F-body conservatively forbids front charts. It is
    # not an invented courtyard, and opposite-face projection remains typed.
    unknown = pcbnew.FOOTPRINT(board); unknown.SetReference('UNKNOWN'); board.Add(unknown)
    unknown.SetPosition(pcbnew.VECTOR2I_MM(45, 45))
    for item in unknown.GetFields(): item.SetVisible(False)
    field._save_field_snapshot(board, source)
    refresh_grade(source, grade)
    data = json.loads(grade.read_text()); producer = data['boards']['candidate']['native_producer']
    report = Path(producer['report']); payload = json.loads(report.read_text())
    payload['violations'].append(dict(type='silk_overlap', severity='warning',
        items=[dict(uuid=force._uid(second.Reference()))]))
    force._write(report, payload); producer['report_sha256'] = force._hash(report); force._write(grade, data)
    proposal = op.plan(source, grade=grade, board_hint='synthetic_local_map_reuse', maximum_components=2,
        reverse_ownership='rigid_root_group_per_component')
    assert len(proposal['records']) == 2 and proposal['mode'] == 'opposite_face_projected_courtyard'
    original_nodes = op.additive._nodes; real_plan = op.plan; inside = [False]; parses = []
    def nodes(path):
        if Path(path) == source: parses.append(inside[0])
        return original_nodes(path)
    def plan(*args, **kwargs):
        inside[0] = True
        try: return real_plan(*args, **kwargs)
        finally: inside[0] = False
    monkeypatch.setattr(op.additive, '_nodes', nodes); monkeypatch.setattr(op, 'plan', plan)
    native, manifest = op.construct(source, proposal)
    assert len(manifest['added_reverse_group_uuids']) == 2
    assert len(list(native.Groups())) == 2 and parses == [True]


@pytest.mark.parametrize('fault', ['literal', 'sidecar', 'source', 'grade'])
def test_local_expected_reuse_never_bypasses_existing_binding_gates(tmp_path, fault):
    source, candidate, proposal, _, _ = rigid_saved(tmp_path)
    if fault == 'literal':
        candidate.write_text(candidate.read_text().replace('(general', '(opaque_future 7)\n(general', 1))
    elif fault == 'sidecar': force._write(candidate.with_suffix('.kicad_pro'), {'different': True})
    elif fault == 'source': source.write_text(source.read_text()+'\n; Source changed\n')
    else:
        path = Path(proposal['grade']); data = json.loads(path.read_text()); data['code_identity'] = {}
        force._write(path, data)
    assert not op.receive(source, candidate, proposal)['ok']


def test_mask_preflight_is_still_independent_after_cached_expected_comparisons(tmp_path, monkeypatch):
    source, grade, _ = fixture(tmp_path)
    proposal = masked.plan(source, grade=grade, board_hint='synthetic_local_map_reuse', maximum_components=1,
        reverse_ownership='rigid_root_group_per_component')
    candidate = force._copy_family(source, tmp_path/'masked-child'); masked.write_private(source, candidate, proposal)
    observed = []
    def refuse(*args):
        observed.append(True)
        return dict(ok=False, complete=False, errors=['independent-mask-refused'])
    monkeypatch.setattr(masked.masks, 'observe', refuse)
    result = masked.receive(source, candidate, proposal)
    assert observed == [True] and not result['ok'] and result['errors'] == ['independent-mask-refused']

"""A titled, led, rigid rear callout is not a phantom component placement."""
import copy
import json
import pcbnew
import pytest
import cec_dense_reference_mapping as dense
import cec_mask_search_reference_mapping as maps
import cec_reference_map_material_identity as identity
import cec_field_coupling as field
import cec_force_current as force
from test_dense_reference_mapping import fixture
from test_interrupted_reference_guides import opening
from shapely.geometry import box


def case(tmp_path, *, back=False, quarter=0):
    source, grade, owner = fixture(tmp_path, roomy=True, back=back, quarter=quarter)
    b = pcbnew.LoadBoard(str(source)); fp = next(iter(b.GetFootprints()))
    source_face = pcbnew.B_SilkS if back else pcbnew.F_SilkS
    target = pcbnew.F_SilkS if back else pcbnew.B_SilkS
    opening(b, box(0, 0, 60, 60), source_face)
    # Actual unrelated Source ink blocks a projected corner, but not the
    # free neighboring back-side callout area. It may NOT be clipped away.
    x0, y0, x1, y1 = dense.court(fp).bounds
    line = pcbnew.PCB_SHAPE(b); line.SetShape(pcbnew.SHAPE_T_SEGMENT)
    line.SetStart(pcbnew.VECTOR2I_MM(x1, y0)); line.SetEnd(pcbnew.VECTOR2I_MM(x1, y0 + .3))
    line.SetLayer(target); line.SetWidth(150000); b.Add(line)
    field._save_field_snapshot(b, source)
    j = json.loads(grade.read_text()); row = j['boards']['candidate']
    row['sha256'] = force._hash(source)
    row['native_producer']['source_files'] = {str(source): force._hash(source)}
    force._write(grade, j)
    options = dict(grade=grade, board_hint='arbitrary-rear-chart', owner_uuid_scope=[owner],
        maximum_components=1, reverse_ownership='rigid_root_group_per_component',
        via_ink_policy='native_mask_and_bore')
    with pytest.raises(ValueError, match='no_readable_clear_opposite_face'):
        maps.plan(source, **options)
    q = maps.plan(source, **options, opposite_face_chart=True)
    assert q['mode'] == 'nearby_opposite_face_mapping_chart'
    assert q['opposite_face_chart'] is True and any(r['fits'] for r in q['opposite_face_chart_trials'])
    child = force._copy_family(source, tmp_path/'private')
    maps.write_private(source, child, q)
    qpath = tmp_path/'proposal.json'; force._write(qpath, q)
    return source, child, q, qpath, owner


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('quarter', range(4))
def test_readable_titled_chart_leader_and_source_members_receive_on_both_faces(tmp_path, back, quarter):
    source, child, q, qpath, owner = case(tmp_path, back=back, quarter=quarter)
    before = source.read_bytes(); r = maps.receive(source, child, q)
    assert r['ok'] and r['complete'], r
    material = identity.receive(source, child, qpath, timeout_s=10.)
    assert material['ok'] and material['complete'] and material['same_material'], material
    assert material['mutation_authority'] is False and not material['full_kelvin_qualification']
    a, b = [pcbnew.LoadBoard(str(p)) for p in (source, child)]
    assert field._field_snapshot_inventory(a) == field._field_snapshot_inventory(b)
    texts = [g for g in b.GetDrawings() if g.GetClass() == 'PCB_TEXT']
    assert {t.GetText() for t in texts} == {'REF MAP', 'Z77'}
    assert all(t.IsMirrored() is (not back) and t.GetTextSize().y >= 1000000
        and t.GetTextThickness() >= 150000 for t in texts)
    groups = list(b.Groups()); assert len(groups) == 1 and groups[0].IsLocked()
    members = list(groups[0].GetItems())
    assert any(g.GetClass() == 'FOOTPRINT' and force._uid(g) == owner for g in members)
    assert not next(iter(b.GetFootprints())).IsLocked()
    assert r['manifest']['added_group_uuid'] and not r['manifest']['added_reverse_group_uuids']
    assert source.read_bytes() == before


@pytest.mark.parametrize('fault', ['flag', 'mode', 'text', 'mirror', 'position', 'trial', 'stroke'])
def test_rear_chart_geometry_cannot_be_forged_or_relabelled_from_historical_success(tmp_path, fault):
    source, child, q, _, _ = case(tmp_path)
    bad = copy.deepcopy(q)
    if fault == 'flag': del bad['opposite_face_chart']
    elif fault == 'mode': bad['mode'] = 'opposite_face_projected_courtyard'
    elif fault == 'text': bad['records'][0]['reference'] = 'WRONG'
    elif fault == 'mirror': bad['records'][0]['text_mirrored'] = False
    elif fault == 'position': bad['records'][0]['text_xy_mm'][0] += .000001
    elif fault == 'trial': bad['opposite_face_chart_trials'] = []
    else: bad['binding']['factory_legend']['stroke'] = .01
    assert not maps.receive(source, child, bad)['ok']


@pytest.mark.parametrize('value', [None, 0, 1, 'true', [], {}])
def test_rear_chart_requires_an_explicit_boolean_not_a_waiver(tmp_path, value):
    source, grade, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match='explicit_opposite_face_reference_chart'):
        maps.plan(source, grade=grade, board_hint='arbitrary', opposite_face_chart=value)


@pytest.mark.parametrize('fault', ['title', 'group', 'leader', 'pad', 'fab', 'source-ink'])
def test_saved_native_receiver_preserves_title_association_all_source_ink_and_copper(tmp_path, fault):
    source, child, q, qpath, owner = case(tmp_path)
    b = pcbnew.LoadBoard(str(child)); fp = next(iter(b.GetFootprints()))
    if fault == 'title': next(g for g in b.GetDrawings() if g.GetClass() == 'PCB_TEXT' and g.GetText() == 'REF MAP').SetText('')
    elif fault == 'group': next(iter(b.Groups())).RemoveItem(fp)
    elif fault == 'leader':
        ids = rids = set(maps.receive(source, child, q)['manifest']['added_root_annotation_uuids'])
        next(g for g in b.GetDrawings() if force._uid(g) in ids and g.GetClass() == 'PCB_SHAPE').Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'pad': next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'fab': next(g for g in fp.GraphicalItems() if g.GetLayer() == pcbnew.F_Fab).Move(pcbnew.VECTOR2I(1, 0))
    else:
        added = set(maps.receive(source, child, q)['manifest']['added_root_annotation_uuids'])
        next(g for g in b.GetDrawings() if g.GetClass() == 'PCB_SHAPE' and force._uid(g) not in added).Move(pcbnew.VECTOR2I(1, 0))
    field._save_field_snapshot(b, child)
    assert not maps.receive(source, child, q)['ok']
    assert not identity.receive(source, child, qpath)['ok']

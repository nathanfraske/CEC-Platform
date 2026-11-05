"""Only new, nonfunctional projected guide strokes may yield to openings.

Synthetic discovery grades are not native hardware qualification. Actual
saved reconstruction and literal/native material receiving remain real.
"""
import copy
import json

import pcbnew
import pytest
from shapely import affinity
from shapely.geometry import GeometryCollection, LineString, Point, box
from shapely.ops import unary_union
import cec_dense_reference_mapping as dense
import cec_mask_search_reference_mapping as maps
import cec_field_coupling as field
import cec_force_current as force
import cec_reference_map_material_identity as identity
from test_dense_reference_mapping import fixture


def formatted(item):
    writer = pcbnew.PCB_IO_KICAD_SEXPR(); writer.Format(item)
    return writer.GetStringOutput(True)


def opening(board, shape, face):
    # Native mask artwork is a real aperture, not invented copper or a
    # caller-provided obstacle list used as annotation permission.
    assert shape.geom_type == 'Polygon'
    points = list(shape.exterior.coords)
    assert len(points) == 5
    item = pcbnew.PCB_SHAPE(board)
    item.SetShape(pcbnew.SHAPE_T_RECT)
    item.SetStart(pcbnew.VECTOR2I_MM(*points[0]))
    item.SetEnd(pcbnew.VECTOR2I_MM(*points[2]))
    item.SetFillMode(pcbnew.FILL_T_FILLED_SHAPE)
    item.SetWidth(0)
    item.SetLayer(pcbnew.F_Mask if face == pcbnew.F_SilkS else pcbnew.B_Mask)
    board.Add(item)
    return item


@pytest.mark.parametrize('face', [pcbnew.F_SilkS, pcbnew.B_SilkS])
@pytest.mark.parametrize('quarter', range(4))
def test_exact_opening_difference_is_native_clear_without_mutating_source(face, quarter):
    board = pcbnew.BOARD()
    shape = affinity.rotate(box(10, 10, 14, 13), quarter * 90, origin=(12, 11.5))
    aperture = affinity.rotate(box(13.5, 9.5, 14.5, 10.5), quarter * 90, origin=(12, 11.5))
    item = opening(board, aperture, face)
    before = field._field_snapshot_inventory(board)
    native_before = formatted(item)
    f = dict(height=1., stroke=.15, clearance=.15, edge=.2)
    segments, witness = dense._interrupted_body_guides(board, shape, face, f)
    assert 2 <= len(segments) <= 24
    retained = unary_union([LineString(s) for s in segments])
    assert retained.difference(shape.boundary.buffer(.000002)).is_empty
    assert retained.intersection(aperture.buffer(.15 + .075 + .002)).is_empty
    assert 0 < witness['removed_length_mm'] < shape.length
    assert witness['retained_length_mm'] + witness['removed_length_mm'] == pytest.approx(shape.length)
    assert force._uid(item) in witness['native_opening_uuids']
    assert witness['only_new_nonfunctional_body_guide_strokes'] is True
    assert witness['complete_fab_courtyard_and_functional_marks_unchanged'] is True
    assert field._field_snapshot_inventory(board) == before and formatted(item) == native_before


def test_no_native_opening_cannot_grant_a_shortened_or_arbitrary_guide():
    board = pcbnew.BOARD()
    shape = box(10, 10, 14, 13)
    f = dict(height=1., stroke=.15, clearance=.15, edge=.2)
    segments, witness = dense._interrupted_body_guides(board, shape, pcbnew.B_SilkS, f)
    assert segments == [[list(a), list(z)] for a, z in zip(shape.exterior.coords, list(shape.exterior.coords)[1:])]
    assert witness['removed_length_mm'] == 0 and not witness['native_opening_uuids']
    fp = pcbnew.FOOTPRINT(board); fp.SetReference('ARBITRARY_7'); board.Add(fp)
    # An ordinary silkscreen conflict must not become clipping authority.
    blocked = box(13.5, 9.5, 14.5, 10.5)
    with pytest.raises(ValueError, match='no_readable_clear_projected'):
        dense.reverse_component(board, (fp, shape), pcbnew.B_SilkS, f, blocked,
            box(0, 0, 30, 30), GeometryCollection(), interrupt_projected_body_guides=True)


def test_nearest_point_envelope_contact_is_not_a_zero_length_native_leader(monkeypatch):
    board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);fp.SetReference('Z91');board.Add(fp)
    native_nearest=dense.nearest_points;calls=[]
    def nearest(a,z):
        calls.append(True)
        return (Point(10,10),Point(10,10))if len(calls)==1 else native_nearest(a,z)
    monkeypatch.setattr(dense,'nearest_points',nearest)
    _,_,rows=dense.reverse_component(board,(fp,box(10,10,11.05,10.54)),pcbnew.B_SilkS,
        dict(height=1.,stroke=.15,clearance=.15,edge=.2),GeometryCollection(),
        box(0,0,30,30),GeometryCollection(),peripheral_seats=True,positive_leaders_only=True)
    assert len(calls)>1 and rows[0]['leader_xy_mm']
    a,z=rows[0]['leader_xy_mm']
    assert [round(v*1e6)for v in a]!=[round(v*1e6)for v in z]


@pytest.mark.parametrize('face', [pcbnew.F_SilkS, pcbnew.B_SilkS])
def test_actual_drill_is_reserved_even_without_an_exposed_copper_land(face):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    fp = pcbnew.FOOTPRINT(board); board.Add(fp)
    pad = pcbnew.PAD(fp); fp.Add(pad)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetPosition(pcbnew.VECTOR2I_MM(14, 10))
    pad.SetSize(pcbnew.VECTOR2I_MM(.5, .5)); pad.SetDrillSize(pcbnew.VECTOR2I_MM(.5, .5))
    pad.SetLayerSet(pcbnew.LSET())
    shape = box(10, 10, 14, 13)
    segments, witness = dense._interrupted_body_guides(board, shape, face,
        dict(height=1., stroke=.15, clearance=.15, edge=.2))
    assert witness['removed_length_mm'] > 0
    assert force._uid(pad) + ':hole' in witness['native_opening_uuids']
    assert not unary_union([LineString(s) for s in segments]).intersects(
        Point(14, 10).buffer(.25 + .15 + .075 + .002))


@pytest.mark.parametrize('covered', [box(9, 9, 15, 14), box(9, 9, 15, 12.9)])
def test_no_usable_association_is_not_permission_to_erase_the_whole_guide(covered):
    board = pcbnew.BOARD(); shape = box(10, 10, 14, 13)
    opening(board, covered, pcbnew.B_SilkS)
    with pytest.raises(ValueError, match='usable_interrupted_body_guide'):
        dense._interrupted_body_guides(board, shape, pcbnew.B_SilkS,
            dict(height=1., stroke=.15, clearance=.15, edge=.2))


def saved_case(tmp_path, *, back=False, quarter=0):
    source, grade, owner = fixture(tmp_path, back=back, quarter=quarter)
    board = pcbnew.LoadBoard(str(source)); fp = next(iter(board.GetFootprints()))
    target = pcbnew.F_SilkS if back else pcbnew.B_SilkS
    actual = dense.court(fp); x0, y0, x1, y1 = actual.bounds
    opening(board, box(x1 - .5, y0 - .5, x1 + .5, y0 + .5), target)
    field._save_field_snapshot(board, source)
    data = json.loads(grade.read_text()); entry = data['boards']['candidate']
    entry['sha256'] = force._hash(source)
    entry['native_producer']['source_files'] = {str(source): force._hash(source)}
    force._write(grade, data)
    options = dict(grade=grade, board_hint='arbitrary-reference-board', maximum_components=1,
        owner_uuid_scope=[owner], reverse_ownership='rigid_root_group_per_component',
        via_ink_policy='native_mask_and_bore', peripheral_reverse_seats=True)
    with pytest.raises(ValueError, match='no_readable_clear_opposite_face'):
        maps.plan(source, **options)
    proposal = maps.plan(source, **options, interrupt_projected_body_guides=True)
    assert proposal['interrupt_projected_body_guides'] is True
    assert proposal['mode'] == 'opposite_face_projected_courtyard'
    assert proposal['records'][0]['outline_style'] == 'native_opening_interrupted_body_guide'
    child = force._copy_family(source, tmp_path/'private')
    maps.write_private(source, child, proposal)
    qpath = tmp_path/'proposal.json'; force._write(qpath, proposal)
    return source, child, proposal, qpath, owner


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('quarter', range(4))
def test_saved_front_back_cardinal_map_retains_real_text_fab_marks_and_all_material(tmp_path, back, quarter):
    source, child, q, qpath, owner = saved_case(tmp_path, back=back, quarter=quarter)
    before = source.read_bytes()
    received = maps.receive(source, child, q)
    assert received['ok'] and received['complete'], received
    material = identity.receive(source, child, qpath, timeout_s=10.)
    assert material['ok'] and material['complete'] and material['same_material'], material
    assert material['mutation_authority'] is False and not material['full_kelvin_qualification']
    a, b = [pcbnew.LoadBoard(str(p)) for p in (source, child)]
    assert field._field_snapshot_inventory(a) == field._field_snapshot_inventory(b)
    old = next(f for f in a.GetFootprints() if force._uid(f) == owner)
    new = next(f for f in b.GetFootprints() if force._uid(f) == owner)
    assert [formatted(g) for g in old.GraphicalItems()] == [formatted(g) for g in new.GraphicalItems()]
    texts = [g for g in b.GetDrawings() if g.GetClass() == 'PCB_TEXT']
    assert len(texts) == 1 and texts[0].GetText() == old.GetReference()
    assert texts[0].IsMirrored() is (not back)
    assert texts[0].GetTextSize().y >= 1000000 and texts[0].GetTextThickness() >= 150000
    assert source.read_bytes() == before


@pytest.mark.parametrize('fault', ['removed-flag', 'segment', 'reference', 'mirror', 'factory-floor', 'witness'])
def test_saved_plan_cannot_authorize_unproved_guide_deletion_or_text_changes(tmp_path, fault):
    source, child, q, _, _ = saved_case(tmp_path)
    bad = copy.deepcopy(q)
    if fault == 'removed-flag': del bad['interrupt_projected_body_guides']
    elif fault == 'segment': bad['records'][0]['outline_segments_xy_mm'].pop()
    elif fault == 'reference': bad['records'][0]['reference'] = 'HIDDEN_ASSOCIATION'
    elif fault == 'mirror': bad['records'][0]['text_mirrored'] = False
    elif fault == 'factory-floor': bad['binding']['factory_legend']['clearance'] = 0
    else: bad['records'][0]['body_guide_interruption']['native_opening_uuids'] = []
    result = maps.receive(source, child, bad)
    assert not result['ok'] and not result['complete'] and result['errors']


@pytest.mark.parametrize('value', [None, 0, 1, 'true', [], {}])
def test_interruption_requires_exact_explicit_boolean_not_a_truthy_waiver(tmp_path, value):
    source, grade, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match='explicit_projected_body_guide_interruption'):
        maps.plan(source, grade=grade, board_hint='arbitrary', interrupt_projected_body_guides=value)


@pytest.mark.parametrize('fault', ['fab', 'courtyard', 'functional-mark', 'mask', 'glyph', 'copper'])
def test_complete_saved_receiver_still_rejects_source_artwork_and_electrical_mutation(tmp_path, fault):
    source, child, q, _, _ = saved_case(tmp_path)
    board = pcbnew.LoadBoard(str(child)); fp = next(iter(board.GetFootprints()))
    if fault in ('fab', 'courtyard', 'functional-mark'):
        layer = {'fab': pcbnew.F_Fab, 'courtyard': pcbnew.F_CrtYd,
            'functional-mark': pcbnew.F_SilkS}[fault]
        mark = next(g for g in fp.GraphicalItems() if g.GetLayer() == layer and g.GetClass() == 'PCB_SHAPE')
        mark.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'mask': next(g for g in board.GetDrawings() if g.GetLayer() == pcbnew.B_Mask).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'glyph': next(g for g in board.GetDrawings() if g.GetClass() == 'PCB_TEXT').SetText('WRONG')
    else: next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(.1, .1))
    field._save_field_snapshot(board, child)
    result = maps.receive(source, child, q)
    assert not result['ok'] and result['errors']

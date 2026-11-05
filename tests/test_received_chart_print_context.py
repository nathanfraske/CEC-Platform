"""A complete saved rear chart can compose with printing, never waive it."""
import copy
import shutil

import pcbnew
import pytest
from shapely.geometry import box

import cec_field_coupling as field
import cec_force_current as force
import cec_mask_search_reference_mapping as maps
import cec_nonpolar_print_context as printing
from test_interrupted_reference_guides import opening
from test_nonpolar_print_context import fixture


def case(tmp_path, monkeypatch, *, back=False, turn=0):
    source, table, ids, _ = fixture(tmp_path, monkeypatch, turn=turn, back=back,
                                  selected_name='R_0402_1005Metric')
    board = pcbnew.LoadBoard(str(source))
    props=board.GetProperties()
    props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal'
    board.SetProperties(props)
    fp = next(f for f in board.GetFootprints() if force._uid(f) == ids[0])
    fp.SetReference('Z91')
    fp.Reference().SetTextSize(pcbnew.VECTOR2I_MM(1, 1))
    fp.Reference().SetTextThickness(150000)
    for a, z in zip([(0, 0), (60, 0), (60, 40), (0, 40)],
                    [(60, 0), (60, 40), (0, 40), (0, 0)]):
        line = pcbnew.PCB_SHAPE(board)
        line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetLayer(pcbnew.Edge_Cuts)
        line.SetStart(pcbnew.VECTOR2I_MM(*a))
        line.SetEnd(pcbnew.VECTOR2I_MM(*z))
        line.SetWidth(50000)
        board.Add(line)
    opening(board, box(0, 0, 60, 40), pcbnew.B_SilkS if back else pcbnew.F_SilkS)
    # An actual unrelated Source stroke defeats the ordinary rear projection;
    # only the public titled/led rear-chart fallback may find a different seat.
    x0, y0, x1, _ = maps.court(fp).bounds
    line = pcbnew.PCB_SHAPE(board)
    line.SetShape(pcbnew.SHAPE_T_SEGMENT)
    line.SetLayer(pcbnew.F_SilkS if back else pcbnew.B_SilkS)
    line.SetStart(pcbnew.VECTOR2I_MM(x1, y0))
    line.SetEnd(pcbnew.VECTOR2I_MM(x1, y0 + .3))
    line.SetWidth(150000)
    board.Add(line)
    field._save_field_snapshot(board, source)
    report = tmp_path / 'native.json'
    force._write(report, dict(violations=[dict(type='silk_overlap', severity='warning',
        items=[dict(uuid=force._uid(fp.Reference()))])], unconnected_items=[]))
    grade = tmp_path / 'grade.json'
    force._write(grade, dict(code_identity=force._code_identity(), boards=dict(source=dict(
        sha256=force._hash(source), native_producer=dict(ok=True, complete=True,
            native_inventory=dict(potentially_truncated=False), report=str(report),
            report_sha256=force._hash(report), source_files={str(source):force._hash(source)})))))
    q = maps.plan(source, grade=grade, board_hint='renamed-chart', maximum_components=1,
        owner_uuid_scope=[ids[0]], reverse_ownership='rigid_root_group_per_component',
        via_ink_policy='native_mask_and_bore', opposite_face_chart=True)
    assert q['mode'] == 'nearby_opposite_face_mapping_chart'
    qpath = tmp_path / 'map.json'
    force._write(qpath, q)
    shutil.copytree(source.parent, tmp_path / 'mapped')
    mapped = tmp_path / 'mapped' / source.name
    maps.write_private(source, mapped, q)
    assert maps.receive(source, mapped, q)['ok']
    declaration = dict(source=dict(path=str(source), sha256=force._hash(source)),
                       proposal=dict(path=str(qpath), sha256=force._hash(qpath)))
    options = dict(library_table=table, footprint_ids=['cec-Resistor_SMD:R_0402_1005Metric'],
                   expected_instance_uuids=ids, board_hint='renamed-chart')
    return source, mapped, q, qpath, declaration, options


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('turn', [0, 90, 180, 270])
def test_complete_native_rear_chart_survives_fresh_saved_printing(tmp_path, monkeypatch, back, turn):
    ancestor, mapped, _, _, declaration, options = case(tmp_path, monkeypatch, back=back, turn=turn)
    before = {p:p.read_bytes() for p in (ancestor, mapped)}
    with pytest.raises(ValueError):
        printing.plan(mapped, **options)
    q = printing.plan(mapped, **options, reference_mapping_transition=declaration)
    proofs = [r['source_reference_map'] for r in q['records'] if r.get('source_reference_map')]
    assert len(proofs) == 1
    assert proofs[0]['reference_association_kind'] == 'fresh_received_rigid_rear_chart'
    assert proofs[0]['closed_assembly_body_authority'] is False
    assert proofs[0]['shared_chart_is_not_component_pose_or_closed_body_authority'] is True
    artifact = printing.construct_private(mapped, q, tmp_path / 'printed')
    received = printing.receive(mapped, artifact['candidate'], q)
    assert received['ok'] and received['complete'], received
    assert all(p.read_bytes() == value for p, value in before.items())


@pytest.mark.parametrize('fault', ['title', 'leader', 'group-owner', 'group-lock', 'pad',
                                  'fab', 'source-ink', 'mirror', 'unknown-mode', 'no-flag'])
def test_rear_chart_composition_independently_refuses_real_or_declared_mutation(tmp_path, monkeypatch, fault):
    _, mapped, map_q, qpath, declaration, options = case(tmp_path, monkeypatch)
    board = pcbnew.LoadBoard(str(mapped))
    fp = next(f for f in board.GetFootprints() if f.GetReference() == 'Z91')
    if fault == 'title':
        next(g for g in board.GetDrawings() if g.GetClass() == 'PCB_TEXT'
             and g.GetText() == 'REF MAP').SetText('wrong')
    elif fault == 'leader':
        next(g for g in next(iter(board.Groups())).GetItems()
             if g.GetClass() == 'PCB_SHAPE').Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'group-owner':
        next(iter(board.Groups())).RemoveItem(fp)
    elif fault == 'group-lock':
        next(iter(board.Groups())).SetLocked(False)
    elif fault == 'pad':
        next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'fab':
        next(g for g in fp.GraphicalItems() if g.GetLayer() == pcbnew.F_Fab).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'source-ink':
        grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
        next(g for g in board.GetDrawings() if g.GetClass() == 'PCB_SHAPE'
             and force._uid(g)not in grouped and g.GetLayer()in(pcbnew.F_SilkS,pcbnew.B_SilkS)).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'mirror':
        text=next(g for g in board.GetDrawings() if g.GetClass() == 'PCB_TEXT'
                  and g.GetText() == 'Z91')
        text.SetMirrored(not text.IsMirrored())
    else:
        bad=copy.deepcopy(map_q)
        if fault == 'unknown-mode':bad['mode']='accepted-looking-future-mode'
        else:bad.pop('opposite_face_chart')
        force._write(qpath,bad)
        declaration['proposal']['sha256']=force._hash(qpath)
    if fault not in ('unknown-mode','no-flag'):
        field._save_field_snapshot(board,mapped)
    with pytest.raises(ValueError):
        printing.plan(mapped, **options, reference_mapping_transition=declaration)

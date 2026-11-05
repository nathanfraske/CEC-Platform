"""Enrolled model boundaries, not fabricated physical-routing success.

Synthetic literal packets exercise the independent saved scope subproof.
Public enrollment still requires the actual selected manufacturer's six pins
and a fresh actual hierarchy; the cross-board replay is recorded separately.
"""
import copy
import json
from pathlib import Path
import time
import uuid

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest

import cec_component_internal_connections as op
import cec_component_jumper_metadata as metadata
import cec_force_current as force
import cec_fr as fr
from test_passive_protector_contract import protector_fixture


def fixture(tmp_path, turn=0, face=pcbnew.F_Cu):
    board, fp, _, _ = protector_fixture(turn, False, face)
    group = pcbnew.PCB_GROUP(board)
    board.Add(group)
    group.SetName('retained component reference map')
    group.AddItem(fp)
    source = tmp_path / 'SOURCE' / 'board.kicad_pcb'
    source.parent.mkdir()
    pcbnew.SaveBoard(str(source), board)
    source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    child = force._copy_family(source, tmp_path / 'CHILD')
    contract = dict(groups=(('1', '6'), ('3', '4')),
                    pin_numbers=tuple(str(i) for i in range(1, 7)),
                    pad_nets={p.GetNumber(): str(p.GetNetname()) for p in fp.Pads()})
    owner = dict(owner_ref=fp.GetReference(), owner_uuid=force._uid(fp), exported_contract=contract)
    metadata.apply_saved(child, {fp.GetReference(): contract})
    return source, child, owner


@pytest.mark.parametrize('turn', range(4))
@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_exact_literal_metadata_scope_preserves_every_physical_domain(tmp_path, turn, face):
    source, child, owner = fixture(tmp_path, turn, face)
    before = source.read_bytes()
    scope = op.literal_scope(source, child, [owner])
    assert scope['exact_saved_literal_delta']
    assert scope['changed_refs'] == [owner['owner_ref']]
    assert scope['physical_copper_and_contact_query_inputs_identical']
    assert not scope['PCB_copper_or_current_capacity_inferred']
    assert source.read_bytes() == before
    assert len(pcbnew.LoadBoard(str(child)).FindFootprintByReference(owner['owner_ref']).Pads()) == 6


def physical_links(board):
    graph = fr._read_only_route_connectivity(board)
    return {force._uid(p): sorted(force._uid(i) for i in graph.GetConnectedItems(p))
            for fp in board.GetFootprints() for p in fp.Pads()}


def test_electrical_metadata_does_not_create_a_physical_contact_or_capacity(tmp_path):
    source, child, owner = fixture(tmp_path)
    before, after = [pcbnew.LoadBoard(str(p)) for p in (source, child)]
    assert physical_links(before) == physical_links(after)
    for board in (before, after):
        fp = board.FindFootprintByReference(owner['owner_ref'])
        graph = fr._read_only_route_connectivity(board)
        assert force._uid(fp.FindPadByNumber('6')) not in {
            force._uid(i) for i in graph.GetConnectedItems(fp.FindPadByNumber('1'))}
        assert not list(board.GetTracks()) and not list(board.Zones())
    assert metadata.read_saved(child)[owner['owner_ref']] == (('1', '6'), ('3', '4'))


def test_native_electrical_connection_is_distinct_from_read_only_copper_graph(tmp_path):
    source, child, owner = fixture(tmp_path)
    for index, path in enumerate((source, child)):
        board = pcbnew.LoadBoard(str(path))
        before = physical_links(board)
        nets = {force._uid(p): str(p.GetNetname())
                for fp in board.GetFootprints() for p in fp.Pads()}
        assert board.BuildConnectivity()
        fp = board.FindFootprintByReference(owner['owner_ref'])
        reached = {force._uid(i) for i in board.GetConnectivity().GetConnectedItems(fp.FindPadByNumber('1'))}
        assert (force._uid(fp.FindPadByNumber('6')) in reached) == bool(index)
        assert before == physical_links(board)
        assert nets == {force._uid(p): str(p.GetNetname())
                        for fp in board.GetFootprints() for p in fp.Pads()}


@pytest.mark.parametrize('fault', [
    'pad_number', 'pad_net', 'pad_size', 'pad_position', 'part', 'pose', 'face',
    'owner_uuid', 'pad_uuid', 'added_track', 'group', 'reference', 'source_property',
    'wrong_group', 'missing_group', 'implicit', 'companion',
])
def test_literal_scope_rejects_every_nonmetadata_or_contradictory_change(tmp_path, fault):
    source, child, owner = fixture(tmp_path)
    board = pcbnew.LoadBoard(str(child))
    fp = board.FindFootprintByReference(owner['owner_ref'])
    pad = fp.FindPadByNumber('1')
    if fault == 'pad_number': pad.SetNumber('10')
    elif fault == 'pad_net': pad.SetNet(fp.FindPadByNumber('3').GetNet())
    elif fault == 'pad_size': pad.SetSize(pcbnew.VECTOR2I(800001, 700000))
    elif fault == 'pad_position': pad.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'part': fp.SetField('MPN', 'a different device')
    elif fault == 'pose': fp.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'face': fp.Flip(fp.GetPosition(), False)
    elif fault == 'owner_uuid': fp.m_Uuid.Clone(pcbnew.KIID())
    elif fault == 'pad_uuid': pad.m_Uuid.Clone(pcbnew.KIID())
    elif fault == 'added_track':
        track = pcbnew.PCB_TRACK(board)
        track.SetNet(pad.GetNet()); track.SetLayer(pcbnew.F_Cu); track.SetWidth(200000)
        track.SetStart(pcbnew.VECTOR2I_MM(1, 1)); track.SetEnd(pcbnew.VECTOR2I_MM(2, 1))
        board.Add(track)
    elif fault == 'group': next(iter(board.Groups())).SetName('different Source group')
    elif fault == 'reference': fp.SetReference('different')
    elif fault in ('wrong_group', 'missing_group', 'implicit', 'source_property'):
        root = metadata._parse(child.read_text())
        target = metadata._footprints(root)[owner['owner_ref']]
        target[:] = [n for n in target if not (isinstance(n, list) and n
                                              and n[0] in metadata._FIELDS)]
        if fault == 'source_property':
            root.append(['property', '"unauthorized Source context"', '"changed"'])
            target.append(['jumper_pad_groups', ['"1"', '"6"'], ['"3"', '"4"']])
        elif fault == 'wrong_group':
            target.append(['jumper_pad_groups', ['"1"', '"3"']])
        if fault == 'implicit': target.append(['duplicate_pad_numbers_are_jumpers', 'yes'])
        child.write_text(metadata._render(root))
    elif fault == 'companion': child.with_suffix('.kicad_dru').write_text('(version 2)')
    if fault not in ('wrong_group', 'missing_group', 'implicit', 'companion', 'source_property'):
        pcbnew.SaveBoard(str(child), board)
    with pytest.raises(ValueError): op.literal_scope(source, child, [owner])


@pytest.mark.parametrize('seconds', [True, False, 0, -1, 10.0001, float('nan'), float('inf')])
def test_public_interfaces_cannot_extend_or_disable_the_constituent(seconds):
    for call in (lambda: op.plan('/absent', board_hint='fixture', timeout_s=seconds),
                 lambda: op.construct({}, '/absent', timeout_s=seconds),
                 lambda: op.receive('/absent', '/absent2', {}, timeout_s=seconds)):
        with pytest.raises(ValueError, match='bounded_internal_connection_constituent_required'): call()


@pytest.mark.parametrize('fault', ['supplier', 'mpn', 'lcsc', 'dnp', 'bank_nets', 'missing_pad'])
def test_public_enrollment_refuses_unknown_or_contradictory_parts_before_export(tmp_path, monkeypatch, fault):
    board, fp, _, _ = protector_fixture()
    if fault == 'supplier': fp.SetField('Manufacturer', 'a different manufacturer')
    elif fault == 'mpn': fp.SetField('MPN', 'a different part')
    elif fault == 'lcsc': fp.SetField('LCSC', 'C9999999')
    elif fault == 'dnp': fp.SetDNP(True)
    elif fault == 'bank_nets': fp.FindPadByNumber('6').SetNet(fp.FindPadByNumber('3').GetNet())
    else: fp.FindPadByNumber('6').SetNumber('7')
    source = tmp_path / 'source.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    def forbidden(*args, **kwargs): raise AssertionError('unknown part must not reach Source export')
    monkeypatch.setattr(op.protector, '_source_symbol', forbidden)
    before = source.read_bytes()
    with pytest.raises(ValueError, match='positive_manufacturer'): op.plan(source, board_hint='fixture')
    assert source.read_bytes() == before


def test_reviewed_primary_pdf_is_exact_and_not_a_current_or_release_model():
    board, fp, _, _ = protector_fixture()
    model = op.roles.passive_steering_protector_contract(fp)
    evidence = op._datasheet(model)
    assert evidence['sha256'] == '973ea7520f3cd820e2c9326fcf3ee3ca5239cff491d6f42de057573942dcdf83'
    assert evidence['page'] == 1 and evidence['section'] == '4'
    assert not model['current_authority'] and not model['release_authority']
    model = dict(model, selected_datasheet_sha256='0' * 64)
    with pytest.raises(ValueError, match='datasheet_identity_changed'): op._datasheet(model)


def selection_fixture(tmp_path, monkeypatch, *, turn=0, face=pcbnew.F_Cu,
                      supplier='UMW', lcsc='C2687116', missing=('Manufacturer', 'MPN', 'LCSC')):
    """Actual native fields; mocked discovery only, NOT a public Source proof."""
    from types import SimpleNamespace
    board, fp, _, _ = protector_fixture(turn, False, face)
    fp.SetField('Manufacturer', supplier)
    fp.SetField('LCSC', lcsc)
    source = tmp_path / 'selection.kicad_pcb'
    pcbnew.SaveBoard(str(source), board)
    root = metadata._parse(source.read_text())
    node = metadata._footprints(root)[fp.GetReference()]
    node[:] = [x for x in node if not (isinstance(x, list) and len(x) >= 3
               and x[0] == 'property' and metadata._text(x[1]) in missing)]
    source.write_text(metadata._render(root))
    board = pcbnew.LoadBoard(str(source))
    fp = board.FindFootprintByReference(fp.GetReference())
    values = dict(Reference=fp.GetReference(), Value=fp.GetValue(), Footprint=fp.GetFPIDAsString(),
                  Manufacturer=supplier, MPN='USBLC6-2SC6', LCSC=lcsc)
    block = '(symbol ' + ' '.join('(property ' + json.dumps(k) + ' ' + json.dumps(v) + ')'
                                  for k, v in values.items()) + ')'
    sf = SimpleNamespace(children=[('symbol', block)])
    monkeypatch.setattr(op.protector.source_nc, '_root', lambda *_: source)
    monkeypatch.setattr(op.protector.source_pin, '_hierarchy', lambda *_:
        ([], {str(source): force._hash(source)}, {fp.GetReference(): [(source, sf, {}, ())]}))
    return board, fp, source


@pytest.mark.parametrize('turn', range(4))
@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_blank_fields_recover_exact_source_choice_without_copper_or_pose_change(tmp_path, monkeypatch, turn, face):
    board, fp, source = selection_fixture(tmp_path, monkeypatch, turn=turn, face=face)
    before = source.read_bytes()
    records = op._fill_missing_selection(board, source, 'synthetic', op._deadline(10.))
    fields = records[force._uid(fp)]
    assert {r['name'] for r in fields} == set(op._SELECTION_FIELDS)
    assert all(r['before'] is None for r in fields)
    owner = dict(owner_ref=fp.GetReference(), restored_source_fields=fields)
    child = force._copy_family(source, tmp_path / 'restored')
    op._apply_missing_selection(child, [owner], op._deadline(10.))
    after = pcbnew.LoadBoard(str(child))
    for r in fields:
        f = after.FindFootprintByReference(fp.GetReference()).GetField(r['name'])
        assert f.GetText() == r['value'] and not f.IsVisible()
        assert f.GetLayer() == (pcbnew.F_Fab if face == pcbnew.F_Cu else pcbnew.B_Fab)
    assert physical_links(board) == physical_links(after)
    assert force._uid(fp) == force._uid(after.FindFootprintByReference(fp.GetReference()))
    assert source.read_bytes() == before
    again = pcbnew.LoadBoard(str(source))
    assert records == op._fill_missing_selection(again, source, 'synthetic', op._deadline(10.))


@pytest.mark.parametrize('supplier,lcsc', [('unregistered', 'C2687116'), ('UMW', 'C7519'),
                                          ('STMicroelectronics', 'C2687116')])
def test_source_supplier_is_never_inferred_from_a_shared_part_name(tmp_path, monkeypatch, supplier, lcsc):
    board, fp, source = selection_fixture(tmp_path, monkeypatch, supplier=supplier, lcsc=lcsc)
    assert op._fill_missing_selection(board, source, 'synthetic', op._deadline(10.)) == {}
    assert 'MPN' not in op.footprint_properties(fp)


@pytest.mark.parametrize('key,value', [('MPN', 'different'), ('Manufacturer', 'different'), ('LCSC', 'C999')])
def test_missing_other_fields_cannot_override_nonblank_selection_conflicts(tmp_path, monkeypatch, key, value):
    board, fp, source = selection_fixture(tmp_path, monkeypatch, missing=tuple(k for k in op._SELECTION_FIELDS if k != key))
    fp.SetField(key, value)
    assert op._fill_missing_selection(board, source, 'synthetic', op._deadline(10.)) == {}
    assert op.footprint_properties(fp)[key] == value


def test_st_part_requires_its_own_reviewed_manufacturer_binary():
    _, fp, _, _ = protector_fixture()
    fp.SetField('Manufacturer', 'STMicroelectronics')
    fp.SetField('LCSC', 'C7519')
    model = op.roles.passive_steering_protector_contract(fp)
    assert model['io_banks'] == [['1', '6'], ['3', '4']]
    assert model['selected_manufacturer'] == 'STMicroelectronics'
    assert op._datasheet(model)['sha256'] == '8ba7ab4ec1781b7f6052f5999a2304bd611c0ed2b5e8f36ffa5092552932a42e'
    assert not model['current_authority'] and not model['release_authority']


def test_selection_field_scope_refuses_overwriting_a_populated_part(tmp_path):
    source, child, owner = fixture(tmp_path)
    before = metadata._footprints(metadata._parse(source.read_text()))[owner['owner_ref']]
    record = dict(name='MPN', before=op._property(before, 'MPN'),
                  after=op._property(before, 'MPN'), value='USBLC6-2SC6')
    owner['restored_source_fields'] = [record]
    with pytest.raises(ValueError, match='only_blank_source_selection'):
        op.literal_scope(source, child, [owner])


def embedded_fixture(tmp_path, declarations):
    uid = str(uuid.uuid4())
    path = tmp_path / 'source.kicad_sch'
    path.write_text(f'''(kicad_sch (version 20250114) (generator "fixture")
      (uuid "{uuid.uuid4()}") (paper "A4")
      (lib_symbols (symbol "fixture:six" {declarations}))
      (symbol (lib_id "fixture:six") (at 20 20 0) (unit 1)
        (uuid "{uid}") (property "Reference" "Q91") (property "Value" "fixture")))''')
    return dict(sheet=str(path), symbol_uuid=uid)


def test_actual_embedded_groups_not_defaults_or_a_caller_bank_list(tmp_path):
    proof = embedded_fixture(tmp_path, '(jumper_pin_groups ("1" "6") ("3" "4"))')
    assert op._source_groups(proof) == (('1', '6'), ('3', '4'))


@pytest.mark.parametrize('declarations', ['',
    '(jumper_pin_groups ("1" "6")) (jumper_pin_groups ("3" "4"))',
    '(jumper_pin_groups ("1" "6") ("6" "3"))',
    '(jumper_pin_groups ("1" "6") ("3" "4")) (duplicate_pin_numbers_are_jumpers yes)',
    '(extends "some-unproven-parent") (jumper_pin_groups ("1" "6") ("3" "4"))',
])
def test_missing_duplicate_implicit_or_inherited_embedded_declaration_refused(tmp_path, declarations):
    proof = embedded_fixture(tmp_path, declarations)
    with pytest.raises(ValueError): op._source_groups(proof)


def test_deadline_covers_final_source_liveness(monkeypatch):
    end = op._deadline(10.)
    monkeypatch.setattr(op.time, 'monotonic', lambda: end)
    with pytest.raises(ValueError, match='constituent_deadline'): op._remaining(end)


def test_json_recipe_cannot_change_a_physical_enrollment_owner(tmp_path):
    source, child, owner = fixture(tmp_path)
    encoded = json.loads(json.dumps([owner]))
    assert op.literal_scope(source, child, encoded)['changed_refs'] == [owner['owner_ref']]
    encoded[0]['owner_uuid'] = str(uuid.uuid4())
    with pytest.raises(ValueError, match='identity_changed'): op.literal_scope(source, child, encoded)


def liveness_fixture(tmp_path):
    """Final-guard unit packet only, not a Source/manufacturer enrollment."""
    source, child, owner = fixture(tmp_path)
    tool = tmp_path / 'exporter-fixture'; tool.write_text('unchanged fixture tool bytes')
    evidence = tmp_path / 'evidence-fixture'; evidence.write_text('unchanged evidence fixture')
    owner.update(source_symbol=dict(files_sha256={}, exporter=dict(
        exporter=str(tool), exporter_sha256=force._hash(tool))),
        datasheet=dict(path=str(evidence), sha256=force._hash(evidence)))
    q = dict(source=str(source), source_sha256=force._hash(source), board_hint='fixture',
             source_family=force._family(source, 'fixture'), code_identity=force._code_identity(),
             owners=[owner])
    return source, child, tool, q


def test_final_live_boundary_rechecks_the_exact_exporter_binary(tmp_path):
    source, child, tool, q = liveness_fixture(tmp_path)
    op._live(q, time.monotonic() + 10.)
    tool.write_text('replaced exporter, after an earlier hypothetical export')
    with pytest.raises(ValueError, match='exporter_changed'):
        op._live(q, time.monotonic() + 10.)


@pytest.mark.parametrize('operation', ['construct', 'receive'])
def test_final_candidate_hash_cannot_finish_outside_the_same_lease(tmp_path, monkeypatch, operation):
    source, child, tool, q = liveness_fixture(tmp_path)
    q = op._stable(q)
    # This unit test substitutes ONLY Source compilation to reach the final
    # clock boundary. Actual native literal scope/setter remain exercised;
    # it makes no positive public manufacturer/admission claim.
    monkeypatch.setattr(op, 'plan', lambda *a, **kw: copy.deepcopy(q))
    clock = [0.]; armed = [False]
    monkeypatch.setattr(op.time, 'monotonic', lambda: clock[0])
    actual_scope, actual_hash = op.literal_scope, force._hash
    def scope(*args, **kwargs):
        value = actual_scope(*args, **kwargs); armed[0] = True; return value
    def delayed_hash(path):
        value = actual_hash(path)
        if armed[0] and Path(path).suffix == '.kicad_pcb' and Path(path).resolve() != source.resolve():
            clock[0] = 11.
        return value
    monkeypatch.setattr(op, 'literal_scope', scope)
    monkeypatch.setattr(force, '_hash', delayed_hash)
    with pytest.raises(ValueError, match='constituent_deadline'):
        if operation == 'construct': op.construct(q, tmp_path / 'NEW-CONSTRUCT')
        else: op.receive(source, child, q)
    assert armed[0] and clock[0] == 11.


def test_receive_rechecks_child_family_after_materializing_candidate_hash(tmp_path, monkeypatch):
    source, child, tool, q = liveness_fixture(tmp_path)
    q = op._stable(q)
    monkeypatch.setattr(op, 'plan', lambda *a, **kw: copy.deepcopy(q))
    actual_scope, actual_hash = op.literal_scope, force._hash
    armed = [False]
    def scope(*args, **kwargs):
        value = actual_scope(*args, **kwargs)
        armed[0] = True
        return value
    def mutate_during_hash(path):
        value = actual_hash(path)
        if armed[0] and Path(path).resolve() == child.resolve():
            armed[0] = False
            child.with_suffix('.kicad_dru').write_text('(version 2)')
        return value
    monkeypatch.setattr(op, 'literal_scope', scope)
    monkeypatch.setattr(force, '_hash', mutate_during_hash)
    with pytest.raises(ValueError, match='candidate_family_changed'):
        op.receive(source, child, q)

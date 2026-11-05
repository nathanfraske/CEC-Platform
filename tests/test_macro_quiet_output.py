"""Source-canonical projected quiet output and saved macro composition tests.

The canonical fixture substitutes only the CLI export boundary. Native pads,
net connectivity, manufacturer roles and Source hierarchy remain real. The
complete integration separately receives quiet material and the whole macro.
"""
import ast
import copy
import inspect
import json
from pathlib import Path
import time
import uuid

import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_macro_quiet_output as op
import cec_quiet_signal_completion as quiet
import cec_source_ground_leaf as canonical
import cec_source_netlist_semantics as semantics
import cec_device_power_roles as roles
import cec_force_current as force
import cec_field_coupling as field
import cec_route_dimensions as dimensions
from test_quiet_signal_requests import fixture as canonical_fixture
from test_field_proposals import track


def fixture(tmp_path, monkeypatch, *, quarter=0, back=False):
    real_resolver = op.fr._project_netclass_resolver
    parent, source, root, tree, spec, output, target = canonical_fixture(
        tmp_path, monkeypatch, quarter=quarter, back=back)
    monkeypatch.setattr(op.fr, '_project_netclass_resolver', real_resolver)
    # Use the established full-tree date-only semantic identity at the
    # external CLI boundary; do not replace Source roles or native graphs.
    exporter = canonical._export
    def export(path, deadline):
        actual, proof = exporter(path, deadline)
        return actual, dict(proof, **semantics.metadata(actual))
    monkeypatch.setattr(canonical, '_export', export)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(
        board=dict(design_settings=dict(rules=dict(min_track_width=.2))),
        net_settings=dict(classes=[dict(name='Default', track_width=.22, clearance=.2),
            dict(name='Sense', track_width=.25, clearance=.2, via_diameter=.6, via_drill=.3)],
            netclass_assignments={'/renamed_quiet':['Sense']}))))
    spec = dimensions.NetclassTable.from_board_path(source).resolve('/renamed_quiet')
    # Source-authored simple geometry. Neither actual public graph nor the
    # quiet native receiving decision is mocked by these fixtures.
    for index, pad in enumerate(p for f in parent.GetFootprints() for p in f.Pads()
                                 if force._uid(p) not in {force._uid(output), force._uid(target)}):
        pad.SetPosition(pcbnew.VECTOR2I_MM(5 + (index % 20), 30 + index // 20))
    output.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
    target.SetPosition(pcbnew.VECTOR2I_MM(20, 11))
    for a, b in [((0, 0), (50, 0)), ((50, 0), (50, 50)), ((50, 50), (0, 50)), ((0, 50), (0, 0))]:
        edge = pcbnew.PCB_SHAPE(parent); edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT); edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*b)); edge.SetWidth(50000); parent.Add(edge)
    field._save_field_snapshot(parent, source)
    projected = pcbnew.LoadBoard(str(source))
    owner = output.GetParentFootprint(); moved = projected.FindFootprintByReference(owner.GetReference())
    moved.Move(pcbnew.VECTOR2I_MM(0, 1))
    pose = [moved.GetPosition().x / 1e6, moved.GetPosition().y / 1e6, moved.GetOrientationDegrees()]
    proposal = dict(scope='source_typed_complete_cell_escape_proposal', board_hint=str(root),
        source_native_binding=op.row._source_binding(parent), poses={owner.GetReference(): pose},
        stationary_device_owners=[], device_contracts={owner.GetReference(): roles.footprint_contract(owner)},
        inherited_unrouted_measurement_lands=[], source_explicit_schematic_no_connects=[])
    return parent, projected, source, root, tree, spec, output, target, proposal


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_fresh_source_typed_projected_output_is_an_obligation_not_a_port_claim(tmp_path, monkeypatch, quarter, back):
    parent, projected, source, root, tree, spec, output, target, proposal = fixture(
        tmp_path, monkeypatch, quarter=quarter, back=back)
    raw = source.read_bytes(); before = op.row._source_binding(parent)
    rows = op.plan(parent, projected, proposal, [force._uid(output)])
    assert len(rows) == 1
    request = rows['quiet_output:' + force._uid(output)]
    assert request['kind'] == op.KIND and request['width_nm'] == 250000
    assert request['a']['at_nm'] == [10000000, 11000000]
    assert request['b']['at_nm'] == [20000000, 11000000]
    assert request['source_quiet_request']['target']['manufacturer']['adc_capable']
    assert request['source_quiet_request']['root']['manufacturer']['pins'][output.GetNumber()] == 'signal_output'
    assert not request['ordinary_authority'] and not request['current_authority']
    assert request['incoming_native_terminal_join_mandatory']
    assert source.read_bytes() == raw and before == op.row._source_binding(parent)
    assert op.discharged(parent, projected, proposal, rows, [force._uid(output)]) == {force._uid(output)}


@pytest.mark.parametrize('fault', ['power', 'pair', 'Kelvin', 'wrong_class', 'wrong_role', 'wrong_adc',
    'malformed_owner', 'source_unrequested', 'source_binding', 'projected_root', 'moved_adc',
    'third_terminal', 'source_nonisolated', 'source_raw_mutation', 'semantic_export_mutation'])
def test_fresh_wrong_or_changed_source_never_acquires_projected_quiet_scope(tmp_path, monkeypatch, fault):
    parent, projected, source, root, tree, spec, output, target, proposal = fixture(tmp_path, monkeypatch)
    values = [force._uid(output)]; net = output.GetNetname()
    if fault == 'power': monkeypatch.setattr(op.source_requests.synth, 'spec_net_current_contract', lambda *a: {'amps': 1})
    elif fault == 'pair': monkeypatch.setattr(op.fr, 'coupled_pair_nets', lambda b: {net})
    elif fault == 'Kelvin': monkeypatch.setattr(op.source_requests.pairs, 'analog_input_pairs', lambda b: [dict(p=net, n='/other')])
    elif fault == 'wrong_class':
        project = json.loads(source.with_suffix('.kicad_pro').read_text())
        project['net_settings']['netclass_assignments']['/renamed_quiet'] = ['Default']
        source.with_suffix('.kicad_pro').write_text(json.dumps(project))
    elif fault == 'wrong_role': proposal['device_contracts'][output.GetParentFootprint().GetReference()]['pins'][output.GetNumber()] = 'measurement'
    elif fault == 'wrong_adc': root.write_text(root.read_text().replace('(name "IO1")', '(name "USB_D-")'))
    elif fault == 'malformed_owner': proposal['device_contracts'][output.GetParentFootprint().GetReference()] = {}
    elif fault == 'source_unrequested': values = [force._uid(target)]
    elif fault == 'source_binding': proposal['source_native_binding'] = {'worker_says_ok': True}
    elif fault == 'projected_root': op._pads(projected)[force._uid(output)].Move(pcbnew.VECTOR2I_MM(.1, 0))
    elif fault == 'moved_adc': op._pads(projected)[force._uid(target)].Move(pcbnew.VECTOR2I_MM(.1, 0))
    elif fault == 'third_terminal':
        new = pcbnew.PAD(projected.FindFootprintByReference(target.GetParentFootprint().GetReference()))
        new.SetNumber('99'); new.SetNet(projected.FindNet(net)); new.GetParentFootprint().Add(new)
    elif fault == 'source_nonisolated':
        track(parent, net, (10, 10), (11, 10), width=.25)
        field._save_field_snapshot(parent, source); proposal['source_native_binding'] = op.row._source_binding(parent)
    else:
        original = canonical._export
        def mutate(path, deadline):
            result = original(path, deadline)
            if fault == 'source_raw_mutation': source.write_bytes(source.read_bytes() + b'\n')
            else: root.write_text(root.read_text().replace('(name "OUT")', '(name "IN+")'))
            return result
        monkeypatch.setattr(canonical, '_export', mutate)
    with pytest.raises((ValueError, KeyError)):
        op.plan(parent, projected, proposal, values)


@pytest.mark.parametrize('fault', ['width', 'role', 'target', 'layers', 'missing', 'unrequested', 'old_unprojected'])
def test_discharge_rederives_full_current_request_instead_of_trusting_worker_packet(tmp_path, monkeypatch, fault):
    parent, projected, source, root, tree, spec, output, target, proposal = fixture(tmp_path, monkeypatch)
    uid = force._uid(output); rows = op.plan(parent, projected, proposal, [uid]); request = rows['quiet_output:' + uid]
    ids = [uid]
    if fault == 'width': request['width_nm'] = 200000
    elif fault == 'role': request['kind'] = 'source_boundary'
    elif fault == 'target': request['b']['pad_uuid'] = str(uuid.uuid4())
    elif fault == 'layers': request['allowed_layers'].append(int(pcbnew.In3_Cu))
    elif fault == 'missing': rows.clear()
    elif fault == 'unrequested': ids = []
    else: request['a']['at_nm'] = list(output.GetPosition())
    with pytest.raises(ValueError): op.discharged(parent, projected, proposal, rows, ids)


def test_default_guard_still_reports_isolated_output_and_fake_packet_does_not_discharge_it(tmp_path, monkeypatch):
    parent, projected, source, root, tree, spec, output, target, proposal = fixture(tmp_path, monkeypatch)
    uid = force._uid(output)
    missing = escape.unplanned_source_terminals(parent, proposal, {}, board=projected)
    assert any(row['pad_uuid'] == uid for row in missing)
    rows = op.plan(parent, projected, proposal, [uid])
    with pytest.raises(ValueError): escape.unplanned_source_terminals(parent, proposal, rows, board=projected)
    accepted = escape.unplanned_source_terminals(parent, proposal, rows, board=projected,
        required_quiet_output_pad_uuids=[uid])
    assert not any(row['pad_uuid'] == uid for row in accepted)


@pytest.mark.parametrize('value', [None, False, 'not-a-list', ['bad'], [True],
    ['00000000-0000-0000-0000-000000000001'] * 2, [str(uuid.uuid4()) for _ in range(5)],
    [{'pad_uuid': '00000000-0000-0000-0000-000000000001', 'width_nm': 1}]])
def test_identity_only_finite_schema(value):
    with pytest.raises(ValueError): op.ids(value)


def test_default_option_preserves_old_empty_request_inventory():
    assert op.ids(()) == []
    assert op.plan(None, None, {}, ()) == {}
    assert compiler.packet_options({}) == {}


@pytest.mark.parametrize('key', ['source_packet', 'width_nm', 'net', 'layers', 'current',
    'callback', 'positive_proof', 'source_sha256', 'required_quiet_output_pad_uuids'])
def test_projected_public_receiver_does_not_accept_asserted_scope(key):
    with pytest.raises(ValueError):
        op.receiving_stages({key: 'untrusted'}, [str(uuid.uuid4())], 10.)


def test_three_compile_phases_are_separate_from_path_field_returns_and_identity():
    uid = str(uuid.uuid4())
    stages = op.receiving_stages({'compilation_phase_timeouts_s': [10., 10., 10.]}, [uid], 10.)
    assert len(stages) == 8
    assert stages[1:4] == ['compile:' + name for name in compiler.COMPILATION_PHASES]
    assert stages[4:] == ['actual_quiet_path:' + uid, 'quiet_native_field_delta',
        'all_original_physical_returns', 'final_live_identity']
    with pytest.raises(ValueError): op.receiving_stages({'compilation_phase_timeouts_s': [10., 10., 10.]}, [uid], 9.)


def test_expired_stage_cannot_borrow_next_phase_time(monkeypatch):
    clock = [time.monotonic()]; monkeypatch.setattr(op.time, 'monotonic', lambda: clock[0])
    lease = op._Lease(10., ['first', 'next']); clock[0] += 10.001
    with pytest.raises(ValueError, match='deadline'): lease.advance('next')
    assert lease.index == 0


def test_observer_context_is_restored_on_exception():
    previous = op._observer.get()
    with pytest.raises(RuntimeError):
        with op.observe_receiving_phases(lambda event: None):
            raise RuntimeError('unit fault')
    assert op._observer.get() is previous


def test_projected_public_call_graph_has_no_recursive_macro_receiving():
    tree = ast.parse(inspect.getsource(op))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != 'cec_complete_macro_cell' for alias in node.names)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert not (node.func.attr == 'receive' and isinstance(node.func.value, ast.Name)
                        and node.func.value.id in ('macro', 'complete_macro'))
    assert 'compiler.compile' in inspect.getsource(op.receive)
    assert 'cell._poses' in inspect.getsource(op.receive)


def saved_path_fixture(tmp_path, monkeypatch):
    parent, projected, source, root, tree, spec, output, target, proposal = fixture(tmp_path, monkeypatch)
    uid = force._uid(output); request = op.plan(parent, projected, proposal, [uid])['quiet_output:' + uid]
    candidate = force._copy_family(source, tmp_path / 'private-child')
    track(projected, output.GetNetname(), (10, 11), (20, 11), width=.25)
    field._save_field_snapshot(projected, candidate)
    child = pcbnew.LoadBoard(str(candidate))
    return parent, projected, child, source, candidate, str(root), request


def test_real_saved_path_observer_uses_projected_root_fixed_adc_and_exact_source_width(tmp_path, monkeypatch):
    parent, projected, child, source, candidate, hint, request = saved_path_fixture(tmp_path, monkeypatch)
    raw = [p.read_bytes() for p in (source, candidate)]
    proof = op._observe_path(parent, projected, child, source, candidate, request, time.monotonic() + 10.)
    assert (proof['source_components'], proof['candidate_components']) == (2, 1)
    assert len(proof['added_native_uuids']) == 1
    assert proof['exact_original_quiet_copper_preserved']
    assert raw == [p.read_bytes() for p in (source, candidate)]
    # Legacy public receiver is deliberately STILL stationary/additive-only.
    refused = quiet.receive(source, candidate, board_hint=hint, net=request['net'])
    assert not refused['ok'] and any('identity_pose' in error for error in refused['errors'])


@pytest.mark.parametrize('fault', ['width', 'forbidden_face', 'no_actual_path', 'orphan', 'moved_target', 'raw_wrong_net'])
def test_saved_quiet_path_is_not_a_named_pad_port_or_phantom_via_claim(tmp_path, monkeypatch, fault):
    parent, projected, child, source, candidate, hint, request = saved_path_fixture(tmp_path, monkeypatch)
    edge = next(iter(child.GetTracks()))
    if fault == 'width': edge.SetWidth(200000)
    elif fault == 'forbidden_face': edge.SetLayer(pcbnew.In3_Cu)
    elif fault == 'no_actual_path':
        from cec_native_items import discard_items
        discard_items(child, [edge])
    elif fault == 'orphan': track(child, request['net'], (25, 15), (26, 15), width=.25)
    elif fault == 'moved_target': op._pads(child)[request['b']['pad_uuid']].Move(pcbnew.VECTOR2I_MM(.1, 0))
    else: edge.SetNet(child.FindNet('+3V3'))
    # Deliberately bad native raw material is test input, not a safe producer.
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(candidate), child)
    loaded = pcbnew.LoadBoard(str(candidate))
    with pytest.raises(ValueError):
        op._observe_path(parent, projected, loaded, source, candidate, request, time.monotonic() + 10.)


def test_public_receiver_cannot_replace_fresh_compiler_with_saved_worker_success(tmp_path, monkeypatch):
    # Dispatch-only negative. It supplies no fabricated positive receiver.
    source, candidate = tmp_path / 'a.kicad_pcb', tmp_path / 'b.kicad_pcb'
    source.write_text('not a Source'); candidate.write_text('not a child')
    with pytest.raises(ValueError):
        quiet.receive_projected(source, candidate, board_hint='synthetic',
            required_quiet_output_pad_uuids=[str(uuid.uuid4())],
            macro_options={'source_packet': {'complete': True}})


def test_distinct_directory_identical_project_retains_every_policy_field(tmp_path, monkeypatch):
    parent, projected, child, source, candidate, hint, request = saved_path_fixture(tmp_path, monkeypatch)
    before = op._policy(parent, source, request['net'])
    after = op._policy(child, candidate, request['net'])
    assert before != after
    assert before['spec']['dimension_contract']['source'] == str(source.with_suffix('.kicad_pro'))
    assert after['spec']['dimension_contract']['source'] == str(candidate.with_suffix('.kicad_pro'))
    assert op._candidate_policy(parent, child, source, candidate, request['net'], before) == before
    assert before['spec']['clearance'] == .2 and before['spec']['track_width'] == .25


@pytest.mark.parametrize('fault', ['width', 'clearance', 'project_reference', 'native_floor', 'rules'])
def test_copied_family_does_not_normalize_different_source_policy(tmp_path, monkeypatch, fault):
    parent, projected, child, source, candidate, hint, request = saved_path_fixture(tmp_path, monkeypatch)
    path = candidate.with_suffix('.kicad_pro')
    project = json.loads(path.read_text())
    if fault in ('width', 'clearance'):
        project['net_settings']['classes'][1]['track_width' if fault == 'width' else 'clearance'] = .1
        path.write_text(json.dumps(project))
    elif fault == 'project_reference': path.rename(path.with_name('different.kicad_pro'))
    elif fault == 'native_floor': child.GetDesignSettings().m_TrackMinWidth = 310000
    else: candidate.with_suffix('.kicad_dru').write_text('(version 1)\n')
    with pytest.raises(ValueError):
        op._candidate_policy(parent, child, source, candidate, request['net'], request['source_policy'])


def test_retained_foreign_uuid_cannot_become_part_of_the_saved_quiet_path(tmp_path, monkeypatch):
    parent, projected, source, root, tree, spec, output, target, proposal = fixture(tmp_path, monkeypatch)
    foreign = track(parent, '/foreign', (25, 15), (26, 15), width=.25)
    field._save_field_snapshot(parent, source)
    projected = pcbnew.LoadBoard(str(source))
    projected.FindFootprintByReference(output.GetParentFootprint().GetReference()).Move(pcbnew.VECTOR2I_MM(0, 1))
    proposal['source_native_binding'] = op.row._source_binding(parent)
    request = op.plan(parent, projected, proposal, [force._uid(output)])['quiet_output:' + force._uid(output)]
    next(t for t in projected.GetTracks() if force._uid(t) == force._uid(foreign)).SetNet(projected.FindNet(request['net']))
    track(projected, request['net'], (10, 11), (20, 11), width=.25)
    candidate = force._copy_family(source, tmp_path / 'retagged-child')
    field._save_field_snapshot(projected, candidate)
    with pytest.raises(ValueError, match='retagged_or_unowned'):
        op._observe_path(parent, projected, pcbnew.LoadBoard(str(candidate)), source, candidate,
            request, time.monotonic() + 10.)


@pytest.mark.parametrize('shadow', ['foreign_track', 'nested_pad'])
def test_new_quiet_literal_uuid_cannot_shadow_existing_source_identity(tmp_path, monkeypatch, shadow):
    parent, projected, child, source, candidate, hint, request = saved_path_fixture(tmp_path, monkeypatch)
    incoming = force._uid(next(iter(child.GetTracks())))
    if shadow == 'nested_pad':
        uid = request['b']['pad_uuid']
    else:
        foreign = track(parent, '/foreign', (30, 15), (31, 15), width=.25)
        field._save_field_snapshot(parent, source); uid = force._uid(foreign)
    # Retain the pre-normalization raw collision. Native normalization must
    # not make a forged UUID acquire Source/new-addition permission.
    candidate.write_text(candidate.read_text().replace(incoming, uid))
    with pytest.raises(ValueError, match='shadow|duplicate|literal_and_native|bounded_complete_macro_copper_inventory'):
        op._observe_path(parent, projected, child, source, candidate, request, time.monotonic() + 10.)


def test_normalized_export_identity_still_has_live_source_binding_checks(tmp_path, monkeypatch):
    parent, projected, source, root, tree, spec, output, target, proposal = fixture(tmp_path, monkeypatch)
    request = op.plan(parent, projected, proposal, [force._uid(output)])['quiet_output:' + force._uid(output)]
    proof = dict(scope='source_typed_quiet_analog_requests',
        source_bindings=request['source_quiet_request']['source_bindings'])
    assert 'netlist_sha256' not in proof['source_bindings']['exporter']
    assert proof['source_bindings']['exporter']['netlist_semantic_policy'] == semantics.POLICY
    assert op.source_requests.bindings_current(proof)
    Path(proof['source_bindings']['exporter']['exporter']).write_bytes(b'changed exporter')
    assert not op.source_requests.bindings_current(proof)


def test_saved_project_via_floor_is_not_replaced_by_weak_loadboard_defaults(tmp_path, monkeypatch):
    parent, projected, source, root, tree, spec, output, target, proposal = fixture(tmp_path, monkeypatch)
    path = source.with_suffix('.kicad_pro'); project = json.loads(path.read_text())
    project['board']['design_settings']['rules'].update(min_via_diameter=.8,
        min_through_hole_diameter=.4, min_via_annular_width=.15)
    path.write_text(json.dumps(project))
    request = op.plan(parent, projected, proposal, [force._uid(output)])['quiet_output:' + force._uid(output)]
    candidate = force._copy_family(source, tmp_path / 'via-child')
    via = pcbnew.PCB_VIA(projected); via.SetNet(projected.FindNet(request['net']))
    via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetPosition(pcbnew.VECTOR2I_MM(15, 11)); via.SetWidth(600000); via.SetDrill(300000)
    projected.Add(via)
    assert dimensions.board_limits(parent)['via_diameter'] < .8
    assert dimensions.source_board_limits(parent, source)['via_diameter'] == .8
    # A profile or geometrically local shape alone is not the Source rule.
    with pytest.raises(ValueError): op._via_process(parent, projected, projected, source, candidate, via, request)
    via.SetWidth(800000); via.SetDrill(400000)
    assert op._via_process(parent, projected, projected, source, candidate, via, request)['kind'] == 'ordinary'


def test_local_via_geometry_is_not_a_profile_only_ordinary_floor_alias(tmp_path, monkeypatch):
    parent, projected, source, root, tree, spec, output, target, proposal = fixture(tmp_path, monkeypatch)
    props = parent.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'; parent.SetProperties(props)
    props = projected.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'; projected.SetProperties(props)
    field._save_field_snapshot(parent, source); proposal['source_native_binding'] = op.row._source_binding(parent)
    request = op.plan(parent, projected, proposal, [force._uid(output)])['quiet_output:' + force._uid(output)]
    candidate = force._copy_family(source, tmp_path / 'unowned-local-child')
    via = pcbnew.PCB_VIA(projected); via.SetNet(projected.FindNet(request['net']))
    via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetPosition(pcbnew.VECTOR2I_MM(10, 11)); via.SetWidth(300000); via.SetDrill(200000)
    projected.Add(via)
    # Containment is not enough: missing Source local rule/group refuses.
    with pytest.raises(ValueError, match='membership|existing_local_rule'):
        op._via_process(parent, projected, projected, source, candidate, via, request)


def complete_source_fixture(tmp_path, monkeypatch):
    """A real complete manufacturer INA240/cap cell and fixed ESP ADC.

    Only the external CLI netlist producer is substituted with the complete
    fixture hierarchy. No role, assignment, current, native graph, geometry,
    field, return, compiler or saved receiving decision is mocked.
    """
    import hashlib
    import cec_additive_route_receiving as additive
    import cec_synth_pipeline as synth
    from cec_native_items import discard_items
    real_resolver = op.fr._project_netclass_resolver
    board, source, root, _, _, output, target = canonical_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(op.fr, '_project_netclass_resolver', real_resolver)
    board.SetCopperLayerCount(6)
    props = board.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    board.SetProperties(props)
    board.GetDesignSettings().m_MinClearance = 200000
    owner = output.GetParentFootprint(); owner.SetReference('U_source_amplifier')
    owner.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
    for name in ('/input_negative', '/input_positive'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    layout = {
        '1': ('/input_negative', (9, 11), 'input', 'IN-'),
        '2': ('GND', (9, 10), 'power_in', 'GND'),
        '3': ('GND', (9, 9), 'input', 'REF1'),
        '4': ('GND', (10, 8), 'passive', 'NC'),
        '5': ('/renamed_quiet', (11, 9), 'output', 'OUT'),
        '6': ('+3V3', (11, 10), 'power_in', 'VS'),
        '7': ('GND', (11, 11), 'input', 'REF2'),
        '8': ('/input_positive', (10, 12), 'input', 'IN+'),
    }
    for pad in owner.Pads():
        net, at, typ, name = layout[pad.GetNumber()]
        pad.SetNetCode(board.GetNetcodeFromNetname(net) if net else 0)
        pad.SetPosition(pcbnew.VECTOR2I_MM(*at)); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetPinType(typ); pad.SetPinFunction(name)
    controller = target.GetParentFootprint()
    controller.SetPosition(pcbnew.VECTOR2I_MM(40, 30))
    for index, pad in enumerate(controller.Pads()):
        pad.SetPosition(pcbnew.VECTOR2I_MM(35 + index % 15, 30 + index // 15))
    target.SetPosition(pcbnew.VECTOR2I_MM(20, 9.5))
    cap = pcbnew.FOOTPRINT(board); cap.SetReference('C_source_bypass'); cap.SetValue('100nF')
    cap.SetField('MPN', 'CL05B104KO5NNNC')
    cap.SetFPID(pcbnew.LIB_ID('cec-Capacitor_SMD', 'C_0402_1005Metric'))
    cap.SetPosition(pcbnew.VECTOR2I_MM(13, 10)); board.Add(cap)
    for number, name, at in [('1', '+3V3', (12.5, 10)), ('2', 'GND', (13.5, 10))]:
        pad = pcbnew.PAD(cap); pad.SetNumber(number); pad.SetNet(board.FindNet(name))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I_MM(.5, .5))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*at)); pad.SetPinType('passive'); pad.SetPinFunction('~')
        cap.Add(pad)
    for name, start, end in [('/input_negative', (9, 11), (6, 11)),
                              ('/input_positive', (10, 12), (10, 16))]:
        fp = pcbnew.FOOTPRINT(board); fp.SetReference('fixed_' + name[1:]); board.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I_MM(*end))
        pad = pcbnew.PAD(fp); pad.SetNumber('1'); pad.SetNet(board.FindNet(name))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I_MM(.5, .5))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*end)); pad.SetPinType('passive'); pad.SetPinFunction('~'); fp.Add(pad)
        track(board, name, start, end, width=.25)
    track(board, '+3V3', (11, 10), (12.5, 10), width=.5)
    vias = []
    for fp in (owner, cap):
        for pad in fp.Pads():
            if pad.GetNetname() != 'GND': continue
            via = pcbnew.PCB_VIA(board); via.SetNet(pad.GetNet()); via.SetPosition(pad.GetPosition())
            via.SetWidth(350000); via.SetDrill(250000); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            board.Add(via); vias.append(via)
        boxes = [p.GetBoundingBox() for p in fp.Pads()]
        court = pcbnew.PCB_SHAPE(fp); court.SetShape(pcbnew.SHAPE_T_RECT)
        court.SetLayer(pcbnew.F_CrtYd); court.SetWidth(50000)
        court.SetStart(pcbnew.VECTOR2I(min(b.GetLeft() for b in boxes)-100000, min(b.GetTop() for b in boxes)-100000))
        court.SetEnd(pcbnew.VECTOR2I(max(b.GetRight() for b in boxes)+100000, max(b.GetBottom() for b in boxes)+100000))
        fp.Add(court)
    assert op.fr.group_local_pofv_signal_vias(board, vias)
    for a, b in [((0, 0), (60, 0)), ((60, 0), (60, 50)), ((60, 50), (0, 50)), ((0, 50), (0, 0))]:
        edge = pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_SEGMENT); edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b)); edge.SetWidth(50000); board.Add(edge)
    for face in (pcbnew.In1_Cu, pcbnew.In4_Cu):
        zone = pcbnew.ZONE(board); zone.SetNet(board.FindNet('GND')); zone.SetLayer(face)
        zone.Outline().NewOutline()
        for x, y in ((0, 0), (60, 0), (60, 50), (0, 50)): zone.Outline().Append(x*1000000, y*1000000)
        board.Add(zone)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(
        board=dict(design_settings=dict(rules=dict(min_track_width=.2, min_clearance=.2))),
        net_settings=dict(classes=[dict(name='Default', track_width=.2, clearance=.2, via_diameter=.6, via_drill=.3),
            dict(name='Sense', track_width=.25, clearance=.2, via_diameter=.6, via_drill=.3),
            dict(name='Supply', track_width=.5, clearance=.2, via_diameter=.6, via_drill=.3)],
            netclass_assignments={'/renamed_quiet':['Sense'], '/input_negative':['Sense'],
                '/input_positive':['Sense'], '+3V3':['Supply']}))))
    # Literal fixture policy, consumed through the real repository-local
    # loader and unchanged current/fabrication formulas. It rates no board.
    (tmp_path / 'pipeline-policy.json').write_text(json.dumps(dict(schema=1,
        board=tmp_path.name, params=dict(net_current_contracts={'+3V3': .1}))))
    library = []; symbols = []; components = []; native_nets = {}
    for index, fp in enumerate(board.GetFootprints()):
        uid = str(uuid.uuid4()); name = 'Part' + str(index); ref = fp.GetReference()
        props = dict(Reference=ref, Value=fp.GetValue(), Footprint=fp.GetFPIDAsString(),
            MPN=fp.GetField('MPN').GetText() if fp.GetField('MPN') else '')
        pins = []
        for pin_index, pad in enumerate(fp.Pads()):
            typ, function = pad.GetPinType() or 'passive', pad.GetPinFunction() or 'P' + pad.GetNumber()
            pins.append('(pin '+typ+' line (at '+str(pin_index)+' 0 0) (length 1.27) (name "'+function+'") (number "'+pad.GetNumber()+'"))')
            if pad.GetNetname(): native_nets.setdefault(pad.GetNetname(), []).append((ref, pad.GetNumber()))
        library.append('(symbol "fixture:'+name+'" (symbol "'+name+'_1_1" '+' '.join(pins)+'))')
        symbols.append('(symbol (lib_id "fixture:'+name+'") (at '+str(index*100)+' 0 0) (unit 1) (uuid "'+uid+'") '+' '.join('(property "'+k+'" "'+v+'")' for k,v in props.items())+')')
        components.append('(comp (ref "'+ref+'") (value "'+props['Value']+'") (footprint "'+props['Footprint']+'") (property (name "MPN") (value "'+props['MPN']+'")) (tstamps "'+uid+'"))')
    root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") (lib_symbols '+' '.join(library)+') '+' '.join(symbols)+')')
    tree = synth.parse_sexpr('(export (components '+' '.join(components)+') (nets '+' '.join(
        '(net (name "'+name+'") '+' '.join('(node (ref "'+ref+'") (pin "'+pin+'"))' for ref,pin in members)+')'
        for name,members in native_nets.items())+'))')
    exporter = tmp_path / 'exporter'; exporter.write_bytes(b'complete synthetic external compiler')
    def export(path, deadline):
        assert Path(path) == root
        return tree, dict(netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),
            exporter=str(exporter), exporter_sha256=force._hash(exporter), **semantics.metadata(tree))
    monkeypatch.setattr(canonical, '_export', export)
    additive._ground_refill(board); field._save_field_snapshot(board, source)
    additive.bind_local_via_rule(board, source)
    parent = pcbnew.LoadBoard(str(source))
    poses = {fp.GetReference(): [fp.GetPosition().x/1e6+.5, fp.GetPosition().y/1e6+.5, fp.GetOrientationDegrees()]
        for fp in (owner, cap)}
    return source, str(root), parent, poses, force._uid(output)


def test_complete_canonical_moved_cell_saved_quiet_and_macro_same_identity(tmp_path, monkeypatch):
    import tempfile
    # The actual policy resolver deliberately accepts repository-local
    # policies only. Keep this temporary synthetic owner inside that root;
    # do not monkeypatch policy discovery or a positive current contract.
    with tempfile.TemporaryDirectory(prefix='quiet-integration-',
            dir=Path(compiler.__file__).resolve().parents[1] / 'build') as directory:
        _complete_canonical_saved_case(Path(directory), monkeypatch)


def _construct_complete_canonical_case(tmp_path, monkeypatch):
    import cec_additive_route_receiving as additive
    import cec_complete_macro_cell as macro
    source, hint, parent, poses, uid = complete_source_fixture(tmp_path, monkeypatch)
    source_bytes = source.read_bytes()
    options = dict(compilation_phase_timeouts_s=[10., 10., 10.])
    private, packet = compiler.compile(source, poses, board_hint=hint,
        required_quiet_output_pad_uuids=[uid], **options)
    assert packet['requests']['quiet_output:' + uid]['kind'] == op.KIND
    screen = macro.screen(source, private, packet, board_hint=hint, timeout_s=10.)
    if not screen['complete']:
        print(json.dumps({k: screen.get(k) for k in ('errors', 'empty_obligations',
            'inherited_unplanned_terminals', 'selection', 'complete_selection_partition_trials',
            'complete_selection_ground_return_trials', 'complete_selection_trace_craft_trials')}, default=str))
    assert screen['complete'], {k: screen.get(k) for k in ('errors', 'empty_obligations',
        'missing_source_terminals', 'independent_macro_native_frame', 'native_pose',
        'source_ground', 'complete_selection_partition_trials', 'complete_selection_ground_return_trials',
        'complete_selection_trace_craft_trials', 'selection')}
    assert all(screen['packet']['domains'].values())
    escape.construct_private(private, screen['packet'], screen['selection'])
    additive._ground_refill(private)
    candidate = force._copy_family(source, tmp_path / 'complete-private-child')
    macro.save_private(private, candidate, packet)
    return source, candidate, hint, uid, options, source_bytes


def _complete_canonical_saved_case(tmp_path, monkeypatch):
    import cec_complete_macro_cell as macro
    source, candidate, hint, uid, options, source_bytes = _construct_complete_canonical_case(tmp_path, monkeypatch)
    saved_sha = force._hash(candidate)
    independent = quiet.receive_projected(source, candidate, board_hint=hint,
        required_quiet_output_pad_uuids=[uid], macro_options=options, timeout_s=10.)
    assert independent['ok'] and independent['complete'], independent
    received = macro.receive(source, candidate, board_hint=hint,
        required_quiet_output_pad_uuids=[uid], **options, timeout_s=10.)
    assert received['ok'] and received['complete'], received
    nested = received['independent_saved_projected_quiet_paths']
    assert nested['ok'] and nested['candidate_sha256'] == saved_sha == force._hash(candidate)
    assert independent['candidate_sha256'] == saved_sha
    assert all(t < 10 for t in independent['stage_timings_s'].values())
    assert all(t < 10 for t in nested['stage_timings_s'].values())
    assert source.read_bytes() == source_bytes
    assert all(t < 10 for t in received['stage_timings_s'].values())
    print(json.dumps(dict(integration='complete_canonical_moved_INA_and_bypass',
        source_sha256=force._hash(source), candidate_sha256=saved_sha,
        projected_stage_timings_s=independent['stage_timings_s'],
        macro_stage_timings_s=received['stage_timings_s'],
        nested_projected_stage_timings_s=nested['stage_timings_s'],
        synthetic_fixture=True, hardware_qualification=False), sort_keys=True))


@pytest.fixture(scope='module')
def actual_saved_fault_material():
    """Reuse immutable material only; each test freshly receives all scopes."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix='quiet-fault-material-',
            dir=Path(compiler.__file__).resolve().parents[1] / 'build') as directory:
        mp = pytest.MonkeyPatch()
        try:
            yield _construct_complete_canonical_case(Path(directory), mp)
        finally:
            mp.undo()


@pytest.mark.parametrize('stage_index', range(8))
@pytest.mark.parametrize('fault', ['source', 'policy'])
def test_each_real_receiving_stage_rejects_input_or_policy_epoch_mutation(
        actual_saved_fault_material, monkeypatch, stage_index, fault):
    _receiving_fault(actual_saved_fault_material, monkeypatch, stage_index, fault)


@pytest.mark.parametrize('stage_index', [0, 4, 7])
@pytest.mark.parametrize('fault', ['candidate', 'code', 'options'])
def test_real_saved_receiver_rejects_early_path_and_final_epoch_mutation(
        actual_saved_fault_material, monkeypatch, stage_index, fault):
    _receiving_fault(actual_saved_fault_material, monkeypatch, stage_index, fault)


def _receiving_fault(material, monkeypatch, stage_index, fault):
    import cec_complete_cell_receiving as cell
    source, candidate, hint, uid, original_options, _ = material
    options = copy.deepcopy(original_options)
    path = (source if fault == 'source' else candidate.with_suffix('.kicad_pro')
        if fault == 'policy' else candidate if fault == 'candidate' else None)
    prior = path.read_bytes() if path is not None else None
    actual_epoch = force._code_identity
    epoch_fault_active = [False]
    if fault == 'code':
        # Negative-only observer injection. Never write a Python file into
        # canonical scripts: other test/receiving processes share that tree.
        # Each call still reads the actual live epoch before adding the
        # late fault, and no positive verdict or role/native fact is mocked.
        def faulted_epoch():
            live = actual_epoch()
            if epoch_fault_active[0]:
                live = dict(live, __negative_test_epoch__='f' * 64)
            return live
        monkeypatch.setattr(force, '_code_identity', faulted_epoch)
    changed = []
    def mutate():
        assert not changed
        changed.append(fault)
        if fault == 'policy':
            project = json.loads(path.read_text())
            next(c for c in project['net_settings']['classes'] if c['name'] == 'Sense')['clearance'] = .1
            path.write_text(json.dumps(project))
        elif fault == 'options': options['max_shift_mm'] = 5.
        elif fault == 'code': epoch_fault_active[0] = True
        else: path.write_bytes(prior + b'\n')
    # Phase zero emits its diagnostic before identity capture. Inject after
    # the actual native pose observer returns, so this is genuinely a live
    # mid-stage change, not a different valid starting input.
    if stage_index == 0:
        actual = cell._poses
        def mutate_after_actual_poses(*args, **kwargs):
            result = actual(*args, **kwargs); mutate(); return result
        monkeypatch.setattr(cell, '_poses', mutate_after_actual_poses)
    def observe(event):
        if stage_index and event['index'] == stage_index: mutate()
    before_epoch = actual_epoch()
    try:
        with op.observe_receiving_phases(observe):
            result = quiet.receive_projected(source, candidate, board_hint=hint,
                required_quiet_output_pad_uuids=[uid], macro_options=options, timeout_s=10.)
        assert changed == [fault], result
        assert not result['ok'] and not result['complete'], result
        assert result['errors'] and not result['routing_admitted'] and not result['release_authority']
        assert 'source_sha256' not in result and 'candidate_sha256' not in result
        assert op._observer.get() is None
    finally:
        epoch_fault_active[0] = False
        if path is not None:
            path.write_bytes(prior)
    assert actual_epoch() == before_epoch
    assert force._code_identity() == before_epoch

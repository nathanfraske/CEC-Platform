"""Native switch-cut ownership only; synthetic canonical export/current authority.

No fixture establishes barrel ampacity, an admitted route, or production readiness.
"""
import copy
import json

import pcbnew
import pytest

import cec_source_grounded_switch_cell as op
import cec_control_gate_bias_placement as gate
import cec_full_current_planar_reflow as full
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_synth_pipeline as synth
from cec_native_items import discard_items
from test_control_gate_bias_placement import fixture as canonical_fixture
from test_field_proposals import track

REAL_CURRENT_MODEL = full._model
REAL_WIDTH_FLOOR = full._source_width_floor


def fixture(tmp_path, monkeypatch, *, annotation=False):
    data = canonical_fixture(tmp_path, monkeypatch, series=False,
        names=('S9', 'opaque_bias', 'unused'))
    board, mos = data['board'], data['mos']
    board.SetCopperLayerCount(6)
    props = board.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    board.SetProperties(props)
    # The canonical MOS pin table comes from the existing complete hierarchy
    # fixture. Copper is independently native and deliberately dual-face.
    discard_items(board, list(board.GetTracks()))
    barrels = {}
    for name, number in (('source', '2'), ('drain', '3')):
        pad = mos.FindPadByNumber(number)
        pad.SetSize(pcbnew.VECTOR2I_MM(1., .65))
        via = pcbnew.PCB_VIA(board); via.SetNet(pad.GetNet())
        via.SetPosition(pad.GetPosition()); via.SetWidth(500000); via.SetDrill(250000)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetLocked(True); board.Add(via)
        barrels[name] = via
    process = pcbnew.PCB_GROUP(board); process.SetName('CEC_LOCAL_POFV_SIGNAL_VIA')
    board.Add(process); process.AddItem(barrels['drain'])
    gate_pad = mos.FindPadByNumber('1'); gate_xy = [v / 1e6 for v in gate_pad.GetPosition()]
    gate_track = track(board, gate_pad.GetNetname(), gate_xy, [gate_xy[0] - 1., gate_xy[1]], width=.2)
    fixed = pcbnew.PCB_VIA(board); fixed.SetNet(gate_pad.GetNet())
    fixed.SetPosition(gate_track.GetEnd()); fixed.SetWidth(600000); fixed.SetDrill(300000)
    fixed.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(fixed)
    drain = mos.FindPadByNumber('3'); xy = [v / 1e6 for v in drain.GetPosition()]
    front = track(board, drain.GetNetname(), xy, [xy[0] + 2., xy[1]], width=.5)
    back = track(board, drain.GetNetname(), xy, [xy[0], xy[1] + 2.], width=.5)
    back.SetLayer(pcbnew.B_Cu)
    drain_boundaries = []
    for edge in (front, back):
        via = pcbnew.PCB_VIA(board); via.SetNet(drain.GetNet())
        via.SetPosition(edge.GetEnd()); via.SetWidth(800000); via.SetDrill(400000)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(via)
        drain_boundaries.append(via)
    for face in (pcbnew.In1_Cu, pcbnew.In4_Cu):
        zone = pcbnew.ZONE(board); zone.SetNet(board.FindNet('GND')); zone.SetLayer(face)
        poly = pcbnew.SHAPE_POLY_SET(); poly.NewOutline()
        for x, y in ((16.5, 11.5), (17.5, 11.5), (17.5, 12.5), (16.5, 12.5)):
            poly.Outline(0).Append(round(x * 1000000), round(y * 1000000))
        zone.Outline().NewOutline()
        for x, y in ((16.5, 11.5), (17.5, 11.5), (17.5, 12.5), (16.5, 12.5)):
            zone.Outline().Append(round(x * 1000000), round(y * 1000000))
        zone.SetFilledPolysList(face, poly); zone.SetIsFilled(True); board.Add(zone)
    group = None
    if annotation:
        from test_source_measurement_auxiliary_join import annotation as mapped
        group = mapped(board, mos)
        # Reuse the closed-map constructor, but seat its native courtyard
        # around this MOS and honor the actual declared profile font floor.
        delta = pcbnew.VECTOR2I_MM(7.5, 1.)
        for item in mos.GraphicalItems():
            if item.GetLayer() == pcbnew.F_CrtYd: item.Move(delta)
        for item in group.GetItems():
            if item.GetClass() == 'FOOTPRINT': continue
            item.Move(delta)
            if item.GetClass() == 'PCB_TEXT':
                item.SetTextSize(pcbnew.VECTOR2I_MM(1., 1.)); item.SetTextThickness(150000)
            else: item.SetWidth(150000)
    contract = dict(net=drain.GetNetname(), role='all_terminal_conservative_aggregate',
        current_authority=dict(amps=.321, geometry_margin=1.25, margin_included=False,
            source='explicit synthetic conductor test authority'),
        routing_layers=['F.Cu', 'B.Cu'], required_by_layer_mm={'F.Cu': .123456, 'B.Cu': .123456},
        source_sink_inferred=False, branch_sharing_assumed=False,
        release_authority=False, barrel_capacity_qualified=False)
    monkeypatch.setattr(full, '_model', lambda *a, **kw:
        ('explicit_all_terminal_distributed_supply', None, copy.deepcopy(contract)))
    monkeypatch.setattr(full, '_source_width_floor', lambda *a, **kw: 500000)
    monkeypatch.setattr(ordinary, 'eligible_nets', lambda *a, **kw: {gate_pad.GetNetname()})
    field._save_field_snapshot(board, data['source'])
    data.update(barrels=barrels, fixed=fixed, gate_track=gate_track, front=front, back=back,
        drain_boundaries=drain_boundaries, process=process,
        switch_group=group, current_contract=contract,
        target=[mos.GetPosition().x / 1e6 + 1., mos.GetPosition().y / 1e6, mos.GetOrientationDegrees()])
    return data


def plan(data, **kwargs):
    return op.plan(data['source'], footprint_uuid=force._uid(data['mos']),
        target_pose=data['target'], board_hint=str(data['root']), **kwargs)


@pytest.mark.parametrize('annotation', [False, True])
def test_complete_native_switch_plan_preserves_both_drain_faces_and_literal_source(tmp_path, monkeypatch, annotation):
    data = fixture(tmp_path, monkeypatch, annotation=annotation)
    raw = data['source'].read_bytes()
    proposal = plan(data)
    assert proposal['role'] == 'source_grounded_switch_cell'
    assert proposal['source_barrels']['source']['uuid'] == force._uid(data['barrels']['source'])
    assert proposal['source_barrels']['drain']['uuid'] == force._uid(data['barrels']['drain'])
    assert set(proposal['source_retired_track_uuids']) == {
        force._uid(data[k]) for k in ('gate_track', 'front', 'back')}
    obligations = proposal['source_restore_obligations']
    assert {r['layer_id'] for r in obligations if r['role'] == 'drain'} == {0, 2}
    assert {r['source_track_uuid'] for r in obligations} == set(proposal['source_retired_track_uuids'])
    assert all(r['width_nm'] >= 500000 for r in obligations if r['role'] == 'drain')
    assert bool(proposal['source_reference_group_transport']) is annotation
    assert proposal['current_contract'] == data['current_contract']
    assert all(proposal[k] is False for k in ('routing_admitted', 'current_authority',
        'new_barrel_authority', 'release_authority'))
    assert data['source'].read_bytes() == raw


@pytest.mark.parametrize('fault', ['missing_source_barrel', 'missing_drain_barrel',
    'offcenter_source', 'offcenter_drain', 'duplicate_source', 'source_surface_branch',
    'drain_interior_contact', 'drain_too_thin', 'gate_branch', 'gate_no_fixed_via',
    'missing_reference_plane', 'no_profile', 'wrong_manufacturer', 'wrong_package', 'DNP',
    'locked_gate', 'locked_drain', 'grouped_drain', 'missing_drain_boundary', 'unknown_barrel_group'])
def test_partial_or_unowned_source_material_never_grants_a_switch_cut(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch); board = data['board']; mos = data['mos']
    if fault.startswith('missing_') and fault.endswith('_barrel'):
        discard_items(board, [data['barrels'][fault.split('_')[1]]])
    elif fault.startswith('offcenter_'):
        data['barrels'][fault.split('_')[1]].Move(pcbnew.VECTOR2I(100000, 0))
    elif fault == 'duplicate_source':
        old = data['barrels']['source']; via = pcbnew.PCB_VIA(board)
        via.SetNet(old.GetNet()); via.SetPosition(old.GetPosition()); via.SetWidth(500000)
        via.SetDrill(250000); via.SetLayerPair(0, 2); board.Add(via)
    elif fault == 'source_surface_branch':
        track(board, 'GND', (17, 12), (17, 13), width=.5)
    elif fault == 'drain_interior_contact': data['front'].SetStart(pcbnew.VECTOR2I_MM(18, 11))
    elif fault == 'drain_too_thin': data['front'].SetWidth(499999)
    elif fault == 'gate_branch': track(board, '/opaque/gate', (16.5, 10), (16.5, 9), width=.2)
    elif fault == 'gate_no_fixed_via': discard_items(board, [data['fixed']])
    elif fault == 'missing_reference_plane': next(iter(board.Zones())).UnFill()
    elif fault == 'no_profile':
        props = board.GetProperties(); props['CEC_FAB_PROFILE'] = ''; board.SetProperties(props)
    elif fault == 'wrong_manufacturer': mos.SetField('Manufacturer', 'Unknown')
    elif fault == 'wrong_package': mos.SetFPID(pcbnew.LIB_ID('fixture', 'SOT-23-6'))
    elif fault == 'DNP': mos.SetDNP(True)
    elif fault == 'locked_gate': data['gate_track'].SetLocked(True)
    elif fault == 'locked_drain': data['front'].SetLocked(True)
    elif fault == 'grouped_drain': data['process'].AddItem(data['front'])
    elif fault == 'missing_drain_boundary': discard_items(board, [data['drain_boundaries'][0]])
    elif fault == 'unknown_barrel_group': data['process'].SetName('UNKNOWN_VIA_OWNER')
    field._save_field_snapshot(board, data['source']); raw = data['source'].read_bytes()
    with pytest.raises(ValueError): plan(data)
    assert data['source'].read_bytes() == raw


def test_multiedge_gate_chain_has_one_restore_obligation_and_every_exact_retirement(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch); board = data['board']; first = data['gate_track']
    first.SetEnd(pcbnew.VECTOR2I_MM(16, 10))
    second = track(board, '/opaque/gate', (16, 10), (15.5, 10.5), width=.2)
    third = track(board, '/opaque/gate', (15.5, 10.5), (15.5, 11.5), width=.2)
    data['fixed'].SetPosition(third.GetEnd())
    field._save_field_snapshot(board, data['source'])
    proposal = plan(data)
    obligations = [r for r in proposal['source_restore_obligations'] if r['role'] == 'gate']
    assert len(obligations) == 1
    assert set(obligations[0]['source_track_uuids']) == {force._uid(first), force._uid(second), force._uid(third)}
    assert set(obligations[0]['source_track_uuids']) <= set(proposal['source_retired_track_uuids'])
    assert obligations[0]['fixed_boundary_item_uuids'] == [force._uid(data['fixed'])]


@pytest.mark.parametrize('which', ['model', 'floor'])
def test_unknown_current_model_or_face_floor_cannot_become_signal_width_authority(tmp_path, monkeypatch, which):
    data = fixture(tmp_path, monkeypatch)
    def refused(*args, **kwargs): raise ValueError('synthetic missing current authority')
    monkeypatch.setattr(full, '_model' if which == 'model' else '_source_width_floor', refused)
    with pytest.raises(ValueError, match='synthetic missing current authority'): plan(data)


@pytest.mark.parametrize('pose', [[18, 11, 1], [99, 11, 0], [float('nan'), 11, 0]])
def test_noncardinal_unbounded_or_nonfinite_pose_never_grants_a_cut(tmp_path, monkeypatch, pose):
    data = fixture(tmp_path, monkeypatch); data['target'] = pose
    with pytest.raises(ValueError): plan(data)


@pytest.mark.parametrize('fault', ['second_departure', 'midsegment_via', 'midsegment_pad',
    'foreign_crossing', 'boundary_offset', 'locked_second_edge', 'wrong_boundary_net'])
def test_gate_cut_requires_one_literal_unbranched_same_face_endpoint_chain(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch); board = data['board']
    if fault == 'second_departure': track(board, '/opaque/gate', (17, 10), (17, 9), width=.2)
    elif fault == 'midsegment_via': data['fixed'].SetPosition(pcbnew.VECTOR2I_MM(16.5, 10))
    elif fault == 'midsegment_pad':
        data['bias'].FindPadByNumber('2').SetPosition(pcbnew.VECTOR2I_MM(16.5, 10))
    elif fault == 'foreign_crossing': track(board, '/opaque/drain', (16.5, 9), (16.5, 11), width=.5)
    elif fault == 'boundary_offset': data['fixed'].Move(pcbnew.VECTOR2I(100000, 0))
    elif fault == 'wrong_boundary_net': data['fixed'].SetNet(board.FindNet('/opaque/drain'))
    elif fault == 'locked_second_edge':
        data['gate_track'].SetEnd(pcbnew.VECTOR2I_MM(16.5, 10))
        edge = track(board, '/opaque/gate', (16.5, 10), (16, 10), width=.2); edge.SetLocked(True)
    if fault in ('foreign_crossing', 'wrong_boundary_net'):
        # Hostile Source only: allow the actual native loader/canonical parity
        # to reject it even if KiCad normalizes a physically shorted net.
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(data['source']), board)
        if fault == 'wrong_boundary_net':
            literal = synth.parse_sexpr(data['source'].read_text())
            nodes = [n for n in synth._kids(literal, 'via')
                if synth._val(n, 'uuid', '') == force._uid(data['fixed'])]
            assert len(nodes) == 1 and synth._val(nodes[0], 'net', '') == '/opaque/drain'
    else: field._save_field_snapshot(board, data['source'])
    with pytest.raises(ValueError): plan(data)


@pytest.mark.parametrize('number', ['1', '2', '3'])
def test_canonical_export_requires_exact_gate_source_and_drain_names(tmp_path, monkeypatch, number):
    data = fixture(tmp_path, monkeypatch)
    for net in synth._kids(synth._first(data['tree'], 'nets'), 'net'):
        for node in synth._kids(net, 'node'):
            if synth._val(node, 'ref', '') == data['mos'].GetReference() and synth._val(node, 'pin', '') == number:
                synth._first(node, 'pinfunction')[1] = 'incorrect_function'
    with pytest.raises(ValueError): plan(data)


def test_actual_full_current_lookup_refuses_absent_synthetic_board_authority(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(full, '_model', REAL_CURRENT_MODEL)
    with pytest.raises(ValueError): plan(data)


def test_actual_source_floor_cannot_be_reduced_to_the_current_only_width(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch)
    data['front'].SetWidth(200000)
    project = json.loads(data['source'].with_suffix('.kicad_pro').read_text())
    project['net_settings']['netclass_patterns'].append(dict(netclass='Power', pattern='/opaque/drain'))
    data['source'].with_suffix('.kicad_pro').write_text(json.dumps(project))
    field._save_field_snapshot(data['board'], data['source'])
    monkeypatch.setattr(full, '_source_width_floor', REAL_WIDTH_FLOOR)
    with pytest.raises(ValueError, match='below_whole_current_floor'): plan(data)


@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_retained_midsegment_drain_tap_needs_its_own_boundary_not_only_a_logged_contact(tmp_path, monkeypatch, face):
    data = fixture(tmp_path, monkeypatch)
    if face == pcbnew.F_Cu:
        start, end = (20, 11), (20, 12)
    else:
        start, end = (19, 12), (20, 12)
    branch = track(data['board'], '/opaque/drain', start, end, width=.5)
    branch.SetLayer(face)
    field._save_field_snapshot(data['board'], data['source'])
    raw = data['source'].read_bytes()
    with pytest.raises(ValueError): plan(data)
    assert data['source'].read_bytes() == raw

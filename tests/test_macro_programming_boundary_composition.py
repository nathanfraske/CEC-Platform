"""A retired passive-to-passive bend is not a surviving routing terminal."""
import copy
import time
from pathlib import Path

import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_force_current as force
import cec_macro_boundary_composition as compose
import cec_macro_cut_components as components
import cec_programming_resistor_placement as programming
from cec_native_items import discard_items
from test_programming_resistor_placement import fixture as programming_fixture


def fixture(tmp_path, monkeypatch, quarter=0, back=False, retained=False):
    board, owner, lower, root, tree, _ = programming_fixture(
        tmp_path, monkeypatch, monitor_pin='5')
    upper = board.FindFootprintByReference('R_upper')
    upper.SetPosition(pcbnew.VECTOR2I_MM(49, 12))
    discard_items(board, list(board.GetTracks()))
    nodes = [upper.FindPadByNumber('2'), lower.FindPadByNumber('1')]
    join = pcbnew.VECTOR2I_MM(51.5, 12)
    edges = []
    for pad in nodes:
        edge = pcbnew.PCB_TRACK(board)
        edge.SetStart(pad.GetPosition()); edge.SetEnd(join)
        edge.SetWidth(250000); edge.SetLayer(pcbnew.F_Cu)
        edge.SetNetCode(pad.GetNetCode()); board.Add(edge); edges.append(edge)
    via = None
    if retained == 'track':
        via = pcbnew.PCB_TRACK(board); via.SetStart(join)
        via.SetEnd(join + pcbnew.VECTOR2I(0, 2000000))
        via.SetWidth(250000); via.SetLayer(pcbnew.F_Cu)
        via.SetNetCode(nodes[0].GetNetCode()); board.Add(via)
    elif retained:
        via = pcbnew.PCB_VIA(board); via.SetPosition(join)
        via.SetWidth(500000); via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(nodes[0].GetNetCode()); board.Add(via)
    if back:
        for fp in board.GetFootprints():
            fp.Flip(pcbnew.VECTOR2I(0, 0), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for edge in edges:
            edge.Flip(pcbnew.VECTOR2I(0, 0), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if via: via.Flip(pcbnew.VECTOR2I(0, 0), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if quarter:
        for item in [*board.GetFootprints(), *board.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I(0, 0), pcbnew.EDA_ANGLE(90 * quarter, pcbnew.DEGREES_T))
    source = Path(board.GetFileName()); field._save_field_snapshot(board, source)
    poses = {fp.GetReference(): [fp.GetPosition().x / 1e6,
        fp.GetPosition().y / 1e6 + .5, fp.GetOrientationDegrees()] for fp in (upper, lower)}
    selected = programming.plan(board, poses, board_hint=str(root))
    assert selected and selected[lower.GetReference()]['source_monitor_divider']['upper_motion']
    plan = dict(scope='source_typed_complete_cell_escape_proposal',
        source_native_binding=row._source_binding(board), board_hint=str(root),
        retired_track_uuids=[force._uid(e) for e in edges], poses=poses,
        device_contracts={}, selected_programming_resistors=selected)
    requests = {'boundary:' + force._uid(edge): dict(kind='source_boundary',
        net=pad.GetNetname(), width_nm=250000,
        a=dict(pad_uuid=force._uid(pad), at_nm=list(pad.GetPosition()), layers=[int(edge.GetLayer())]),
        b=dict(at_nm=list(edge.GetEnd()), layers=[int(edge.GetLayer())]))
        for edge, pad in zip(edges, nodes)}
    # One request reversed to exercise both source endpoint orders.
    reverse = requests['boundary:' + force._uid(edges[1])]
    reverse['a'], reverse['b'] = reverse['b'], reverse['a']
    monkeypatch.setattr(compose.ordinary, 'eligible_nets', lambda *a: {nodes[0].GetNetname()})
    return board, source, plan, requests, nodes, edges, via


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('retained', [False, True, 'track'])
def test_actual_source_programming_pair_composes_and_keeps_every_real_port(
        tmp_path, monkeypatch, quarter, back, retained):
    board, source, plan, requests, nodes, edges, via = fixture(tmp_path, monkeypatch, quarter, back, retained)
    before = source.read_bytes(); binding = row._source_binding(board)
    original = copy.deepcopy(plan); old = copy.deepcopy(requests)
    pending, extras, proofs = compose.compose(board, source, plan, requests, [], deadline=time.monotonic() + 10.)
    assert not pending and len(extras) == len(proofs) == 2
    retired = set(plan['retired_track_uuids'])
    assert {q['change']['uuid'] for q in extras} == retired
    assert {p['original_request_id'] for p in proofs} == set(requests)
    assert all(p['source_composition_proof']['no_additional_source_edge_retired'] for p in proofs)
    private = pcbnew.LoadBoard(str(source))
    for ref, target in plan['poses'].items():
        fp = private.FindFootprintByReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(*target[:2])); fp.SetOrientationDegrees(target[2])
    discard_items(private, [t for t in private.GetTracks() if force._uid(t) in retired])
    transport = dict(source_process_barrel_motion=[], explicit_source_typed_ordinary_barrel_motion=[])
    demands, groups = components.requests(board, private, extras, retired, transport,
        project_contacts=compiler._project_contacts, deadline=time.monotonic() + 10.)
    expected = {force._uid(p) for p in nodes}
    if via: expected.add(force._uid(via))
    assert len(groups) == 1 and len(demands) == len(expected) - 1
    assert {c['source_item_uuid'] for c in groups[0]['surviving_contacts']} == expected
    assert all(q['every_surviving_source_component_port_mandatory'] for q in demands.values())
    assert plan == original and requests == old
    assert source.read_bytes() == before and row._source_binding(board) == binding


@pytest.mark.parametrize('fault', ['forged_selection', 'missing_selection', 'supply_pad',
    'ground_pad', 'width', 'wider_demand', 'native_width', 'source_contact', 'stale_binding'])
def test_pair_composition_cannot_invent_source_roles_or_copper_ownership(tmp_path, monkeypatch, fault):
    board, source, plan, requests, nodes, edges, via = fixture(tmp_path, monkeypatch)
    request = next(iter(requests.values()))
    if fault == 'forged_selection':
        next(iter(plan['selected_programming_resistors'].values()))['net'] = 'forged'
    elif fault == 'missing_selection': plan['selected_programming_resistors'] = {}
    elif fault in ('supply_pad', 'ground_pad'):
        fp = nodes[0 if fault == 'supply_pad' else 1].GetParentFootprint()
        request['a']['pad_uuid'] = force._uid(fp.FindPadByNumber('1' if fault == 'supply_pad' else '2'))
    elif fault == 'width': request['width_nm'] = 100000
    elif fault == 'wider_demand': request['width_nm'] = 300000
    elif fault == 'stale_binding': plan['source_native_binding'] = 'forged'
    else:
        if fault == 'native_width': edges[0].SetWidth(800000)
        else: edges[0].SetStart(edges[0].GetStart() + pcbnew.VECTOR2I(0, 1000000))
        field._save_field_snapshot(board, source)
        plan['source_native_binding'] = row._source_binding(board)
    with pytest.raises(ValueError):
        compose.compose(board, source, plan, requests, [], deadline=time.monotonic() + 10.)


@pytest.mark.parametrize('fault', ['not_owned', 'different_join', 'ground', 'already_extra'])
def test_incomplete_base_pairs_remain_mandatory(tmp_path, monkeypatch, fault):
    board, source, plan, requests, nodes, edges, via = fixture(tmp_path, monkeypatch)
    extras = []
    if fault == 'not_owned': plan['retired_track_uuids'].pop()
    elif fault == 'different_join': next(iter(requests.values()))['b']['at_nm'][0] += 1
    elif fault == 'ground':
        for request in requests.values(): request['net'] = 'GND'
    else: extras = [dict(change=dict(uuid=force._uid(edges[0])), authority={})]
    pending, result, proofs = compose.compose(board, source, plan, requests, extras, deadline=time.monotonic() + 10.)
    assert pending == requests and result == extras and not proofs

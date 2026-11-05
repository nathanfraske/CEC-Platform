"""Saved native repair contracts have bounded geometry and no role escalation."""
import copy
import json
from types import SimpleNamespace
from unittest import mock
import pcbnew
import pytest

from cec_pipeline import routes
from cec_pipeline.construction import _construct
import cec_force_current as force
import cec_field_coupling as field
from test_lastmile import _board
from test_field_proposals import track


STRAIGHT = [[5000000, 5000000], [15000000, 5000000]]
DETOUR = [[5000000, 5000000], [7000000, 5000000],
          [9000000, 7000000], [11000000, 7000000],
          [13000000, 5000000], [15000000, 5000000]]


def fixture(tmp_path, *, net='/CONTROL', barrels=False, roles='SIG/GND/SIG/SIG/GND/SIG'):
    board = _board([(5, 5, net), (15, 5, net)], edge=(0, 0, 25, 25))
    board.SetCopperLayerCount(6)
    props = board.GetProperties()
    props['CEC_STACKUP_ROLES'] = roles
    board.SetProperties(props)
    item = track(board, net, (5, 5), (15, 5), width=.2)
    item.SetLocked(True)
    ids = [force._uid(item)]
    if barrels:
        for point in STRAIGHT:
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pcbnew.VECTOR2I(*point))
            via.SetNetCode(item.GetNetCode())
            via.SetWidth(600000)
            via.SetDrill(300000)
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            board.Add(via)
    source = tmp_path/'source'/'board.kicad_pcb'
    source.parent.mkdir()
    field._save_field_snapshot(board, source)
    operation = dict(kind='repair_chain', track_uuids=ids,
                     allow_locked_track_uuids=ids, points_nm=copy.deepcopy(DETOUR),
                     layer='F.Cu', max_added_length_nm=2000000)
    return source, operation


def child(tmp_path, source, operation):
    target = force._copy_family(source, tmp_path/'child')
    _construct(source, target, dict(operations=[operation], target_field_issue_ids=['field-target']), 'synthetic')
    return target


def test_same_face_repair_allows_explicit_bounded_growth_without_touching_source(tmp_path):
    source, operation = fixture(tmp_path)
    original = source.read_bytes()
    target = child(tmp_path, source, operation)
    result = routes.receive(source, target, operation, board_hint='synthetic')
    assert result['ok'] and result['complete']
    assert result['candidate_length_nm'] > result['source_length_nm']
    assert not result['existing_barrel_uuids']
    assert not result['new_barrels_or_power_authority']
    assert source.read_bytes() == original


@pytest.mark.parametrize('fault', ['port', 'tangent', 'growth', 'negative', 'bool', 'unbounded'])
def test_source_ports_tangents_and_growth_are_not_waived(tmp_path, fault):
    source, op = fixture(tmp_path)
    if fault == 'port': op['points_nm'][0][0] += 100000
    elif fault == 'tangent': op['points_nm'] = [STRAIGHT[0], [7000000, 7000000], [13000000, 7000000], STRAIGHT[-1]]
    elif fault == 'growth': op['max_added_length_nm'] = 0
    elif fault == 'negative': op['max_added_length_nm'] = -1
    elif fault == 'bool': op['max_added_length_nm'] = True
    else: op['max_added_length_nm'] = 16000001
    with pytest.raises(ValueError): child(tmp_path, source, op)


@pytest.mark.parametrize('fault', ['actual_path', 'width', 'layer', 'lock', 'growth_scope', 'new_via'])
def test_independent_receiver_reads_actual_native_child_not_authored_claims(tmp_path, fault):
    source, op = fixture(tmp_path)
    target = child(tmp_path, source, op)
    board = pcbnew.LoadBoard(str(target))
    incoming = list(board.GetTracks())
    item = incoming[0]
    if fault == 'actual_path': item.SetStart(item.GetStart()+pcbnew.VECTOR2I(100000, 0))
    elif fault == 'width': item.SetWidth(250000)
    elif fault == 'layer': item.SetLayer(pcbnew.In2_Cu)
    elif fault == 'lock': item.SetLocked(False)
    elif fault == 'growth_scope': op['max_added_length_nm'] = 0
    else:
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(item.GetStart())
        via.SetNetCode(item.GetNetCode())
        via.SetWidth(600000)
        via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(via)
    field._save_field_snapshot(board, target)
    with pytest.raises(ValueError): routes.receive(source, target, op, board_hint='synthetic')


def test_relayer_requires_literal_existing_through_barrels_and_source_signal_role(tmp_path):
    source, op = fixture(tmp_path, barrels=True)
    op.update(layer='In2.Cu', points_nm=copy.deepcopy(STRAIGHT), max_added_length_nm=0)
    target = child(tmp_path, source, op)
    proof = routes.receive(source, target, op, board_hint='synthetic')
    assert len(proof['existing_barrel_uuids']) == 2
    assert proof['target_layer'] == pcbnew.In2_Cu
    before = pcbnew.LoadBoard(str(source))
    after = pcbnew.LoadBoard(str(target))
    assert {force._uid(t) for t in before.GetTracks() if t.GetClass() == 'PCB_VIA'} == {force._uid(t) for t in after.GetTracks() if t.GetClass() == 'PCB_VIA'}


@pytest.mark.parametrize('fault', ['missing_barrels', 'plane', 'missing_roles', 'blind'])
def test_relayer_cannot_invent_barrels_or_claim_plane_faces(tmp_path, fault):
    source, op = fixture(tmp_path, barrels=fault != 'missing_barrels', roles='' if fault == 'missing_roles' else 'SIG/GND/SIG/SIG/GND/SIG')
    op.update(layer='In1.Cu' if fault == 'plane' else 'In2.Cu', points_nm=copy.deepcopy(STRAIGHT))
    if fault == 'blind':
        board = pcbnew.LoadBoard(str(source))
        for item in board.GetTracks():
            if item.GetClass() == 'PCB_VIA': item.SetViaType(pcbnew.VIATYPE_BLIND)
        field._save_field_snapshot(board, source)
    with pytest.raises(ValueError): child(tmp_path, source, op)


@pytest.mark.parametrize('net', ['+5V', 'GND', '/USB_D_P', '/CAN_H', '/SENSE_HI'])
def test_repair_does_not_grant_power_pair_or_sense_authority(tmp_path, net):
    source, op = fixture(tmp_path, net=net)
    with pytest.raises(ValueError): child(tmp_path, source, op)


@pytest.mark.parametrize('missing_target', [True, False])
def test_repair_requires_one_operation_and_explicit_field_target(tmp_path, missing_target):
    source, op = fixture(tmp_path)
    target = force._copy_family(source, tmp_path/'child')
    request = dict(operations=[op] if missing_target else [op, copy.deepcopy(op)],
                   target_field_issue_ids=[] if missing_target else ['field-target'])
    with pytest.raises(ValueError): _construct(source, target, request, 'synthetic')


def test_repair_selection_requires_both_native_transaction_delta_and_route_contract():
    from cec_pipeline.execution import required_gates
    gates = required_gates(dict(ordinary_only=True, kinds=['repair_chain']))
    assert 'transaction_delta' in gates
    assert 'route_contract' in gates
    assert len(gates) == len(set(gates))


def qualified_profile_fixture(tmp_path):
    """Generate an actual canonical buildup through the normal board builder."""
    import cec_pcb
    import cec_fab_profile as fab
    import cec_constraints as constraints
    profile = 'jlcpcb_6l_pofv_high_current'
    source = tmp_path/'qualified.kicad_pcb'
    with mock.patch.object(cec_pcb, 'parse_netlist', return_value=({}, {}, {'/CONTROL': []})):
        cec_pcb.build_board(str(source), 'synthetic.net', {}, [], None, 25, 25,
                            zones=False, stackup_profile=profile)
    board = pcbnew.LoadBoard(str(source))
    if board.GetNetcodeFromNetname('/CONTROL') < 1:
        board.Add(pcbnew.NETINFO_ITEM(board, '/CONTROL'))
    item = track(board, '/CONTROL', (5, 5), (15, 5), width=.2)
    item.SetLayer(pcbnew.In2_Cu)
    for point in STRAIGHT:
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(*point))
        via.SetNetCode(item.GetNetCode())
        via.SetWidth(600000)
        via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        board.Add(via)
    field._save_field_snapshot(board, source)
    board = pcbnew.LoadBoard(str(source))
    assert constraints._fab_profile_errors(board, source, profile) == []
    assert len(fab.get_profile(profile)['roles']) == 6
    cut = [t for t in board.GetTracks() if t.GetClass() == 'PCB_TRACK']
    op = dict(layer='B.Cu', max_added_length_nm=0)
    return source, board, cut, op


@pytest.mark.parametrize('face', ['F.Cu', 'B.Cu'])
def test_qualified_compound_outer_signal_power_role_is_one_physical_layer(tmp_path, face):
    source, board, cut, op = qualified_profile_fixture(tmp_path)
    original = source.read_bytes()
    op['layer'] = face
    props = {str(k): str(v) for k, v in board.GetProperties().items()}
    assert len(props['CEC_STACKUP_ROLES'].split('/')) == 8
    result = routes.policy(board, cut, copy.deepcopy(STRAIGHT), op)
    assert result['target_layer'] == board.GetLayerID(face)
    assert len(result['existing_barrel_uuids']) == 2
    assert source.read_bytes() == original


@pytest.mark.parametrize('fault', ['vendor', 'roles', 'profile', 'copper', 'dielectric', 'missing_profile'])
def test_profile_relayer_requires_saved_native_buildup_not_just_a_profile_claim(tmp_path, fault):
    source, board, cut, op = qualified_profile_fixture(tmp_path)
    if fault in ('vendor', 'roles', 'profile', 'missing_profile'):
        props = board.GetProperties()
        if fault == 'vendor': props['CEC_VENDOR_STACKUP'] = 'wrong-stackup'
        elif fault == 'roles': props['CEC_STACKUP_ROLES'] = 'SIG/GND/SIG/PWR/GND/SIG'
        elif fault == 'profile': props['CEC_FAB_PROFILE'] = 'unknown-profile'
        else:
            # A compound display string without its declared profile is not a
            # parseable fallback or authority from a board-family filename.
            props['CEC_FAB_PROFILE'] = ''
        board.SetProperties(props)
        field._save_field_snapshot(board, source)
    else:
        text = source.read_text()
        if fault == 'copper':
            assert '(thickness 0.07)' in text
            text = text.replace('(thickness 0.07)', '(thickness 0.035)', 1)
        else:
            assert '(thickness 0.0994)' in text
            text = text.replace('(thickness 0.0994)', '(thickness 0.1994)', 1)
        source.write_text(text)
    board = pcbnew.LoadBoard(str(source))
    cut = [t for t in board.GetTracks() if t.GetClass() == 'PCB_TRACK']
    control = source.read_bytes()
    with pytest.raises(ValueError): routes.policy(board, cut, copy.deepcopy(STRAIGHT), op)
    assert source.read_bytes() == control


@pytest.mark.parametrize('state', ['missing', 'failed'])
def test_actual_verdict_refuses_missing_or_failed_route_contract(tmp_path, state):
    from cec_pipeline.workbench import Workbench
    from cec_pipeline.execution import required_gates
    from cec_pipeline.identity import inspection
    source, op = fixture(tmp_path)
    target = child(tmp_path, source, op)
    construction = dict(ordinary_only=True, kinds=['repair_chain'])
    data = dict(candidate=str(target), source_sha256=inspection.sha(source),
                request=dict(operations=[op], target_field_issue_ids=['a'*64]))
    path = target.parent/'job.json'
    path.write_text(json.dumps(data))
    for step in ('construct', *required_gates(construction)):
        if step == 'route_contract' and state == 'missing':
            continue
        result = construction if step == 'construct' else dict(
            ok=not(step == 'route_contract' and state == 'failed'),
            complete=True, counts=dict(opens=0, errors=0, exclusions=0))
        (path.parent/(step+'.json')).write_text(json.dumps(dict(
            complete=True, candidate_sha256=inspection.sha(target), result=result)))
    fake = SimpleNamespace(_job=lambda token: (path, data))
    verdict = Workbench.verdict(fake, 'synthetic-repair-job')
    assert verdict['ok'] is False and verdict['selected'] is False
    if state == 'missing':
        assert 'route_contract' in verdict['missing']
    else:
        assert any('route_contract' in reason for reason in verdict['failed'])


@pytest.mark.parametrize('fault', ['retained_via', 'retained_zone'])
def test_mandatory_native_delta_rejects_mutated_unowned_retained_objects(tmp_path, fault):
    import cec_ordinary_route_receiving as ordinary
    source, op = fixture(tmp_path, barrels=True)
    if fault == 'retained_zone':
        board = pcbnew.LoadBoard(str(source))
        board.Add(pcbnew.NETINFO_ITEM(board, 'GND'))
        zone = pcbnew.ZONE(board)
        zone.SetLayer(pcbnew.F_Cu)
        zone.SetNetCode(board.GetNetcodeFromNetname('GND'))
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        zone.Outline().NewOutline()
        for point in [(20000000, 20000000), (22000000, 20000000),
                      (22000000, 22000000), (20000000, 22000000)]:
            zone.Outline().Append(*point)
        board.Add(zone)
        import cec_additive_route_receiving as additive
        additive._ground_refill(board)
        field._save_field_snapshot(board, source)
    target = child(tmp_path, source, op)
    control = source.read_bytes()
    baseline = ordinary.receive(source, target, board_hint='synthetic',
                                retired_track_uuids=op['track_uuids'],
                                allow_locked_track_uuids=op['allow_locked_track_uuids'])
    assert baseline['ok'] and baseline['complete'], baseline
    board = pcbnew.LoadBoard(str(target))
    if fault == 'retained_via':
        via = next(t for t in board.GetTracks() if t.GetClass() == 'PCB_VIA')
        via.SetWidth(via.GetWidth()+100000)
    else:
        zone = next(iter(board.Zones()))
        zone.SetLocalClearance(450000)
    field._save_field_snapshot(board, target)
    # Contract-owned route geometry is still valid; the mandatory native
    # transaction delta independently owns retained object preservation.
    assert routes.receive(source, target, op, board_hint='synthetic')['ok']
    result = ordinary.receive(source, target, board_hint='synthetic',
                              retired_track_uuids=op['track_uuids'],
                              allow_locked_track_uuids=op['allow_locked_track_uuids'])
    assert result['ok'] is False and result['errors']
    assert source.read_bytes() == control

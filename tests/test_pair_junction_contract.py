"""Native shared-junction and dimensional-authority regressions, no board IDs."""
from unittest.mock import patch
import json
import pytest
import pcbnew
import cec_precision_route as route
import cec_fab_profile as fab


def fixture():
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    props = board.GetProperties()
    props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    board.SetProperties(props)
    pads = []
    for name in ('P', 'N', 'foreign'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    for ref, name, x, y in [('A', 'P', 3, 4), ('B', 'N', 3, 5),
                             ('C', 'P', 8, 4), ('D', 'N', 8, 5)]:
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); board.Add(fp)
        pad = pcbnew.PAD(fp); pad.SetNumber('1')
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.8, .8))
        pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
        pad.SetNet(board.FindNet(name)); fp.Add(pad); pads.append(pad)
    return board, pads


def add_via(board, pad, *, diameter=.35, drill=.25, net=None):
    via = pcbnew.PCB_VIA(board); via.SetPosition(pad.GetPosition())
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetWidth(pcbnew.FromMM(diameter)); via.SetDrill(pcbnew.FromMM(drill))
    via.SetNet(board.FindNet(net) if net else pad.GetNet())
    board.Add(via)
    return via


def test_qualified_existing_barrel_is_reused_by_exact_identity():
    board, pads = fixture(); via = add_via(board, pads[0])
    result = route._existing_endpoint_barrel(board, pads[0], pads[0].GetPosition(), pcbnew.In2_Cu)
    assert result['status'] == 'reused'
    assert result['uuids'] == [via.m_Uuid.AsString()]
    assert len(list(board.GetTracks())) == 1


@pytest.mark.parametrize('problem', ['duplicate', 'foreign', 'unqualified', 'wrong_span'])
def test_existing_hole_is_not_permission_to_overlay_another(problem):
    board, pads = fixture()
    via = add_via(board, pads[0], diameter=.2 if problem == 'unqualified' else .35,
                  net='foreign' if problem == 'foreign' else None)
    if problem == 'duplicate': add_via(board, pads[0])
    if problem == 'wrong_span':
        via.SetViaType(pcbnew.VIATYPE_BLIND)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.In1_Cu)
    assert route._existing_endpoint_barrel(
        board, pads[0], pads[0].GetPosition(), pcbnew.In2_Cu)['status'] == 'refused'


def test_nearby_barrel_is_not_claimed_as_exact_endpoint():
    board, pads = fixture(); via = add_via(board, pads[0])
    via.Move(pcbnew.VECTOR2I(1, 0))
    assert route._existing_endpoint_barrel(
        board, pads[0], pads[0].GetPosition(), pcbnew.In2_Cu)['status'] == 'absent'


def test_new_via_guard_rejects_same_net_occupied_origin():
    # Reach the occupied-origin predicate with legal new-hole dimensions;
    # an undersized request is correctly refused at the earlier native floor.
    board, pads = fixture(); via = add_via(board, pads[0], diameter=.5, drill=.3); evidence = {}
    assert not route.cec_fr._via_spot_clear(
        board, via.GetPosition(), via.GetWidth(), pcbnew.FromMM(.2),
        {via.GetNetCode()}, drill_nm=via.GetDrillValue(), net_code=via.GetNetCode(), report=evidence)
    assert evidence['reason'] == 'existing via occupies drill origin'
    assert evidence['blockers'][0]['uuid'] == via.m_Uuid.AsString()


def test_new_hole_clearance_is_net_independent_and_replacement_is_identity_bound():
    board, pads = fixture(); via = add_via(board, pads[0])
    code = via.GetNetCode(); at = via.GetPosition()
    kwargs = dict(drill_nm=via.GetDrillValue(), net_code=code)
    assert not route.cec_fr._via_spot_clear(
        board, at + pcbnew.VECTOR2I(1,0), via.GetWidth(), 200000, {code}, **kwargs)
    assert route.cec_fr._via_spot_clear(
        board, at, via.GetWidth(), 200000, {code}, existing_via_uuid=via.m_Uuid.AsString(), **kwargs)
    assert not route.cec_fr._via_spot_clear(
        board, at, via.GetWidth(), 200000, {code}, existing_via_uuid='missing', **kwargs)
    add_via(board, pads[0])
    assert not route.cec_fr._via_spot_clear(
        board, at, via.GetWidth(), 200000, {code}, existing_via_uuid=via.m_Uuid.AsString(), **kwargs)


@pytest.mark.parametrize('kind', ['pad','track','via'])
@pytest.mark.parametrize('cached', [False,True])
def test_stricter_foreign_item_clearance_reaches_exact_collision_and_spatial_index(kind,cached,tmp_path):
    board, pads = fixture()
    if kind == 'pad':
        item = pads[2]; item.SetNet(board.FindNet('foreign'))
        item.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
        item.SetPosition(pcbnew.VECTOR2I_MM(10,6))
    elif kind == 'via':
        item = add_via(board,pads[2],diameter=.2,drill=.1,net='foreign')
        item.SetPosition(pcbnew.VECTOR2I_MM(10,6))
    else:
        emit_track(board,'foreign',.01)
        item = list(board.GetTracks())[-1]
        item.SetStart(pcbnew.VECTOR2I_MM(10,6));item.SetEnd(pcbnew.VECTOR2I_MM(10.01,6))
        item.SetLayer(pcbnew.F_Cu)
    path = tmp_path/'board.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    path.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings': {
        'classes': [{'name':'Default','clearance':.2}, {'name':'strict','clearance':.25}],
        'netclass_patterns': [{'netclass':'strict','pattern':'foreign'}]}}))
    board = pcbnew.LoadBoard(str(path))
    obstacle = next(obj for obj in [*board.GetPads(),*board.GetTracks()] if obj.GetNetname()=='foreign')
    assert route.cec_fr._foreign_clearance_resolver(board)(obstacle,pcbnew.F_Cu)==250000, (
        board.GetFileName(), obstacle.GetNetname(), obstacle.GetOwnClearance(0),
        path.with_suffix('.kicad_pro').read_text())
    cache = {} if cached else None
    for y, expected in [(6.425,False),(6.451,True)]:
        assert route.cec_fr._tap_foreign_clear(
            board, pcbnew.VECTOR2I_MM(9.9,y),pcbnew.VECTOR2I_MM(10.1,y),
            pcbnew.FromMM(.2),pcbnew.F_Cu,pcbnew.FromMM(.2),
            {board.GetNetcodeFromNetname('P'),board.GetNetcodeFromNetname('N')},
            foreign_cache=cache) is expected


@pytest.mark.parametrize('fail', [False, True])
def test_shared_pofv_endpoint_reuses_and_rolls_back_only_new_copper(fail):
    board, pads = fixture()
    before = {add_via(board, pad).m_Uuid.AsString() for pad in pads[:2]}
    pair = dict(name='arbitrary', p='P', n='N', width=.2, gap=.25, clearance=.25)
    with patch.object(route, 'route_coupled_pair', return_value=(
            {'refused': 'test blockage'} if fail else {'route_mode': 'native-test'})), \
         patch.object(route, '_add_pair_transition_returns', return_value=([], 'covered')):
        result = route._route_coupled_endpoint_pofv(
            board, pair, ((3,4),(8,4),(3,5),(8,5)), target_layer='In2.Cu')
    after = {item.m_Uuid.AsString() for item in board.GetTracks()}
    assert before <= after
    if fail:
        assert result.get('refused') and after == before
    else:
        assert not result.get('refused'), result
        assert len(after) == 4 and len(result['pofv']['reused_barrels']) == 2


@pytest.mark.parametrize('requested,expected', [(None,.25),(.2,.25),(.3,.3)])
def test_override_cannot_reduce_declared_clearance(requested, expected):
    board, _ = fixture()
    assert route._pair_clearance(board, {'clearance': .25}, requested) == expected


def test_actual_pair_route_consumes_declared_clearance_on_every_guard():
    board, _ = fixture(); observed = []
    pair = dict(name='arbitrary', p='P', n='N', width=.2, gap=.25, clearance=.25)
    def guard(*args, **kwargs):
        observed.append(args[5]); return False
    with patch.object(route, '_route_paired_stub', return_value={'refused': 'prefilter'}), \
         patch.object(route.cec_fr, '_edge_leg_clear', return_value=True), \
         patch.object(route.cec_fr, '_tap_foreign_clear', side_effect=guard):
        result = route.route_coupled_pair(board, pair, endpoints=((3,4),(8,4),(3,5),(8,5)),
                                          allow_layer_transitions=False)
    assert result.get('refused')
    assert observed and set(observed) == {pcbnew.FromMM(.25)}


def test_nonfinite_clearance_fails_closed():
    board, _ = fixture()
    with pytest.raises(ValueError): route._pair_clearance(board, {'clearance': float('nan')})


def test_changed_or_invalid_project_cannot_reuse_old_clearance_table(tmp_path):
    board, pads = fixture(); path = tmp_path/'board.kicad_pcb'
    pcbnew.SaveBoard(str(path),board)
    project = path.with_suffix('.kicad_pro')
    board.SetFileName(str(path))
    for value in (.26,.35):
        project.write_text(json.dumps({'net_settings': {
            'classes':[{'name':'Default','clearance':value}]}}))
        assert route.cec_fr._foreign_clearance_resolver(board)(pads[0],pcbnew.F_Cu)==pcbnew.FromMM(value)
    project.write_text('{invalid')
    with pytest.raises(ValueError): route.cec_fr._foreign_clearance_resolver(board)


def emit_track(board, net, length):
    item = pcbnew.PCB_TRACK(board); item.SetNet(board.FindNet(net))
    item.SetLayer(pcbnew.In2_Cu); item.SetWidth(pcbnew.FromMM(.2))
    item.SetStart(pcbnew.VECTOR2I_MM(2, 10))
    item.SetEnd(pcbnew.VECTOR2I_MM(2 + length, 10)); board.Add(item)


def tree_fixture():
    return dict(ports={name: dict(p=(index*5,0), n=(index*5,1),
                                 center=(index*5,.5), layers=['F.Cu'], through=False)
                       for index,name in enumerate(('A','B','C'))},
                edges=[dict(a='A',b='B',length_mm=5,layers=['F.Cu']),
                       dict(a='B',b='C',length_mm=4,layers=['F.Cu'])],
                terminals=['A','B','C'], preferred_signal_layers=['F.Cu'])


def test_whole_tree_skew_failure_tries_next_bounded_order_and_preserves_parent():
    board, _ = fixture(); plan = tree_fixture(); calls = []
    parent = add_via(board, list(board.GetFootprints())[0].Pads()[0])
    pair = dict(name='arbitrary',kind='can',p='P',n='N',width=.2,gap=.25)
    def edge(*args, **kwargs):
        # Both initial edges have legal local 3 mm skew, but total 6 mm fails.
        calls.append(kwargs)
        if len(calls) == 3:
            assert {item.m_Uuid.AsString() for item in board.GetTracks()} == {parent.m_Uuid.AsString()}
        emit_track(board, 'P', 6 if len(calls) <= 2 else 3)
        emit_track(board, 'N', 3)
        return {'segments': 2}
    with patch.object(route, 'route_coupled_pair', side_effect=edge), \
         patch.object(route, '_drop_fully_covered_tracks', return_value={}), \
         patch.object(route, '_pair_graph_geometry', return_value={'ok':True}), \
         patch.object(route, '_pair_transaction_detour', return_value={'ok':True}):
        result = route._route_multidrop_topologies(board, pair, plan)
    assert len(calls) == 4 and not result.get('refused')
    assert result['topology_attempts'][0]['attempt']['physical_skew_admission']['skew_mm'] == 6
    assert result['physical_skew_admission']['skew_mm'] == 0


def test_native_terminal_allowance_is_actual_copper_bounded_not_airline_bounded():
    board, _ = fixture(); plan = tree_fixture(); plan['edges'] = plan['edges'][:1]
    plan['edges'][0].update(bounded_terminal_fanout=True,terminal_fanout_limit_mm=8)
    pair = dict(name='arbitrary',kind='can',p='P',n='N',width=.2,gap=.25)
    def edge(*args, **kwargs):
        assert kwargs['minimum_coupled_fraction'] == 0
        emit_track(board, 'P', 9); emit_track(board, 'N', 7)
        return {'segments': 2}
    with patch.object(route, 'route_coupled_pair', side_effect=edge), \
         patch.object(route, '_drop_fully_covered_tracks', return_value={}), \
         patch.object(route, '_pair_graph_geometry', return_value={'ok':True}), \
         patch.object(route, '_pair_transaction_detour', return_value={'ok':True}):
        result = route._route_direct_pair_tree(board, pair, plan)
    assert result.get('refused') and not list(board.GetTracks())
    assert not result['legs'][0]['bounded_terminal_contract']['ok']

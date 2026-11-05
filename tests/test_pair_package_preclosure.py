"""Topology-selected local-first pair construction and transaction rollback."""
from unittest.mock import patch

import pcbnew
import pytest
import cec_precision_route as route


def fixture(angle, names):
    board = pcbnew.BOARD()
    board.GetDesignSettings().m_MinClearance = pcbnew.FromMM(.2)
    for name in (*names, 'GND'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    for a, b in [((0, 0), (40, 0)), ((40, 0), (40, 40)),
                 ((40, 40), (0, 40)), ((0, 40), (0, 0))]:
        edge = pcbnew.PCB_SHAPE(board); edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        board.Add(edge)
    groups = {name: [] for name in names}
    for ref, rows in [('BANK', [(names[1], 10, 20), (names[0], 10.5, 20),
                                (names[1], 11, 20), (names[0], 11.5, 20)]),
                       ('REMOTE', [(names[0], 10, 6), (names[1], 11, 6)])]:
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); board.Add(fp)
        for i, (name, x, y) in enumerate(rows):
            pad = pcbnew.PAD(fp); pad.SetNumber(str(i+1))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I_MM(.3, 1.15))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x, y)); pad.SetNet(board.FindNet(name))
            fp.Add(pad)
            if ref == 'BANK': groups[name].append(pad)
        fp.Rotate(pcbnew.VECTOR2I_MM(20, 20), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    via = pcbnew.PCB_VIA(board); via.SetPosition(pcbnew.VECTOR2I_MM(32, 32))
    via.SetWidth(pcbnew.FromMM(.6)); via.SetDrill(pcbnew.FromMM(.3))
    via.SetNet(board.FindNet('GND')); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetLocked(True); board.Add(via)
    return board, groups, {'name': 'PAIR', 'kind': 'usb', 'p': names[0],
                           'n': names[1], 'width': .2, 'gap': .34, 'clearance': .2}


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('names', [('/LINK_P', '/LINK_N'), ('CAN_H_BUS', 'CAN_L_BUS'),
                                  ('/USB_DP', '/USB_DM'), ('/DATA_A', '/DATA_B')])
def test_all_duplicate_lands_connected_before_trunk_and_rolled_back_on_failure(angle, names):
    board, groups, pair = fixture(angle, names)
    before = {t.m_Uuid.AsString() for t in board.GetTracks()}
    observed = []

    def trunk(b, p, **kwargs):
        b.BuildConnectivity()
        for pads in groups.values():
            assert pads[1].m_Uuid.AsString() in {
                i.m_Uuid.AsString() for i in b.GetConnectivity().GetConnectedItems(pads[0])}
        observed.append(len(list(b.GetTracks())))
        # Simulate infrastructure from the same transaction, not only signals.
        via = pcbnew.PCB_VIA(b); via.SetPosition(pcbnew.VECTOR2I_MM(30, 30))
        via.SetNet(b.FindNet('GND')); b.Add(via)
        return {'name': p['name'], 'p': p['p'], 'n': p['n'], 'refused': 'bounded external refusal'}

    with patch.object(route, 'derive_coupled_pairs', return_value=[pair]), \
            patch.object(route, 'route_coupled_pair', side_effect=trunk):
        result = route.precision_route_board(board, board_path='synthetic.kicad_pcb', do_kelvin=False)
    assert observed and observed[0] > len(before)
    row = result['pairs']['refused'][0]
    assert row['package_pad_preclosure']['pair_linked'] == 2
    assert row['refused'] == 'bounded external refusal'
    assert {t.m_Uuid.AsString() for t in board.GetTracks()} == before


def test_failed_package_breakout_never_starts_external_trunk():
    board, _, pair = fixture(0, ('/LINK_P', '/LINK_N'))
    before = {t.m_Uuid.AsString() for t in board.GetTracks()}
    with patch.object(route, 'derive_coupled_pairs', return_value=[pair]), \
            patch.object(route.cec_fr, 'synthesize_same_footprint_links',
                         return_value={'pair_refused': 2}), \
            patch.object(route, 'route_coupled_pair') as trunk:
        result = route.precision_route_board(board, board_path='synthetic.kicad_pcb', do_kelvin=False)
    trunk.assert_not_called()
    assert 'before external routing' in result['pairs']['refused'][0]['refused']
    assert {t.m_Uuid.AsString() for t in board.GetTracks()} == before


@pytest.mark.parametrize('owned',[False,True])
def test_expired_outer_budget_never_starts_new_copper_or_discards_owned_pair(monkeypatch,owned):
    board,_,pair=fixture(0,('/LINK_P','/LINK_N'))
    if owned:
        # A declaration alone is not native ownership. This fixture actually
        # connects every duplicate and remote terminal before expiring time.
        paths={pair['p']:[(11.5,20),(11.5,18.825),(10.5,18.825),(10.5,20)],
               pair['n']:[(10,20),(10,21.175),(11,21.175),(11,20)]}
        owned_paths=[(pair['p'],paths[pair['p']]),(pair['n'],paths[pair['n']]),
            (pair['p'],[(10.5,18.825),(10.5,17.5),(10,17),(10,6)]),
            (pair['n'],[(11,21.175),(13,21.175),(13,8),(11,6)])]
        for name,points in owned_paths:
            for a,z in zip(points,points[1:]):
                t=pcbnew.PCB_TRACK(board); t.SetNet(board.FindNet(name)); t.SetLayer(pcbnew.F_Cu)
                t.SetWidth(pcbnew.FromMM(.2)); t.SetStart(pcbnew.VECTOR2I_MM(*a))
                t.SetEnd(pcbnew.VECTOR2I_MM(*z)); t.SetLocked(True); board.Add(t)
        board.BuildConnectivity()
        for name in (pair['p'],pair['n']):
            pads=[p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname()==name]
            connected={i.m_Uuid.AsString() for i in board.GetConnectivity().GetConnectedItems(pads[0])}
            assert all(p.m_Uuid.AsString() in connected for p in pads[1:])
        native=route._native_pair_completion(board,pair)
        assert native['connected'] is True,native
        # Isolate the deadline decision from physical signoff; the latter has
        # separate complete/unknown/debt tests in test_existing_pair_receiving.
        # Keep real native terminal connectivity; only the physics summaries
        # are mocked here, not ownership or copper/rollback accounting.
        import cec_constraints as constraints
        import cec_field_coupling as field
        monkeypatch.setattr(constraints,'high_speed_pair_summary',lambda *a,**kw:
            dict(applicable=True,pairs=[dict(p=pair['p'],n=pair['n'],violations=[])]))
        monkeypatch.setattr(field,'field_coupling_summary',lambda *a,**kw:dict(interactions=[]))
    before={t.m_Uuid.AsString() for t in board.GetTracks()}
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH','1')
    with patch.object(route,'derive_coupled_pairs',return_value=[pair]), \
            patch.object(route.cec_fr,'synthesize_same_footprint_links') as local, \
            patch.object(route,'route_coupled_pair') as trunk:
        result=route.precision_route_board(board,do_kelvin=False,
            existing_locked_nets={pair['p'],pair['n']} if owned else ())
    local.assert_not_called()
    trunk.assert_not_called()
    assert {t.m_Uuid.AsString() for t in board.GetTracks()} == before
    if owned:
        assert result['pairs']['routed'],result['pairs']['refused']
        assert result['pairs']['routed'][0]['route_mode']=='preexisting-native-qualified'
        assert not result['pairs']['refused']
    else:
        assert result['pairs']['refused'][0]['pair_search_budget_exhausted']


def test_expired_budget_does_not_trust_declared_ownership_without_native_terminal_closure(monkeypatch):
    board,_,pair=fixture(0,('/LINK_P','/LINK_N'))
    before={t.m_Uuid.AsString() for t in board.GetTracks()}
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH','1')
    with patch.object(route,'derive_coupled_pairs',return_value=[pair]), \
            patch.object(route.cec_fr,'synthesize_same_footprint_links') as local, \
            patch.object(route,'route_coupled_pair') as trunk:
        result=route.precision_route_board(board,do_kelvin=False,existing_locked_nets={pair['p'],pair['n']})
    local.assert_not_called(); trunk.assert_not_called()
    assert not result['pairs']['routed']
    assert 'every native terminal' in result['pairs']['refused'][0]['refused']
    assert {t.m_Uuid.AsString() for t in board.GetTracks()}==before


def test_pair_solver_receives_remaining_outer_budget_with_completion_reserve(monkeypatch):
    board,_,pair=fixture(0,('/LINK_P','/LINK_N'))
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH','180')
    import cec_operation_budget as budget
    with patch.object(budget.time,'time',return_value=100), \
            patch.object(route.time,'monotonic',return_value=10), \
            patch.object(route,'derive_coupled_pairs',return_value=[pair]), \
            patch.object(route.cec_fr,'synthesize_same_footprint_links',return_value={}), \
            patch.object(route,'route_coupled_pair',return_value={
                'name':pair['name'],'p':pair['p'],'n':pair['n'],'refused':'bounded test'}) as trunk:
        result=route.precision_route_board(board,do_kelvin=False)
    assert trunk.call_args.kwargs['deadline']==60
    assert result['pairs']['schedule'][0]['budget']['allowed_s']==50


@pytest.mark.parametrize('pairs', [
    [{'p': '/LINK_P', 'n': '/LINK_P'}],
    [{'p': '/LINK_P', 'n': ''}],
    [{'p': '/LINK_P', 'n': '/LINK_N'}, {'p': '/LINK_P', 'n': 'GND'}],
])
def test_ambiguous_pair_declaration_refuses_before_any_mutation(pairs):
    board, _, _ = fixture(0, ('/LINK_P', '/LINK_N'))
    before = {t.m_Uuid.AsString() for t in board.GetTracks()}
    with pytest.raises(ValueError, match='pair declaration'):
        route.cec_fr.synthesize_same_footprint_links(board, pair_declarations=pairs)
    assert {t.m_Uuid.AsString() for t in board.GetTracks()} == before


def test_atomic_pair_does_not_escape_explicit_net_scope():
    board, _, pair = fixture(0, ('/LINK_P', '/LINK_N'))
    before = {t.m_Uuid.AsString() for t in board.GetTracks()}
    report = route.cec_fr.synthesize_same_footprint_links(
        board, include_nets={pair['p']}, pair_declarations=[pair])
    assert report['pair_linked'] == 0
    assert {t.m_Uuid.AsString() for t in board.GetTracks()} == before


def test_heuristic_cannot_capture_an_explicitly_owned_member():
    board, _, pair = fixture(0, ('/LINK_P', '/LINK_N'))
    before = {t.m_Uuid.AsString() for t in board.GetTracks()}
    # /LINK_N looks like the mate of /LINK_P but electrical authority says
    # otherwise. The heuristic must not create that counterfeit paired group.
    report = route.cec_fr.synthesize_same_footprint_links(
        board, include_nets={pair['p'],pair['n']},
        pair_declarations=[{'p': pair['p'], 'n': 'declared-elsewhere'}])
    assert report['pair_groups'] == 0
    assert {t.m_Uuid.AsString() for t in board.GetTracks()} == before

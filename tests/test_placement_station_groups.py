"""Collateral local repair must not destroy the router's paired stations."""
import copy
import pytest
import cec_placement_station_groups as groups


def fixture():
    positions = dict(OWNER=(10., 10., 0.), CAP=(12., 10., 90.),
                     RP=(14., 10., 180.), RN=(14., 12., 180.))
    primary = dict(OWNER=(10., 10., 180.), CAP=(14., 10., 270.))
    variant = dict(primary, RP=(12., 10., 180.))
    context = dict(ok=True, groups=[('RN', 'RP')])
    return positions, primary, variant, context


def test_secondary_member_brings_station_with_identical_translation():
    p, primary, variant, context = fixture()
    before = copy.deepcopy((p, primary, variant, context))
    result = groups.complete_eviction(p, primary, variant, context)
    assert result['ok'] and result['added_refs'] == ['RN']
    assert result['placements']['RN'] == (12., 12., 180.)
    assert result['placements']['RP'] == (12., 10., 180.)
    assert (p, primary, variant, context) == before


@pytest.mark.parametrize('locked', ['RN', 'RP'])
def test_either_fixed_member_prevents_whole_eviction(locked):
    p, primary, variant, context = fixture()
    assert groups.complete_eviction(p, primary, variant, context,
        immovable={locked})['reason'] == 'station_member_immovable'


@pytest.mark.parametrize('pose', [(13., 12., 180.), (12., 12., 90.),
                                 (float('nan'), 12., 180.)])
def test_conflicting_secondary_transforms_are_not_overwritten(pose):
    p, primary, variant, context = fixture()
    variant['RN'] = pose
    assert groups.complete_eviction(p, primary, variant, context)['reason'] == 'station_transform_conflict'


def test_missing_member_does_not_reduce_station_to_available_population():
    p, primary, variant, context = fixture()
    del p['RN']
    assert groups.complete_eviction(p, primary, variant, context)['reason'] == 'station_member_missing'


def test_primary_station_solver_can_change_internal_geometry_intentionally():
    p, primary, variant, context = fixture()
    primary['RP'] = variant['RP']
    assert groups.complete_eviction(p, primary, variant, context)['placements'] == variant


def test_overlap_with_primary_member_requires_identical_transform():
    p, primary, variant, context = fixture()
    primary['RN'] = p['RN']
    variant.update(primary)
    assert not groups.complete_eviction(p, primary, variant, context)['ok']
    primary['RN'] = variant['RN'] = (12., 12., 180.)
    assert groups.complete_eviction(p, primary, variant, context)['ok']


def test_unavailable_station_context_refuses_collateral_but_not_primary_moves():
    p, primary, variant, _ = fixture()
    assert not groups.complete_eviction(p, primary, variant, dict(ok=False))['ok']
    assert groups.complete_eviction(p, primary, primary, dict(ok=False))['ok']


def test_unrelated_secondary_part_is_unchanged():
    p, primary, variant, _ = fixture()
    result = groups.complete_eviction(p, primary, variant, dict(ok=True, groups=[]))
    assert result['ok'] and result['placements'] == variant


@pytest.mark.parametrize('rotation', [0., 90., 180., 270.])
@pytest.mark.parametrize('names', [('RP', 'RN'), ('ELEMENT_A', 'ELEMENT_B')])
def test_translation_is_reference_and_orientation_independent(rotation, names):
    p, primary, variant, context = fixture()
    remap = {'RP': names[0], 'RN': names[1]}
    p = {remap.get(ref, ref): (*pose[:2], rotation) for ref, pose in p.items()}
    primary = {ref: (*pose[:2], rotation) for ref, pose in primary.items()}
    variant = dict(primary, **{names[0]: (12., 10., rotation)})
    result = groups.complete_eviction(p, primary, variant, dict(ok=True, groups=[names]))
    assert result['ok'] and result['placements'][names[1]] == (12., 12., rotation)


def test_overlapping_station_closure_is_transitive_and_order_independent():
    rows = [dict(physical_refs=['A', 'B']), dict(physical_refs=['C', 'D']),
            dict(physical_refs=['B', 'C']), dict(physical_refs=['Z'])]
    assert groups.station_groups(rows) == [('A', 'B', 'C', 'D')]
    assert groups.station_groups(rows[::-1]) == groups.station_groups(rows)


def test_missing_board_does_not_fall_back_to_empty_success(tmp_path):
    assert not groups.from_board(tmp_path / 'missing.kicad_pcb')['ok']


@pytest.mark.parametrize('flip', [False, True])
def test_loaded_native_station_membership_matches_router(tmp_path, monkeypatch, flip):
    import pcbnew
    import cec_precision_route as precision
    board = pcbnew.BOARD()
    nets = []
    for name in ('/example/CAN_H', '/example/CAN_L'):
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        nets.append(net)
    for ref, net, y in zip(('R931', 'R847'), nets, (10., 12.)):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref)
        fp.SetValue('60.4')
        fp.SetFPID(pcbnew.LIB_ID('Any', 'R_0603'))
        fp.SetPosition(pcbnew.VECTOR2I_MM(10, y))
        board.Add(fp)
        for number, net_obj, offset in (('1', net, -.8), ('2', None, .8)):
            pad = pcbnew.PAD(fp)
            pad.SetNumber(number)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetSize(pcbnew.VECTOR2I_MM(.8, .8))
            layers = pcbnew.LSET()
            layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers)
            pad.SetPosition(pcbnew.VECTOR2I_MM(10 + offset, y))
            if net_obj is not None:
                pad.SetNet(net_obj)
            fp.Add(pad)
        if flip:
            fp.Flip(fp.GetPosition(), False)
    path = tmp_path / 'native.kicad_pcb'
    pcbnew.SaveBoard(str(path), board, True)
    result = groups.from_board(path)
    assert result['ok'] and result['groups'] == [('R847', 'R931')]
    assert len(result['board_sha256']) == 64
    monkeypatch.setattr(precision, '_pair_endpoint_stations',
                        lambda *a: (_ for _ in ()).throw(ValueError('bad topology')))
    assert not groups.from_board(path)['ok']

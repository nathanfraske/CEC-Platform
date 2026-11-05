import math

import pytest

from cec_mating_rows import align_row, companion_on_axis, clearance_row


def test_shared_parent_datums_preserve_pitch_not_old_daughter_compaction():
    from cec_mating_rows import shared_row_datums
    assert shared_row_datums([[30, 37.75, 45.5, 53.25], [61, 68.75, 76.5, 84.25]],
                             first_datum_mm=3.5) == [3.5, 11.25, 19, 26.75]
    with pytest.raises(ValueError, match='disagree'):
        shared_row_datums([[0, 8], [20, 27]], first_datum_mm=3)


@pytest.mark.parametrize('angle', [0, 90, 180, 37])
def test_authorized_span_restores_compressed_row_without_moving_its_center(angle):
    a = math.radians(angle)
    def pose(x): return (125+x*math.cos(a), -73-x*math.sin(a), angle)
    poses = {'a': pose(-7), 'b': pose(0), 'c': pose(7)}
    result = align_row(poses, poses, [0, 7.75, 15.5], axis_angle_deg=angle, maximum_span_mm=15.5)
    assert result['a'] == pytest.approx(pose(-7.75), abs=1e-6)
    assert result['b'] == pytest.approx(pose(0), abs=1e-6)
    assert result['c'] == pytest.approx(pose(7.75), abs=1e-6)
    with pytest.raises(ValueError, match='enlarge'):
        align_row(poses, poses, [0, 8, 16], axis_angle_deg=angle, maximum_span_mm=15.5)


def test_actual_copper_envelope_cannot_be_replaced_by_smaller_body_width():
    from cec_mating_rows import envelope_row_screen
    result = envelope_row_screen([3.5, 10.5, 17.5, 24.5], [(-3.75, 3.75)]*4,
                                 maximum_last_mm=24.5)
    assert not result['ok'] and not result['fits_fixed_envelope']
    assert result['excess_mm'] == 1.5
    assert all(pair['actual_gap_mm'] == -.5 for pair in result['pairs'])
    assert not result['dimensions_changed']


def test_copper_screen_handles_asymmetry_translation_and_declared_clearance():
    from cec_mating_rows import envelope_row_screen
    kwargs = dict(copper_intervals=[(-2, 3), (-1, 4)], minimum_clearance_mm=.25)
    a = envelope_row_screen([1, 5], maximum_last_mm=6, **kwargs)
    b = envelope_row_screen([101, 105], maximum_last_mm=106, **kwargs)
    assert a['pairs'] == b['pairs']
    assert a['proposed_datums_mm'] == [1, 5.25]
    assert a['fits_fixed_envelope'] and not a['ok']


@pytest.mark.parametrize('intervals', [[], [(0, float('nan'))]*2, [(1, -1)]*2])
def test_copper_screen_invalid_envelopes_fail_closed(intervals):
    from cec_mating_rows import envelope_row_screen
    with pytest.raises(ValueError):
        envelope_row_screen([0, 5], intervals, maximum_last_mm=10)


def test_body_clearance_uses_both_size_and_position_tolerances():
    xs = clearance_row([5, 13.35, 20.2, 27.05, 33.9, 42.25],
                       [10, 6.3, 6.3, 6.3, 6.3, 10], [.3]*6,
                       position_error_mm=.1, minimum_gap_mm=.2,
                       maximum_last_mm=43.9)
    assert xs == pytest.approx([5, 13.85, 20.85, 27.85, 34.85, 43.7])
    with pytest.raises(ValueError, match='fixed interface envelope'):
        clearance_row([0, 5], [5, 5], [.2, .2], position_error_mm=.1,
                      minimum_gap_mm=.2, maximum_last_mm=5)


def test_shared_pitch_and_center_without_expansion():
    poses = {'alpha': (30, 7, 0), 'beta': (38, 7, 0), 'gamma': (46, 7, 0)}
    actual = align_row(poses, poses, [5, 12, 19])
    assert actual == {'alpha': (31, 7, 0), 'beta': (38, 7, 0), 'gamma': (45, 7, 0)}
    assert align_row(actual, actual, [5, 12, 19]) == actual


@pytest.mark.parametrize('angle', [0, 90, 180, 270, 37])
def test_row_is_frame_invariant(angle):
    a = math.radians(angle)
    def pose(x):
        return (125 + x * math.cos(a), -73 - x * math.sin(a), angle)
    actual = align_row({'alpha': pose(0), 'beta': pose(16)},
                       ['alpha', 'beta'], [0, 14], axis_angle_deg=angle)
    assert actual['alpha'] == pytest.approx(pose(1), abs=1e-6)
    assert actual['beta'] == pytest.approx(pose(15), abs=1e-6)


def test_pin_order_is_not_derived_from_incorrect_current_position():
    actual = align_row({'force': (24, 8, 0), 'return': (10, 8, 0)},
                       ['force', 'return'], [0, 14])
    assert actual['force'][0] == 10
    assert actual['return'][0] == 24


def test_refuse_expansion_or_incoherent_row():
    with pytest.raises(ValueError, match='enlarge'):
        align_row({'a': (0, 0, 0), 'b': (5, 0, 0)}, ['a', 'b'], [0, 6])
    with pytest.raises(ValueError, match='coherent row'):
        align_row({'a': (0, 0, 0), 'b': (9, 1, 0)}, ['a', 'b'], [0, 6])
    with pytest.raises(ValueError, match='finite'):
        align_row({'a': (0, 0, 0), 'b': (9, 0, 0)}, ['a', 'b'], [0, float('nan')])


def test_companion_only_changes_lateral_position():
    assert companion_on_axis((30, 19, 0), (5, 2, 0), 20) == (25, 19, 0)
    assert companion_on_axis((19, -30, 90), (2, -5, 90), 20,
                             axis_angle_deg=90) == (19, -25, 90)


def test_edge_channel_obeys_fixed_depth_and_width_budget():
    from cec_mating_rows import edge_channel_origin
    policy = dict(copper_extent=3, edge=20, edge_clearance=.5,
                  route_width=.5, copper_clearance=.25, margin=.05, maximum_shift=1)
    assert edge_channel_origin(16.5, **policy) == pytest.approx(15.7)
    assert edge_channel_origin(15, **policy) == 15
    with pytest.raises(ValueError, match='depth-change'):
        edge_channel_origin(17, **policy)


def test_every_feasible_family_compiles_same_pitch_and_order():
    import cec_xfcn_contract as c
    for name, ports in c.OUTPUT_MOUNT_PORTS.items():
        plan = c.PROJECTS[name]
        if not plan['mating_row_compilation']['ok']:
            with pytest.raises(ValueError, match='paired mating row'):
                c.mating_row_targets(name, plan['placements_mm'])
            assert plan['placements_mm'] == plan['interface_frame_seed_mm']
            continue
        for mate, refs, db_refs in ports:
            xs = [plan['placements_mm'][r][0] for r in refs]
            db = [c.PROJECTS[mate]['placements_mm'][r][0] for r in db_refs]
            assert [b - a for a, b in zip(xs, xs[1:])] == pytest.approx(
                [b - a for a, b in zip(db, db[1:])])
        assert c.mating_row_targets(name, plan['placements_mm']) == {
            r: plan['placements_mm'][r] for r in c.mating_row_targets(name, plan['placements_mm'])}


def test_domain_targets_follow_translated_candidate_not_old_origin():
    import cec_xfcn_contract as c
    for name in c.OUTPUT_MOUNT_PORTS:
        plan = c.PROJECTS[name]
        poses = {r: (x - 173, y + 91, a) for r, (x, y, a) in
                 plan['interface_frame_seed_mm'].items()}
        if not plan['mating_row_compilation']['ok']:
            with pytest.raises(ValueError, match='paired mating row'):
                c.mating_row_targets(name, poses)
            continue
        actual = c.mating_row_targets(name, poses)
        for ref, row in actual.items():
            x, y, a = plan['placements_mm'][ref]
            assert row == pytest.approx((x - 173, y + 91, a))

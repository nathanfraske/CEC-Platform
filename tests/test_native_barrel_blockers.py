import time

import pcbnew
import pytest

import cec_force_current as force
import cec_measurement_leaf as leaf
import cec_native_barrel_blockers as blockers
import cec_fr as fr
from test_measurement_leaf import fixture


def make_board(quarter=0, mirror=False):
    board, pad, _, _, xy = fixture('caller_owned_renamed_net', quarter)
    foreign = pcbnew.NETINFO_ITEM(board, 'arbitrary_foreign_bus'); board.Add(foreign)
    def position(p):
        x, y = p
        return xy((30-x if mirror else x, y))
    tracks = []
    for layer in (pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.B_Cu):
        t = pcbnew.PCB_TRACK(board); t.SetLayer(layer); t.SetNet(foreign)
        t.SetWidth(200000); t.SetStart(position((12, 8))); t.SetEnd(position((12, 12)))
        board.Add(t); tracks.append(t)
    return board, pad, tracks, position


def inspect(board, pad, at, **kwargs):
    args = dict(diameter_nm=600000, drill_nm=300000, clearance_nm=200000,
        deadline=time.monotonic()+3.)
    args.update(kwargs)
    return blockers.inventory(board, pad.GetNetCode(), tuple(at), **args)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
def test_first_refusal_cannot_hide_later_face_blockers(quarter, mirror):
    board, pad, tracks, xy = make_board(quarter, mirror)
    before = leaf._binding(board)
    result = inspect(board, pad, xy((12, 10)))
    assert result['inventory_complete'] and not result['native_guard_clear']
    actual = {hit['uuid'] for row in result['layer_rows'] for hit in row['blockers']}
    assert actual == {force._uid(t) for t in tracks}
    assert result['native_guard_report']['layer'] == 'F.Cu'
    assert len(result['layer_rows']) == 6
    assert result['source_unchanged'] and before == leaf._binding(board)
    assert not any(result[k] for k in ('retirement_authorized', 'current_authority',
        'routing_admitted', 'no_path_proved', 'release_authority'))


@pytest.mark.parametrize('quarter', range(4))
def test_clear_inventory_keeps_existing_guard_verdict(quarter):
    board, pad, _, xy = make_board(quarter)
    at = xy((17, 17)); first = fr._via_spot_clear(board, at, 600000, 200000,
        {pad.GetNetCode()}, drill_nm=300000, net_code=pad.GetNetCode(), foreign_cache={})
    result = inspect(board, pad, at)
    assert first == result['native_guard_clear'] is True
    assert result['inventory_complete'] and not any(r['blockers'] for r in result['layer_rows'])


def test_absolute_native_floor_refusal_still_collects_later_copper():
    board, pad, tracks, xy = make_board()
    result = inspect(board, pad, xy((12, 10)), diameter_nm=300000, drill_nm=100000)
    assert not result['native_guard_clear'] and 'minimum' in result['native_guard_report']['reason']
    assert result['inventory_complete']
    assert {hit['uuid'] for row in result['layer_rows'] for hit in row['blockers']} == {
        force._uid(t) for t in tracks}


def test_output_truncation_is_explicitly_incomplete():
    board, pad, tracks, xy = make_board()
    other = pcbnew.PCB_TRACK(board); other.SetLayer(pcbnew.In3_Cu)
    other.SetNetCode(tracks[0].GetNetCode()); other.SetWidth(200000)
    other.SetStart(xy((10, 10))); other.SetEnd(xy((14, 10))); board.Add(other)
    result = inspect(board, pad, xy((12, 10)), max_blockers_per_layer=1)
    row = next(r for r in result['layer_rows'] if r['layer'] == 'In3.Cu')
    assert row['truncated'] and not row['inventory_complete']
    assert not result['inventory_complete'] and len(row['blockers']) == 1


def test_silent_native_shape_omission_is_not_complete(monkeypatch):
    board, pad, tracks, xy = make_board()
    original = fr._identified_foreign_shape_indexes
    def omit(board, layer, codes):
        zones, copper = original(board, layer, codes)
        if layer == pcbnew.In3_Cu:
            copper = fr._bucket_foreign_shapes([])
        return zones, copper
    monkeypatch.setattr(fr, '_identified_foreign_shape_indexes', omit)
    result = inspect(board, pad, xy((12, 10)))
    row = next(r for r in result['layer_rows'] if r['layer'] == 'In3.Cu')
    assert row['missing_native_uuids'] == [force._uid(tracks[2])]
    assert not result['inventory_complete']


def test_deadline_never_reports_partial_stack_as_complete(monkeypatch):
    board, pad, _, xy = make_board()
    tick = blockers._tick; count = [0]
    def deadline(value):
        tick(value); count[0] += 1
        if count[0] > 20: raise TimeoutError('synthetic_bounded_stop')
    monkeypatch.setattr(blockers, '_tick', deadline)
    result = inspect(board, pad, xy((12, 10)))
    assert not result['inventory_complete'] and result['errors']
    assert result['source_unchanged'] and len(result['layer_rows']) < 6


@pytest.mark.parametrize('kwargs', [dict(diameter_nm=True), dict(drill_nm=600000),
    dict(clearance_nm=-1), dict(deadline=0), dict(deadline=float('inf')),
    dict(max_blockers_per_layer=0), dict(max_blockers_per_layer=True),
    dict(diameter_nm=8_000_001)])
def test_typed_finite_boundaries(kwargs):
    board, pad, _, xy = make_board()
    with pytest.raises(ValueError, match='bounded_explicit_native_barrel_diagnostic_required'):
        inspect(board, pad, xy((12, 10)), **kwargs)


def test_native_inventory_bound_precedes_geometry(monkeypatch):
    board, pad, _, xy = make_board(); monkeypatch.setattr(blockers, 'MAX_ITEMS', 2)
    monkeypatch.setattr(fr, '_via_spot_clear', lambda *a, **kw: pytest.fail('unbounded geometry'))
    with pytest.raises(ValueError, match='item_bound'):
        inspect(board, pad, xy((12, 10)))


def test_collision_unknown_is_not_a_complete_inventory(monkeypatch):
    board, pad, _, xy = make_board()
    original = fr._snapshot_foreign_blockers
    def unknown(*args, **kwargs):
        hits = original(*args, **kwargs)
        return [dict(hit, geometry_status='unknown', contact='geometry_unknown') for hit in hits]
    monkeypatch.setattr(fr, '_snapshot_foreign_blockers', unknown)
    result = inspect(board, pad, xy((12, 10)))
    assert not result['inventory_complete'] and not result['native_guard_clear']


def test_mutation_during_native_read_refuses_the_entire_receipt(monkeypatch):
    board, pad, tracks, xy = make_board()
    original = fr._via_spot_clear
    def mutate(*args, **kwargs):
        verdict = original(*args, **kwargs); tracks[-1].SetWidth(300000)
        return verdict
    monkeypatch.setattr(fr, '_via_spot_clear', mutate)
    with pytest.raises(ValueError, match='diagnostic_source_mutated'):
        inspect(board, pad, xy((12, 10)))

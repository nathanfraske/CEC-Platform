"""Local bypass routes see mandatory future copper without borrowing locality."""
import copy
import math

import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
from test_local_supply_native_detours import source


@pytest.mark.parametrize('turn', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_local_supply_is_refined_around_actual_mandatory_future_copper(monkeypatch, turn, back):
    board, request, obstacle, contract = source(monkeypatch, turn, back)
    board.Remove(obstacle.GetParentFootprint())
    a = request['a']['at_nm']
    b = request['b']['at_nm']
    face = request['a']['layers'][0]
    centre = [(x+y)//2 for x, y in zip(a, b)]
    normal = [(b[1]-a[1])//2, (a[0]-b[0])//2]
    shift = lambda p,n:[p[i]+round(normal[i]*n) for i in range(2)]
    fixed = dict(id='0', cost=0, net='foreign_material', clearance_nm=200000,
        ops=[['trk', shift(centre, -.3), shift(centre, .3), 200000, face]])
    alternatives = [dict(id=str(index), cost=2+index, net=request['net'], clearance_nm=200000,
        ops=[['trk', p, q, 250000, face] for p,q in zip(path,path[1:])])
        for index,path in enumerate([[a,b], [a,shift(a,.1),shift(b,.1),b]])]
    packet = dict(domains={'fixed':[fixed], 'supply':alternatives},
        source_native_binding=row._source_binding(board))
    requests = dict(fixed=dict(kind='source_boundary',net=fixed['net']), supply=request)
    before = row._source_binding(board)
    unchanged = copy.deepcopy(packet)
    failed = escape.choose(board, packet)
    assert not failed['complete'] and failed['failure_frontier'][0]['obligation'] == 'supply'
    refined = escape.refine_conflict_frontier(board, packet, requests, failed,
        board_path='opaque_fixture', board_hint='opaque_fixture', timeout_s=2.)
    trials = refined['conflict_aware_refinement']['trials']
    assert trials and trials[0]['added_choices'] > 0
    selected = escape.choose(board, refined)
    assert selected['complete'] and selected['selected']['fixed'] == fixed
    ops = selected['selected']['supply']['ops']
    assert all(op[0] == 'trk' and op[3] == 250000 and op[4] == face for op in ops)
    assert tuple(ops[0][1]) == tuple(a) and tuple(ops[-1][2]) == tuple(b)
    limit = escape.cell._local_supply_limit_mm(math.dist(a,b)/1e6, .25, .2)
    assert sum(math.dist(op[1],op[2]) for op in ops)/1e6 <= limit
    assert refined['conflict_aware_refinement']['one_bounded_pass_only']
    assert packet == unchanged and row._source_binding(board) == before

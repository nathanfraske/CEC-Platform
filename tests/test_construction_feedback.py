import copy
from types import SimpleNamespace

import pytest

from cec_construction_feedback import placement_regions


def report(segment=(10., 10., 10., 20., 2.), *, ref='UNRELATED_PACKAGE', layer='F.Cu'):
    return {'construction_evidence': {'ARBITRARY_CONDUCTOR': {
        'constructed': False, 'blocked_segments': [dict(kind='pad', ref=ref,
            net='/ARBITRARY_CURRENT', layer=layer, segment_mm=list(segment),
            clearance_mm=.25)]}}}


@pytest.mark.parametrize('shift', [(0., 0.), (134.8, -27.3)])
@pytest.mark.parametrize('rotation', [0, 1, 2, 3])
def test_corridor_follows_geometry_not_board_name_or_reference(shift, rotation):
    def point(x, y):
        for _ in range(rotation):
            x, y = -y, x
        return x + shift[0], y + shift[1]
    a, b = point(10., 10.), point(10., 20.)
    source = report((*a, *b, 2.), ref='RENAMED_' + str(rotation))
    before = copy.deepcopy(source)
    rows = placement_regions(source)
    assert source == before
    assert len(rows) == 1
    assert rows[0]['regions'][0]['box'] == pytest.approx([
        min(a[0], b[0]) - 1.25, min(a[1], b[1]) - 1.25,
        max(a[0], b[0]) + 1.25, max(a[1], b[1]) + 1.25])
    assert rows[0]['proposal_only'] and rows[0]['release_authority'] is False


@pytest.mark.parametrize('kind', ['track', 'via', 'reserved_return', None])
def test_non_pad_obstruction_cannot_authorize_a_placement_move(kind):
    source = report()
    source['construction_evidence']['ARBITRARY_CONDUCTOR']['blocked_segments'][0]['kind'] = kind
    assert placement_regions(source) == []


def test_constructed_or_legacy_text_failures_produce_no_move():
    source = report()
    source['construction_evidence']['ARBITRARY_CONDUCTOR']['constructed'] = True
    assert placement_regions(source) == []
    assert placement_regions({'refused': {'A': 'package at (10,15)'}}) == []


def test_invalid_geometry_and_limits_fail_closed():
    for segment in [(0., 0., 1., 1., -2.), (0., 0., 1., float('nan'), 2.)]:
        assert placement_regions(report(segment)) == []
    assert placement_regions(report(), limit=0) == []
    with pytest.raises(ValueError):
        placement_regions(report(), limit=-1)
    source = report()
    source['construction_evidence']['OTHER_CONDUCTOR'] = copy.deepcopy(
        source['construction_evidence']['ARBITRARY_CONDUCTOR'])
    assert len(placement_regions(source)) == 1


def test_real_move_dispatch_preserves_fixed_refs_and_bypass_macro(monkeypatch):
    import cec_pcb
    import cec_synth_pipeline as synth
    candidate = SimpleNamespace(P={'UNRELATED_PACKAGE': (10., 15., 0.),
                                  'BYPASS': (12., 15., 90.)})
    evidence = {'force_rail': report(), 'decoupler': {'details': [dict(
        status='assigned', cap_ref='BYPASS', owner_ref='UNRELATED_PACKAGE')]}}
    comps = {ref: object() for ref in candidate.P}
    monkeypatch.setattr(cec_pcb, 'courtyard_bbox', lambda comp, x, y, r, **kw:
                        (x - .5, x + .5, y - .5, y + .5))
    diagnostics = {}
    moves = synth._placement_craft_move_specs(candidate, evidence, comps=comps,
        required_stages=['force_rail_placement'], proposal_diagnostics=diagnostics)
    moves = [m for m in moves if m['kind'] == 'power_territory_cell_reseat']
    assert len(moves) == 12
    for move in moves:
        assert move['ref'] == 'UNRELATED_PACKAGE'
        owner, cap = (move['placements'][ref] for ref in ('UNRELATED_PACKAGE', 'BYPASS'))
        assert (cap[0] - owner[0], cap[1] - owner[1], cap[2]) == pytest.approx((2., 0., 90.))
        x0, y0, x1, y1 = placement_regions(report())[0]['regions'][0]['box']
        assert (owner[0] + .5 < x0 or owner[0] - .5 > x1
                or owner[1] + .5 < y0 or owner[1] - .5 > y1)
    assert diagnostics['force_rail_construction']['movable_refs'] == ['UNRELATED_PACKAGE']
    fixed = synth._placement_craft_move_specs(candidate, evidence, comps=comps,
        immovable={'UNRELATED_PACKAGE'}, required_stages=['force_rail_placement'])
    assert not any(m['kind'].startswith('power_territory') for m in fixed)


@pytest.mark.parametrize('shift', [(0., 0.), (113.2, -18.7)])
@pytest.mark.parametrize('layer', ['F.Cu', 'In3.Cu'])
def test_serial_obstruction_followup_is_a_bounded_composed_proposal(shift, layer):
    import cec_construction_feedback as feedback
    segment = (10.+shift[0], 10.+shift[1], 10.+shift[0], 20.+shift[1], 2.)
    before = report(segment, ref='FIRST', layer=layer)
    after = report(segment, ref='SECOND', layer=layer)
    parent = dict(kind='power_territory_reseat', ref='FIRST', position=(5., 15., 90.))
    children = [dict(kind='power_territory_reseat', ref='SECOND',
                     position=(float(x), 16., 0.)) for x in range(1, 10)]
    snapshots = copy.deepcopy((before, after, parent, children))
    moves = feedback.followup_moves(before, after, parent,
        {'FIRST': parent['position']}, children, limit=3)
    assert len(moves) == 3
    assert (before, after, parent, children) == snapshots
    for move in moves:
        assert move['kind'] == 'force_rail_blocker_sequence'
        assert move['construction_depth'] == 2
        assert set(move['placements']) == {'FIRST', 'SECOND'}
        assert move['placements']['FIRST'] == parent['position']
        assert move['construction_transition']['cleared_refs'] == ['FIRST']
        assert move['construction_transition']['new_refs'] == ['SECOND']
        assert move['release_authority'] is False
        assert move['allows_power_replan'] is False


@pytest.mark.parametrize('invalid', ['same_ref', 'different_layer', 'different_segment',
                                   'foreign_copper', 'constructed', 'unmoved_blocker',
                                   'recursive', 'errors'])
def test_serial_obstruction_followup_does_not_infer_permission(invalid):
    import cec_construction_feedback as feedback
    before, after = report(ref='FIRST'), report(ref='SECOND')
    parent = dict(kind='power_territory_reseat', ref='FIRST', position=(5., 15., 0.))
    placed = {'FIRST': parent['position']}
    domain = after['construction_evidence']['ARBITRARY_CONDUCTOR']
    if invalid == 'same_ref':
        domain['blocked_segments'][0]['ref'] = 'FIRST'
    elif invalid == 'different_layer':
        domain['blocked_segments'][0]['layer'] = 'B.Cu'
    elif invalid == 'different_segment':
        domain['blocked_segments'][0]['segment_mm'][1] += 1.
    elif invalid == 'foreign_copper':
        domain['blocked_segments'][0]['kind'] = 'track'
    elif invalid == 'constructed':
        domain['constructed'] = True
    elif invalid == 'unmoved_blocker':
        placed = {'OTHER': (5., 15., 0.)}
    elif invalid == 'recursive':
        parent['construction_depth'] = 2
    else:
        after['error'] = 'native failed'
    children = [dict(ref='SECOND', position=(7., 15., 0.))]
    assert feedback.followup_moves(before, after, parent, placed, children) == []


def test_serial_obstruction_child_cannot_overwrite_parent_or_move_unwitnessed_root():
    import cec_construction_feedback as feedback
    parent = dict(kind='power_territory_reseat', ref='FIRST', position=(5., 15., 0.))
    children = [dict(ref='THIRD', position=(7., 15., 0.)),
                dict(ref='SECOND', placements={'UNRELATED': (7., 15., 0.)}),
                dict(ref='SECOND', placements={'SECOND': (7., 15., 0.),
                                              'FIRST': (10., 15., 0.)}),
                dict(ref='SECOND', position=(float('nan'), 15., 0.))]
    assert feedback.followup_moves(report(ref='FIRST'), report(ref='SECOND'),
        parent, {'FIRST': parent['position']}, children) == []


def test_serial_obstruction_followup_limit_and_macro_members():
    import cec_construction_feedback as feedback
    parent = dict(kind='power_territory_reseat', ref='FIRST', position=(5., 15., 0.))
    child = dict(ref='SECOND', position=(7., 15., 0.),
                 placements={'SECOND': (7., 15., 0.), 'BYPASS': (7., 16., 90.)})
    args = (report(ref='FIRST'), report(ref='SECOND'), parent,
            {'FIRST': parent['position']}, [child, child])
    moves = feedback.followup_moves(*args)
    assert len(moves) == 1
    assert set(moves[0]['placements']) == {'FIRST', 'SECOND', 'BYPASS'}
    assert feedback.followup_moves(*args, limit=0) == []
    for invalid in [-1, 17, True]:
        with pytest.raises(ValueError):
            feedback.followup_moves(*args, limit=invalid)


def complete_report(*, refs=('A', 'B', 'C'), shift=(0., 0.), layer='F.Cu'):
    x, y = shift
    segment = [10.+x, 5.+y, 10.+x, 25.+y, 2.]
    attempt = dict(schema=1, complete_pad_set=True, nets=['/ARBITRARY_CURRENT'],
        conductor_segments=[dict(segment_mm=segment, layer=layer)],
        blocked_segments=[dict(kind='pad', ref=ref, net='/ARBITRARY_CURRENT',
            blocker_net='/OTHER', layer=layer, segment_mm=segment,
            segment_index=0, clearance_mm=.25) for ref in refs], release_authority=False)
    return {'construction_evidence': {'ARBITRARY_CONDUCTOR': {
        'constructed': False, 'obstruction_sets': [attempt]}}}


@pytest.mark.parametrize('shift', [(0., 0.), (61.3, -21.4)])
def test_complete_clearance_group_is_geometry_bound_without_legacy_inference(shift):
    import cec_construction_feedback as feedback
    source = complete_report(shift=shift)
    original = copy.deepcopy(source)
    groups = feedback.clearance_groups(source)
    assert source == original and len(groups) == 1
    group = groups[0]
    assert group['refs'] == ['A', 'B', 'C']
    x, y = shift
    assert group['sweeps_mm'][0] == pytest.approx([8.75+x, 3.75+y, 11.25+x, 26.25+y])
    assert group['release_authority'] is False and group['allows_power_replan'] is False
    assert feedback.clearance_groups(report()) == []


@pytest.mark.parametrize('invalid', ['incomplete', 'hole', 'track', 'wrong_segment',
    'wrong_layer', 'nonfinite', 'constructed', 'error', 'oversized'])
def test_incomplete_or_nonphysical_groups_cannot_claim_complete_clearance(invalid):
    import cec_construction_feedback as feedback
    source = complete_report(refs=tuple('R'+str(i) for i in range(17))
        if invalid == 'oversized' else ('A','B'))
    construction = source['construction_evidence']['ARBITRARY_CONDUCTOR']
    attempt = construction['obstruction_sets'][0]
    if invalid == 'incomplete':attempt['complete_pad_set'] = False
    elif invalid in ('hole', 'track'):attempt['blocked_segments'][0]['kind'] = invalid
    elif invalid == 'wrong_segment':attempt['blocked_segments'][0] = dict(
        attempt['blocked_segments'][0], segment_mm=[1., 2., 3., 4., 2.])
    elif invalid == 'wrong_layer':attempt['blocked_segments'][0]['layer'] = 'B.Cu'
    elif invalid == 'nonfinite':attempt['blocked_segments'][0]['clearance_mm'] = float('nan')
    elif invalid == 'constructed':construction['constructed'] = True
    elif invalid == 'error':source['error'] = 'native failure'
    assert feedback.clearance_groups(source) == []


def test_complete_group_dispatch_carries_each_root_and_bypass_without_partial_fixed_move(monkeypatch):
    import cec_pcb
    import cec_synth_pipeline as synth
    candidate = SimpleNamespace(W=30., H=30., back_refs=(),
        P={'A': (10.,10.,0.), 'B': (10.,15.,90.), 'C': (10.,20.,180.),
           'BYPASS': (10.,21.,0.)})
    comps = {ref:object() for ref in candidate.P}
    monkeypatch.setattr(cec_pcb, 'courtyard_bbox', lambda comp,x,y,r,**kw:
                        (x-.4,x+.4,y-.4,y+.4))
    evidence = {'force_rail':complete_report(), 'decoupler':{'details':[dict(
        status='assigned', cap_ref='BYPASS', owner_ref='C')]}}
    diagnostics = {}
    all_moves = synth._placement_craft_move_specs(candidate,evidence,comps=comps,
        required_stages=['force_rail_placement'],proposal_diagnostics=diagnostics)
    moves = [move for move in all_moves if move['kind']=='force_rail_blocker_group']
    assert moves and len(moves)<=48
    for move in moves:
        assert set(move['placements'])==set(candidate.P)
        assert move['construction_group']['refs']==['A','B','C']
        assert move['release_authority'] is False
        assert move['allows_power_replan'] is False
        c, cap = move['placements']['C'], move['placements']['BYPASS']
        assert (cap[0]-c[0],cap[1]-c[1],cap[2]) == pytest.approx((0.,1.,0.))
    for fixed in [{'B'}, {'BYPASS'}]:
        guarded = synth._placement_craft_move_specs(candidate,evidence,comps=comps,
            immovable=fixed,required_stages=['force_rail_placement'])
        assert not any(move['kind']=='force_rail_blocker_group' for move in guarded)
    assert diagnostics['force_rail_construction']['complete_groups']==1

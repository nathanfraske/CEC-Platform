"""A moving mating row cannot silently drag its upstream current cell."""
import copy
from types import SimpleNamespace
from unittest import mock

import pytest

import cec_pcb
import cec_synth_pipeline as synth
import cec_xfcn_contract as contract


def fixture_plan(angle):
    # Deliberately asymmetric inputs, terminals and auxiliary offsets. Neither
    # reference names nor the authored origin identify mechanical membership.
    return {
        'refs': {'P7': {'part': contract.TTR}, 'P9': {'part': contract.TTR}},
        'aux_refs': {'K2': {'part': contract.ATX_SIGNAL_MAIN}},
        'placements_mm': {'P7': (42., 71., angle),
                          'P9': (58., 71., angle), 'K2': (65., 68., 90.)},
        'fixed_power_path_placements_mm': {'K8': (11., 9., 180.),
                                          'R7': (15., 38., -90.)},
        'mating_row_compilation': {'ok': True},
    }


def copper_y(plan, placements):
    values = []
    for ref, part in plan['refs'].items():
        x, y, angle = placements[ref]
        for x0, y0, x1, y1 in cec_pcb.local_pad_boxes(
                contract.PARTS[part['part']]['footprint']):
            values.extend(y + cec_pcb._rot(px, py, angle)[1]
                          for px, py in ((x0, y0), (x1, y0),
                                         (x1, y1), (x0, y1)))
    return values


@pytest.mark.parametrize('angle', [0., 90., 180., 270.])
@pytest.mark.parametrize('edge,datum', [('top', .9), ('bottom', 54.7)])
def test_mating_macro_uses_rotated_copper_edge_without_moving_upstream(angle, edge, datum):
    plan = fixture_plan(angle)
    before = copy.deepcopy(plan)
    placed = contract.centered_interface_anchor_placements(
        plan, 100., terminal_edge_y_mm=datum, edge=edge,
        anchor_scope='mating_interface')
    assert set(placed) == set(plan['placements_mm'])
    assert not set(placed) & set(plan['fixed_power_path_placements_mm'])
    assert (min if edge == 'top' else max)(copper_y(plan, placed)) == pytest.approx(datum)
    assert (min(p[0] for p in placed.values())
            + max(p[0] for p in placed.values())) / 2 == pytest.approx(50.)
    for ref, pose in placed.items():
        assert pose[0] - placed['P7'][0] == pytest.approx(
            plan['placements_mm'][ref][0] - plan['placements_mm']['P7'][0])
        assert pose[1] - placed['P7'][1] == pytest.approx(
            plan['placements_mm'][ref][1] - plan['placements_mm']['P7'][1])
        assert pose[2] == plan['placements_mm'][ref][2]
    assert plan == before


def test_scope_policy_updates_only_mating_members_and_preserves_unrelated_pins():
    plan = fixture_plan(0.)
    cfg = SimpleNamespace(pins={**plan['fixed_power_path_placements_mm'],
                                'OTHER': (7., 8., 0.)}, params={
        'qualified_interface_anchor': {'provider': 'cec_xfcn_contract',
            'project': 'renamed-fixture', 'anchor_scope': 'mating_interface',
            'edge': 'bottom', 'terminal_edge_margin_mm': .9}})
    before = dict(cfg.pins)
    with mock.patch.dict(contract.PROJECTS, {'renamed-fixture': plan}):
        placed = synth._bind_declared_interface_anchors(cfg, 100., 55.6)
    assert cfg.pins == {**before, **placed}
    for ref in before:
        assert cfg.pins[ref] == before[ref]


def test_default_scope_preserves_explicit_whole_power_path_behavior():
    plan = fixture_plan(0.)
    placed = contract.centered_interface_anchor_placements(
        plan, 100., terminal_edge_y_mm=.9)
    assert set(placed) == (set(plan['placements_mm'])
                           | set(plan['fixed_power_path_placements_mm']))


@pytest.mark.parametrize('failure', ['unknown_scope', 'missing_primary', 'missing_aux', 'uncompiled'])
def test_invalid_scope_or_incomplete_row_cannot_partially_bind_cfg(failure):
    plan = fixture_plan(0.)
    scope = 'mating_interface'
    if failure == 'unknown_scope': scope = 'guess'
    elif failure == 'missing_primary': del plan['placements_mm']['P9']
    elif failure == 'missing_aux': del plan['placements_mm']['K2']
    else: plan['mating_row_compilation']['ok'] = False
    cfg = SimpleNamespace(pins={'UNCHANGED': (1., 2., 3.)}, params={
        'qualified_interface_anchor': {'provider': 'cec_xfcn_contract',
            'project': 'renamed-fixture', 'anchor_scope': scope, 'edge': 'bottom'}})
    before = copy.deepcopy(cfg.pins)
    with mock.patch.dict(contract.PROJECTS, {'renamed-fixture': plan}):
        with pytest.raises(ValueError):
            synth._bind_declared_interface_anchors(cfg, 100., 55.6)
    assert cfg.pins == before


def test_current_pcie3_policy_keeps_inputs_and_shunts_fixed_and_terminals_inside():
    cfg = synth.Config.load('pcie-8pin-3port')
    upstream = contract.PROJECTS['pcie3-main']['fixed_power_path_placements_mm']
    cfg.pins = dict(upstream)
    placed = synth._bind_declared_interface_anchors(cfg, 103.5, 55.6)
    assert set(placed) == set(contract.PROJECTS['pcie3-main']['placements_mm'])
    assert {ref: cfg.pins[ref] for ref in upstream} == upstream
    assert max(copper_y(contract.PROJECTS['pcie3-main'], placed)) == pytest.approx(54.7)

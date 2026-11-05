from types import SimpleNamespace
from unittest.mock import patch
import pytest
import cec_synth_pipeline as synth
import cec_xfcn_contract as contract
import cec_pcb


def test_reference_prefix_cannot_authorize_blade_geometry():
    assert synth._is_power_terminal('TB_any', 'SomeLib:TwoLegScrew')
    assert not synth._is_blade('TB_any', 'SomeLib:TwoLegScrew')
    assert synth._is_blade('J_any', 'SomeLib:FASTON_tab')


@pytest.mark.parametrize('refs', [('TB51', 'TB52'), ('TB101', 'TB202')])
def test_unbound_nonblade_interface_is_rejected_before_mutation(refs):
    anchors = {refs[0]: (12, 17, 270), refs[1]: (23, 17, 270)}
    before = dict(anchors)
    comps = {ref: 'AnyLib:TwoLegScrew' for ref in refs}
    cables = [({'j_out_blades': [refs[0]]}, 12)]
    with pytest.raises(ValueError, match='requires declared rigid anchors'):
        synth._seat_blade_fields(cables, anchors, None, comps, W=60)
    assert anchors == before


def test_bound_nonblade_interface_never_feeds_blade_slots_or_shunt_rotation():
    anchors = {'TB_A': (15, 37, 270), 'TB_B': (31, 37, 270), 'R_SH': (17, 20, 90)}
    before = dict(anchors)
    synth._seat_blade_fields([({'j_out_blades': ['TB_A'], 'shunt': 'R_SH'}, 17)],
                            anchors, None, {r: 'Lib:Screw' for r in anchors}, W=70,
                            pinned_refs={'TB_A', 'TB_B'})
    assert anchors == before


def test_real_blade_row_still_places_unbound_faston_parts():
    anchors = {'J_A': (10, 30, 0), 'J_B': (30, 30, 0)}
    synth._seat_blade_fields([({'j_out_blades': ['J_A']}, 20)], anchors, None,
                            {r: 'Lib:FASTON' for r in anchors}, W=60)
    assert abs(anchors['J_B'][0] - anchors['J_A'][0]) == pytest.approx(4.7)


@pytest.mark.parametrize('edge,extreme', [('top', min), ('bottom', max)])
def test_synthetic_rigid_macro_preserves_mating_axes_at_either_edge(edge, extreme):
    plan = {'refs': {'CONTACT_A': {'part': 'synthetic'}, 'CONTACT_B': {'part': 'synthetic'}},
            'placements_mm': {'CONTACT_A': (35, 22, 270), 'CONTACT_B': (49, 22, 270)}}
    with patch.dict(contract.PARTS, {'synthetic': {'footprint': 'Lib:synthetic'}}), \
         patch.object(cec_pcb, 'local_pad_boxes', return_value=[(-2, -4, 3, 5)]):
        posed = contract.centered_interface_anchor_placements(plan, 60,
                                      terminal_edge_y_mm=4, edge=edge)
    assert posed['CONTACT_B'][0] - posed['CONTACT_A'][0] == 14
    assert posed['CONTACT_A'][2] == posed['CONTACT_B'][2] == 270
    edge_points = [row[1] + cec_pcb._rot(x, y, row[2])[1]
                   for row in posed.values() for x,y in [(-2,-4),(-2,5),(3,-4),(3,5)]]
    assert extreme(edge_points) == pytest.approx(4)


def test_unfit_eps_policy_cannot_bind_an_electrically_shorted_macro():
    cfg = synth.Config.load('eps-8pin-rev3')
    before = dict(cfg.pins or {})
    with pytest.raises(ValueError, match='paired mating row'):
        synth._bind_declared_interface_anchors(cfg, 94, 44)
    assert dict(cfg.pins or {}) == before


def test_partial_pin_map_cannot_silently_accept_remaining_screw_terminals():
    anchors = {'TB_A': (10, 30, 270), 'TB_B': (24, 30, 270)}
    with pytest.raises(ValueError, match='TB_B'):
        synth._seat_blade_fields([({'j_out_blades': ['TB_A']}, 10)], anchors, None,
                                {r:'Lib:Screw' for r in anchors}, pinned_refs={'TB_A'})

"""Exact body-preflight request transport, independent of native routing."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import cec_synth_pipeline as synth
import cec_pour_plan
import cec_pourplan
import pcbnew


class BodyPreflightParallelAuthority(unittest.TestCase):
    def invoke(self, declarations):
        board = mock.Mock()
        board.Zones.return_value = []
        board.GetFootprints.return_value = []
        plan = mock.Mock()
        plan.pour_polygons.return_value = [
            {'net': '/RAIL', 'layer': 'F.Cu'},
            {'net': '/RAIL', 'layer': 'B.Cu'}]
        with mock.patch.object(pcbnew, 'LoadBoard', return_value=board), \
                mock.patch.object(synth.os.path, 'isfile', return_value=False), \
                mock.patch.object(cec_pourplan.PourPlan, 'from_board', return_value=plan), \
                mock.patch.object(synth, '_placement_relief_fixed_refs', return_value=()), \
                mock.patch.object(cec_pour_plan, 'plan_pours',
                    return_value=([], [], {'/RAIL': {'path_found': True}})) as planner:
            result = synth._oracle_bodies_in_pours(
                '/unused/board.kicad_pcb',
                cfg=SimpleNamespace(params={'pour_asks': declarations}))
        return result, planner

    def test_explicit_fraction_threshold_and_layers_survive(self):
        policy = dict(parallel_layers=['F.Cu', 'B.Cu'],
                      parallel_layer_fraction=0.6, parallel_min_amps=20)
        result, planner = self.invoke([dict(net='/RAIL', **policy)])
        self.assertTrue(result['ok'])
        ask = planner.call_args.args[1][0]
        for key, value in policy.items():
            self.assertEqual(ask[key], value)

    def test_no_opt_in_is_invented(self):
        result, planner = self.invoke([])
        self.assertTrue(result['ok'])
        self.assertNotIn('parallel_layers', planner.call_args.args[1][0])

    def test_conflicting_authority_refuses_before_geometry(self):
        result, planner = self.invoke([
            dict(net='/RAIL', parallel_layer_fraction=0.5),
            dict(net='/RAIL', parallel_layer_fraction=0.6)])
        self.assertFalse(result['ok'])
        self.assertIn('conflicting parallel_layer_fraction', result['error'])
        planner.assert_not_called()

    def test_non_geometric_net_does_not_gain_new_territory(self):
        result, planner = self.invoke([
            dict(net='/UNREQUESTED', parallel_layers=['F.Cu', 'B.Cu'])])
        self.assertTrue(result['ok'])
        self.assertEqual([a['net'] for a in planner.call_args.args[1]], ['/RAIL'])
        self.assertNotIn('parallel_layers', planner.call_args.args[1][0])


if __name__ == '__main__':
    unittest.main()

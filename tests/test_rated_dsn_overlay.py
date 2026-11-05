import unittest,importlib.util
from pathlib import Path
import cec_rated_dsn_overlay as m
DSN='''(pcb "private" (unit um) (resolution um 10)
(structure (layer F.Cu (type signal) (property (index 0)))
(layer SIG2 (type signal) (property (index 1)))
(layer GND (type power) (property (index 2))))
(network (net "/USB (rated)" (pins J-1 U-1)) (net ordinary (pins J-2 U-2))
(class Default "/USB (rated)" ordinary (circuit (use_via "Via600:300")) (rule (width 200) (clearance 250))))
(wiring (wire (path F.Cu 200 1 2 3 4) (net ordinary))))'''
LAYERS={'F.Cu':'F.Cu','SIG2':'In2.Cu','GND':'In1.Cu'}
contract=lambda width:{'required_by_layer_mm':{'F.Cu':.2,'In2.Cu':width,'In1.Cu':width},'amps':.75,'geometry_margin':1.25}

class RatedOverlay(unittest.TestCase):
    def test_width_includes_actual_inner_layer_and_preserves_other_bytes(self):
        result,report=m.overlay(DSN,{'/USB (rated)':contract(.845074761)},LAYERS)
        self.assertIn('(width 845.2)',result)
        self.assertIn('(clearance 250)',result);self.assertIn('(use_via "Via600:300")',result)
        self.assertIn('(net "/USB (rated)" (pins J-1 U-1))',result)
        self.assertIn('(wire (path F.Cu 200 1 2 3 4) (net ordinary))',result)
        self.assertFalse(report['capability_exceptions_accepted']);self.assertEqual(report['deferred_not_completed'],[])

    def test_no_cap_on_force_or_current_budget_reduction(self):
        result,r=m.overlay(DSN,{'/USB (rated)':contract(292.499809226)},LAYERS)
        self.assertIn('(width 292500)',result)
        self.assertEqual(r['nets']['/USB (rated)']['authority']['amps'],.75)

    def test_no_lowering_original_project_width(self):
        result,r=m.overlay(DSN.replace('(width 200)','(width 1000)'),{'/USB (rated)':contract(.8)},LAYERS)
        self.assertIn('(width 1000)',result);self.assertEqual(r['nets']['/USB (rated)']['exported_width_mm'],1.)

    def test_bad_layer_identity_or_index_refused(self):
        with self.assertRaises(ValueError):m.overlay(DSN,{},dict(LAYERS,UNKNOWN='In3.Cu'))
        with self.assertRaises(ValueError):m.overlay(DSN,{},LAYERS,{'F.Cu':0,'SIG2':2,'GND':1})

    def test_missing_contract_layer_or_net_refused(self):
        with self.assertRaises(KeyError):m.overlay(DSN,{'/USB (rated)':{'required_by_layer_mm':{'F.Cu':.8}}},LAYERS)
        result,r=m.overlay(DSN,{'wrong':contract(.8)},LAYERS)
        self.assertNotIn('CEC_RATED_',result)
        self.assertEqual(r['deferred_not_completed'][0]['reason'],'absent_DSN_net')

    def test_plane_and_explicitly_inactive_layers_not_routable(self):
        dsn=DSN.replace('(structure','(structure (autoroute_settings (layer_rule SIG2 (active off)))')
        result,r=m.overlay(dsn,{'/USB (rated)':contract(292)},LAYERS)
        self.assertEqual(r['actual_DSN_routing_layers'],['F.Cu'])
        self.assertEqual(r['nets']['/USB (rated)']['exported_width_mm'],.2)
        self.assertIn('(type power)',result);self.assertIn('(layer_rule SIG2 (active off))',result)

    def test_ambiguous_class_and_units_refused(self):
        with self.assertRaises(ValueError):m.overlay(DSN.replace('(unit um)','(unit mil)'),{},LAYERS)
        dsn=DSN.replace('(class Default','(class Duplicate "/USB (rated)" (rule (width 200))) (class Default')
        with self.assertRaises(ValueError):m.overlay(dsn,{'/USB (rated)':contract(.8)},LAYERS)

    def test_outward_half_width_grid_depends_on_actual_DSN_resolution(self):
        text,r=m.overlay(DSN.replace('(resolution um 10)','(resolution um 1000)'),{'/USB (rated)':contract(.845074761)},LAYERS)
        self.assertIn('(width 845.076)',text)
        self.assertGreaterEqual(r['nets']['/USB (rated)']['exported_width_mm'],.845074761)
        with self.assertRaises(ValueError):m.overlay(DSN.replace('(resolution um 10)','(resolution mil 10)'),{},LAYERS)

    def test_original_literal_member_token_preserved(self):
        original=DSN.replace('/USB (rated)',r'/USB \u03bc')
        text,r=m.overlay(original,{'/USB μ':contract(.8)},LAYERS)
        self.assertIn(r'"/USB \u03bc"',text)
        self.assertNotIn('"/USB μ"',text)

    def test_pending_only_scope_does_not_manufacture_absent_net_classes(self):
        dsn=DSN.replace('(pins J-1 U-1)','(pins)')
        text,r=m.overlay(dsn,{'/USB (rated)':contract(.8),'missing':contract(292)},LAYERS)
        self.assertEqual(r['nets'],{})
        self.assertNotIn('CEC_RATED_',text)
        self.assertEqual({v['net'] for v in r['deferred_not_completed']},{'/USB (rated)','missing'})
        text,r=m.overlay(DSN,{'/USB (rated)':contract(.8)},LAYERS,requested_nets=['ordinary'])
        self.assertEqual(r['nets'],{})
        self.assertEqual(r['deferred_not_completed'][0]['reason'],'outside_explicit_requested_scope')

    def test_actual_network_pin_net_inventory_verification(self):
        expected={'J-1':'/USB (rated)','U-1':'/USB (rated)','J-2':'ordinary','U-2':'ordinary'}
        self.assertEqual(m.verify_network_inventory(DSN,expected)['ordinary'],['J-2','U-2'])
        with self.assertRaises(ValueError):m.verify_network_inventory(DSN,dict(expected,**{'J-1':'wrong'}))
        with self.assertRaises(ValueError):m.network_inventory(DSN.replace('J-2 U-2','J-1 U-2'))

if __name__=='__main__':unittest.main()

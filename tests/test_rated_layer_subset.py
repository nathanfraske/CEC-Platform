import unittest,types,sys
from unittest.mock import patch
import cec_rated_dsn_overlay as m
import cec_rated_trace_scope as gate

DSN='''(pcb private (unit um) (resolution um 10)
(structure (layer F.Cu (type signal) (property (index 0)))
(layer SIG2 (type signal) (property (index 1)))
(layer B.Cu (type signal) (property (index 2))))
(network (net /VBUS (pins J-1 U-1)) (net ordinary (pins J-2 U-2))
(class Default /VBUS ordinary (circuit (use_via Via)) (rule (width 500) (clearance 200))))
(wiring (wire (path F.Cu 200 1 2 3 4) (net ordinary))))'''
MAP={'F.Cu':'F.Cu','SIG2':'In2.Cu','B.Cu':'B.Cu'}
CONTRACT={'/VBUS':{'required_by_layer_mm':{'F.Cu':.2,'In2.Cu':.845074761,'B.Cu':.2},
                  'routing_layers':['F.Cu','In2.Cu','B.Cu'],'amps':.75,'geometry_margin':1.25}}

class LayerSubset(unittest.TestCase):
    def test_disabled_exact_output_and_scoped_no_current_reduction(self):
        original,r=m.overlay(DSN,CONTRACT,MAP)
        disabled,_=m.overlay(DSN,CONTRACT,MAP,construction_layers_by_net={})
        self.assertEqual(original,disabled)
        text,proof=m.overlay(DSN,CONTRACT,MAP,construction_layers_by_net={'/VBUS':['F.Cu','B.Cu']})
        self.assertIn('(width 500)',text)
        self.assertIn('(use_layer "F.Cu" "B.Cu")',text)
        self.assertIn('(use_via Via)',text);self.assertIn('(clearance 200)',text)
        self.assertEqual(m.network_inventory(text),m.network_inventory(DSN))
        self.assertEqual(proof['nets']['/VBUS']['authority'],CONTRACT['/VBUS'])
        self.assertEqual(proof['actual_DSN_routing_layers'],['F.Cu','SIG2','B.Cu'])
        self.assertTrue(proof['nets']['/VBUS']['receiver_must_enforce_new_track_layers'])

    def test_no_global_remap_and_original_stricter_scope_preserved(self):
        source=DSN.replace('(use_via Via)','(use_via Via) (use_layer F.Cu)')
        with self.assertRaisesRegex(ValueError,'widens_original'):
            m.overlay(source,CONTRACT,MAP,construction_layers_by_net={'/VBUS':['F.Cu','B.Cu']})
        text,_=m.overlay(source,CONTRACT,MAP,construction_layers_by_net={'/VBUS':['F.Cu']})
        self.assertIn('(use_layer "F.Cu")',text)
        self.assertIn('(layer SIG2 (type signal)',text)

    def test_malformed_noncurrent_absent_and_inactive_layers_refuse(self):
        for scope in ({'/VBUS':'F.Cu'},{'/VBUS':[]},{'/VBUS':['F.Cu','F.Cu']},
                      {'/VBUS':['In3.Cu']},{'ordinary':['F.Cu']},{'absent':['F.Cu']}):
            with self.assertRaises(ValueError):m.overlay(DSN,CONTRACT,MAP,construction_layers_by_net=scope)
        source=DSN.replace('(type signal)','(type power)',1)
        with self.assertRaisesRegex(ValueError,'not_active'):
            m.overlay(source,CONTRACT,MAP,construction_layers_by_net={'/VBUS':['F.Cu']})

    def test_required_width_outward_grid_and_floor_not_lowered(self):
        c={'/VBUS':dict(CONTRACT['/VBUS'],required_by_layer_mm={'F.Cu':.50011,'In2.Cu':292.,'B.Cu':.50011})}
        text,proof=m.overlay(DSN,c,MAP,construction_layers_by_net={'/VBUS':['F.Cu','B.Cu']})
        self.assertEqual(proof['nets']['/VBUS']['exported_width_mm'],.5002)
        self.assertEqual(proof['nets']['/VBUS']['authority']['required_by_layer_mm']['In2.Cu'],292.)

    def test_new_track_layer_receiver_refuses_inner_and_preserves_original(self):
        class Item:
            def __init__(self,uid,layer):self.m_Uuid=types.SimpleNamespace(AsString=lambda:uid);self.layer=layer
            def GetNetname(self):return '/VBUS'
            def GetClass(self):return 'PCB_TRACK'
            def GetLayer(self):return self.layer
        before=types.SimpleNamespace(GetTracks=lambda:[Item('source-inner','In2.Cu')])
        after=types.SimpleNamespace(GetTracks=lambda:[Item('source-inner','In2.Cu'),Item('new-inner','In2.Cu'),Item('new-outer','F.Cu')])
        modules={'pcbnew':types.SimpleNamespace(LoadBoard=lambda p:before if str(p).endswith('source') else after,LayerName=lambda lid:lid),
                 'cec_force_current':types.SimpleNamespace(_family=lambda *a:{},_code_identity=lambda:{},_hash=lambda p:'hash'),
                 'cec_current_topology':types.SimpleNamespace(route_width_contracts=lambda *a,**k:CONTRACT)}
        bound={'construction_layers_by_net':{'/VBUS':['F.Cu','B.Cu']}}
        with patch.dict(sys.modules,modules),patch.object(gate,'bind_source',return_value=bound):
            proof=gate.receive('source','candidate',scope={'/VBUS':['F.Cu','B.Cu']},board_hint='named')
            self.assertFalse(proof['ok']);self.assertEqual(proof['violations'][0]['uuid'],'new-inner')
            with self.assertRaises(ValueError):
                gate.normalize({'/VBUS':'F.Cu'})

if __name__=='__main__':unittest.main()

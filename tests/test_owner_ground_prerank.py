import sys,unittest,ast
from pathlib import Path
import cec_swig_guard;cec_swig_guard.pin()
import wx
quiet=wx.LogNull()
import cec_native_cell_pose_domains as m
from unittest.mock import patch

class Tests(unittest.TestCase):
 def plan(self):return dict(poses={'RENAMED_OWNER':[0,0,0],'RENAMED_CAP':[0,1,0]},selected_bypasses={'RENAMED_CAP':dict(owner='RENAMED_OWNER',pin='supply',rail='rail')},device_contracts={'RENAMED_OWNER':{'pins':{'return':'ground','reference':'reference'}}},stationary_device_owners=[])
 def screen(self,p,complete):return m._pose_ground_screen(object(),p,board_hint='source-hint',timeout_s=1.5,complete_owner_ground=complete)
 def test_legacy_default_scope_unchanged(self):
  with patch.object(m.frontier,'ground_screen',return_value={'ok':True}) as native:
   self.screen(self.plan(),False);self.assertEqual(native.call_args.args[1],['RENAMED_CAP']);self.assertIsNone(native.call_args.kwargs['selected_bypasses'])
 def test_complete_typed_owner_hierarchy_same_native_guard(self):
  p=self.plan()
  with patch.object(m.frontier,'ground_screen',return_value={'ok':False,'error':'owner ground refused'}) as native:
   self.assertFalse(self.screen(p,True)['ok']);self.assertEqual(set(native.call_args.args[1]),set(p['poses']));self.assertEqual(native.call_args.kwargs['selected_bypasses'],p['selected_bypasses']);self.assertEqual(native.call_args.kwargs['reach_mm'],.8);self.assertEqual(native.call_args.kwargs['timeout_s'],1.5)
 def test_stationary_owner_excluded(self):
  p=self.plan();p['stationary_device_owners']=['RENAMED_OWNER']
  with patch.object(m.frontier,'ground_screen',return_value={'ok':True}) as native:
   self.screen(p,True);self.assertEqual(native.call_args.args[1],['RENAMED_CAP'])
 def test_unposed_device_not_added(self):
  p=self.plan();p['device_contracts']['NOT_IN_POSE']={}
  with patch.object(m.frontier,'ground_screen',return_value={'ok':True}) as native:
   self.screen(p,True);self.assertNotIn('NOT_IN_POSE',native.call_args.args[1])
 def test_native_refusal_propagates(self):
  with patch.object(m.frontier,'ground_screen',side_effect=ValueError('native original material changed')):
   with self.assertRaisesRegex(ValueError,'material changed'):self.screen(self.plan(),True)
 def test_ast_real_offer_and_recursive_hook(self):
  tree=ast.parse(Path(m.__file__).read_text());propose=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='propose');text=ast.unparse(propose)
  self.assertIn('grounds = _pose_ground_screen(',text);self.assertGreaterEqual(text.count('complete_owner_ground=complete_owner_ground'),2);self.assertIn("type(complete_owner_ground) is not bool",text)
if __name__=='__main__':unittest.main()

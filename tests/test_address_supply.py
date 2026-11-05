import sys,unittest,copy,json
from pathlib import Path
import cec_swig_guard;cec_swig_guard.pin()
import pcbnew,wx
quiet=wx.LogNull()
import cec_address_supply_obligations as subject
from unittest.mock import patch

MODEL={'device':'renamable source device','pins':{'1':'address','2':'power_input'},'source':'manufacturer fixture'}
CONTRACT={'current_authority':{'source':'positive fixture'},'required_by_layer_nm':{pcbnew.F_Cu:700000,pcbnew.B_Cu:900000}}
class Graph:
 def GetConnectedItems(self,p):return []

class Tests(unittest.TestCase):
 def fixture(self,rotation=0,back=False):
  source=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(source,'rail-renamable');source.Add(net)
  fp=pcbnew.FOOTPRINT(source);fp.SetReference('ANY_OWNER');source.Add(fp)
  for pin,x in [('1',0),('2',2000000)]:
   mask=pcbnew.LSET();mask.AddLayer(pcbnew.F_Cu)
   p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetSize(pcbnew.VECTOR2I(600000,600000));p.SetLayerSet(mask);p.SetPosition(pcbnew.VECTOR2I(x,0));p.SetNet(net);fp.Add(p)
  if back:fp.Flip(pcbnew.VECTOR2I(0,0),True)
  ground=pcbnew.NETINFO_ITEM(source,'GND');source.Add(ground)
  cap=pcbnew.FOOTPRINT(source);cap.SetReference('ANY_CAP');source.Add(cap)
  for pin,x,n in [('1',2500000,net),('2',3000000,ground)]:
   mask=pcbnew.LSET();mask.AddLayer(pcbnew.F_Cu)
   land=pcbnew.PAD(cap);land.SetNumber(pin);land.SetAttribute(pcbnew.PAD_ATTRIB_SMD);land.SetSize(pcbnew.VECTOR2I(500000,500000));land.SetPosition(pcbnew.VECTOR2I(x,0));land.SetLayerSet(mask);land.SetNet(n);cap.Add(land)
  if back:cap.Flip(pcbnew.VECTOR2I(0,0),True)
  child=pcbnew.BOARD();clone=pcbnew.FOOTPRINT(fp);child.Add(clone);clone.SetPosition(pcbnew.VECTOR2I(12000000,17000000));clone.SetOrientationDegrees(rotation)
  proposal={'poses':{'ANY_OWNER':[12,17,rotation]},'stationary_device_owners':[],'board_hint':'fixture','selected_bypasses':{'ANY_CAP':{'owner':'ANY_OWNER','pin':'2','rail':'rail-renamable'}}}
  return source,child,proposal
 def setUp(self):
  assignment={'assigned':{'fixture':{'cap_ref':'ANY_CAP','requirement':{'ref':'ANY_OWNER','pin':'2','rail':'rail-renamable'}}}}
  self.patches=[patch.object(subject.constraints,'_device_bypass_assignment',return_value=assignment),patch.object(subject.roles,'footprint_contract',return_value=copy.deepcopy(MODEL)),patch.object(subject.fr,'_read_only_route_connectivity',return_value=Graph()),patch.object(subject.cell,'_supply_current_widths',return_value=copy.deepcopy(CONTRACT)),patch.object(subject.cell,'_netclass',return_value={'width':500000})]
  for p in self.patches:p.start()
  self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])
 def test_rotations_faces_and_rename(self):
  for back in [False,True]:
   for angle in [0,90,180,270]:
    with self.subTest(back=back,angle=angle):
     s,b,p=self.fixture(angle,back);q=subject.requests(s,b,p);self.assertEqual(len(q),1);r=next(iter(q.values()));self.assertEqual(r['width_nm'],900000 if back else 700000);self.assertEqual(subject.discharged(s,b,p,q),{r['a']['pad_uuid']})
 def test_wrong_net(self):
  s,b,p=self.fixture();other=pcbnew.NETINFO_ITEM(s,'other');s.Add(other);s.FindFootprintByReference('ANY_OWNER').FindPadByNumber('1').SetNet(other);self.assertEqual(subject.requests(s,b,p),{})
 def test_same_named_child_net_can_have_board_local_code(self):
  s,b,p=self.fixture();b.Add(pcbnew.NETINFO_ITEM(b,'unrelated-first'))
  net=pcbnew.NETINFO_ITEM(b,'rail-renamable');b.Add(net)
  for pad in b.FindFootprintByReference('ANY_OWNER').Pads():pad.SetNet(net)
  self.assertNotEqual(net.GetNetCode(),s.FindFootprintByReference('ANY_OWNER').FindPadByNumber('1').GetNetCode())
  self.assertEqual(len(subject.requests(s,b,p)),1)
 def test_changed_child_net_name_never_discharges_source(self):
  s,b,p=self.fixture();net=pcbnew.NETINFO_ITEM(b,'wrong-child-rail');b.Add(net)
  b.FindFootprintByReference('ANY_OWNER').FindPadByNumber('1').SetNet(net)
  with self.assertRaisesRegex(ValueError,'exact_surface_source_endpoint'):
   subject.requests(s,b,p)
 def test_unknown_role(self):
  s,b,p=self.fixture()
  with patch.object(subject.roles,'footprint_contract',return_value=None):self.assertEqual(subject.requests(s,b,p),{})
 def test_alias(self):
  s,b,p=self.fixture();s.FindFootprintByReference('ANY_OWNER').FindPadByNumber('2').SetNumber('1')
  with self.assertRaisesRegex(ValueError,'unaliased|real_local_surface_bypass'):subject.requests(s,b,p)
 def test_unknown_current(self):
  s,b,p=self.fixture()
  with patch.object(subject.cell,'_supply_current_widths',return_value=None):
   with self.assertRaisesRegex(ValueError,'positive_source_current'):subject.requests(s,b,p)
 def test_missing_owned_bypass_root(self):
  s,b,p=self.fixture();p['selected_bypasses']={};self.assertEqual(subject.requests(s,b,p),{})
 def test_wrong_bypass_owner(self):
  s,b,p=self.fixture();p['selected_bypasses']['ANY_CAP']['owner']='some_other_owner'
  self.assertEqual(subject.requests(s,b,p),{})
 def test_fake_cap_root(self):
  s,b,p=self.fixture();p['selected_bypasses']['FAKE_CAP']=p['selected_bypasses'].pop('ANY_CAP')
  with self.assertRaisesRegex(ValueError,'unique_source_bypass'):subject.requests(s,b,p)
 def test_extra_ambiguous_root(self):
  s,b,p=self.fixture();p['selected_bypasses']['OTHER_CAP']=dict(p['selected_bypasses']['ANY_CAP'])
  with self.assertRaisesRegex(ValueError,'unique_source_bypass'):subject.requests(s,b,p)
 def test_ambiguous_actual_assignment(self):
  s,b,p=self.fixture();item={'cap_ref':'ANY_CAP','requirement':{'ref':'ANY_OWNER','pin':'2','rail':'rail-renamable'}}
  with patch.object(subject.constraints,'_device_bypass_assignment',return_value={'assigned':{'a':item,'b':item}}):
   with self.assertRaisesRegex(ValueError,'unique_source_bypass'):subject.requests(s,b,p)
 def test_pad_stack_mutation(self):
  s,b,p=self.fixture();mask=pcbnew.LSET();mask.AddLayer(pcbnew.B_Cu);b.FindFootprintByReference('ANY_OWNER').FindPadByNumber('1').SetLayerSet(mask)
  with self.assertRaisesRegex(ValueError,'copper_stack_changed'):subject.requests(s,b,p)
 def test_empty_inventory_refuses_before_graph(self):
  s,b,p=self.fixture();p['poses']={}
  with self.assertRaisesRegex(ValueError,'pose_inventory'):subject.requests(s,b,p)
 def test_dangling_forgery_not_discharged(self):
  s,b,p=self.fixture();q=subject.requests(s,b,p);r=next(iter(q.values()));r['b']['pad_uuid']='fake';self.assertEqual(subject.discharged(s,b,p,q),set())
 def test_json_round_trip_keeps_exact_current_and_pad_obligation(self):
  for back in [False,True]:
   for angle in [0,90,180,270]:
    with self.subTest(back=back,angle=angle):
     s,b,p=self.fixture(angle,back);q=subject.requests(s,b,p)
     received=json.loads(json.dumps(q,allow_nan=False));r=next(iter(received.values()))
     self.assertNotEqual(q,received)
     self.assertEqual(subject.discharged(s,b,p,received),{r['a']['pad_uuid']})
 def test_json_packet_never_waives_numeric_or_source_current_changes(self):
  s,b,p=self.fixture();base=json.loads(json.dumps(subject.requests(s,b,p),allow_nan=False))
  for fault in ['width','layer_width','authority','role','point','extra','bool_for_int','float_for_int','int_for_bool']:
   with self.subTest(fault=fault):
    received=copy.deepcopy(base);r=next(iter(received.values()))
    if fault=='width':r['width_nm']+=1
    elif fault=='layer_width':r['unchanged_full_rail_current_contract']['required_by_layer_nm']['0']+=1
    elif fault=='authority':r['unchanged_full_rail_current_contract']['current_authority']={'source':'guessed'}
    elif fault=='role':r['source_address_supply']['manufacturer_contract']['pins']['1']='signal_input'
    elif fault=='point':r['a']['at_nm'][0]+=1
    elif fault=='extra':r['caller_claimed_current_waiver']=True
    elif fault=='bool_for_int':r['a']['layers'][0]=False
    elif fault=='float_for_int':r['width_nm']=float(r['width_nm'])
    else:r['source_address_supply']['exact_same_package_positive_power_input']=1
    self.assertEqual(subject.discharged(s,b,p,received),set())
 def test_isolated_terminal_inventory_consumes_the_serialized_request(self):
  import cec_cell_escape_replan as escape
  s,b,p=self.fixture();p.update(inherited_unrouted_measurement_lands=[],device_contracts={'ANY_OWNER':MODEL})
  received=json.loads(json.dumps(subject.requests(s,b,p),allow_nan=False))
  with patch.object(escape.fr,'_read_only_route_connectivity',return_value=Graph()):
   self.assertEqual(escape.unplanned_source_terminals(s,p,received,board=b),[])
   r=next(iter(received.values()));r['width_nm']+=1
   missing=escape.unplanned_source_terminals(s,p,received,board=b)
   self.assertEqual([q['pad_uuid']for q in missing],[r['a']['pad_uuid']])
 def test_whole_discharge_lease_includes_independent_rebuild_time(self):
  s,b,p=self.fixture();q=subject.requests(s,b,p)
  with patch.object(subject,'requests',return_value=q),patch.object(subject.time,'monotonic',side_effect=[0.,11.]):
   with self.assertRaisesRegex(ValueError,'deadline'):subject.discharged(s,b,p,q)
 def test_origin_mutation(self):
  s,b,p=self.fixture();land=b.FindFootprintByReference('ANY_OWNER').FindPadByNumber('1');land.SetPosition(pcbnew.VECTOR2I(13000000,17000000))
  with self.assertRaisesRegex(ValueError,'relative_geometry'):subject.requests(s,b,p)
 def test_wrong_role_not_discharge(self):
  s,b,p=self.fixture();q=subject.requests(s,b,p)
  with patch.object(subject.roles,'footprint_contract',return_value=dict(MODEL,pins={'1':'signal_input','2':'power_input'})):self.assertEqual(subject.discharged(s,b,p,q),set())
 def test_removed_endpoint(self):
  s,b,p=self.fixture();fp=b.FindFootprintByReference('ANY_OWNER');fp.Remove(fp.FindPadByNumber('2'))
  with self.assertRaisesRegex(ValueError,'identity_changed'):subject.requests(s,b,p)
 def test_production_hook_ast(self):
  import ast
  tree=ast.parse(Path(subject.__file__).with_name('cec_cell_escape_replan.py').read_text());functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
  for name in ['cec_complete_cell_receiving.py','cec_complete_macro_cell.py']:
   received=ast.parse(Path(subject.__file__).with_name(name).read_text())
   calls=[n for n in ast.walk(received) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='unplanned_source_terminals']
   self.assertEqual(len(calls),1);self.assertTrue(any(k.arg=='board' and isinstance(k.value,ast.Name) and k.value.id=='projected' for k in calls[0].keywords))
  # Public/default callers must still enter the complete implementation;
  # a private macro composition path cannot bypass address restoration.
  entry=functions['obligations'];implementation=functions.get('_obligations',entry)
  if implementation is not entry:
   self.assertEqual([a.arg for a in entry.args.args],['source','board','proposal'])
   self.assertEqual(entry.args.kwonlyargs,[])
   self.assertEqual(ast.unparse(entry.body[0]),'return _obligations(source, board, proposal)')
  self.assertIn('address_supply.requests',ast.unparse(implementation));self.assertIn('address_supply.discharged',ast.unparse(functions['unplanned_source_terminals']));self.assertIn('board=board',ast.unparse(functions['complete_connection_screen']))
 def test_nonaddress_partial_model_neutral_without_expensive_authority(self):
  s,b,p=self.fixture();p['selected_bypasses']={'UNRELATED_CAP':{'owner':'other','pin':'unknown','rail':'other'}}
  with patch.object(subject.roles,'footprint_contract',return_value={'pins':{'not-complete':'power_input'}}), patch.object(subject.fr,'_read_only_route_connectivity',side_effect=AssertionError('graph invoked')), patch.object(subject.cell,'_supply_current_widths',side_effect=AssertionError('current invoked')), patch.object(subject.constraints,'_device_bypass_assignment',side_effect=AssertionError('assignment invoked')):
   self.assertEqual(subject.requests(s,b,p),{})
 def test_timeout_bounds_and_expired_derivation(self):
  s,b,p=self.fixture()
  for value in [True,0,-1,11,float('nan')]:
   with self.assertRaisesRegex(ValueError,'bounded_address_supply'):
    subject.requests(s,b,p,timeout_s=value)
  with patch.object(subject.time,'monotonic',side_effect=[0.,11.]):
   with self.assertRaisesRegex(ValueError,'derivation_deadline'):
    subject.requests(s,b,p)
if __name__=='__main__':unittest.main()

import hashlib,json,sys,types,unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
import cec_rated_trace_scope as scope

class CanonicalScope(unittest.TestCase):
    def native_contract_fixture(self):
        # Native topology contract descriptors genuinely use these tuple fields.
        return {'/rated':dict(amps=.75,geometry_margin=1.25,
            routing_layers=('F.Cu','In2.Cu','B.Cu'),authority_refs=('source-terminal','sink-terminal'),
            required_by_layer_mm={'F.Cu':.2,'In2.Cu':.845074761,'B.Cu':.2})}

    def binding(self,contracts=None):
        contracts=self.native_contract_fixture() if contracts is None else contracts
        board=object();path=Path('source.kicad_pcb').resolve()
        modules={'pcbnew':types.SimpleNamespace(LoadBoard=lambda source:board),
            'cec_force_current':types.SimpleNamespace(_family=lambda *a:{str(path):'a'*64},_thermal_hint=lambda *a:nullcontext()),
            'cec_current_topology':types.SimpleNamespace(route_width_contracts=lambda *a,**k:contracts),
            'cec_fab_profile':types.SimpleNamespace(enabled_copper_layers=lambda *a:('F.Cu','In2.Cu','B.Cu'),
                routing_layers=lambda *a,**k:('F.Cu','In2.Cu','B.Cu'))}
        with patch.dict(sys.modules,modules):return scope.bind_source(path,'logical',{'/rated':['F.Cu','B.Cu']})

    def test_real_native_descriptor_tuple_fields_survive_job_and_receipt_json(self):
        contract=self.native_contract_fixture();bound=self.binding(contract)
        job={'identity':{'new_trace_scope':bound},'scope':{'/rated':['F.Cu','B.Cu']}}
        receipt={'epoch':{'new_trace_scope':bound},'new_trace_layer_receiving':{'binding':bound}}
        self.assertEqual(json.loads(json.dumps(job)),job)
        self.assertEqual(json.loads(json.dumps(receipt)),receipt)
        self.assertEqual(bound['source_contracts'],json.loads(json.dumps(contract)))
        self.assertEqual(bound['source_contracts']['/rated']['routing_layers'],['F.Cu','In2.Cu','B.Cu'])
        self.assertEqual(bound['source_contracts']['/rated']['authority_refs'],['source-terminal','sink-terminal'])
        payload=dict(bound);digest=payload.pop('binding_sha256')
        self.assertEqual(digest,hashlib.sha256(json.dumps(payload,sort_keys=True,allow_nan=False).encode()).hexdigest())

    def test_current_layers_authority_refs_and_margin_changes_still_change_binding(self):
        original=self.binding()
        for key,value in [('amps',1.0),('geometry_margin',1.0),('authority_refs',('different-source','sink-terminal')),
                          ('required_by_layer_mm',{'F.Cu':.5,'In2.Cu':.845074761,'B.Cu':.5})]:
            changed=self.native_contract_fixture();changed['/rated'][key]=value
            self.assertNotEqual(original['binding_sha256'],self.binding(changed)['binding_sha256'])

    def test_nonfinite_and_opaque_source_descriptors_refuse(self):
        for value in (float('nan'),float('inf'),object()):
            contract=self.native_contract_fixture();contract['/rated']['unexpected']=value
            with self.assertRaises((ValueError,TypeError)):self.binding(contract)

if __name__=='__main__':unittest.main()

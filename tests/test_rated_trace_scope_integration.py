import ast,json,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import cec_rated_wave_context as wave
import cec_rated_trace_scope as gate
import cec_source_retaining_ses_import as retaining
SCRIPTS=Path(wave.__file__).resolve().parent

class ScopeIntegration(unittest.TestCase):
    def policy(self,**extra):
        p=dict(wave_rated_current_export=True,wave_source_retaining_import=True,
            wave_rated_current_nets=['/rated'],wave_rated_current_layers={'/rated':['F.Cu','B.Cu']})
        p.update(extra);return wave.policy_from_params(p,'logical')

    def test_explicit_scope_requires_retaining_gate_and_selected_net(self):
        self.assertEqual(self.policy()['construction_layers_by_net'],{'/rated':['F.Cu','B.Cu']})
        for bad in (dict(wave_source_retaining_import=False),dict(wave_rated_current_nets=[]),
                    dict(wave_rated_current_layers={'/rated':'F.Cu'})):
            with self.assertRaises(ValueError):self.policy(**bad)
        p=wave.policy_from_params(dict(wave_rated_current_export=True),'logical')
        self.assertNotIn('construction_layers_by_net',p)

    def test_job_policy_mutation_refused_even_same_source(self):
        policy=self.policy()
        with patch.object(wave,'_identity',return_value={'source_sha256':'a'*64}),patch.object(wave,'_authority',return_value='fixed'),patch.object(gate,'bind_source',return_value={'scope':'bound'}):
            job=wave.bind_job('source',policy)
            self.assertEqual(json.loads(json.dumps(job)),job)
            wave.validate_job('source',job)
            job['policy']['construction_layers_by_net']['/rated']=['F.Cu']
            with self.assertRaisesRegex(ValueError,'epoch_changed'):wave.validate_job('source',job)

    def test_factory_forwards_scope_not_capability_record(self):
        policy=self.policy();job=dict(policy=policy,identity={'source_sha256':'a'*64})
        with patch.object(wave,'validate_job'),patch.object(retaining,'route_once_operator',return_value={'ok':True}) as callback:
            worker_operator=wave.import_operator('source',job)
            worker_operator('source','ses','output')
            self.assertEqual(callback.call_args.kwargs['trace_layer_scope'],policy['construction_layers_by_net'])
            self.assertNotIn('receiver_ok',callback.call_args.kwargs)

    def test_receipt_requires_actual_gate_and_exact_candidate_binding(self):
        force=types.SimpleNamespace(_hash=lambda candidate:'correct')
        binding={'scope':'real'}
        with patch.dict(sys.modules,{'cec_force_current':force}):
            for proof in ({},{'ok':True},{'ok':True,'complete':True,'enabled':True,'binding':binding,'candidate_sha256':'stale'}):
                with self.assertRaises(ValueError):gate.assert_receipt({'candidate':'candidate','new_trace_layer_receiving':proof},binding)
            proof=dict(ok=True,complete=True,enabled=True,binding=binding,candidate_sha256='correct')
            gate.assert_receipt({'candidate':'candidate','new_trace_layer_receiving':proof},binding)

    def test_gate_is_inside_native_worker_before_ok_and_publication_guard(self):
        tree=ast.parse((SCRIPTS/'cec_source_retaining_ses_import.py').read_text())
        worker=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_worker')
        text=ast.unparse(worker)
        self.assertLess(text.index('trace_scope.receive'),text.index("report['ok'] = True"))
        self.assertLess(text.index('current = debt.receive'),text.index('trace_scope.receive'))
        self.assertIn("new_trace_scope=trace_scope.bind_source",text)
        live=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='assert_receipt_live')
        self.assertIn('trace_scope.assert_receipt',ast.unparse(live))
        self.assertIn("epoch.get('new_trace_scope')",ast.unparse(live))

    def test_normalization_refuses_unknown_shapes_and_preserves_explicit_empty(self):
        self.assertEqual(gate.normalize(None),{})
        self.assertEqual(gate.normalize({}),{})
        for bad in ('F.Cu',[],{'/rated':[]},{'/rated':['F.Cu','F.Cu']},{'/rated':[True]}):
            with self.assertRaises(ValueError):gate.normalize(bad)

if __name__=='__main__':unittest.main()

import ast
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cec_rated_wave_context as wave
import cec_source_retaining_ses_import as retaining
SCRIPTS = Path(wave.__file__).resolve().parent


def function(file, name, env):
    tree = ast.parse((SCRIPTS / file).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    node.returns = None
    for arg in node.args.args + node.args.kwonlyargs: arg.annotation = None
    exec(compile(ast.Module(body=[node], type_ignores=[]), file, 'exec'), env)
    return env[name]


class RetainingWaveTests(unittest.TestCase):
    def policy(self, **extra):
        params = dict(wave_rated_current_export=True, wave_source_retaining_import=True)
        params.update(extra)
        return wave.policy_from_params(params, 'named')

    def job(self):
        return dict(policy=self.policy(), identity={'source_sha256': 'a'*64})

    def test_default_and_configuration_bounds(self):
        self.assertIsNone(wave.policy_from_params({}, None))
        disabled = wave.policy_from_params({'wave_rated_current_export': True}, 'named')
        self.assertNotIn('retaining_import', disabled)
        self.assertFalse(wave.retaining_requested(disabled))
        self.assertEqual(self.policy()['retaining_import']['native_s'], 10.)
        for extra in ({'wave_source_retaining_import': 1},
                      {'wave_source_retaining_wall_s': True},
                      {'wave_source_retaining_wall_s': 301},
                      {'wave_source_retaining_wall_s': float('nan')},
                      {'wave_source_retaining_native_s': 11},
                      {'wave_source_retaining_cleanup': 1},
                      {'wave_source_retaining_assembly_instance': 'unbound'}):
            with self.assertRaises(ValueError): self.policy(**extra)
        with self.assertRaises(ValueError):
            wave.policy_from_params({'wave_source_retaining_import': True}, 'named')

    def test_factory_disabled_never_creates_callback(self):
        self.assertIsNone(wave.import_operator('source', None))
        job = {'policy': {'board_hint': 'named', 'selected_current_nets': []}}
        with patch.object(wave, 'validate_job') as validation:
            self.assertIsNone(wave.import_operator('source', job))
            validation.assert_called_once_with('source', job)

    def test_factory_partial_epoch_and_bounds(self):
        job = self.job(); calls = []
        def callback(source, ses, out, **kwargs):
            calls.append(kwargs)
            kwargs['publication_guard']()
            return {'ok': True}
        with patch.object(wave, 'validate_job') as validation, patch.object(retaining, 'route_once_operator', callback):
            operator = wave.import_operator('source', job)
            self.assertEqual(json.loads(json.dumps(job)), job)  # no callable in IPC payload
            self.assertTrue(operator('source', 'ses', 'output')['ok'])
            self.assertEqual(validation.call_count, 3)  # construction, pre, in-transaction guard
        self.assertEqual(calls[0]['expected_source_sha256'], 'a'*64)
        self.assertEqual(calls[0]['native_s'], 10.)
        self.assertEqual(calls[0]['wall_s'], 120.)
        self.assertFalse(calls[0]['cleanup_dangling'])

    def test_factory_stale_job_refuses_before_import(self):
        with patch.object(wave, 'validate_job', side_effect=ValueError('stale')), patch.object(retaining, 'route_once_operator') as operator:
            with self.assertRaisesRegex(ValueError, 'stale'): wave.import_operator('source', self.job())
            operator.assert_not_called()

    def test_actual_worker_constructs_inside_execution(self):
        captured = []
        worker = function('cec_fr.py', '_worker', {'route_once': lambda *a, **k: captured.append(k)})
        args = dict(board_path='source', out_path='out', passes=2, opt_time=20, threads=4, seed=0)
        with patch.object(wave, 'import_operator', return_value='executing-worker-callback') as factory:
            worker(args); factory.assert_not_called()
            self.assertIsNone(captured[-1]['ses_import_operator'])
            args['rated_current_job'] = self.job(); worker(args)
            factory.assert_called_once_with('source', args['rated_current_job'])
            self.assertEqual(captured[-1]['ses_import_operator'], 'executing-worker-callback')

    def test_tier_refuses_before_scratch_export_or_jvm(self):
        env = dict(tempfile=types.SimpleNamespace(mkdtemp=lambda **k: self.fail('scratch created')))
        tier = function('cec_staged_fr.py', 'route_tiered', env)
        with self.assertRaisesRegex(ValueError, 'not_supported_by_tiered_backend'):
            tier('source', 'output', rated_current_policy=self.policy())

    def test_direct_oracle_constructs_before_call(self):
        tree = ast.parse((SCRIPTS / 'cec_synth_pipeline.py').read_text())
        route = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and n.func.attr == 'route_once'
                     and getattr(n.func.value, 'id', None) == 'cec_fr')
        kwargs = {kw.arg: ast.unparse(kw.value) for kw in route.keywords}
        self.assertEqual(kwargs['ses_import_operator'], '_retaining_import')
        self.assertEqual(kwargs['rated_current_job'], '_rated_job')

    def test_assembly_identity_is_resolved_not_caller_approval(self):
        policy = self.policy(wave_source_retaining_assembly_instance={'opaque': 'not-a-real-instance'})
        with patch.object(wave, '_identity', return_value={'source_sha256': 'a'*64}), patch.object(retaining, 'assembly_identity', side_effect=ValueError('unbound assembly')):
            with self.assertRaises(ValueError):
                wave._job_identity('source', policy)

    def test_guard_false_and_exception_rollback_exact_own_publication(self):
        for fail_at in (1, 3, 4):  # upfront, pre-board, post-board transaction checks
            for kind in ('false', 'exception'):
                with self.subTest(fail_at=fail_at, kind=kind), tempfile.TemporaryDirectory() as temp:
                    base = Path(temp); source = base/'source.kicad_pcb'; source.write_bytes(b'ORIGINAL OPAQUE')
                    sidecar = source.with_suffix('.kicad_pro'); sidecar.write_bytes(b'ORIGINAL POLICY')
                    control = base/'immutable-control.kicad_pcb'; control.write_bytes(b'CONTROL')
                    output = base/'output'/'child.kicad_pcb'; calls = 0
                    def guard():
                        nonlocal calls
                        calls += 1
                        if calls == fail_at:
                            if kind == 'false': return False
                            raise ValueError('late epoch')
                        return True
                    def fake_import(source, ses, proof, **kwargs):
                        proof = Path(proof); (proof/'candidate').mkdir(parents=True)
                        candidate = proof/'candidate'/'board.kicad_pcb'; candidate.write_bytes(b'NEW CANDIDATE')
                        candidate.with_suffix('.kicad_pro').write_bytes(b'NEW EXACT POLICY')
                        (proof/'receiving.json').write_text('{"ok":true}')
                        return dict(ok=True, candidate=str(candidate))
                    with patch.object(retaining, 'import_retaining_source', fake_import), patch.object(retaining, 'assert_receipt_live') as own_guard:
                        with self.assertRaises(ValueError):
                            retaining.route_once_operator(source, base/'route.ses', output,
                                board_hint='named', expected_source_sha256='a'*64, publication_guard=guard)
                        if fail_at > 1: self.assertTrue(own_guard.called)
                    self.assertFalse(output.exists())
                    self.assertFalse(output.with_suffix('.kicad_pro').exists())
                    self.assertFalse((output.parent/'source-retaining-proof-child').exists())
                    self.assertEqual(source.read_bytes(), b'ORIGINAL OPAQUE')
                    self.assertEqual(sidecar.read_bytes(), b'ORIGINAL POLICY')
                    self.assertEqual(control.read_bytes(), b'CONTROL')

    def test_bad_guard_rejected_before_output_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'output'/'child.kicad_pcb'
            with self.assertRaisesRegex(ValueError, 'callable_live_publication_guard_required'):
                retaining.route_once_operator(Path(temp)/'source.kicad_pcb', 'ses', output,
                    board_hint='named', expected_source_sha256='a'*64, publication_guard=True)
            self.assertFalse(output.parent.exists())


if __name__ == '__main__': unittest.main()

import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cec_rated_wave_context as wave
SCRIPTS = Path(wave.__file__).resolve().parent


def function(name, file, env):
    tree = ast.parse((SCRIPTS / file).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    node.returns = None
    for arg in node.args.args + node.args.kwonlyargs:
        arg.annotation = None
    exec(compile(ast.Module(body=[node], type_ignores=[]), file, 'exec'), env)
    return env[name]


class WaveTests(unittest.TestCase):
    def test_policy_default_and_shape(self):
        self.assertIsNone(wave.policy_from_params({}, None))
        self.assertIsNone(wave.bind_job('does-not-exist', None))
        for invalid in (1, 'true', [], None):
            with self.assertRaises(ValueError):
                wave.policy_from_params({'wave_rated_current_export': invalid}, 'named')
        with self.assertRaises(ValueError):
            wave.policy_from_params({'wave_rated_current_export': True}, '')

    def test_no_name_or_amp_heuristic(self):
        d = {'small': {'complete': True, 'source_refs': ['a'], 'sink_refs': ['b'], 'amps': .001},
             'large': {'complete': True, 'source_refs': ['c'], 'sink_refs': ['d'], 'amps': 9999}}
        self.assertEqual(wave._selected({'selected_current_nets': []}, d, d), set())
        self.assertEqual(wave._selected({'selected_current_nets': ['large']}, d, d), {'large'})
        with self.assertRaises(ValueError):
            wave._selected({'selected_current_nets': ['absent']}, d, d)

    def test_queued_mutation_and_companion_reject(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'board.kicad_pcb'; p.write_text('saved')
            def identity(path, hint):
                return {'source': str(p), 'source_sha256': wave._sha(p),
                        'companions': {}, 'code': 'fixed'}
            with patch.object(wave, '_identity', identity), patch.object(wave, '_authority', return_value='fixed'):
                job = wave.bind_job(p, {'board_hint': 'named', 'selected_current_nets': []})
                self.assertEqual(json.loads(json.dumps(job)), job)
                wave.validate_job(p, job)
                p.write_text('changed')
                with self.assertRaisesRegex(ValueError, 'epoch_changed'):
                    wave.validate_job(p, job)

    def test_family_identity_uses_bounded_family_and_inventory_race_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'board.kicad_pcb'; p.write_text('saved')
            family = {str(p): 'a'*64, str(p.with_suffix('.kicad_pro')): None}
            force = types.SimpleNamespace(_companion_inventory=lambda path: ({}, {}),
                _family=lambda path, hint: family, _code_identity=lambda: {'helper': 'hash'})
            with patch.dict(sys.modules, {'cec_force_current': force}):
                result = wave._identity(p, 'named')
                self.assertEqual(result['family'], family)
                self.assertIsNone(result['family'][str(p.with_suffix('.kicad_pro'))])
                inventory = iter([({}, {}), ({'.unknown': p}, {})])
                force._companion_inventory = lambda path: next(inventory)
                with self.assertRaisesRegex(ValueError, 'inventory_changed'):
                    wave._identity(p, 'named')

    def test_worker_actual_ast_forwarding(self):
        seen = []
        worker = function('_worker', 'cec_fr.py', {'route_once': lambda *a, **k: seen.append(k),
                                                  'Candidate': object})
        args = dict(board_path='board', out_path='out', passes=2, opt_time=20, threads=4, seed=0)
        worker(args); self.assertIsNone(seen[-1]['rated_current_job'])
        args['rated_current_job'] = {'identity': 'exact'}
        helper = types.SimpleNamespace(import_operator=lambda *args: None)
        with patch.dict(sys.modules, {'cec_rated_wave_context': helper}):
            worker(args)
        self.assertEqual(seen[-1]['rated_current_job'], args['rated_current_job'])

    def test_actual_route_export_default_bytes_and_optin(self):
        tree = ast.parse((SCRIPTS / 'cec_fr.py').read_text())
        route = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'route_once')
        branch = next(n for n in ast.walk(route) if isinstance(n, ast.If)
                      and ast.unparse(n.test) == 'rated_current_job is None')
        seen = []
        with tempfile.TemporaryDirectory() as temp:
            dsn = Path(temp) / 'export.dsn'
            def export(*args, **kwargs):
                dsn.write_bytes(b'EXACT DEFAULT DSN')
                seen.append(kwargs)
            env = dict(rated_current_job=None, hinted_board='hinted', dsn_path=str(dsn),
                       export_dsn=export, board_path='source', completed_nets=())
            block = compile(ast.Module(body=[branch], type_ignores=[]), 'actual_route_ast', 'exec')
            exec(block, env)
            self.assertEqual(dsn.read_bytes(), b'EXACT DEFAULT DSN')
            self.assertEqual(seen[-1], {})
            helper = types.SimpleNamespace(prepare=lambda *a, **k: {'export_context': {'bound': True}},
                                            restrict_pending=lambda *a: None)
            env['rated_current_job'] = {'saved': 'epoch'}
            with patch.dict(sys.modules, {'cec_rated_wave_context': helper}): exec(block, env)
            self.assertEqual(seen[-1]['rated_current_context'], {'bound': True})

    def test_actual_batch_construction_feeds_worker(self):
        seen = []
        class Pool:
            def __init__(self, **kw): pass
            def submit(self, worker, args):
                seen.append(args)
                return types.SimpleNamespace(result=lambda: types.SimpleNamespace(ok=True))
        # Future must be hashable.
        class Future:
            def result(self): return types.SimpleNamespace(ok=True)
        Pool.submit = lambda self, worker, args: (seen.append(args), Future())[1]
        guard = types.SimpleNamespace(pool_wall_budget=lambda *a, **k: 1,
            watched_as_completed=lambda pool, futures, **k: list(futures),
            shutdown_process_pool=lambda *a, **k: {}, WorkerPoolStalled=RuntimeError)
        helper = types.SimpleNamespace(bind_job=lambda path, policy: {'bound': path, 'policy': policy})
        env = dict(os=os, tempfile=tempfile, ensure_jar=lambda jar: 'pinned.jar',
            _worker=lambda args: None, ProcessPoolExecutor=Pool,
            Candidate=object, _TMP='/tmp', _DEFAULT_SEED_SPREAD={})
        batch = function('generate_batch', 'cec_fr.py', env)
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules,
                {'cec_rated_wave_context': helper, 'cec_process_pool': guard}):
            board = Path(temp) / 'board'; board.write_text('source')
            batch(str(board), seeds=(0,), out_dir=temp, params={}, max_workers=1)
            self.assertIsNone(seen[-1]['rated_current_job'])
            batch(str(board), seeds=(0,), out_dir=temp, params={}, max_workers=1,
                  rated_current_policy={'board_hint': 'named'})
            self.assertEqual(seen[-1]['rated_current_job']['bound'], str(board))

    def test_all_automatic_callers_opt_in(self):
        for filename, targets in [('cec_router.py', {'generate_batch', 'route_tiered'}),
                                  ('cec_synth_pipeline.py', {'route_tiered', 'route_once'})]:
            tree = ast.parse((SCRIPTS / filename).read_text())
            calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and n.func.attr in targets
                     and getattr(n.func.value, 'id', None) in {'cec_fr', 'cec_staged_fr'}]
            self.assertTrue(calls)
            for call in calls:
                key = 'rated_current_job' if call.func.attr == 'route_once' else 'rated_current_policy'
                self.assertIn(key, {kw.arg for kw in call.keywords})

    def test_staged_rebinds_and_restricts_before_backend(self):
        tree = ast.parse((SCRIPTS / 'cec_staged_fr.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == '_route_tiered_in_work')
        text = ast.unparse(fn)
        self.assertIn('rated_wave.bind_job(cur, rated_current_policy)', text)
        self.assertLess(text.index('rated_wave.restrict_pending'), text.index('cec_fr.run_freerouting'))
        self.assertLess(text.index('rated_wave.record'), text.index('cec_fr.run_freerouting'))

    def test_schema_boolean_and_malformed_net_collections(self):
        for value in ('/one-net', {'claimed': True}, 1, None, [None], ['']):
            with self.assertRaises(ValueError): wave._nets(value)
        self.assertIsNone(wave._nets(None, optional=True))
        self.assertEqual(wave._nets(('/a', '/b')), {'/a', '/b'})
        job = dict(schema=True, policy={'board_hint': 'named', 'selected_current_nets': []},
                   identity={}, authority_sha256='fixed')
        with self.assertRaises(ValueError): wave.validate_job('source', job)

    def test_native_pending_and_completed_revalidation_synthetic(self):
        class Pad:
            def __init__(self, net): self.net = net
            def GetNetname(self): return self.net
        class Board:
            def BuildConnectivity(self): pass
            def GetFootprints(self):
                return [types.SimpleNamespace(Pads=lambda: [Pad('/pending'), Pad('/complete'), Pad('/force')])]
        native = {'nets': {'/pending': {'complete': False}, '/force': {'complete': False},
                           '/complete': {'complete': True}}}
        domain = {'complete': True, 'source_refs': ['physical-source'], 'sink_refs': ['physical-sink']}
        modules = {'pcbnew': types.SimpleNamespace(LoadBoard=lambda source: Board()),
            'cec_current_topology': types.SimpleNamespace(
                board_current_domains=lambda *a, **k: {n: domain for n in native['nets']},
                route_width_contracts=lambda *a, **k: {n: {'amps': 9999} for n in native['nets']}),
            'cec_locked_net_ownership': types.SimpleNamespace(certificate=lambda *a, **k: native)}
        job = {'policy': {'board_hint': 'named', 'selected_current_nets': ['/pending', '/complete']},
               'identity': {'source': 'source', 'source_sha256': 'a'*64}}
        with patch.dict(sys.modules, modules), patch.object(wave, 'validate_job'):
            result = wave.prepare('source', job, completed_nets=['/pending', '/complete', '/unknown'])
            self.assertEqual(result['route_nets'], ['/pending'])
            self.assertEqual(result['completed_nets'], ['/complete'])
            self.assertEqual(result['completed_demoted'], ['/pending', '/unknown'])
            self.assertEqual(result['deferred_not_completed'], ['/force'])
            for bad in ('/pending', 7, {'/pending': True}):
                with self.assertRaises(ValueError): wave.prepare('source', job, requested_nets=bad)
                with self.assertRaises(ValueError): wave.prepare('source', job, completed_nets=bad)

    def test_spec_positional_fields_append_only(self):
        tree = ast.parse((SCRIPTS / 'cec_router.py').read_text())
        spec = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Spec')
        fields = [n.target.id for n in spec.body if isinstance(n, ast.AnnAssign)]
        self.assertEqual(fields[-2:], ['power_pours', 'rated_current_policy'])


if __name__ == '__main__': unittest.main()

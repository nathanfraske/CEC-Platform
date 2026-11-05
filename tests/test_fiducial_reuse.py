"""Bounded fiducial no-op reuse must never become physical admission."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cec_fiducial_reuse as reuse
import cec_full_pipeline as pipeline


def successful_noop():
    return {'ok': True, 'changed': False, 'moved': [], 'process_isolated': True,
            'craft_guard': {'applicable': False, 'reason': 'unchanged', 'before_key': [0]},
            'global_site_selection': {'enabled': True, 'power_state_error': None},
            'operation_evidence': {'operation': 'fiducial-repair',
                'status': 'complete', 'exit_code': 0, 'elapsed_s': 27.239,
                'directory': '/original/worker'}}


class FiducialReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.board = self.root / 'board.kicad_pcb'
        self.board.write_text('(kicad_pcb (footprint "cec:Test"))')
        self.footprint = self.root / 'Test.kicad_mod'
        self.footprint.write_text('(footprint "Test" (pad "1" smd circle))')
        scripts = self.root / 'scripts'
        scripts.mkdir()
        self.code = scripts / 'fiducial_engine.py'
        self.code.write_text('def operation(): return 1\n')
        self.cfg = SimpleNamespace(board='fixture', board_key='fixture',
            dir=str(self.root), sch=None, net=None, pcb=str(self.board),
            profile='consumer', pins={}, bom_csv=None,
            params={'fiducial_process_isolation': True})
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(reuse, 'ROOT', self.root).start()
        mock.patch('cec_pcb.fp_path', return_value=str(self.footprint)).start()
        self.cache = reuse.SameRunNoopReuse()
        self.action = mock.Mock(side_effect=lambda: successful_noop())

    def run_repair(self, **kwargs):
        return self.cache.run(self.cfg, self.board, self.action, **kwargs)

    def test_identical_successful_noop_reuses_and_copies_result(self):
        self.assertTrue(reuse.capture(self.cfg, self.board)['sha256'])
        first = self.run_repair(reconsider_all=True)
        self.assertTrue(first['fiducial_reuse']['eligible'])
        first['global_site_selection']['enabled'] = False
        second = self.run_repair(reconsider_all=True)
        self.assertTrue(second['fiducial_reuse']['used'])
        self.assertTrue(second['global_site_selection']['enabled'])
        self.assertEqual(second['operation_evidence']['status'], 'reused')
        self.assertNotIn('exit_code', second['operation_evidence'])
        self.assertEqual(second['fiducial_reuse']['source_operation_evidence']
                         ['elapsed_s'], 27.239)
        second['craft_guard']['reason'] = 'caller mutation'
        self.assertEqual(self.run_repair(reconsider_all=True)['craft_guard']['reason'],
                         'unchanged')
        self.assertEqual(self.action.call_count, 1)

    def test_no_cross_invocation_or_implicit_process_global_reuse(self):
        self.run_repair()
        reuse.SameRunNoopReuse().run(self.cfg, self.board, self.action)
        self.assertEqual(self.action.call_count, 2)
        with mock.patch.object(pipeline, '_run_priority_placement_operation_isolated',
                               side_effect=lambda *a, **k: successful_noop()) as worker:
            pipeline._transactional_fiducial_edge_repair(self.cfg, self.board)
            pipeline._transactional_fiducial_edge_repair(self.cfg, self.board)
        self.assertEqual(worker.call_count, 2)

    def test_only_isolated_wrapper_uses_explicit_invocation_cache(self):
        with mock.patch.object(pipeline, '_run_priority_placement_operation_isolated',
                               side_effect=lambda *a, **k: successful_noop()) as worker:
            pipeline._transactional_fiducial_edge_repair(
                self.cfg, self.board, reuse=self.cache)
            result = pipeline._transactional_fiducial_edge_repair(
                self.cfg, self.board, reuse=self.cache)
            self.assertTrue(result['fiducial_reuse']['used'])
            self.assertEqual(worker.call_count, 1)
        self.cfg.params['fiducial_process_isolation'] = False
        with mock.patch.object(self.cache, 'run') as cached, mock.patch.object(
                pipeline, '_transactional_fiducial_edge_repair_in_process',
                return_value={'ok': True}) as in_process:
            pipeline._transactional_fiducial_edge_repair(
                self.cfg, self.board, reuse=self.cache)
        cached.assert_not_called()
        in_process.assert_called_once()

    def test_pcb_edit_delete_and_recreate_invalidate(self):
        self.assertTrue(self.run_repair()['fiducial_reuse']['eligible'])
        self.board.write_text('(kicad_pcb (footprint "cec:Test") (net 1 "other"))')
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
        self.board.unlink()
        self.assertFalse(self.run_repair()['fiducial_reuse']['eligible'])
        self.board.write_text('(kicad_pcb (footprint "cec:Test"))')
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
        self.assertEqual(self.action.call_count, 4)

    def test_present_and_absent_authority_rule_family_add_edit_delete(self):
        import cec_route_evidence
        paths = list(cec_route_evidence.artifact_paths(self.board).values())
        paths.extend(self.board.with_suffix(suffix) for suffix in reuse.EXTRA_SIDECARS)
        for path in sorted(set(paths) - {self.board}):
            with self.subTest(path=path.name):
                self.cache = reuse.SameRunNoopReuse()
                self.assertTrue(self.run_repair()['fiducial_reuse']['eligible'])
                path.write_text('{}')
                self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
                path.write_text('{"revision": 2}')
                self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
                path.unlink()
                self.assertFalse(self.run_repair()['fiducial_reuse']['used'])

    def test_referenced_external_skeleton_and_its_rules_are_bound(self):
        skeleton = self.root / 'external.kicad_pcb'
        self.board.with_suffix('.pourfirst-state.json').write_text(
            json.dumps({'skeleton': str(skeleton)}))
        self.assertTrue(self.run_repair()['fiducial_reuse']['eligible'])
        skeleton.write_text('native external skeleton')
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
        skeleton.with_suffix('.kicad_dru').write_text('(version 1)')
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
        skeleton.unlink()
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])

    def test_actual_footprint_bytes_add_edit_delete_and_resolver_path_invalidate(self):
        self.assertTrue(self.run_repair()['fiducial_reuse']['eligible'])
        self.footprint.write_text('(footprint "Test" (pad "1" smd rect))')
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
        self.footprint.unlink()
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
        self.footprint.write_text('(footprint "Test")')
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
        alternate = self.root / 'alternate.kicad_mod'
        alternate.write_bytes(self.footprint.read_bytes())
        with mock.patch('cec_pcb.fp_path', return_value=str(alternate)):
            self.assertFalse(self.run_repair()['fiducial_reuse']['used'])

    def test_options_config_code_and_new_dynamic_module_invalidate(self):
        self.assertTrue(self.run_repair(reconsider_all=False)['fiducial_reuse']['eligible'])
        self.assertFalse(self.run_repair(reconsider_all=True)['fiducial_reuse']['used'])
        self.cfg.params['optical_policy'] = {'revision': 2}
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
        self.cfg.pins['J1'] = 'MECHANICAL'
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
        self.cfg.profile = 'pro'
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
        self.code.write_text('def operation(): return 2\n')
        self.assertFalse(self.run_repair()['fiducial_reuse']['eligible'])
        self.assertFalse(self.run_repair()['fiducial_reuse']['eligible'])
        dynamic = self.code.with_name('gen-module-pcb.py')
        dynamic.write_text('LIBRARY_REVISION = 1\n')
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
        dynamic.unlink()
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])

    def test_missing_file_valued_config_and_policy_add_edit_delete_invalidate(self):
        referenced = self.root / 'authority.json'
        self.cfg.params['authority_file'] = str(referenced)
        for path in (referenced, self.root / 'pipeline-policy.json',
                     self.root / 'fp-lib-table'):
            self.run_repair()
            for payload in ('{}', '{"revision":2}', None):
                if payload is None:
                    path.unlink()
                else:
                    path.write_text(payload)
                self.assertFalse(self.run_repair()['fiducial_reuse']['used'])

    def test_source_mutation_during_work_including_edit_restore_never_seeds(self):
        sidecar = self.board.with_suffix('.kicad_dru')
        sidecar.write_text('rules')
        for path in (self.board, sidecar, self.footprint, self.code):
            for restore in (False, True):
                with self.subTest(path=path.name, restore=restore):
                    original = path.read_bytes()
                    self.cache = reuse.SameRunNoopReuse()
                    def mutate():
                        path.write_bytes(original + b'\n')
                        if restore:
                            path.write_bytes(original)
                        return successful_noop()
                    self.action.side_effect = mutate
                    self.assertFalse(self.run_repair()['fiducial_reuse']['eligible'])
                    self.action.side_effect = lambda: successful_noop()
                    self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
                    path.write_bytes(original)

    def test_config_mutation_during_work_does_not_seed(self):
        def mutate():
            self.cfg.params['new_option'] = True
            return successful_noop()
        self.action.side_effect = mutate
        self.assertFalse(self.run_repair()['fiducial_reuse']['eligible'])
        self.action.side_effect = lambda: successful_noop()
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])

    def test_environment_policy_changes_invalidate_but_supervisor_deadlines_do_not(self):
        self.assertTrue(self.run_repair()['fiducial_reuse']['eligible'])
        with mock.patch.dict(os.environ, {'CEC_JOB_DEADLINE_EPOCH': '9999999999',
                                         'CEC_OPERATION_DEADLINE_EPOCH': '9999999998'}):
            self.assertTrue(self.run_repair()['fiducial_reuse']['used'])
        with mock.patch.dict(os.environ, {'CEC_FIDUCIAL_TEST_POLICY': 'changed'}):
            self.assertFalse(self.run_repair()['fiducial_reuse']['used'])

    def test_authority_add_delete_during_work_cannot_seed(self):
        sidecar = self.board.with_suffix('.power-prefix.json')
        for add in (True, False):
            with self.subTest(add=add):
                self.cache = reuse.SameRunNoopReuse()
                def mutate():
                    if add:
                        sidecar.write_text('{}')
                    else:
                        sidecar.unlink()
                    return successful_noop()
                self.action.side_effect = mutate
                self.assertFalse(self.run_repair()['fiducial_reuse']['eligible'])
                self.action.side_effect = lambda: successful_noop()
                self.assertFalse(self.run_repair()['fiducial_reuse']['used'])

    def test_failed_rolled_back_skipped_timeout_and_incomplete_do_not_seed(self):
        modifications = (
            {'ok': False}, {'changed': True}, {'skipped': 'no_front_fiducials'},
            {'rolled_back': True}, {'error': 'native error'}, {'errors': ['error']},
            {'budget_exhausted': True}, {'timed_out': True},
            {'global_site_selection': {'enabled': True, 'power_state_error': 'bad JSON'}},
            {'global_site_selection': {'enabled': False}},
            {'operation_evidence': {'operation': 'fiducial-repair',
                                    'status': 'complete', 'exit_code': 1}},
            {'operation_evidence': {'operation': 'fiducial-repair',
                                    'status': 'operation_budget_exhausted', 'exit_code': 0}},
            {'operation_evidence': {}}, {'changed': None}, {'ok': 1},
            {'craft_guard': {'reason': 'unchanged', 'before_key': [1]}},
        )
        for change in modifications:
            with self.subTest(change=change):
                self.cache = reuse.SameRunNoopReuse()
                candidate = successful_noop()
                candidate.update(change)
                self.action.side_effect = lambda: copy.deepcopy(candidate)
                self.assertFalse(self.run_repair()['fiducial_reuse']['eligible'])
                self.assertFalse(self.run_repair()['fiducial_reuse']['used'])

    def test_exception_and_unreadable_identity_fall_back_without_seeding(self):
        self.action.side_effect = TimeoutError('worker timed out')
        with self.assertRaises(TimeoutError):
            self.run_repair()
        self.action.side_effect = lambda: successful_noop()
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])
        with mock.patch.object(reuse, 'capture', side_effect=OSError('unreadable')):
            self.assertFalse(self.run_repair()['fiducial_reuse']['eligible'])
        self.assertFalse(self.run_repair()['fiducial_reuse']['used'])

    def test_mutation_during_hit_validation_forces_fresh_operation(self):
        self.run_repair()
        original = reuse.capture
        captures = 0
        def changing(*args, **kwargs):
            nonlocal captures
            captures += 1
            if captures == 2:
                self.footprint.write_text('(footprint "changed geometry")')
            return original(*args, **kwargs)
        with mock.patch.object(reuse, 'capture', side_effect=changing):
            result = self.run_repair()
        self.assertFalse(result['fiducial_reuse']['used'])
        self.assertFalse(result['fiducial_reuse']['eligible'])
        self.assertEqual(self.action.call_count, 2)

    def test_late_finalization_still_rebinds_physical_authority_on_hit(self):
        with mock.patch.object(pipeline, '_run_priority_placement_operation_isolated',
                               side_effect=lambda *a, **k: successful_noop()), \
                mock.patch.object(pipeline, '_snapshot_placement_authority'), \
                mock.patch('cec_synth_pipeline.config_with_board_route_authority',
                           return_value=(self.cfg, {'ok': True, 'bound': False})) as bind:
            pipeline._transactional_fiducial_edge_repair(
                self.cfg, self.board, reconsider_all=True, reuse=self.cache)
            result = pipeline._finalize_fiducials_after_route_authority(
                self.cfg, self.board, fiducial_reuse=self.cache)
        self.assertTrue(result['repair']['fiducial_reuse']['used'])
        self.assertFalse(result['accepted'])
        self.assertFalse(result['changed'])
        bind.assert_called_once()


if __name__ == '__main__':
    unittest.main()

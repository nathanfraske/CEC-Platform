"""Pure policy/receiver orchestration tests ONLY: no production/native imports."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1]/'scripts'/'cec_source_ground_leaf_slide.py'
spec = importlib.util.spec_from_file_location('source_ground_leaf_slide_tests', MODULE)
slide = importlib.util.module_from_spec(spec)
spec.loader.exec_module(slide)


def facts():
    return dict(axis_nm=[2000000, 0], corner_nm=[0, 0], role_kind=slide.ROLE,
        role_current_authority=False, edge_count=2, pad_count=1, other_barrel_count=0,
        branch_count=0, foreign_zone_contact_count=0, copper_graphic_contact_count=0,
        net='GND', all_unlocked=True, all_ungrouped=True, same_face=True,
        full_width_nm=500000, edge_widths_nm=[500000, 500000],
        ordinary_uniform_through=True, dimensions_meet_class=True,
        source_reference_contacts_proved=True)


def rotate(point, turn):
    x, y = point
    for _ in range(turn):
        x, y = -y, x
    return [x, y]


class Policy(unittest.TestCase):
    def test_wide_terminal_may_touch_the_same_single_root_only(self):
        self.assertEqual(slide._exclusive_root_contacts(['root'], [], []), 'root')
        self.assertEqual(slide._exclusive_root_contacts(['root'], ['root'], []), 'root')
        for contacts in (([], [], []), (['root', 'other'], [], []),
                         (['root'], ['other'], []), (['root'], ['root', 'other'], []),
                         (['root'], [], ['root']), (['root'], ['root'], ['other'])):
            with self.subTest(contacts=contacts), self.assertRaises(ValueError):
                slide._exclusive_root_contacts(*contacts)

    def test_quarter_turns_and_back_face_do_not_change_positive_policy(self):
        for turn in range(4):
            for back in (False, True):
                with self.subTest(turn=turn, back=back):
                    f = facts()
                    # Face selection is an exhaustive native fact, not a face
                    # name grant; both F/B use the same integer geometry policy.
                    f['axis_nm'] = rotate(f['axis_nm'], turn)
                    f['corner_nm'] = rotate(f['corner_nm'], turn)
                    new = rotate([1600000, 0], turn)
                    if back:
                        for p in (f['axis_nm'], f['corner_nm'], new):
                            p[0] = -p[0]
                    result = slide._policy(f, new)
                    self.assertEqual(result['translation_nm'], 400000)
                    self.assertEqual(result['shortened_terminal_length_nm'], 1600000)

    def test_diagonal_collinear_positive(self):
        f = facts(); f['axis_nm'] = [2000000, 2000000]
        self.assertLess(slide._policy(f, [1600000, 1600000])['translation_nm'], 1000000)

    def test_bounded_one_mm_inclusive(self):
        self.assertEqual(slide._policy(facts(), [1000000, 0])['translation_nm'], 1000000)

    def test_illegal_new_axes(self):
        for new in ([2000000, 0], [0, 0], [-1, 0], [2000001, 0], [1600000, 1],
                    [999999, 0], [True, 0], [1600000., 0], (1600000, 0), [], [0, 0, 0]):
            with self.subTest(new=new), self.assertRaises((ValueError, TypeError)):
                slide._policy(facts(), new)

    def test_every_independent_refusal(self):
        cases = dict(role_kind='unknown', role_current_authority=True, edge_count=3,
            pad_count=2, other_barrel_count=1, branch_count=1, foreign_zone_contact_count=1,
            copper_graphic_contact_count=1, net='+3V3', all_unlocked=False,
            all_ungrouped=False, same_face=False, full_width_nm=0,
            edge_widths_nm=[500000, 350000], ordinary_uniform_through=False,
            dimensions_meet_class=False, source_reference_contacts_proved=False)
        for key, value in cases.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                f = facts(); f[key] = value; slide._policy(f, [1600000, 0])

    def test_no_lowpower_or_programming_alias(self):
        for role in ('positive_existing_low_power_ground_boundary', 'source_programming_resistor',
                     'grounded_voltage_monitor_divider_lower', '', None):
            with self.subTest(role=role), self.assertRaises(ValueError):
                f = facts(); f['role_kind'] = role; slide._policy(f, [1600000, 0])

    def test_strict_current_and_process_booleans(self):
        for key, value in (('role_current_authority', 0), ('all_unlocked', 1),
                           ('ordinary_uniform_through', 1), ('source_reference_contacts_proved', 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                f = facts(); f[key] = value; slide._policy(f, [1600000, 0])

    def test_rename_independent_facts_no_designator_input(self):
        self.assertNotIn('reference', facts())
        self.assertNotIn('board_hint', facts())
        self.assertEqual(slide._policy(facts(), [1600000, 0])['translation_nm'], 400000)

    def test_request_strict_types_and_no_extra_authority_fields(self):
        request = slide._request('11111111-1111-4111-8111-111111111111', [1, 2])
        self.assertEqual(set(request), {'via_uuid', 'new_axis_nm'})
        for uid in ('R18', '', None, '11111111-1111-4111-8111-11111111111Z'):
            with self.subTest(uid=uid), self.assertRaises((ValueError, TypeError, AttributeError)):
                slide._request(uid, [1, 2])

    def test_deadline_bound(self):
        for seconds in (True, 0, -1, 9.100001, 10, float('inf'), float('nan')):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                slide._deadline(seconds)

    def test_canonical_json_rejects_false_zero(self):
        with self.assertRaises(ValueError):
            slide._same({'authority': False}, {'authority': 0}, 'changed')

    def test_no_boolean_counts_or_float_widths(self):
        for key, value in (('branch_count', False), ('pad_count', True),
                           ('edge_widths_nm', [500000., 500000])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                f = facts(); f[key] = value; slide._policy(f, [1600000, 0])

    def test_exact_saved_integer_coordinate_and_no_extra_attributes(self):
        self.assertEqual(slide._saved_axis([('at', 'at'), ('1.600000', '1.600000'),
                                           ('-0.000001', '-0.000001')], 'at'), [1600000, -1])
        for tokens in ([('at', 'at'), ('1', '1'), ('2', '2'), ('90', '90')],
                       [('at', 'at'), ('0.0000001', '0.0000001'), ('0', '0')],
                       [('at', 'at'), ('1', '"1"'), ('0', '0')],
                       [('at', 'at'), ('NaN', 'NaN'), ('0', '0')],
                       [('at', 'at'), ('bad', 'bad'), ('0', '0')]):
            with self.subTest(tokens=tokens), self.assertRaises(ValueError):
                slide._saved_axis(tokens, 'at')


class FreshnessAndReceiving(unittest.TestCase):
    def test_proposal_rederived_not_accepted_as_authority(self):
        original = {'kind': slide.KIND, 'board_hint': 'fixture', 'request':
                    {'via_uuid': '11111111-1111-4111-8111-111111111111', 'new_axis_nm': [1, 2]},
                    'context': {'Source': 'a', 'code': 'b'}}
        for key in ('Source', 'code'):
            with self.subTest(key=key):
                changed = copy.deepcopy(original); changed['context'][key] = 'changed'
                with patch.object(slide, 'plan', return_value=changed), self.assertRaises(ValueError):
                    slide._fresh(Path('unused'), original, slide._deadline(1))

    def _receive(self, contexts=None, failing=None):
        with tempfile.TemporaryDirectory() as work:
            source = Path(work)/'source'; candidate = Path(work)/'candidate'
            source.write_bytes(b'source'); candidate.write_bytes(b'candidate')
            proposal = {'board_hint': 'fixture'}
            calls = []
            bindings = iter(contexts or [{'Source': 'a', 'candidate': 'b', 'code': 'c'}]*4)
            def operation(*args, phase, timeout_s):
                calls.append(phase)
                if phase == failing:
                    raise ValueError('refused:' + phase)
                return dict(phase=phase, phase_complete=True, complete=False, ok=True,
                            context=next(bindings), proposal_sha256='same-proposal',
                            Source_role={'canonical_files': 'same'}, evidence=True)
            with patch.object(slide, 'receive_phase', side_effect=operation):
                result = slide.receive(source, candidate, proposal, constituent_timeout_s=1)
            return result, calls

    def test_all_named_gates_mandatory_and_no_admission(self):
        result, calls = self._receive()
        self.assertEqual(calls, list(slide.PHASES))
        self.assertEqual(list(result['phase_results']), list(slide.PHASES))
        self.assertEqual(result['declared_maximum_composite_s'], 4)
        self.assertFalse(result['current_authority'])
        self.assertFalse(result['release_authority'])
        self.assertFalse(result['routing_admitted'])

    def test_each_saved_source_candidate_code_mutation_is_fatal(self):
        for key in ('Source', 'candidate', 'code'):
            for boundary in range(1, 4):
                original = {'Source': 'a', 'candidate': 'b', 'code': 'c'}
                contexts = [copy.deepcopy(original) for _ in range(4)]
                contexts[boundary][key] = 'changed'
                with self.subTest(key=key, boundary=boundary), self.assertRaises(ValueError):
                    self._receive(contexts)

    def test_any_receiver_gate_refusal_is_terminal(self):
        for gate in slide.PHASES:
            with self.subTest(gate=gate), self.assertRaisesRegex(ValueError, 'refused:' + gate):
                self._receive(failing=gate)

    def test_live_canonical_schematic_and_exporter_fence(self):
        monitor = types.SimpleNamespace(_owner_live=lambda role: False)
        with patch.dict('sys.modules', {'cec_monitor_divider_ground_return': monitor}), \
             patch.object(slide, '_context', return_value={'same': True}), \
             self.assertRaisesRegex(ValueError, 'canonical_schematic_or_exporter_changed'):
            slide._live({'same': True}, [], 'fixture', {'fresh-role': True})

    def test_source_family_and_code_fence_even_if_role_is_live(self):
        monitor = types.SimpleNamespace(_owner_live=lambda role: True)
        with patch.dict('sys.modules', {'cec_monitor_divider_ground_return': monitor}), \
             patch.object(slide, '_context', return_value={'changed': True}), \
             self.assertRaisesRegex(ValueError, 'Source_candidate_code_or_family_changed'):
            slide._live({'same': True}, [], 'fixture', {'fresh-role': True})

    def test_partial_phase_runs_canonical_finally_fence_on_success_and_refusal(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as work:
                source = Path(work)/'source'; candidate = Path(work)/'candidate'
                source.write_bytes(b'source'); candidate.write_bytes(b'candidate')
                role = {'fresh-role': True}
                proposal = dict(kind=slide.KIND, source=str(source.resolve()), board_hint='fixture',
                                context={'Source': 'same'}, proof={'Source_role': role})
                with patch.object(slide, '_context', return_value={'bound': True}), \
                     patch.object(slide, '_live') as live, \
                     patch.object(slide, '_material', side_effect=ValueError('refused') if fail else None,
                                  return_value={'passed': True}):
                    if fail:
                        with self.assertRaisesRegex(ValueError, 'refused'):
                            slide.receive_phase(source, candidate, proposal, phase=slide.PHASES[1], timeout_s=1)
                    else:
                        result = slide.receive_phase(source, candidate, proposal, phase=slide.PHASES[1], timeout_s=1)
                        self.assertFalse(result['complete'])
                        self.assertTrue(result['phase_complete'])
                    self.assertEqual(live.call_count, 2)
                    self.assertEqual(live.call_args.args[-1], role)

    def test_normal_only_and_actual_circle_stock_adapter_present(self):
        # Static contract guard, NOT a native exercise.
        source = MODULE.read_text()
        self.assertIn('via.Padstack().Mode() == pcbnew.PADSTACK.MODE_NORMAL', source)
        self.assertIn('native_lands.inspect(board, via', source)
        self.assertIn('native_padstack_via=via', source)
        self.assertNotIn('coordinate-only.kicad_pcb', source)

    def test_no_production_imports_for_policy_tests(self):
        # The test module calls ONLY the pure functions and mocked orchestration.
        self.assertNotIn('pcbnew', slide.__dict__)


if __name__ == '__main__':
    unittest.main()

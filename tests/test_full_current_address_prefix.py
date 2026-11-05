"""Native source-role fixtures; no worker-authored address allow-list."""
import copy
import unittest
from unittest.mock import patch
import test_address_supply as base
import cec_full_current_supply_prefix as subject
import cec_cell_escape_replan as escape


class PrefixTests(base.Tests):
    def context(self):
        source, child, proposal = self.fixture()
        proposal.update(scope='source_typed_complete_cell_escape_proposal', max_shift_mm=16.)
        contract = dict(copy.deepcopy(base.CONTRACT), profile='fixture-profile')
        return source, child, proposal, contract

    def derive(self, source, child, proposal, contract, *, received=None):
        contracts = {'rail-renamable': contract if received is None else received}
        with patch.object(escape, 'prepare', return_value=copy.deepcopy(proposal)), \
                patch.object(base.subject.cell, '_supply_current_widths', return_value=contract):
            return subject._source_address_roles(child, contracts, source, proposal, timeout_s=2.)

    def test_prefix_positive_exact_native_address(self):
        s, b, p, c = self.context()
        result = self.derive(s, b, p, c)
        self.assertEqual(set(result), {base.subject.force._uid(b.FindFootprintByReference('ANY_OWNER').FindPadByNumber('1'))})

    def test_prefix_default_context_neutral(self):
        s, b, p, c = self.context()
        self.assertEqual(subject._source_address_roles(b, {}, None, None, timeout_s=1.), {})

    def test_prefix_replay_retains_source_reference_scope(self):
        s,b,p,c=self.context();p['reference_group_uuids']=['renamable-source-owned-reference-group']
        with patch.object(escape,'prepare',return_value=copy.deepcopy(p))as replay, \
                patch.object(base.subject.cell,'_supply_current_widths',return_value=c):
            assert subject._source_address_roles(b,{'rail-renamable':c},s,p,timeout_s=2.)
        self.assertEqual(replay.call_args.kwargs['reference_group_uuids'],p['reference_group_uuids'])

    def test_prefix_partial_context_refuses(self):
        s, b, p, c = self.context()
        for first, second in ((s, None), (None, p)):
            with self.assertRaisesRegex(ValueError, 'complete_source_address_prefix_context'):
                subject._source_address_roles(b, {}, first, second, timeout_s=1.)

    def test_prefix_forged_proposal_refuses(self):
        s, b, p, c = self.context()
        with patch.object(escape, 'prepare', return_value=dict(p, max_shift_mm=8.)):
            with self.assertRaisesRegex(ValueError, 'stale_or_forged'):
                subject._source_address_roles(b, {'rail-renamable': c}, s, p, timeout_s=1.)

    def test_prefix_wrong_current_refuses(self):
        s, b, p, c = self.context(); changed = dict(c, current_authority={'new': 'guessed-current'})
        with self.assertRaisesRegex(ValueError, 'unchanged_current_contract'):
            self.derive(s, b, p, c, received=changed)

    def test_prefix_wrong_source_owner_refuses(self):
        s, b, p, c = self.context(); p['poses'] = {'UNKNOWN_OWNER': [12, 17, 0]}
        with self.assertRaisesRegex(ValueError, 'source_owner_missing'):
            self.derive(s, b, p, c)

    def test_prefix_unknown_role_grants_nothing(self):
        s, b, p, c = self.context()
        with patch.object(base.subject.roles, 'footprint_contract', return_value={'pins': {'1': 'signal_input', '2': 'power_input'}}):
            self.assertEqual(self.derive(s, b, p, c), {})

    def test_prefix_default_classifier_does_not_expand_address(self):
        s, b, p, c = self.context()
        self.assertIsNone(subject.supply_terminal_role(b.FindFootprintByReference('ANY_OWNER').FindPadByNumber('1')))

    def test_prefix_wrong_native_origin_refuses(self):
        s, b, p, c = self.context();land=b.FindFootprintByReference('ANY_OWNER').FindPadByNumber('1')
        land.SetPosition(base.pcbnew.VECTOR2I(13000000,17000000))
        with self.assertRaisesRegex(ValueError, 'relative_geometry'):
            self.derive(s, b, p, c)


if __name__ == '__main__':
    unittest.main()

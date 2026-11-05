"""No nested saved receiver may silently drop source ownership options."""
import copy
from unittest.mock import patch

import pytest
import cec_cell_escape_replan as subject


@pytest.mark.parametrize('explicit',[False,True])
@pytest.mark.parametrize('with_rc_prefix',[False,True])
def test_one_replay_forwards_every_current_source_option_without_authorizing_it(explicit,with_rc_prefix):
    board=object()
    proposal=dict(scope='source_typed_complete_cell_escape_proposal',board_hint='renamed-source',
        poses={'renamed-owner':[1.,2.,90.]},max_shift_mm=16.)
    if explicit:
        proposal.update(allow_owned_locked_escapes=True,rebuild_projected_ground=True,
            allow_octilinear_rotations=True,reference_group_uuids=['arbitrary-source-group'])
    prefix=[dict(pad_uuid='actual-input',canonical_span_uuid='actual-span',
        boundary_track_uuid='actual-boundary')] if with_rc_prefix else ()
    if with_rc_prefix:proposal['source_rc_input_prefixes']=copy.deepcopy(prefix)
    before=copy.deepcopy(proposal);fresh=dict(proposal,independently_recompiled=True)
    with patch.object(subject,'prepare',return_value=fresh)as compiler:
        assert subject.recompile_source_proposal(board,proposal,board_hint='renamed-source')is fresh
        compiler.assert_called_once_with(board,proposal['poses'],board_hint=proposal['board_hint'],
            max_shift_mm=16.,allow_owned_locked_escapes=explicit,
            rebuild_projected_ground=explicit,allow_octilinear_rotations=explicit,
            reference_group_uuids=['arbitrary-source-group']if explicit else (),
            source_rc_input_prefixes=prefix)
    assert proposal==before


@pytest.mark.parametrize('proposal,hint',[(None,None),({},None),
    ({'scope':'caller-authored-permission'},None),
    ({'scope':'source_typed_complete_cell_escape_proposal','board_hint':'one'},'another')])
def test_wrong_source_context_refuses_before_any_compilation(proposal,hint):
    with patch.object(subject,'prepare')as compiler:
        with pytest.raises(ValueError,match='exact_source_proposal_replay_context'):
            subject.recompile_source_proposal(object(),proposal,board_hint=hint)
        compiler.assert_not_called()


def test_source_compiler_failure_is_not_converted_to_ownership_permission():
    proposal=dict(scope='source_typed_complete_cell_escape_proposal',board_hint='renamed-source',
        poses={'renamed-owner':[1.,2.,90.]},max_shift_mm=16.,reference_group_uuids=['unproved'])
    with patch.object(subject,'prepare',side_effect=ValueError('actual_source_group_not_owned')):
        with pytest.raises(ValueError,match='actual_source_group_not_owned'):
            subject.recompile_source_proposal(object(),proposal)

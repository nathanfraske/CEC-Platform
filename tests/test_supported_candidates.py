import time
from unittest.mock import Mock, patch
import pytest
import cec_supported_candidates as supported
import cec_priority_dependency as dependency


def test_support_precedes_small_beam_without_changing_objective_order():
    stats={}
    rows=supported.select_ranked(range(256),limit=2,predicate=lambda n:n in {90,91,110},
        max_checks=128,diagnostics=stats)
    assert rows==[90,91]
    assert stats['checked']==92 and stats['rejected']==90
    assert stats['stop_reason']=='selection_limit' and not stats['admission_authority']


def test_check_cap_is_inconclusive_not_an_unchecked_fallback():
    stats={}
    assert supported.select_ranked(range(1000),limit=4,predicate=lambda n:n>32,
        max_checks=32,diagnostics=stats)==[]
    assert stats['checked']==stats['rejected']==32
    assert stats['stop_reason']=='check_limit'


def test_no_predicate_retains_historical_prefix_and_zero_limit_checks_nothing():
    assert supported.select_ranked(range(100),limit=3,max_checks=0)==[0,1,2]
    predicate=Mock(side_effect=AssertionError('not allowed'))
    assert supported.select_ranked(range(100),limit=0,predicate=predicate)==[]
    assert supported.select_ranked(range(100),limit=2,predicate=predicate,
        deadline=time.monotonic()-1)==[]
    assert not predicate.called


def test_checker_failure_and_truthy_error_dict_do_not_admit_candidates():
    stats={}
    with pytest.raises(TypeError,match='bool'):
        supported.select_ranked(range(2),limit=1,predicate=lambda n:{'ok':False},diagnostics=stats)
    assert stats['stop_reason']=='predicate_error'
    with pytest.raises(RuntimeError,match='checker failed'):
        supported.select_ranked(range(2),limit=1,predicate=Mock(side_effect=RuntimeError('checker failed')))


def test_native_predicate_accepts_only_normal_or_scoped_retained_proof():
    conflict={'ok':False,'violations':[{'reason':'owned'}]}
    context=Mock();context.check.side_effect=[{'ok':True},conflict,conflict]
    poses={'arbitrary':(1,2,90)}
    with patch('cec_frozen_copper.FrozenCopperContext',return_value=context), \
            patch.object(dependency,'screen_placement_handoff',side_effect=[{'ok':False},{'ok':True}]) as screen:
        predicate=dependency.placement_support_predicate('immutable-board',{},back_refs=('back',),max_pairs=2)
        assert predicate(poses) is True
        assert not screen.called
        assert predicate(poses) is False
        assert predicate(poses) is True
        assert screen.call_count==2
        assert screen.call_args.kwargs['max_pairs']==2
        assert screen.call_args.kwargs['back_refs']==('back',)
        assert screen.call_args.args[3]=={'placements':poses}

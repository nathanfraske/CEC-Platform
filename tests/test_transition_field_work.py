"""Do not spend secondary return-field work on impossible primary barrels."""
from unittest.mock import Mock

import pytest
import cec_precision_route as route


ROW = dict(p=(3.,4.), n=(3.,4.75), center=(3.,4.375), side='start')


@pytest.mark.parametrize('failed', [1,2,3])
def test_blocked_signal_pair_skips_ground_search_and_keeps_both_witnesses(failed):
    def signal(point, net, *, report):
        report.update(ok=not bool(failed & net), blockers=[{'net':net}])
        return None if failed & net else object()
    returns=Mock()
    result=route._probe_matched_transition_field(ROW,p_code=1,n_code=2,route_axis=(1.,0.),
        add_signal_via=signal,add_return_via=returns)
    assert not result['ok']
    assert result['return_status']=='not_attempted_signal_field_blocked'
    assert result['p_via']['blockers']==[{'net':1}]
    assert result['n_via']['blockers']==[{'net':2}]
    returns.assert_not_called()


@pytest.mark.parametrize('status,ok', [('covered',True),('added',True),
    ('no legal GND return via within 1.50mm of every pair member',False)])
def test_clear_signals_still_require_full_return_field(status,ok):
    events=[]
    def signal(point,net,**kw):events.append(net);return object()
    def returns(center,vector,**kw):
        assert events==[1,2]
        assert center==ROW['center'] and vector==(0.,.75)
        assert kw['signal_points']==(ROW['p'],ROW['n'])
        assert kw['portal_side']=='start'
        events.append('return');return [],status
    result=route._probe_matched_transition_field(ROW,p_code=1,n_code=2,route_axis=(1.,0.),
        add_signal_via=signal,add_return_via=returns)
    assert events==[1,2,'return'] and result['ok']==ok
    assert result['reason']==(None if ok else status)

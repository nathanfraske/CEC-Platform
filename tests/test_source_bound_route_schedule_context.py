"""The runtime caller must not silently erase its constrained-first policy."""
import pytest
import cec_native_route_schedule as schedule
import cec_ordinary_route_receiving as ordinary


def rows():return [dict(uid='a',net='SCALAR',width=200000),dict(uid='z',net='ANALOG',width=200000),
    dict(uid='p',net='HELD_POWER',width=600000),dict(uid='g',net='GND',width=200000)]


@pytest.mark.parametrize('priorities',[[],['SCALAR']])
def test_empty_optional_priority_list_does_not_disable_source_typing(monkeypatch,priorities):
    calls=[];board=object();source=object()
    def classify(b,s,h):calls.append((b,s,h));return {'SCALAR'}
    monkeypatch.setattr(ordinary,'eligible_nets',classify)
    got,eligible,proof=schedule.order_from_source(board,source,'synthetic',rows(),priorities,
        constrained_before_ordinary=True)
    assert calls==[(board,source,'synthetic')] and eligible=={'SCALAR'}
    assert [r['uid'] for r in got]==['p','g','z','a']
    assert proof['source_classifier_used'] and not proof['release_authority']


def test_legacy_untyped_order_does_not_claim_or_invoke_source_classification(monkeypatch):
    def forbidden(*args):raise AssertionError('legacy policy does not need classifier')
    monkeypatch.setattr(ordinary,'eligible_nets',forbidden)
    got,eligible,proof=schedule.order_from_source(None,None,'synthetic',rows(),[])
    assert [r['uid'] for r in got]==['p','g','a','z'] and eligible is None
    assert not proof['source_classifier_used']


@pytest.mark.parametrize('flag',[1,None,'yes'])
def test_source_policy_is_explicit_boolean(flag):
    with pytest.raises(ValueError):schedule.order_from_source(None,None,'synthetic',rows(),[],
        constrained_before_ordinary=flag)

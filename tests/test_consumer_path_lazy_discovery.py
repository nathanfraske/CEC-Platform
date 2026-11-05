"""Try a promising fully guarded path now; defer unused alternatives."""
import runpy
from pathlib import Path
import pytest
import cec_force_current as force
from test_consumer_corner_miter_tool import case,BUILD
from test_consumer_path_reflow_tool import baseline

TOOL=Path(__file__).resolve().parents[1]/'ops/cec_consumer_path_reflow.py'


def test_native_constructor_does_not_eagerly_prove_unused_alternatives(tmp_path,monkeypatch):
    source,b,*_=case(tmp_path,monkeypatch);api=runpy.run_path(str(TOOL));calls=[]
    original=api['inventory'];fn=api['run']
    def watched(*args,**kwargs):
        assert kwargs['limit_offers']==1;result=original(*args,**kwargs)
        assert len(result['offers'])<=1;calls.append(result);return result
    monkeypatch.setitem(fn.__globals__,'inventory',watched)
    result=fn(source,tmp_path/'work',board_hint='synthetic',expected_source_sha256=force._hash(source),
        grade=baseline(tmp_path,source),reporting_build=BUILD,allow_locked_source=True)
    assert result['changed'] and len(calls)==len(result['attempts'])==1
    assert calls[0]['stopped_at_offer_limit'] and not calls[0]['bounded_search_exhaustive']
    assert calls[0]['deferred_source_windows']>0 and not result['attempts'][0]['new_native_faults']


def test_refused_first_native_producer_resumes_search_without_repeating_the_offer(tmp_path,monkeypatch):
    source,b,*_=case(tmp_path,monkeypatch);api=runpy.run_path(str(TOOL));grade=baseline(tmp_path,source)
    original=api['native'].run;calls=[]
    def refusal_then_real(*args,**kwargs):
        calls.append(args)
        if len(calls)==1:return dict(ok=False,complete=False,errors=['synthetic negative producer refusal'])
        return original(*args,**kwargs)
    monkeypatch.setattr(api['native'],'run',refusal_then_real)
    result=api['run'](source,tmp_path/'work',board_hint='synthetic',expected_source_sha256=force._hash(source),
        grade=grade,reporting_build=BUILD,allow_locked_source=True)
    assert result['changed'] and len(calls)>=2 and len(result['discovery_passes'])>=2
    assert not result['attempts'][0]['accepted'] and result['attempts'][-1]['accepted']
    keys=[api['offer_key'](m['offers'][0]['request']['source_track_uuids'],m['offers'][0]['replacement_points_nm'])
        for m in result['discovery_passes'] if m['offers']]
    assert len(keys)==len(set(keys)) and result['native_candidate_producer']['complete']
    assert not result['attempts'][-1]['new_native_faults'] and result['attempts'][-1]['opens']==0


@pytest.mark.parametrize('options',[dict(limit_offers=0),dict(limit_offers=9),dict(limit_offers=True),dict(excluded_offers=set())])
def test_lazy_work_and_exclusions_stay_explicitly_bounded(tmp_path,monkeypatch,options):
    source,b,*_=case(tmp_path,monkeypatch)
    with pytest.raises(ValueError):runpy.run_path(str(TOOL))['inventory'](b,source,board_hint='synthetic',**options)

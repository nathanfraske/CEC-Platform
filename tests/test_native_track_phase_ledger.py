"""Saved native deltas are checked atomically, not inferred from success flags."""
import copy
import pytest
import cec_native_track_phase_ledger as ledger
from test_pour_backed_current_path import saved


def test_both_actual_sets_are_registered_after_independent_saved_receiving(tmp_path,monkeypatch):
    source,child,q,_,_,_=saved(tmp_path,monkeypatch)
    import cec_pour_backed_current_path as owner
    proof=owner.receive(source,child,q);old=set();new=set();nets=set()
    result=ledger.register(source,child,proof,old,new,nets,net=q['current_proposal']['net'])
    assert result['actual_saved_track_delta_registered']
    assert old==set(proof['retired_track_uuids']) and new==set(proof['added_native_uuids'])
    assert len(old)==5 and len(new)==1 and nets=={q['current_proposal']['net']}
    assert not result['geometry_or_release_authority']


@pytest.mark.parametrize('fault',['truthy','incomplete','errors','source','omitted_new','omitted_old','extra_new'])
def test_bad_proof_cannot_partially_mutate_any_ledger(tmp_path,monkeypatch,fault):
    source,child,q,_,_,_=saved(tmp_path,monkeypatch)
    import cec_pour_backed_current_path as owner
    proof=copy.deepcopy(owner.receive(source,child,q))
    if fault=='truthy':proof['ok']=1
    elif fault=='incomplete':proof['complete']=False
    elif fault=='errors':proof['errors']=['unreceived']
    elif fault=='source':proof['source_sha256']='0'*64
    elif fault=='omitted_new':proof['added_native_uuids']=[]
    elif fault=='omitted_old':proof['retired_track_uuids']=[]
    else:proof['added_native_uuids'].append('invented')
    old={'incumbent_old'};new={'incumbent_new'};nets={'incumbent_net'}
    with pytest.raises(ValueError):ledger.register(source,child,proof,old,new,nets,net=q['current_proposal']['net'])
    assert old=={'incumbent_old'} and new=={'incumbent_new'} and nets=={'incumbent_net'}

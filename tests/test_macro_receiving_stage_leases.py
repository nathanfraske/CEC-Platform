import pytest
import cec_complete_macro_cell as op


def clock(monkeypatch):
    value=[0.];monkeypatch.setattr(op.time,'monotonic',lambda:value[0]);return value


def test_compilation_and_independent_map_replay_are_separate_ten_second_proofs(monkeypatch):
    now=clock(monkeypatch)
    lease=op._ReceivingLease(10.,['compile','map','native','delta','paths','returns'])
    now[0]=9.;lease.advance('map');now[0]=11.;lease.advance('native')
    for stage in['delta','paths','returns']:
        now[0]+=1.;lease.advance(stage)
    now[0]+=1.;lease.finish()
    assert lease.timings==dict(compile=9.,map=2.,native=1.,delta=1.,paths=1.,returns=1.)


@pytest.mark.parametrize('phase',['compile','map'])
def test_no_constituent_receives_more_than_its_own_ten_seconds(monkeypatch,phase):
    now=clock(monkeypatch);lease=op._ReceivingLease(10.,['compile','map'])
    if phase=='map':now[0]=9.;lease.advance('map')
    now[0]+=10.
    with pytest.raises(ValueError,match=phase+'_deadline'):lease.remaining()
    with pytest.raises(ValueError):lease.finish()


def test_cannot_skip_repeat_or_finish_before_every_mandatory_proof(monkeypatch):
    now=clock(monkeypatch);lease=op._ReceivingLease(10.,['compile','map','native'])
    with pytest.raises(ValueError,match='stage_order'):lease.advance('native')
    with pytest.raises(ValueError,match='stages_required'):lease.finish()
    now[0]=1.;lease.advance('map')
    with pytest.raises(ValueError,match='stage_order'):lease.advance('map')
    now[0]=2.;lease.advance('native');now[0]=3.;lease.finish()

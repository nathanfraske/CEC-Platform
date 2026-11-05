"""Stage dispatch/refusal tests are not candidate-admission mocks."""
import pytest
import cec_received_private_stage as stage
import cec_native_portal_cpu_portfolio as cpu
from test_native_portal_face_portfolio import plated_fixture
from test_received_private_stage import receipt


def test_finite_cpu_refusal_stops_before_shared_receiving(tmp_path,monkeypatch):
    source,board,net,target=plated_fixture(tmp_path)
    monkeypatch.setattr(stage,'identity',lambda *a:{'bound':'epoch'})
    seen=[]
    def construct(*args,**kwargs):
        seen.append((args,kwargs));return dict(complete=False,received_private_candidates=[])
    monkeypatch.setattr(cpu,'construct',construct)
    result=stage.worker(dict(source=str(source),directory=str(tmp_path),board_hint='synthetic',
        assembly_instance=None,identity={'bound':'epoch'},operator='ordinary_native_portfolio',
        net=net,wall_s=100.))
    assert result['gates']=={} and result['reason']=='finite_proposal_incomplete'
    assert seen[0][1]==dict(board_hint='synthetic',net=net,maximum_lanes=7,max_workers=4,wall_s=40.)
    assert not (tmp_path/'publication.json').exists()


@pytest.mark.parametrize('gate',list(receipt()['gates']))
def test_portfolio_proposal_is_never_a_substitute_for_any_shared_gate(tmp_path,gate):
    # Publish's real strict predicate, not a fake successful shared receiver.
    proof=receipt();proof['operator']='ordinary_native_portfolio';proof['gates'][gate]=False
    proof['construction']={'complete':True,'received_private_candidates':[{'candidate':'untrusted'}]}
    result=stage.publish(proof,tmp_path/'publication.json',live=lambda:True)
    assert not result['ok'] and not (tmp_path/'publication.json').exists()


@pytest.mark.parametrize('net',[None,'',False,3])
def test_cpu_stage_requires_literal_net_before_namespace(tmp_path,net):
    with pytest.raises(ValueError,match='explicit_bounded_received_operator_required'):
        stage.run(tmp_path/'missing',tmp_path/'out',board_hint='synthetic',
            expected_source_sha256='0'*64,operator='ordinary_native_portfolio',net=net)
    assert not (tmp_path/'out').exists()

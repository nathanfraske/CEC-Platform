"""Wide locked copper is not proof that a supply's source reaches its loads."""
from types import SimpleNamespace
import pytest
import cec_fr


@pytest.mark.parametrize('net',['SUPPLY','/unrelated/hierarchy/RAIL_42'])
@pytest.mark.parametrize('available,connected,complete,expected',[
    (True,False,False,False), (True,False,True,False),
    (True,True,False,True), (True,True,True,True),
    (False,False,False,False), (False,False,True,True)])
def test_pour_suppression_requires_native_connectivity(monkeypatch,net,available,connected,complete,expected):
    import pcbnew,cec_current_topology
    loaded=object()
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda p:loaded)
    monkeypatch.setattr(cec_fr,'locked_pour_authority_nets_board',lambda b:{net})
    monkeypatch.setattr(cec_fr,'owned_locked_nets_board',lambda b:{net} if complete else set())
    calls=[]
    def proof(board,name,*,board_hint):
        assert board is loaded and name==net
        calls.append(board_hint)
        return dict(available=available,connected=connected)
    monkeypatch.setattr(cec_current_topology,'authority_connectivity',proof)
    assert (net in cec_fr.completed_locked_pour_authority_nets('arbitrary.kicad_pcb'))==expected
    assert calls==['arbitrary.kicad_pcb']


def test_check_error_cannot_suppress_required_pour(monkeypatch):
    import pcbnew,cec_current_topology
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda p:object())
    monkeypatch.setattr(cec_fr,'locked_pour_authority_nets_board',lambda b:{'PWR'})
    monkeypatch.setattr(cec_fr,'owned_locked_nets_board',lambda b:{'PWR'})
    def fail(*args,**kwargs):raise RuntimeError('native unavailable')
    monkeypatch.setattr(cec_current_topology,'authority_connectivity',fail)
    with pytest.raises(RuntimeError,match='native unavailable'):
        cec_fr.completed_locked_pour_authority_nets('any.kicad_pcb')

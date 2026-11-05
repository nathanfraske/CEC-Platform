"""A routed artifact is not permission to silently discard ordinary copper."""
from types import SimpleNamespace

import pytest

import cec_placement_route_prefix as prefix
import cec_synth_pipeline as synth


def track(net,uid):
    return SimpleNamespace(GetNetname=lambda:net,
        m_Uuid=SimpleNamespace(AsString=lambda:uid),GetClass=lambda:'PCB_TRACK')


@pytest.mark.parametrize('name', ['CUSTOM_NET','RENAMED/RAIL'])
def test_all_tracks_and_vias_must_have_retained_ownership(name):
    board=SimpleNamespace(GetTracks=lambda:iter([
        track(name,'power'),track('RETURN','owned-return'),track('OTHER','ordinary')]))
    contract={'nets':[name], 'placement_preserved_uuids':['owned-return']}
    report=prefix.rehydration_coverage(board,contract)
    assert not report['ok'] and report['total_items']==3
    assert report['preserved_items']==2 and report['unpreserved_items']==1
    assert report['unpreserved_by_net']=={'OTHER':1}
    assert report['requires_owned_reroute'] and not report['release_authority']


def test_prefix_only_and_copper_free_placement_remain_eligible():
    for items in ([],[track('P','one')]):
        report=prefix.rehydration_coverage(SimpleNamespace(GetTracks=lambda:iter(items)),{'nets':['P']})
        assert report['ok'] and report['unpreserved_items']==0
    # Merely being locked does not grant the placement materializer ownership.
    item=track('NONOWNED','locked');item.IsLocked=lambda:True
    assert not prefix.rehydration_coverage(
        SimpleNamespace(GetTracks=lambda:iter([item])),{'nets':['P']})['ok']


def test_materialization_refuses_unretained_copper_before_any_write(monkeypatch):
    import pcbnew
    board=SimpleNamespace(GetTracks=lambda:iter([track('SIGNAL','route')]))
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda path:board)
    def forbidden(*args,**kwargs):raise AssertionError('reconstruction must not start')
    monkeypatch.setattr(synth.shutil,'copy2',forbidden)
    monkeypatch.setattr(synth.subprocess,'run',forbidden)
    candidate=SimpleNamespace(source_board='generic.kicad_pcb',source_had_routed_copper=True,
                               protected_power_prefix={},P={})
    with pytest.raises(prefix.UnownedRoutedCopper) as failure:
        synth._materialize_rehydrated_board(candidate,SimpleNamespace(params={}),
                                           'unwritten.kicad_pcb')
    assert failure.value.evidence['unpreserved_by_net']=={'SIGNAL':1}


def test_priority_adapter_reports_route_owner_handoff_without_mutation(monkeypatch,tmp_path):
    import cec_full_pipeline as pipeline
    import pcbnew
    board=tmp_path/'board.kicad_pcb';board.write_text('ordinary copper must survive')
    loaded=SimpleNamespace(GetTracks=lambda:iter([track('N','x')]))
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda path:loaded)
    cfg=SimpleNamespace(params={'placement_route_repair_trials':1,'placement_route_repair_rounds':1})
    monkeypatch.setattr(synth,'config_with_board_route_authority',
                        lambda *a:(cfg,dict(ok=True,applicable=False,bound=False)))
    evidence=dict(ok=False,unpreserved_items=1,unpreserved_by_net={'N':1})
    def refuse(*a,**k):raise prefix.UnownedRoutedCopper(evidence)
    monkeypatch.setattr(synth,'placement_candidate_from_board',refuse)
    report=pipeline._repair_placement_priority_routes_in_process(cfg,board,allow_authored_prefix=True)
    assert not report['changed'] and not report['ok']
    assert report['reason']=='routed_copper_requires_owned_transaction'
    assert report['copper_ownership']==evidence
    assert board.read_text()=='ordinary copper must survive'

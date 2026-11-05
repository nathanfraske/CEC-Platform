"""Committed power ownership across renamed critical-pair transactions."""
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pcbnew
import pytest
import cec_critical_checkpoint as checkpoint
import cec_precision_route as precision
import cec_synth_pipeline as synth


def test_committed_context_overrides_stale_environment_and_restores_it(monkeypatch):
    original={'CEC_POURFIRST_STATE':'old.json','CEC_POUR_RESERVE':'0',
              'CEC_ROUTE_PRIORITY_POLICY':'critical-first'}
    for key,value in original.items(): monkeypatch.setenv(key,value)
    cfg=SimpleNamespace(params={})
    binding={'ok':True,'bound':True,'state':'exact-current.json'}
    with patch.object(synth,'config_with_board_route_authority',return_value=(cfg,binding)):
        with pytest.raises(RuntimeError,match='test interruption'):
            with checkpoint.frozen_power_context(Path('renamed.kicad_pcb'),cfg):
                assert os.environ['CEC_POURFIRST_STATE']=='exact-current.json'
                assert os.environ['CEC_POUR_RESERVE']=='1'
                assert os.environ['CEC_ROUTE_PRIORITY_POLICY']=='power-first'
                raise RuntimeError('test interruption')
    assert all(os.environ[key]==value for key,value in original.items())
    assert cfg.params=={}


@pytest.mark.parametrize('binding',[{'ok':False,'bound':True},{'ok':True,'bound':False},{}])
def test_unbound_or_invalid_committed_authority_fails_before_search(binding):
    cfg=SimpleNamespace(params={})
    with patch.object(synth,'config_with_board_route_authority',return_value=(cfg,binding)):
        with pytest.raises(ValueError,match='cannot bind'):
            with checkpoint.frozen_power_context('board.kicad_pcb',cfg):
                pytest.fail('unproven context entered')


def test_constructor_cannot_run_when_committed_reservations_are_disabled(tmp_path):
    import cec_fr
    import cec_route_preflight as preflight
    source=tmp_path/'source.kicad_pcb';source.write_text('original')
    cfg=SimpleNamespace(params={})
    pair=dict(name='anonymous',p='positive',n='negative')
    with patch.object(synth,'config_with_board_route_authority',return_value=(cfg,{
            'ok':True,'bound':True,'state':'state.json'})), \
            patch.object(cec_fr,'owned_locked_nets',return_value=set()), \
            patch.object(preflight,'compile_route_reservations',return_value={'enabled':False}), \
            patch.object(precision,'precision_route') as route:
        report=checkpoint.construct(source,tmp_path/'output',[pair],frozen_route_config=cfg)
    route.assert_not_called()
    assert not report['ok']
    assert 'reservations were disabled' in report['attempts'][0]['error']
    assert source.read_text()=='original'


def board_fixture():
    board=pcbnew.BOARD()
    for name in ('positive','negative'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    for a,b in [((0,0),(40,0)),((40,0),(40,40)),((40,40),(0,40)),((0,40),(0,0))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)
    return board


@pytest.mark.parametrize('quarter',[0,1,2,3])
def test_local_pair_search_can_choose_legal_alternative_around_reserved_power(quarter):
    board=board_fixture()
    def transform(point):
        x,y=point[0]-20,point[1]-20
        for _ in range(quarter): x,y=-y,x
        return x+20,y+20
    endpoints=tuple(map(transform,((10,20),(20,20),(10,20.5),(20,20.5))))
    corners=list(map(transform,((14,19.9),(16,20.1))))
    avoid=(min(p[0] for p in corners),min(p[1] for p in corners),
           max(p[0] for p in corners),max(p[1] for p in corners),'committed-power','F.Cu')
    pair=dict(name='anonymous',p='positive',n='negative',width=.2,gap=.3)
    with patch.object(precision,'_short_pair_ribbon_candidates',return_value=()):
        result=precision._route_paired_stub(board,pair,endpoints,avoid=[avoid])
    assert not result.get('refused'),result
    assert len(list(board.GetTracks()))>2
    for track in board.GetTracks():
        points=[(pt.x/1e6,pt.y/1e6) for pt in (track.GetStart(),track.GetEnd())]
        assert not precision._crosses_avoid(points,[avoid[:5]],.2)
        assert precision._polyline_is_octilinear(points)


@pytest.mark.parametrize('layer,blocked',[('F.Cu',True),('B.Cu',False)])
def test_blocked_terminal_refuses_without_mutation_but_other_layer_is_available(layer,blocked):
    board=board_fixture()
    pair=dict(name='anonymous',p='positive',n='negative',width=.2,gap=.3)
    before=len(list(board.GetTracks()))
    report=precision._route_paired_stub(board,pair,((10,20),(20,20),(10,20.5),(20,20.5)),
        avoid=[(9,19,11,21,'committed-power',layer)])
    assert bool(report.get('refused'))==blocked
    if blocked: assert len(list(board.GetTracks()))==before

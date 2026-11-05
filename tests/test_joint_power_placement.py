import copy
from types import SimpleNamespace
import pytest
import cec_full_pipeline as pipeline


def state(count,*,power=True,nets=('arbitrary-domain',)):
    craft={'ok':count==0,'decoupler':{'ok':count==0,
        'violations':[(f'BYPASS-{i}','local-cell-access',1.) for i in range(count)]}}
    return dict(authority={'ok':power,'planner':{'frozen_nets':list(nets)}},
        physical=({'ok':True},{'ok':True},craft,False,{'ok':count==0},{'ok':True},count==0),
        profile={},fiducial={'ok':True},service={'ok':True})


@pytest.mark.parametrize('after,accepted',[(state(2),True),(state(3),False),
    (state(5),False),(state(0,power=False),False),(state(0,nets=()),False)])
def test_joint_admission_requires_real_progress_and_preserved_power(after,accepted):
    assert pipeline._joint_power_placement_admission(state(3),after)['accepted'] is accepted


@pytest.mark.parametrize('outcome',['regression','exception','accepted'])
def test_transaction_restores_board_sidecars_and_configuration(tmp_path,outcome):
    board=tmp_path/'board.kicad_pcb';board.write_text('baseline copper')
    power=board.with_suffix('.pourfirst-state.json');power.write_text('baseline state')
    cfg=SimpleNamespace(params={'pourfirst_state':'baseline','net_currents':{'rail':7.3}},pins={'terminal':[1,2,3]})
    original=copy.deepcopy(vars(cfg))
    def propose():
        board.write_text('proposed copper');power.write_text('proposed state')
        cfg.params['pourfirst_state']='proposed';cfg.pins['terminal']=[4,5,6]
        return {'changed':True,'ok':True}
    def rebuild():
        if outcome=='exception':raise ValueError('native exact check failed')
        return state(2 if outcome=='accepted' else 5)
    report,chosen=pipeline._transactional_power_placement_trial(cfg,board,state(3),propose,rebuild)
    if outcome=='accepted':
        assert report['changed'] and board.read_text()=='proposed copper'
        assert len(chosen['physical'][2]['decoupler']['violations'])==2
    else:
        assert not report['changed'] and report['rolled_back']
        assert board.read_text()=='baseline copper' and power.read_text()=='baseline state'
        assert vars(cfg)==original
        assert len(chosen['physical'][2]['decoupler']['violations'])==3

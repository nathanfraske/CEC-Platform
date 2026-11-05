"""A pair access transaction is neither a local budget waiver nor a fab pass."""
import copy
from pathlib import Path
from types import SimpleNamespace
import pcbnew
import pytest
import cec_fr
import cec_future_pin_access as access
import cec_route_pair_admission as admission
import cec_pair_access_repair as pair_repair
import cec_full_pipeline as pipeline
import cec_operation_budget as budget
import cec_synth_pipeline as synth
import cec_search_policy as policy
from cec_local_copper_cell import copper_inventory
from test_future_pin_access import fixture, foreign_track
from test_priority_dependency import contract
from test_route_residual_resume import grade


def pair_proof():
    return dict(ok=False,parent_copper=dict(ok=False),placement_unchanged=True,
        functional_placement_unchanged=True,outline_unchanged=True,power_zones_unchanged=True,
        qualified_pairs=dict(ok=True),power_obligations=dict(ok=True),
        score_admission=dict(accepted=True))


@pytest.mark.parametrize('missing',list(pair_proof()))
def test_incomplete_or_wrong_preservation_cannot_enter_pair_transaction(missing):
    proof=pair_proof()
    assert admission.pair_only_failure(proof)
    proof.pop(missing)
    assert not admission.pair_only_failure(proof)


@pytest.mark.parametrize('fault',['none','power','unknown','unqualified','renet','oversize','partial_identity'])
def test_whole_pair_scope_preserves_every_non_pair_parent(fault):
    c=contract()
    before={'p':['PCB_TRACK','s+',True,1], 'n':['PCB_TRACK','s-',True,2],
            'power':['PCB_TRACK','rail',True,3], 'other':['PCB_TRACK','ordinary',False,4]}
    after=copy.deepcopy(before)
    del after['p']
    if fault=='power':del after['power']
    if fault=='unknown':del after['other']
    if fault=='unqualified':c['qualified_critical_pairs'][0]['qualified']=False
    if fault=='renet':after['n'][1]='different'
    if fault=='partial_identity':del c['member_nets']['a']
    result=admission.changed_pair_scope(before,after,c,max_pair_items=1 if fault=='oversize' else 256)
    assert result['ok']==(fault=='none')
    if fault=='none':
        assert result['nets']==['s+','s-']
        assert result['owned_parent_uuids']==['n','p']


@pytest.mark.parametrize('limit',[0,True,4097])
def test_pair_item_limits_are_explicit_and_bounded(limit):
    with pytest.raises(ValueError):admission.changed_pair_scope({}, {}, contract(),max_pair_items=limit)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_native_access_witness_is_source_bound_and_board_neutral(tmp_path,angle,back):
    board,fp,pads,nets,pair=fixture(angle=angle,back=back,prefix='UNRELATED',extra_pads=10)
    foreign_track(board,pads[1],nets['P'],dy=.27)
    foreign_track(board,pads[1],nets['N'],dy=-.27)
    sentinel=foreign_track(board,pads[1],nets['RETURN'],dy=8)
    source=tmp_path/'source.kicad_pcb'
    pcbnew.SaveBoard(str(source),board)
    owned=cec_fr.copper_geometry_prefix_contract(str(source),{pair['p'],pair['n'],nets['RETURN'].GetNetname()})
    owned.update(placement_power_nets=[nets['RETURN'].GetNetname()],
        placement_preserved_nets=owned['nets'],placement_preserved_uuids=[],
        qualified_critical_pairs=[dict(pair,qualified=True)])
    before=source.read_bytes(); inventory=copper_inventory(board)
    result=access.replacement_witness(source,owned,pair,{nets['SUPPLY'].GetNetname()})
    assert result['ok'] and result['target_nets']==[nets['SUPPLY'].GetNetname()]
    assert not result['release_authority'] and not result['no_path_proof']
    assert sentinel.m_Uuid.AsString() not in result['removed_pair_uuids']
    assert source.read_bytes()==before and copper_inventory(board)==inventory
    assert not access.replacement_witness(source,owned,pair,{'unrelated_target'})['ok']
    assert not access.replacement_witness(source,owned,pair,{nets['SUPPLY'].GetNetname()},
                                          max_pair_items=1)['ok']
    assert not access.replacement_witness(source,owned,pair,{nets['SUPPLY'].GetNetname()},
                                          deadline_monotonic=0)['ok']


def test_a_clear_pin_does_not_authorize_replacement(tmp_path):
    board,fp,pads,nets,pair=fixture()
    foreign_track(board,pads[1],nets['P'],dy=8)
    foreign_track(board,pads[1],nets['N'],dy=9)
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    owned=cec_fr.copper_geometry_prefix_contract(str(source),{pair['p'],pair['n']})
    owned.update(placement_power_nets=[],placement_preserved_nets=owned['nets'],
                 qualified_critical_pairs=[dict(pair,qualified=True)])
    result=access.replacement_witness(source,owned,pair,{nets['SUPPLY'].GetNetname()})
    assert not result['ok'] and result['reason']=='no_typed_pair_owned_pin_obstruction'


@pytest.mark.parametrize('fault',['none','unfunded','worker_refused','gate_loss','no_gain','source_changed'])
def test_coordinator_requires_owned_transaction_and_fresh_grade(tmp_path,monkeypatch,fault):
    source=tmp_path/'source.kicad_pcb';source.write_text('immutable')
    target=tmp_path/'target.kicad_pcb';target.write_text('proposal')
    cfg=SimpleNamespace(params={})
    incumbent=grade(source,opens=2)
    monkeypatch.setattr(budget,'optional_work_admission',lambda *a,**k:dict(start=fault!='unfunded'))
    calls=[]
    def attempt(*args,**kwargs):
        calls.append(args)
        if fault=='source_changed':source.write_text('damaged')
        return dict(ok=fault!='worker_refused',changed=True,board=str(target))
    monkeypatch.setattr(pair_repair,'attempt',attempt)
    monkeypatch.setattr(synth,'config_with_board_route_authority',lambda c,p:(c,dict(ok=True)))
    after=grade(target,opens=2 if fault=='no_gain' else 1)
    if fault=='gate_loss':after['gate_terms']['pairs_ok']=False
    monkeypatch.setattr(pipeline,'_grade_route_incumbent',lambda *a,**k:after)
    if fault=='source_changed':
        with pytest.raises(pipeline.PipelineBlocked):
            pipeline._resume_owned_pair_access(incumbent,tmp_path/'out',cfg,seed=1,thermal='lazy')
        return
    result,evidence=pipeline._resume_owned_pair_access(incumbent,tmp_path/'out',cfg,seed=1,thermal='lazy')
    assert bool(result)==(fault=='none')
    assert evidence['release_authority'] is False
    if fault=='none':assert result['candidate_origin']=='route_pair_access_repair'
    if fault=='unfunded':assert not calls


def test_residual_scheduler_prioritizes_a_proved_upstream_gain(tmp_path,monkeypatch):
    source=tmp_path/'source.kicad_pcb';source.write_text('immutable')
    cfg=SimpleNamespace(params={})
    incumbent=grade(source,opens=2,pairs_ok=True,incumbent_identity={'sha256':pipeline.sha256_file(source)})
    better=grade(tmp_path/'candidate.kicad_pcb',opens=1)
    better['candidate_origin']='route_pair_access_repair'
    monkeypatch.setattr(pipeline,'_resume_owned_pair_access',lambda *a,**k:(better,dict(changed=True)))
    monkeypatch.setattr(synth,'_route_oracle_certificate_repair',lambda *a,**k:pytest.fail('do not repeat downstream searches'))
    result,evidence=pipeline._resume_route_residuals(incumbent,tmp_path/'out',cfg,seed=1,thermal='lazy')
    assert result==better and evidence['skip_global'] and evidence['changed']
    assert evidence['stop']=='owned_pair_access_improved'


def test_additive_guard_does_not_learn_an_exception():
    import inspect
    import cec_route_checkpoint as checkpoint
    source=inspect.getsource(checkpoint.preservation)
    assert 'receipt' not in source and 'replacement' not in source
    assert "copper['ok']" in source

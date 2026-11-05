"""Rejecting causal clauses save work; they never manufacture acceptance."""
import copy
import dataclasses
import time

import pcbnew
import pytest
import cec_cell_endpoint_groups as groups
import cec_force_current as force
import cec_joint_connection_search as joint


def menu(prefix='opaque',late=48):
    return {prefix+key:[dict(id=str(i),cost=i,net=net,ops=[])for i in range(count)]
        for key,count,net in [('a_power',2,'rail'),('b_power',2,'rail'),
            ('c_other',late,'different'),('d_ground',late,'GND')]}


@pytest.mark.parametrize('prefix',['opaque','renamed_without_board_dispatch'])
def test_independent_rejection_skips_thousands_of_unrelated_complete_variants(prefix):
    domains=menu(prefix);before=copy.deepcopy(domains);binding=joint._binding(domains);calls=[]
    def receive(selected):
        calls.append({key:q['id']for key,q in selected.items()})
        if selected[prefix+'a_power']['id']==selected[prefix+'b_power']['id']=='0':
            return joint.RejectedSelection(binding,tuple((prefix+key,'0')for key in ('a_power','b_power')),
                'synthetic_complete_same_net_construction_refused')
        return True
    result=joint.solve(domains,conflicts=lambda *_:False,validate_selection=receive,
        timeout_s=2.,max_states=64)
    assert result['complete']and len(calls)==2 and result['complete_selections_checked']==2
    assert result['learned_prefix_cuts']>0 and len(result['learned_rejections'])==1
    assert result['selected'][prefix+'a_power']['id']=='0'and result['selected'][prefix+'b_power']['id']=='1'
    assert result['input_unchanged']and domains==before
    assert not result['routing_admitted']and not result['source_authority']and not result['release_authority']


def test_boolean_receiver_remains_strict_and_does_not_acquire_unasked_learning():
    domains=menu(late=2);calls=[]
    def refuse(selected):calls.append(selected);return False
    result=joint.solve(domains,conflicts=lambda *_:False,validate_selection=refuse,timeout_s=2.)
    assert not result['complete']and result['selected']=={}and len(calls)==16
    assert result['learned_rejections']==[]and result['learned_prefix_cuts']==0


def test_clause_is_local_to_the_exact_domain_epoch_and_cannot_be_reused_next_run():
    domains=menu(late=1);binding=joint._binding(domains)
    def refuse(selected):return joint.RejectedSelection(binding,tuple((k,q['id'])for k,q in selected.items()),'this run only')
    first=joint.solve(domains,conflicts=lambda *_:False,validate_selection=refuse,timeout_s=2.)
    assert not first['complete']and first['learned_rejections']
    second=joint.solve(domains,conflicts=lambda *_:False,validate_selection=lambda _:True,timeout_s=2.)
    assert second['complete']and second['learned_rejections']==[]


@pytest.mark.parametrize('fault',['stale','empty','unknown_key','wrong_id','duplicate_pair','duplicate_owner',
    'list_instead_of_tuple','list_pair','numeric_id','empty_reason','long_reason','boolean','dict'])
def test_malformed_or_forged_rejecting_feedback_never_exports_a_partial_selection(fault):
    domains=menu(late=1);binding=joint._binding(domains)
    def forged(selected):
        pairs=tuple((key,q['id'])for key,q in selected.items());epoch=binding;reason='reject'
        if fault=='stale':epoch='stale'
        elif fault=='empty':pairs=()
        elif fault=='unknown_key':pairs=(('not-selected','0'),)
        elif fault=='wrong_id':pairs=((pairs[0][0],'not-selected'),)
        elif fault=='duplicate_pair':pairs=(pairs[0],pairs[0])
        elif fault=='duplicate_owner':pairs=(pairs[0],(pairs[0][0],'1'))
        elif fault=='list_instead_of_tuple':pairs=list(pairs)
        elif fault=='list_pair':pairs=(list(pairs[0]),)
        elif fault=='numeric_id':pairs=((pairs[0][0],0),)
        elif fault=='empty_reason':reason=''
        elif fault=='long_reason':reason='x'*257
        elif fault=='boolean':return 1
        else:return {'reject':True}
        return joint.RejectedSelection(epoch,pairs,reason)
    result=joint.solve(domains,conflicts=lambda *_:False,validate_selection=forged,timeout_s=2.)
    assert not result['complete']and result['selected']=={}and result['errors']
    assert result['input_unchanged']


def test_rejected_result_is_immutable_and_never_truthy_success():
    value=joint.RejectedSelection('epoch',(('one','0'),),'reason')
    with pytest.raises(dataclasses.FrozenInstanceError):value.reason='accepted'
    result=joint.solve(menu(late=1),conflicts=lambda *_:False,validate_selection=lambda _:value,timeout_s=2.)
    assert not result['complete']and result['selected']=={}


def test_unknown_classification_scope_keeps_other_net_measurement_rescuers():
    domains={key:[dict(id=str(i),cost=i,net='rail',ops=[])for i in range(2)]for key in ('a','b','wide_cover')}
    domains['unrelated_ground']=[dict(id=str(i),cost=i,net='GND',ops=[])for i in range(48)]
    binding=joint._binding(domains);seen=[]
    def receive(selected):
        seen.append({k:q['id']for k,q in selected.items()})
        if selected['wide_cover']['id']=='1':return True
        error=groups.EndpointMaterializationRefused([dict(net='rail',reason='escape_budget_exceeded')])
        return groups.rejection_clause(error,selected,domain_binding=binding)
    result=joint.solve(domains,conflicts=lambda *_:False,validate_selection=receive,timeout_s=2.)
    assert result['complete']and len(seen)==49
    assert result['selected']['a']['id']==result['selected']['b']['id']=='0'
    assert result['selected']['wide_cover']['id']=='1'
    clause=result['learned_rejections'][0]['choices']
    assert {pair[0]for pair in clause}=={'a','b','wide_cover','unrelated_ground'}


def test_ordinary_unknown_failures_do_not_invent_a_causal_clause():
    assert groups.rejection_clause(ValueError('unknown current'),{},domain_binding='x')is False
    assert groups.rejection_clause(groups.EndpointMaterializationRefused([]),{},domain_binding='x')is False
    assert groups.rejection_clause(groups.EndpointMaterializationRefused([dict(net='rail',reason='unknown')]),
        {'one':dict(id='0',net='rail')},domain_binding='x')is False


def test_actual_native_narrow_branch_exposes_only_its_whole_net_rejecting_scope(monkeypatch):
    from test_cell_endpoint_groups import supply
    board,launch,via,trunk,prefix,current,requests=supply(monkeypatch)
    end=prefix.GetEnd();start=prefix.GetStart();mid=pcbnew.VECTOR2I((start.x+end.x)//2,(start.y+end.y)//2)
    prefix.SetEnd(mid);new=[]
    for at in (end,mid+pcbnew.VECTOR2I_MM(0,.3)):
        t=pcbnew.PCB_TRACK(board);t.SetNet(prefix.GetNet());t.SetLayer(prefix.GetLayer());t.SetWidth(prefix.GetWidth())
        t.SetStart(mid);t.SetEnd(at);board.Add(t);new.append(t)
    with pytest.raises(groups.EndpointMaterializationRefused)as error:
        groups.group(board,[prefix,*new],board_hint='synthetic')
    selected={'one':dict(id='0',net=launch.GetNetname()),'potential_wide_cover':dict(id='1',net=launch.GetNetname()),
        'ground':dict(id='0',net='GND')}
    answer=groups.rejection_clause(error.value,selected,domain_binding='exact-menu-epoch')
    assert type(answer)is joint.RejectedSelection
    assert answer.choices==(('one','0'),('potential_wide_cover','1'))
    assert answer.domain_binding=='exact-menu-epoch'

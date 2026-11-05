"""Real native craft can reject only its complete same-net search context."""
import copy
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_force_current as force
import cec_joint_connection_search as joint
import cec_route_quality as quality
from cec_native_items import create_empty_board


def native_case():
    board=create_empty_board();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'RENAMED_SUPPLY',1);board.Add(net)
    selected={
        'opaque-A':dict(id='0',cost=0.,net='RENAMED_SUPPLY',ops=[]),
        'opaque-B':dict(id='2',cost=0.,net='RENAMED_SUPPLY',ops=[]),
        'same-net-cover':dict(id='7',cost=0.,net='RENAMED_SUPPLY',ops=[]),
        'unrelated-Ground':dict(id='3',cost=0.,net='GND',ops=[])}
    source=quality.analyze_board(board);made={}
    for key,left,right in [
        ('opaque-A',(16.38,12.85),(13.63,15.6)),
        ('opaque-B',(13.63,15.6),(15.340147,15.6))]:
        item=pcbnew.PCB_TRACK(board);item.SetLayer(6);item.SetNet(net);item.SetWidth(500000)
        item.SetStart(pcbnew.VECTOR2I_MM(*left));item.SetEnd(pcbnew.VECTOR2I_MM(*right));board.Add(item)
        made[force._uid(item)]=dict(obligation=key,choice_id=selected[key]['id'])
    current=quality.analyze_board(board)
    assert source['issue_count']==0 and current['issue_count']==1
    assert current['issues'][0]['type']=='acute_backtrack'
    return board,source,current,selected,made


def test_actual_native_acute_rejects_every_same_net_choice_not_unrelated_ground():
    board,source,current,selected,made=native_case()
    before=tuple(force._item_key(t)for t in board.GetTracks())
    clause=escape._clean_source_craft_rejection(source,current,selected,made,domain_binding='epoch')
    assert type(clause)is joint.RejectedSelection
    assert set(clause.choices)=={('opaque-A','0'),('opaque-B','2'),('same-net-cover','7')}
    assert clause.domain_binding=='epoch'
    assert before==tuple(force._item_key(t)for t in board.GetTracks())


@pytest.mark.parametrize('fault',['dirty_Source','unknown_Source','missing_issues',
    'missing_owner','stale_choice','wrong_net','unknown_obligation'])
def test_unknown_or_nonmonotone_context_falls_back_without_learning(fault):
    board,source,current,selected,made=native_case()
    if fault=='dirty_Source':source['issue_count']=1
    elif fault=='unknown_Source':source.pop('issue_count')
    elif fault=='missing_issues':current.pop('issues')
    elif fault=='missing_owner':made={}
    elif fault=='stale_choice':next(iter(made.values()))['choice_id']='stale'
    elif fault=='wrong_net':selected['opaque-A']['net']='different-net'
    else:next(iter(made.values()))['obligation']='missing'
    assert escape._clean_source_craft_rejection(source,current,selected,made,domain_binding='epoch')is False


def test_solver_rejection_does_not_repeat_irrelevant_ground_variants():
    board,source,current,selected,made=native_case()
    domains={key:[copy.deepcopy(value)]for key,value in selected.items()}
    domains['opaque-A'].append(dict(id='good',cost=1.,net='RENAMED_SUPPLY',ops=[]))
    domains['unrelated-Ground']=[dict(id=str(n),cost=float(n),net='GND',ops=[])for n in range(32)]
    visited=[]
    def inspect(chosen):
        visited.append(tuple((key,value['id'])for key,value in chosen.items()))
        if chosen['opaque-A']['id']=='good':return True
        return escape._clean_source_craft_rejection(source,current,chosen,made,
            domain_binding=joint._binding(domains))
    result=joint.solve(domains,conflicts=lambda left,right:False,validate_selection=inspect)
    assert result['complete'] and result['selected']['opaque-A']['id']=='good',result
    assert len(result['learned_rejections'])==1 and len(visited)==2
    assert result['learned_prefix_cuts']>=1

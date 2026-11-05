from types import SimpleNamespace
from unittest.mock import patch
import pytest
import cec_precision_route as p


def fixture():
    ports={name:dict(center=xy,layers=['F.Cu','B.Cu'],through=True)
           for name,xy in [('A',(0,0)),('B',(5,0)),('C',(5,4))]}
    return dict(ports=ports,terminals=list(ports),preferred_signal_layers=['F.Cu','B.Cu'],
                edges=[dict(a='A',b='B',length_mm=5,layers=['F.Cu','B.Cu']),
                       dict(a='B',b='C',length_mm=4,layers=['F.Cu','B.Cu'])])


def test_exchange_domain_connected_unique_bounded_and_keeps_seed():
    plan=fixture(); proposals=p._multidrop_tree_alternatives(plan)
    assert len(proposals)==3
    assert proposals[0]['edges']==plan['edges']
    assert len(p._multidrop_tree_alternatives(plan,max_trees=1))==1
    assert len(p._multidrop_tree_alternatives(plan,max_exchanges=0))==1
    assert len({tuple(sorted(tuple(sorted((e['a'],e['b']))) for e in q['edges'])) for q in proposals})==3
    for q in proposals:
        assert len(q['edges'])==2
        assert {x for e in q['edges'] for x in (e['a'],e['b'])}==set(plan['ports'])
    # An unplated, incompatible endpoint is not assigned a made-up layer.
    plan['ports']['A']['layers']=['F.Cu'];plan['ports']['C']['layers']=['B.Cu']
    assert len(p._multidrop_tree_alternatives(plan))==1


class Board:
    def __init__(self): self.items=[SimpleNamespace(m_Uuid=SimpleNamespace(AsString=lambda:'base'))]
    def GetTracks(self):
        for item in self.items:
            # These are transaction ownership markers, not physical tracks.
            if not hasattr(item, 'GetClass'): item.GetClass=lambda:'TEST_MARKER'
        return list(self.items)
    def Groups(self):return []
    def Delete(self,item):self.items.remove(item)


def test_rejected_tree_rolls_back_support_copper_before_next_tree():
    board=Board();calls=[]
    def route(*args,**kwargs):
        assert len(board.items)==1
        calls.append(1)
        board.items.append(SimpleNamespace(m_Uuid=SimpleNamespace(AsString=lambda:'new-ground')))
        return dict(name='PAIR',p='P',n='N',legs=[])
    with patch.object(p,'_route_layered_multidrop_pair_tree',side_effect=route), \
         patch.object(p,'_route_direct_pair_tree',return_value={'refused':'direct blocked'}), \
         patch.object(p,'_pair_transaction_detour',side_effect=[{'ok':False},{'ok':True}]):
        result=p._route_multidrop_topologies(board,dict(name='PAIR',p='P',n='N'),fixture())
    assert len(calls)==2 and not result.get('refused')
    assert len(board.items)==2
    assert len(result['topology_attempts'])==4


def test_native_orders_keep_backbone_before_bounded_drop_and_are_bounded():
    plan=fixture()
    plan['edges'][1]['bounded_terminal_fanout']=True
    orders=p._native_pair_edge_orders(plan)
    assert [name for name,_ in orders]==['backbone-first','local-first']
    assert orders[0][1][0]['a']=='A'
    assert len(p._native_pair_edge_orders(plan,max_orders=1))==1
    # A single edge has no distinct permutation to waste a second trial on.
    plan['edges']=plan['edges'][:1]
    assert len(p._native_pair_edge_orders(plan))==1


def test_native_alternate_order_is_atomic_and_preserves_saved_parent():
    board=Board();calls=[]
    def route(*args,**kwargs):
        assert len(board.items)==1
        calls.append([edge['a'] for edge in kwargs['edge_order']])
        board.items.append(SimpleNamespace(m_Uuid=SimpleNamespace(AsString=lambda:'new')))
        return {'refused':'detour'} if len(calls)==1 else {'segments':2}
    with patch.object(p,'_route_direct_pair_tree',side_effect=route), \
         patch.object(p,'_route_layered_multidrop_pair_tree') as layered:
        result=p._route_multidrop_topologies(board,dict(name='PAIR',p='P',n='N'),fixture())
    assert len(calls)==2 and calls[0]!=calls[1]
    assert not result.get('refused') and len(board.items)==2
    layered.assert_not_called()


def direct_fixture():
    plan=fixture()
    for index, port in enumerate(plan['ports'].values()):
        port.update(p=(index*5,0),n=(index*5,1))
    return plan


def test_direct_tree_tries_all_native_layers_before_transitions():
    board=Board(); calls=[]
    def route(*args,**kwargs):
        calls.append((kwargs['layer'], kwargs['allow_layer_transitions']))
        assert len(board.items)==1
        if kwargs['layer']=='F.Cu':
            board.items.append(SimpleNamespace(m_Uuid=SimpleNamespace(AsString=lambda:'rejected-ground')))
            return {'refused':'foreign copper'}
        return {'segments':2}
    with patch.object(p,'route_coupled_pair',side_effect=route), \
         patch.object(p,'_drop_fully_covered_tracks',return_value={}), \
         patch.object(p,'_pair_graph_geometry',return_value={'ok':True}), \
         patch.object(p,'_pair_transaction_detour',return_value={'ok':True}):
        result=p._route_direct_pair_tree(board,dict(name='PAIR',p='P',n='N'),direct_fixture())
    assert calls==[('F.Cu',False),('B.Cu',False)]*2
    assert result['completed_edge_count']==2 and not result.get('refused')


def test_direct_tree_never_invents_an_endpoint_layer_or_forces_smd_to_back():
    plan=direct_fixture()
    for port in plan['ports'].values(): port.update(layers=['F.Cu'],through=False)
    with patch.object(p,'route_coupled_pair',return_value={'refused':'blocked'}) as route, \
         patch.object(p,'_drop_fully_covered_tracks',return_value={}), \
         patch.object(p,'_pair_graph_geometry',return_value={'ok':True}), \
         patch.object(p,'_pair_transaction_detour',return_value={'ok':True}):
        result=p._route_direct_pair_tree(Board(),dict(name='PAIR',p='P',n='N'),plan)
    assert [call.kwargs['layer'] for call in route.call_args_list]==['F.Cu','F.Cu']
    assert result['completed_edge_count']==0 and result.get('refused')


def test_direct_tree_budget_exhaustion_is_recorded_as_deferred_not_impossible():
    clock=[0.0];calls=[]
    def route(*args,**kwargs):
        assert kwargs['deadline']<=12
        calls.append(kwargs)
        clock[0]=kwargs['deadline']
        return {'refused':'bounded search stopped'}
    with patch.object(p.time,'monotonic',side_effect=lambda:clock[0]), \
         patch.object(p,'route_coupled_pair',side_effect=route), \
         patch.object(p,'_drop_fully_covered_tracks',return_value={}), \
         patch.object(p,'_pair_graph_geometry',return_value={'ok':True}), \
         patch.object(p,'_pair_transaction_detour',return_value={'ok':True}):
        result=p._route_direct_pair_tree(Board(),dict(name='PAIR',p='P',n='N'),direct_fixture(),deadline=12)
    assert len(calls)==4
    assert result['search_budget_exhausted']
    assert all(row['status']=='deferred_budget' for row in result['legs'][0]['layer_attempts'])


def test_primary_complete_tree_not_starved_by_nested_portfolio_division():
    clock=[0.0]; deadlines=[]
    def route(*args,**kwargs):
        deadlines.append(kwargs['deadline'])
        # A synthetic complete solve needing more than the old 60-second
        # quarter-share remains feasible under the unchanged 240-second cap.
        if kwargs['deadline']-clock[0] >= 100:
            clock[0]+=100
            return {'segments':6}
        clock[0]=kwargs['deadline']
        return {'refused':'search budget exhausted'}
    with patch.object(p.time,'monotonic',side_effect=lambda:clock[0]), \
         patch.object(p,'_route_direct_pair_tree',side_effect=route), \
         patch.object(p,'_route_layered_multidrop_pair_tree') as layered:
        result=p._route_multidrop_topologies(Board(),dict(name='P',p='P',n='N'),fixture(),deadline=240)
    assert deadlines==[160]
    assert not result.get('refused')
    layered.assert_not_called()


def test_preferred_native_lane_gets_constructive_share_without_growing_edge_budget():
    clock=[0.0]; calls=[]
    def route(*args,**kwargs):
        lease=kwargs['deadline']-clock[0];calls.append(lease)
        # Two graph edges share twelve seconds. Six seconds per edge is
        # enough, but the old four-job equal split gave only 1.5 seconds.
        assert kwargs['deadline']<=12
        if lease<3.5:
            clock[0]=kwargs['deadline'];return {'refused':'bounded constructive search stopped'}
        clock[0]+=3.5;return {'segments':2}
    with patch.object(p.time,'monotonic',side_effect=lambda:clock[0]), \
         patch.object(p,'route_coupled_pair',side_effect=route), \
         patch.object(p,'_drop_fully_covered_tracks',return_value={}), \
         patch.object(p,'_pair_graph_geometry',return_value={'ok':True}), \
         patch.object(p,'_pair_transaction_detour',return_value={'ok':True}):
        result=p._route_direct_pair_tree(Board(),dict(name='RENAMED',p='a',n='b'),direct_fixture(),deadline=12)
    assert calls==pytest.approx([4.,17./3.])
    assert result['completed_edge_count']==2 and not result.get('refused')
    assert clock[0]==7.


def test_unused_preferred_native_time_is_reclaimed_by_next_layer():
    clock=[0.0]; calls=[]
    def route(*args,**kwargs):
        calls.append((kwargs['layer'],kwargs['deadline']-clock[0]))
        if kwargs['layer']=='F.Cu':
            clock[0]+=.1;return {'refused':'actual copper blockage'}
        return {'segments':2}
    with patch.object(p.time,'monotonic',side_effect=lambda:clock[0]), \
         patch.object(p,'route_coupled_pair',side_effect=route), \
         patch.object(p,'_drop_fully_covered_tracks',return_value={}), \
         patch.object(p,'_pair_graph_geometry',return_value={'ok':True}), \
         patch.object(p,'_pair_transaction_detour',return_value={'ok':True}):
        result=p._route_direct_pair_tree(Board(),dict(name='RENAMED',p='a',n='b'),direct_fixture(),deadline=12)
    assert calls[0][1]==pytest.approx(4.)
    assert calls[1][1]==pytest.approx(5.9/3.)
    assert result['completed_edge_count']==2


@pytest.mark.parametrize('fraction',[0,1,-1,float('nan'),float('inf'),True,None,'0.5'])
def test_preferred_native_layer_budget_rejects_invalid_fraction(fraction):
    with pytest.raises(ValueError,match='native layer budget fraction'):
        p._route_direct_pair_tree(Board(),dict(name='PAIR',p='P',n='N'),direct_fixture(),
            primary_layer_budget_fraction=fraction)


def test_primary_budget_reclaims_unused_time_and_bounds_alternatives():
    clock=[0.0]; deadlines=[]
    def direct(*args,**kwargs):
        deadlines.append(kwargs['deadline'])
        clock[0]+=10 if len(deadlines)==1 else kwargs['deadline']-clock[0]
        return {'refused':'blocked'}
    def layered(*args,**kwargs):
        deadline=kwargs['_absolute_deadline']; deadlines.append(deadline)
        assert clock[0] <= deadline <= 240
        clock[0]=deadline
        return {'refused':'blocked'}
    with patch.object(p.time,'monotonic',side_effect=lambda:clock[0]), \
         patch.object(p,'_route_direct_pair_tree',side_effect=direct), \
         patch.object(p,'_route_layered_multidrop_pair_tree',side_effect=layered):
        result=p._route_multidrop_topologies(Board(),dict(name='P',p='P',n='N'),fixture(),deadline=240)
    assert deadlines==[160,67.5,125,182.5,240]
    assert result.get('refused') and len(result['topology_attempts'])==5


@pytest.mark.parametrize('fraction',[0,1,-1,float('nan'),float('inf')])
def test_primary_budget_rejects_invalid_configuration(fraction):
    with pytest.raises(ValueError,match='budget fraction'):
        p._route_multidrop_topologies(Board(),{},fixture(),primary_budget_fraction=fraction)

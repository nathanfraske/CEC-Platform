"""Loaded-native transaction tests for series-group order backtracking."""
import time
from unittest.mock import patch

import pcbnew
import pytest
import cec_pair_order_repair as repair
import cec_local_copper_cell as cell
from test_pair_shared_series_launch import fixture


def add_track(board,net,a,b,locked=True):
    item=pcbnew.PCB_TRACK(board);item.SetStart(pcbnew.VECTOR2I_MM(*a))
    item.SetEnd(pcbnew.VECTOR2I_MM(*b));item.SetWidth(pcbnew.FromMM(.2))
    item.SetLayer(pcbnew.F_Cu);item.SetNetCode(board.GetNetcodeFromNetname(net))
    item.SetLocked(locked);board.Add(item);return item


def add_return(board):
    if 'GND' not in board.GetNetsByName():board.Add(pcbnew.NETINFO_ITEM(board,'GND'))
    item=pcbnew.PCB_VIA(board);item.SetPosition(pcbnew.VECTOR2I_MM(29,30))
    item.SetWidth(pcbnew.FromMM(.6));item.SetDrill(pcbnew.FromMM(.3))
    item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);item.SetNetCode(board.GetNetcodeFromNetname('GND'))
    item.SetLocked(True);board.Add(item);return item


def group(board,items,name):
    value=pcbnew.PCB_GROUP(board);value.SetName(name);board.Add(value)
    for item in items:value.AddItem(item)
    return value


def transaction_fixture():
    board,first,second,_,_=fixture()
    fixed=add_track(board,'BLOCKER',(35,31),(36,31))
    group(board,[fixed,next(iter(board.GetFootprints()))],'SOURCE')
    generated=[add_track(board,first['p'],(20,22),(21,22)),
               add_track(board,first['n'],(20,23),(21,23)),add_return(board)]
    group(board,generated,'OLD_PAIR')
    owned={item.m_Uuid.AsString() for item in generated}
    routed=[dict(first,route_mode='synthetic-existing-generation')]
    refused=[dict(second,refused='blocked by earlier generation')]
    return board,first,second,fixed,owned,routed,refused


def candidate(board,pairs,*,ok=True,geometry=True,complete=True):
    made=[]
    for i,pair in enumerate(pairs):
        made.extend([add_track(board,pair['p'],(22+i*2,26),(23+i*2,26)),
                     add_track(board,pair['n'],(22+i*2,27),(23+i*2,27))])
    made.append(add_return(board));group(board,made,'RETRY_PAIR')
    return dict(pairs_ok=ok,route_quality=dict(ok=ok,geometry_ok=geometry),
        pairs=dict(routed=[dict(pair,route_mode='synthetic-qualification') for pair in (pairs if complete else pairs[:1])],
                   refused=[],schedule=[dict(name=pair['name']) for pair in pairs]))


@pytest.mark.parametrize('angle,offset,prefix',[(0,(0,0),'AAA'),(90,(20,20),'OTHER'),(45,(9,8),'CELL')])
def test_shared_support_derivation_is_native_and_name_independent(angle,offset,prefix):
    board,a,b,_,_=fixture(angle,offset,prefix)
    result=repair.shared_series_groups(board,[a,b])
    assert len(result)==1 and result[0]['pairs']==[a['name'],b['name']]
    assert len(result[0]['edges'][0]['supports'])==2


def test_similar_refs_do_not_prove_a_series_connection():
    board,a,b,_,pads=fixture()
    pads[1][1].SetNetCode(board.GetNetcodeFromNetname('BLOCKER'))
    assert not repair.shared_series_groups(board,[a,b])


def test_complete_qualified_group_replaces_only_new_prefix():
    board,a,b,fixed,owned,routed,refused=transaction_fixture()
    before=cell.copper_inventory(board);calls=[]
    def route(order,deadline):
        calls.append(order)
        assert order==[b['name'],a['name']] and time.monotonic()<deadline
        assert not (owned & cell.copper_inventory(board).keys())
        return candidate(board,[b,a])
    rr,ff,report=repair.retry_groups(board,[a,b],routed,refused,{a['name']:owned},
        {fixed.m_Uuid.AsString()},route_order=route)
    after=cell.copper_inventory(board)
    assert report['adopted']==1 and len(calls)==1 and not ff
    assert {row['name'] for row in rr}=={a['name'],b['name']}
    assert after[fixed.m_Uuid.AsString()]==before[fixed.m_Uuid.AsString()]
    assert not (owned & after.keys())
    assert {g.GetName() for g in board.Groups()}=={'SOURCE','RETRY_PAIR'}


@pytest.mark.parametrize('failure',['refused','quality','partial','exception','fixed_mutation','old_uuid_reuse'])
def test_failed_retry_restores_exact_copper_ids_returns_and_groups(failure):
    board,a,b,fixed,owned,routed,refused=transaction_fixture()
    before=cell.copper_inventory(board);groups=repair._group_inventory(board)
    def route(order,deadline):
        rep=candidate(board,[b,a],ok=failure!='refused',geometry=failure!='quality',complete=failure!='partial')
        if failure=='exception':raise RuntimeError('synthetic generator failure')
        if failure=='fixed_mutation':fixed.SetStart(pcbnew.VECTOR2I_MM(40,40))
        if failure=='old_uuid_reuse':
            item=add_track(board,a['p'],(40,40),(41,40));item.m_Uuid.Clone(pcbnew.KIID(sorted(owned)[0]))
        return rep
    rr,ff,report=repair.retry_groups(board,[a,b],routed,refused,{a['name']:owned},
        {fixed.m_Uuid.AsString()},route_order=route)
    assert report['adopted']==0 and report['attempts'][0]['rollback_exact']
    assert rr==routed and ff==refused
    assert cell.copper_inventory(board)==before and repair._group_inventory(board)==groups


@pytest.mark.parametrize('case',['source_net','source_id','overlapping_owner','missing_owner','scope','tiny_budget'])
def test_no_retry_without_valid_budget_and_ownership(case):
    board,a,b,fixed,owned,routed,refused=transaction_fixture();calls=[]
    source={fixed.m_Uuid.AsString()};ownership={a['name']:owned}
    if case=='source_net':source.add(next(uid for uid in owned if cell.copper_inventory(board)[uid][1]==a['p']))
    if case=='source_id':
        ownership[a['name']]=owned|source
    if case=='overlapping_owner':ownership['UNRELATED']=owned
    if case=='missing_owner':ownership[a['name']]=owned|{'missing-native-id'}
    if case=='scope':refused=[]
    before=cell.copper_inventory(board)
    rr,ff,report=repair.retry_groups(board,[a,b],routed,refused,ownership,source,
        route_order=lambda *args:calls.append(args),max_wall_s=.001 if case=='tiny_budget' else 60.)
    assert not calls and report['adopted']==0 and cell.copper_inventory(board)==before


def test_already_failed_first_order_is_not_retried():
    board,a,b,fixed,owned,routed,refused=transaction_fixture()
    result=repair.retry_groups(board,[b,a],routed,refused,{a['name']:owned},
        {fixed.m_Uuid.AsString()},route_order=lambda *_:pytest.fail('repeated same order'))
    assert not result[2]['attempts']


def test_precision_entry_backtracks_once_then_preserves_the_selected_copper():
    import cec_precision_route as precision
    import cec_route_preflight as preflight
    board,a,b,_,_=fixture();fixed=add_track(board,'BLOCKER',(35,31),(36,31))
    fixed_id=fixed.m_Uuid.AsString();before=cell.copper_inventory(board)
    calls=[];reservations=[]
    third=dict(name='INDEPENDENT',p='OUTSIDE_A',n='OUTSIDE_B',width=.2,gap=.2,clearance=.2)
    for net in (third['p'],third['n']):board.Add(pcbnew.NETINFO_ITEM(board,net))
    def solve(native,pair,**kwargs):
        calls.append(pair['name'])
        report=dict(pair,route_mode='synthetic-route-dispatch',segments=2)
        if pair['name']==b['name'] and any(item.GetNetname()==a['p'] for item in native.GetTracks()):
            return dict(report,refused='earlier pair owns the only synthetic corridor')
        index=0 if pair['name']==a['name'] else 1 if pair['name']==b['name'] else 2
        add_track(native,pair['p'],(22+index*2,26),(23+index*2,26))
        add_track(native,pair['n'],(22+index*2,27),(23+index*2,27))
        return report
    def reserve(_board,pending,**kwargs):
        reservations.append([pair['name'] for pair in pending]);return []
    with patch.object(precision,'derive_coupled_pairs',return_value=[a,b,third]), \
            patch.object(precision,'_scheduled_coupled_pairs',return_value=([a,b,third],[dict(name=pair['name']) for pair in (a,b,third)])), \
            patch.object(precision,'_future_pair_launch_reservations',side_effect=reserve), \
            patch.object(precision,'_flow_through_pair_legs',return_value=None), \
            patch.object(precision,'_multidrop_pair_plan',return_value=None), \
            patch.object(precision.cec_fr,'synthesize_same_footprint_links',return_value={}), \
            patch.object(precision,'route_coupled_pair',side_effect=solve), \
            patch.object(precision,'_qualify_pair_candidate',side_effect=lambda board,pair,rep,**kw:rep), \
            patch('cec_route_quality.analyze_board',return_value=dict(ok=True,geometry_ok=True)), \
            patch.object(precision.cec_fr,'owned_locked_nets',return_value=set()), \
            patch.object(precision.cec_fr,'synthesize_kelvin_taps',return_value={}):
        report=preflight._probe_critical_pairs_on_board(board,'synthetic')
    assert calls==[a['name'],b['name'],third['name'],b['name'],a['name']]
    assert reservations==[[b['name'],third['name']],[third['name']],[],[third['name']],[third['name']]]
    assert report['pairs_ok'] and report['group_order_repair']['adopted']==1
    assert not report['refused'] and len(report['routed'])==3
    final=preflight.compact_placement_evidence(dict(critical_routes=report))
    assert final['critical_pair_order_repair']['adopted']==1
    assert final['critical_route_refused_count']==0
    assert cell.copper_inventory(board)[fixed_id]==before[fixed_id]
    assert len(list(board.GetTracks()))==7


def test_internal_schedule_validation_precedes_kelvin_writes():
    import cec_precision_route as precision
    board,a,b,_,_=fixture()
    with patch.object(precision,'derive_coupled_pairs',return_value=[a,b]), \
            patch.object(precision.cec_fr,'synthesize_kelvin_taps') as kelvin:
        with pytest.raises(ValueError):precision.precision_route_board(board,_pair_schedule_override=[a['name'],a['name']])
        kelvin.assert_not_called()


def test_no_unbounded_or_out_of_scope_synthetic_reservation_deferral():
    import cec_precision_route as precision
    board,a,b,_,_=fixture()
    with patch.object(precision,'derive_coupled_pairs',return_value=[a,b]), \
            patch.object(precision.cec_fr,'synthesize_kelvin_taps') as kelvin:
        with pytest.raises(ValueError):precision.precision_route_board(board,
            include_pair_names=[a['name']],_negotiated_pair_scope=[a['name'],b['name']])
        kelvin.assert_not_called()

"""Late legal layer alternatives survive without increasing the menu budget."""
import copy
import pytest
import cec_route_choice_portfolio as p


def choice(index,layer=0,via=False,cost=None,dependency=None):
    ops=[['trk',[index,0],[index+10,0],200000,layer]]
    if via:ops.append(['via',[index,0],.3,.5])
    r=dict(id=str(index),ops=ops,net='renamed_signal',cost=float(index+1 if cost is None else cost))
    if dependency is not None:r['requires_ground_entry']=dependency
    return r


def test_forty_eight_front_paths_cannot_hide_late_legal_inner_bridge():
    rows=[choice(i)for i in range(48)]
    bridge=choice(100,layer=6,via=True,cost=1000)
    result=p.retain(rows,bridge,capacity=48)
    assert result['retained']and result['evicted']and len(rows)==48
    assert bridge in rows and choice(47)not in rows


def test_topology_balance_retains_multiple_late_bridge_port_geometries():
    rows=[choice(i)for i in range(48)]
    for i in range(13):assert p.retain(rows,choice(100+i,6,True),capacity=48)['retained']
    assert len(rows)==48 and sum(q['ops'][0][-1]==6 for q in rows)==13
    assert sorted(q['cost']for q in rows if q['ops'][0][-1]==0)==list(map(float,range(1,36)))


def test_single_topology_preserves_cheapest_bound_not_last_arrival():
    rows=[choice(0),choice(1)]
    assert not p.retain(rows,choice(4),capacity=2)['retained']
    assert p.retain(rows,choice(5,cost=.1),capacity=2)['retained']
    assert sorted(q['cost']for q in rows)==[.1,1.]


def test_ground_dependency_is_part_of_physical_access_signature():
    rows=[choice(0,dependency={'root':'a'}),choice(1,dependency={'root':'a'})]
    incoming=choice(10,cost=100,dependency={'root':'b'})
    assert p.retain(rows,incoming,capacity=2)['retained']
    assert incoming in rows and rows[0]['requires_ground_entry']=={'root':'a'}


def test_same_layer_with_distinct_barrel_count_remains_a_distinct_access():
    rows=[choice(0),choice(1)]
    incoming=choice(3,0,True,cost=100)
    assert p.retain(rows,incoming,capacity=2)['retained']


def test_duplicate_cost_or_identifier_does_not_grant_another_geometry_slot():
    rows=[choice(0)];before=copy.deepcopy(rows);incoming=copy.deepcopy(rows[0]);incoming['id']='new'
    assert p.retain(rows,incoming,capacity=2)['duplicate']and rows==before


@pytest.mark.parametrize('capacity',[0,49,True,1.5,None])
def test_bad_capacity_refuses_without_mutating_candidates(capacity):
    rows=[]
    with pytest.raises(ValueError):p.retain(rows,choice(0),capacity=capacity)
    assert not rows


@pytest.mark.parametrize('fault',['nan','negative','unknown','wrong_layer','oversized'])
def test_invalid_guarded_choice_refuses_without_electrical_permission(fault):
    incoming=choice(0);rows=[];capacity=2
    if fault=='nan':incoming['cost']=float('nan')
    elif fault=='negative':incoming['cost']=-1
    elif fault=='unknown':incoming['ops'][0][0]='zone'
    elif fault=='wrong_layer':incoming['ops'][0][-1]=True
    else:rows=[choice(i)for i in range(3)]
    before=copy.deepcopy(rows)
    with pytest.raises(ValueError):p.retain(rows,incoming,capacity=capacity)
    assert rows==before


def test_capacity_one_cannot_claim_to_represent_two_topologies():
    rows=[choice(0)]
    assert not p.retain(rows,choice(1,6,True,cost=100),capacity=1)['retained']
    assert len(rows)==1


def test_no_empty_noop_dependency_or_source_choice_fields_are_rewritten():
    rows=[];incoming=dict(id='inherited',cost=0,ops=[],net='same_net',
        requires_ground_entry={'actual_owner':'source-pad'},clearance_nm=250000)
    before=copy.deepcopy(incoming);assert p.retain(rows,incoming,capacity=1)['retained']
    assert incoming==before


@pytest.mark.parametrize('capacity',[4,48])
def test_actual_menu_retains_late_layer_choice_and_finalizes_unique_ids(monkeypatch,capacity):
    import pcbnew
    import cec_cell_escape_replan as escape
    from test_cell_escape_replan import fixture
    board,_,_,_=fixture(monkeypatch,'renamed_owner')
    before=escape.row._source_binding(board)
    inner=int(list(board.GetEnabledLayers().CuStack())[2])
    def generated(board,request,**kwargs):
        # Producer-dispatch fixture ONLY, not fake native admission: the
        # production guard remains responsible for every submitted operation.
        for i in range(capacity):
            kwargs['append']([('trk',(i*100000,0),(i*100000+50000,0),200000,pcbnew.F_Cu)])
        kwargs['append']([('trk',(0,0),(50000,0),200000,inner),
            ('via',(0,0),.3,.5),('via',(50000,0),.3,.5)])
    monkeypatch.setattr(escape,'_connection_menu',generated)
    packet=escape.menus(board,{'port':dict(kind='source_boundary',net='OUT')},
        board_path='opaque',board_hint='opaque',max_choices=capacity)
    choices=packet['domains']['port']
    assert len(choices)==capacity and [q['id']for q in choices]==list(map(str,range(capacity)))
    assert any(any(op[0]=='trk'and op[4]==inner for op in q['ops'])for q in choices)
    stats=packet['diagnostics']['port']['bounded_topology_retention']
    assert stats['guarded_candidates']==capacity+1 and stats['evictions']==1
    assert stats['capacity']==capacity and stats['no_geometry_authority']
    assert before==escape.row._source_binding(board)

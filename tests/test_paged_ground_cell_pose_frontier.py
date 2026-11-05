"""Joint pose prefixes resume without skipping states or granting geometry authority."""
import copy
import itertools
import pcbnew
import pytest
import cec_force_current as force
import cec_paged_ground_cell_pose_frontier as frontier


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_literal_column_inventory_is_frame_equivariant(quarter,mirror):
    origin=(12345678,-9988776);p=frontier.points(origin,2000000,500000)
    def turn(v):
        x,y=v[0]-origin[0],v[1]-origin[1]
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return origin[0]+x,origin[1]+y
    assert len(p)==49 and len(set(p))==49 and set(map(turn,p))==set(p)
    assert p[0]==origin


@pytest.mark.parametrize('column',range(4))
def test_every_cardinal_owner_cap_and_spacing_combination_has_one_state(column):
    rows=[frontier.decode(column*48+i) for i in range(48)]
    assert set(rows)==set(itertools.product([column],range(0,360,90),range(0,360,90),(.8,1.2,1.6)))


@pytest.mark.parametrize('page_size',[1,7,47,48,49,95,192])
def test_blocked_column_ranges_and_partial_columns_have_no_gaps_or_duplicate_native_states(page_size):
    binding='b'*64;resume=None;ranges=[];checked=[]
    def blocked(column):return dict(actual_collision=True) if column in (0,2) else None
    def check(*state):checked.append(state);return dict(kind='native_courtyard_refused')
    while True:
        r=frontier.walk(192,binding,blocked,check,resume=resume,page_states=page_size)
        assert r['no_gap_or_overlap_in_actual_attempted_prefix']
        ranges+=r['actual_examined_ranges'];resume=r['continuation']
        if r['all_finite_states_attempted']:break
    assert checked==[frontier.decode(i) for i in range(192) if i//48 in (1,3)]
    assert [n for row in ranges for n in range(row['start'],row['end'])]==list(range(192))
    assert r['finite_menu_closed_without_unknowns'] and not r['global_no_path_or_optimal_placement_proof']


def test_offer_ends_this_page_but_next_page_starts_after_it():
    def check(column,cap,owner,spacing):return dict(kind='offer',offer=[column,cap,owner,spacing])
    first=frontier.walk(96,'a'*64,lambda _:None,check,maximum_offers=1)
    second=frontier.walk(96,'a'*64,lambda _:None,check,maximum_offers=1,resume=first['continuation'])
    assert first['next_index']==1 and second['start_index']==1 and second['next_index']==2
    assert first['offers']!=second['offers'] and not second['all_finite_states_attempted']


def test_unknown_is_an_attempted_state_not_no_path_or_clean_exhaustion():
    r=frontier.walk(2,'c'*64,lambda _:None,lambda *args:dict(kind='bounded_native_unknown'),page_states=1)
    last=frontier.walk(2,'c'*64,lambda _:None,lambda *args:dict(kind='native_surface_refused'),resume=r['continuation'])
    assert last['all_finite_states_attempted'] and last['unknown_states_across_prefix']==1
    assert not last['finite_menu_closed_without_unknowns'] and not last['global_no_path_or_optimal_placement_proof']


@pytest.mark.parametrize('fault',['binding','index','total','unknown','extra','checksum','schema','bool_index','negative','overflow'])
def test_cursor_cannot_silently_change_source_helpers_settings_or_prefix(fault):
    q=frontier.cursor('d'*64,17,96,1)
    if fault=='binding':q['binding']='e'*64
    elif fault=='index':q['next_index']=18
    elif fault=='total':q['total_states']=97
    elif fault=='unknown':q['unknown_states']=0
    elif fault=='extra':q['silently_skip']=True
    elif fault=='checksum':q['checksum']='forged'
    elif fault=='schema':q['schema']=2
    elif fault=='bool_index':q['next_index']=True
    elif fault=='negative':q['next_index']=-1
    else:q['next_index']=97
    with pytest.raises(ValueError):frontier.walk(96,'d'*64,lambda _:None,lambda *a:dict(kind='test'),resume=q)


@pytest.mark.parametrize('option',[dict(total=True),dict(total=-1),dict(page_states=True),dict(page_states=0),
    dict(page_states=32769),dict(maximum_offers=True),dict(maximum_offers=0),dict(maximum_offers=9),
    dict(timeout_s=True),dict(timeout_s=0),dict(timeout_s=float('nan')),dict(timeout_s=45.01)])
def test_truthy_flags_and_unbounded_search_budgets_refuse(option):
    args=dict(total=96,binding='f'*64,blocked=lambda _:None,check=lambda *a:dict(kind='test'));args.update(option)
    with pytest.raises(ValueError):frontier.walk(**args)


@pytest.mark.parametrize('fault',['float_origin','bool_origin','zero_radius','oversized_radius','small_grid','bool_grid'])
def test_lattice_coordinates_and_bounds_are_literal_integer_geometry(fault):
    args=dict(origin=(1,2),radius_nm=1000000,grid_nm=500000)
    if fault=='float_origin':args['origin']=(1.,2)
    elif fault=='bool_origin':args['origin']=(True,2)
    elif fault=='zero_radius':args['radius_nm']=0
    elif fault=='oversized_radius':args['radius_nm']=32000001
    elif fault=='small_grid':args['grid_nm']=249999
    else:args['grid_nm']=True
    with pytest.raises(ValueError):frontier.points(**args)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_saved_native_frame_reuses_no_board_name_or_refdes_authority(tmp_path,monkeypatch,quarter,back):
    from test_complete_macro_cell import fixture
    source,parent,private,packet=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    cap,selected=next(iter(packet['source_plan']['selected_bypasses'].items()))
    owner=selected['owner'];raw=source.read_bytes()
    seed=dict(source=str(source),source_sha256=force._hash(source),board_hint='opaque',
        poses={r:[parent.FindFootprintByReference(r).GetPosition().x/1e6,
            parent.FindFootprintByReference(r).GetPosition().y/1e6,
            parent.FindFootprintByReference(r).GetOrientationDegrees()] for r in (cap,owner)},
        source_selected_bypass=dict(ref=owner,pin=selected['pin'],rail=selected['rail']),required_ground_pad_entries=[])
    context=frontier.prepare(seed,radius_mm=2.,grid_mm=.5)
    first=frontier.scan(context,page_states=1,maximum_offers=1,timeout_s=10.)
    second=frontier.scan(context,resume=first['coverage']['continuation'],page_states=1,maximum_offers=1,timeout_s=10.)
    assert first['coverage']['next_index']==second['coverage']['start_index']==1
    assert first['warm_source_context_reused'] and second['source_family_and_stationary_material_unchanged']
    assert not first['source_selected'] and not first['routing_admitted'] and first['no_board_saved']
    assert source.read_bytes()==raw

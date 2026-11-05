"""Exact discovery filters/cursors, never synthetic hardware current ratings."""
import copy
import pcbnew
import pytest
import cec_cached_current_path_search as cache
from test_pour_backed_current_path import fixture


def menu_fixture(tmp_path,monkeypatch,**kwargs):
    source,args,_,_=fixture(tmp_path,monkeypatch,**kwargs)
    net='/SYNTHETIC_FULL_CURRENT_GEOMETRY_NOT_A_RATING'
    monkeypatch.setattr(cache.owner.full.topology,'board_current_domains',lambda *a:{net:{}})
    monkeypatch.setattr(cache.owner.full.topology,'distributed_supply_contracts',lambda *a,**k:dict(contracts={}))
    return source,args,cache.inventory(source,board_hint=args['board_hint'])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_cached_pages_reach_the_original_native_owner_without_mutating_source(tmp_path,monkeypatch,quarter,face):
    source,args,menu=menu_fixture(tmp_path,monkeypatch,quarter=quarter,face=face)
    original=source.read_bytes();pages=[];cursor=0;offers=[]
    while cursor<menu['ranked_windows']:
        part=cache.page(source,menu,start=cursor,maximum_windows=2,maximum_proposals=32)
        assert part['next_index']>cursor
        cursor=part['next_index'];pages.append(part);offers.extend(part['proposals'])
    proof=cache.receive_sweep(source,menu,pages)
    assert proof['complete_ranked_menu_examined'] and proof['actual_source_inventory_independently_regenerated']
    assert offers and source.read_bytes()==original
    assert menu==cache.inventory(source,board_hint=args['board_hint'])
    for row in offers:
        fresh=cache.owner.plan(source,board_hint=args['board_hint'],**row['target'])
        assert fresh==row['proposal']
    assert not proof['release_authority']


@pytest.mark.parametrize('fault',['source','helper','digest','index','count'])
def test_cached_menu_cannot_be_reused_after_source_or_binding_changes(tmp_path,monkeypatch,fault):
    source,args,menu=menu_fixture(tmp_path,monkeypatch);bad=copy.deepcopy(menu)
    if fault=='source':
        source.write_text(source.read_text()+'\n')
    elif fault=='helper':bad['input_sha256'][str(cache.__file__)]= '0'*64
    elif fault=='digest':bad['inventory_sha256']='0'*64
    elif fault=='index':bad['rows'][0]['index']=1
    else:bad['ranked_windows']+=1
    with pytest.raises(ValueError):cache.page(source,bad)


@pytest.mark.parametrize('fault',['gap','overlap','cut','filter','positive'])
def test_independent_sweep_replay_rejects_forged_coverage(tmp_path,monkeypatch,fault):
    source,args,menu=menu_fixture(tmp_path,monkeypatch)
    part=cache.page(source,menu,maximum_windows=128,maximum_proposals=32)
    bad=copy.deepcopy(part)
    if fault=='gap':bad['start']=1
    elif fault=='overlap':
        with pytest.raises(ValueError):cache.receive_sweep(source,menu,[bad,bad])
        return
    elif fault=='cut':bad['rows'][0]['track_uuids']=['not-source']
    elif fault=='filter':
        bad['rows'][0].update(owner_plan_called=False,proposal=False,refusal='invented_filter')
    else:
        assert bad['proposals']
        bad['proposals'][0]['proposal']['current_proposal']['width_nm']=1
    with pytest.raises(ValueError):cache.receive_sweep(source,menu,[bad])


@pytest.mark.parametrize('key,value',[('start',True),('start',-1),('maximum_windows',True),
    ('maximum_windows',129),('maximum_proposals',0),('timeout_s',11)])
def test_page_work_bounds_are_not_truthy_permissions(tmp_path,monkeypatch,key,value):
    source,_,menu=menu_fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):cache.page(source,menu,**{key:value})


def test_zero_offer_first_page_is_not_a_false_plateau(tmp_path,monkeypatch):
    source,args,menu=menu_fixture(tmp_path,monkeypatch)
    original=cache.owner.plan
    first_ids=menu['rows'][0]['track_uuids']
    def later_only(source,**kwargs):
        if kwargs['retired_track_uuids']==first_ids:raise ValueError('explicit_test_first_window_blocked')
        return original(source,**kwargs)
    monkeypatch.setattr(cache.owner,'plan',later_only)
    first=cache.page(source,menu,maximum_windows=1)
    assert not first['proposals'] and not first['complete_ranked_menu_examined']
    rest=cache.page(source,menu,start=first['next_index'],maximum_windows=128,maximum_proposals=32)
    assert rest['proposals']
    assert cache.receive_sweep(source,menu,[first,rest])['complete_ranked_menu_examined']


def test_necessary_filters_do_not_hide_a_positive_original_owner_plan(tmp_path,monkeypatch):
    source,args,menu=menu_fixture(tmp_path,monkeypatch)
    positives=0
    for row in menu['rows']:
        try:
            cache.owner.plan(source,board_hint=args['board_hint'],retired_track_uuids=row['track_uuids'])
        except ValueError:
            continue
        positives+=1
        assert row['necessary_refusal'] is None
    assert positives


@pytest.mark.parametrize('fault',['omit_window','invent_filter'])
def test_rehashed_menu_still_needs_independent_actual_source_regeneration(tmp_path,monkeypatch,fault):
    source,args,menu=menu_fixture(tmp_path,monkeypatch)
    bad=copy.deepcopy(menu)
    if fault=='omit_window':
        bad['rows'].pop()
        bad['ranked_windows']-=1
    else:
        bad['rows'][0]['necessary_refusal']='invented_filter'
    bad['inventory_sha256']=cache.digest({k:v for k,v in bad.items() if k!='inventory_sha256'})
    page=cache.page(source,bad,maximum_windows=128,maximum_proposals=32)
    with pytest.raises(ValueError,match='actual_source_menu_differs'):
        cache.receive_sweep(source,bad,[page])

"""Finite Ground pages are coverage evidence, never a current/fab rating."""
import copy
import time

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_access_completion as entry
import cec_source_ground_frontier as frontier
from test_ground_access_completion import fixture


def observations(count):
    return {str(n): dict(pad_uuid=f'pad-{n:04d}', at_nm=[n*1000000, 2000000],
        return_mm=4.-n/1000, ref=f'arbitrary-{n}', pin='unrestricted',
        net='GND', layer_id=0) for n in range(count)}


@pytest.mark.parametrize('count', [0, 1, 16, 17, 42, 131])
def test_menu_does_not_starve_terminals_after_the_old_sixteen_limit(count):
    obs=observations(count)
    menu=frontier._menu(obs,reach_mm=.5,offsets_nm=(400000,),resolve=lambda _: (False,None))
    assert len(menu)==count and [v['index'] for v in menu]==list(range(count))
    assert {v['terminal']['pad_uuid'] for v in menu}=={v['pad_uuid'] for v in obs.values()}


def test_every_cardinal_stencil_site_is_a_separate_cursor_row():
    menu=frontier._menu(observations(17),reach_mm=.5,offsets_nm=(400000,),
        resolve=lambda _: (True,(.3,.2)))
    assert len(menu)==85
    for n in range(17):
        rows=menu[n*5:(n+1)*5];assert len({tuple(v['at_nm']) for v in rows})==5
        assert rows[0]['at_nm']==rows[0]['terminal']['at_nm']
    assert len({v['terminal']['pad_uuid'] for v in menu[80:]})==1


def test_unknown_return_is_not_scheduled_as_infinite_or_an_open():
    obs=observations(3);obs['1']['return_mm']=None;obs['2']['return_mm']=.4
    menu=frontier._menu(obs,reach_mm=.5,offsets_nm=(400000,),resolve=lambda _: (False,None))
    assert [v['terminal']['pad_uuid'] for v in menu]==['pad-0000']


def packets(count=17):
    menu=frontier._menu(observations(count),reach_mm=.5,offsets_nm=(400000,),
        resolve=lambda _: (False,None))
    identity=dict(menu=menu);digest=frontier._digest(identity);pages=[]
    for start in range(0,count,4):
        rows=menu[start:start+4]
        pages.append(dict(inventory_sha256=digest,start_index=start,next_index=start+len(rows),
            attempts=[dict(site_index=r['index'],terminal=r['terminal'],plan_arguments=r['plan_arguments'])
                for r in rows]))
    return identity,digest,pages


def test_only_actual_contiguous_pages_can_claim_full_finite_menu_coverage():
    identity,digest,pages=packets()
    first=frontier.coverage(identity,digest,pages[:4]);assert first['examined_sites']==16
    assert not first['all_finite_menu_sites_examined'] and first['unexamined_sites']==1
    full=frontier.coverage(identity,digest,pages)
    assert full['all_finite_menu_sites_examined'] and full['examined_sites']==17
    assert not full['global_shortest_or_no_path_proof'] and not full['release_authority']


@pytest.mark.parametrize('fault',['gap','overlap','missing_attempt','duplicate_attempt','wrong_terminal',
    'wrong_plan','wrong_site','stale_page','rehashed_inventory'])
def test_tampered_coverage_never_hides_an_unexamined_site(fault):
    identity,digest,pages=packets();pages=copy.deepcopy(pages)
    if fault=='gap':pages.pop(1)
    elif fault=='overlap':pages.insert(1,copy.deepcopy(pages[0]))
    elif fault=='missing_attempt':pages[0]['attempts'].pop()
    elif fault=='duplicate_attempt':pages[0]['attempts'][1]=copy.deepcopy(pages[0]['attempts'][0])
    elif fault=='wrong_terminal':pages[0]['attempts'][0]['terminal']['pad_uuid']='forged'
    elif fault=='wrong_plan':pages[0]['attempts'][0]['plan_arguments']['reach_mm']=1.5
    elif fault=='wrong_site':pages[0]['attempts'][0]['site_index']=True
    elif fault=='stale_page':pages[0]['inventory_sha256']='0'*64
    else:identity['menu'].pop()
    with pytest.raises(ValueError):frontier.coverage(identity,digest,pages)


@pytest.mark.parametrize('cursor',[{},dict(inventory_sha256='bad',next_index=0),
    dict(inventory_sha256='abc',next_index=True),dict(inventory_sha256='abc',next_index=-1),
    dict(inventory_sha256='abc',next_index=18),dict(inventory_sha256='abc',next_index=1.5)])
def test_cursor_is_literal_integer_and_bound_to_source_settings_family_and_code(cursor):
    with pytest.raises(ValueError):frontier._index(cursor,'abc',17)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_native_source_proposal_keeps_the_original_saved_receiver(tmp_path,quarter,face):
    b,source,pad,point=fixture(tmp_path,quarter=quarter,layer=face,mode='vip',observed=True)
    before=source.read_bytes();digest=force._hash(source)
    r=frontier.discover_all(source,board_hint='synthetic',expected_source_sha256=digest,
        page_size=1,max_pages=4,timeout_s=10.)
    assert r['proposal'] and r['source_physical_items_unchanged']
    assert r['coverage']['no_gap_or_overlap_in_actual_examined_prefix']
    child=entry.construct(r['proposal']);additive._ground_refill(child)
    target=force._copy_family(source,tmp_path/'native-paged-child');field._save_field_snapshot(child,target)
    received=entry.receive(source,target,board_hint='synthetic',**r['plan_arguments'])
    assert received['ok'] and received['complete'] and received['shortened_return_witness_mm']>0
    assert received['every_source_native_partition_identical']
    assert not received['current_qualified'] and not received['release_authority']
    assert source.read_bytes()==before
    moved=pcbnew.LoadBoard(str(target));next(iter(moved.GetFootprints())).SetValue('forged')
    field._save_field_snapshot(moved,target)
    refused=entry.receive(source,target,board_hint='synthetic',**r['plan_arguments'])
    assert not refused['ok'] and not refused['complete']


def test_resume_rederives_inventory_and_rejects_a_changed_source_family(tmp_path):
    b,source,pad,point=fixture(tmp_path,mode='vip',observed=True);digest=force._hash(source)
    r=frontier.discover_all(source,board_hint='synthetic',expected_source_sha256=digest,
        page_size=1,max_pages=1,timeout_s=10.)
    source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    with pytest.raises(ValueError,match='cursor'):
        frontier.discover_all(source,board_hint='synthetic',expected_source_sha256=digest,
            cursor=r['continuation'])


def test_tighter_target_and_offsets_invalidate_old_continuation(tmp_path):
    b,source,pad,point=fixture(tmp_path,mode='vip',observed=True);digest=force._hash(source)
    r=frontier.discover_all(source,board_hint='synthetic',expected_source_sha256=digest,
        page_size=1,max_pages=1,timeout_s=10.)
    with pytest.raises(ValueError,match='cursor'):
        frontier.discover_all(source,board_hint='synthetic',expected_source_sha256=digest,
            reach_mm=.4,cursor=r['continuation'])


def test_timeout_mid_page_keeps_unexamined_suffix_not_a_false_plateau(tmp_path,monkeypatch):
    b,source,pad,point=fixture(tmp_path,mode='vip',observed=True)
    def blocked(*args,**kwargs):
        time.sleep(.02);raise ValueError('synthetic_finite_attempt_refusal')
    monkeypatch.setattr(frontier.original.entry,'plan',blocked)
    r=frontier.discover_all(source,board_hint='synthetic',expected_source_sha256=force._hash(source),
        page_size=2,max_pages=1,timeout_s=.01)
    assert not r['proposal'] and not r['global_shortest_or_no_path_proof']
    assert r['coverage']['examined_sites']==len(r['attempts'])
    assert all('refusal' in a for a in r['attempts'])

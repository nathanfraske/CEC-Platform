"""Search regions cannot stand in for Source compilation or real obstacles."""
import copy,math
import pcbnew
import pytest
from shapely import affinity
from shapely.geometry import box
import cec_force_current as force
import cec_native_cell_pose_domains as poses
from test_complete_macro_cell import fixture


@pytest.mark.parametrize('origins',[True,[],{'missing':[0,0]},{'owner':True},
    {'owner':[0]},{'owner':[0,0,0]},{'owner':[True,0]},{'owner':[float('nan'),0]},
    {'owner':[float('inf'),0]},{'owner':[1e308,0]},{'owner':['0',0]},
    {'owner':[2147.483648,0]}])
def test_invalid_search_origin_refuses_before_native_source_reads(origins):
    with pytest.raises(ValueError,match='search_origins'):
        poses.propose('missing',{'owner':[0,0,0]},board_hint='opaque',search_origins_mm=origins)


@pytest.mark.parametrize('option',['fixed_refs','frozen_target_refs'])
def test_search_origin_cannot_move_a_literal_frozen_or_source_anchor(option):
    with pytest.raises(ValueError,match='search_origins'):
        poses.propose('missing',{'owner':[0,0,0]},board_hint='opaque',
            search_origins_mm={'owner':[1,1]},**{option:['owner']})


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_search_region_acquires_full_translation_and_rotated_member_envelope(quarter,back):
    shape=affinity.rotate(box(1,-.25,3,.25),90*quarter,origin=(0,0))
    if back:shape=affinity.scale(shape,xfact=-1,origin=(0,0))
    origins={'arbitrary':[20.,15.]};moving={'arbitrary':[{'geometry':shape}]}
    bounds=box(*poses._pose_search_bounds(moving,{'arbitrary':(0,0)},origins,.5))
    for angle in (0,90,180,270):
        rotated=affinity.rotate(shape,angle,origin=(0,0))
        for dx,dy in ((.5,0),(-.5,0),(0,.5),(0,-.5)):
            assert bounds.covers(affinity.translate(rotated,20+dx,15+dy))
    assert bounds.covers(shape)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_search_origin_does_not_move_seed_or_borrow_receiving(tmp_path,monkeypatch,quarter,back):
    source,parent,private,packet=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    seed=copy.deepcopy(packet['source_plan']['poses']);cap=next(iter(packet['source_plan']['selected_bypasses']))
    centre=[seed[cap][0]+.25,seed[cap][1]];centres={cap:centre};before=copy.deepcopy(centres)
    digest=force._hash(source)
    proof=poses.propose(source,seed,board_hint='opaque',transport_source_barrels=True,
        search_origins_mm=centres,radius_mm=.5,grid_mm=.25,max_candidates=16,max_results=4)
    assert proof['offers'],{k:proof[k] for k in ('domain_stages','search','fresh_receiving')}
    assert proof['explicit_search_origins_mm']==centres and centres==before
    assert proof['search_origins_do_not_replace_source_compilation_or_receiving']
    assert proof['seed_source_plan']['poses']==seed
    assert all(math.dist(q['pose'][:2],centre)<=.500003 for q in proof['domains'][cap])
    assert proof['fresh_receiving'][-1]['ok'] and proof['source_and_code_unchanged']
    assert digest==force._hash(source) and not proof['routing_admitted'] and not proof['release_authority']


def test_search_region_never_relaxes_original_source_shift_limit(tmp_path,monkeypatch):
    source,parent,private,packet=fixture(tmp_path,monkeypatch)
    seeds=packet['source_plan']['poses'];ref=next(iter(seeds));fp=parent.FindFootprintByReference(ref)
    centre=[fp.GetPosition().x/1e6+5.,fp.GetPosition().y/1e6]
    with pytest.raises(ValueError,match='unchanged_source_shift_bound'):
        poses.propose(source,seeds,board_hint='opaque',max_shift_mm=4.,search_origins_mm={ref:centre})

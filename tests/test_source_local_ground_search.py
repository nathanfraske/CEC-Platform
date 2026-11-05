"""Ground entry discovery is bounded, source-bound and independent of refdes."""
import math
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_access_completion as entry
import cec_source_local_ground_search as search
from test_ground_access_completion import fixture
from test_existing_local_pofv_pad_rule import case as local_rule_case
from test_field_proposals import track


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_source_native_entry_discovery_has_no_component_name_or_frame_policy(tmp_path,quarter,mirror,layer):
    b,source,pad,point=fixture(tmp_path,quarter=quarter,mirror=mirror,layer=layer,mode='vip',observed=True)
    pad.GetParentFootprint().SetReference('not_a_capacitor_whitelist_entry')
    field._save_field_snapshot(b,source);digest=force._hash(source);original=source.read_bytes()
    r=search.discover(source,board_hint='synthetic',expected_source_sha256=digest)
    assert r['ok'] and r['complete'] and r['proposal'] and not r['release_authority']
    assert r['proposal']['source_sha256']==digest and r['selected_terminal']['return_mm']>1.5
    assert len(r['attempts'])<=200 and r['stopped_reason']=='first_source_guarded_proposal'
    child=entry.construct(r['proposal']);additive._ground_refill(child)
    candidate=force._copy_family(source,tmp_path/'searched-child');field._save_field_snapshot(child,candidate)
    proof=entry.receive(source,candidate,board_hint='synthetic',**r['plan_arguments'])
    assert proof['ok'] and proof['complete'] and proof['shortened_return_witness_mm']>0
    assert proof['every_source_native_partition_identical'] and proof['all_source_known_returns']['ok']
    assert source.read_bytes()==original and r['source_physical_items_unchanged']


def test_exact_finite_stencil_never_invents_raw_diagonals_or_exceeds_reach():
    origin=(12345678,-23456789)
    points=search.sites(origin)
    assert points[0]==origin and len(points)==25 and len(set(points))==25
    distances=[]
    for point in points:
        dx,dy=[point[i]-origin[i] for i in (0,1)]
        assert dx==0 or dy==0 or abs(dx)==abs(dy)
        distances.append(math.dist(origin,point))
    assert distances==sorted(distances) and max(distances)<=1500000
    assert search.sites(origin,offsets_nm=(1000000,),reach_mm=1.)==[
        origin,(origin[0]-1000000,origin[1]),(origin[0],origin[1]-1000000),
        (origin[0],origin[1]+1000000),(origin[0]+1000000,origin[1])]


@pytest.mark.parametrize('options',[dict(offsets_nm=()),dict(offsets_nm=(1,1)),
    dict(offsets_nm=(True,)),dict(offsets_nm=(1500001,)),dict(reach_mm=True),
    dict(reach_mm=0),dict(reach_mm=1.500001),dict(reach_mm=float('nan')),
    dict(at_nm=(1.,2)),dict(at_nm=(2000000001,0))])
def test_unbounded_or_untyped_sites_are_never_construction_authority(options):
    args=dict(at_nm=(0,0));args.update(options)
    with pytest.raises(ValueError):search.sites(**args)


@pytest.mark.parametrize('options',[dict(max_terminals=0),dict(max_terminals=True),
    dict(max_terminals=17),dict(max_attempts=0),dict(max_attempts=257),
    dict(timeout_s=True),dict(timeout_s=0),dict(timeout_s=121),
    dict(board_hint=''),dict(expected_source_sha256='0'*64)])
def test_unbounded_search_and_stale_source_are_refused_before_construction(tmp_path,options):
    b,source,pad,point=fixture(tmp_path,mode='vip',observed=True)
    args=dict(board_hint='synthetic',expected_source_sha256=force._hash(source));args.update(options)
    original=source.read_bytes()
    with pytest.raises(ValueError):search.discover(source,**args)
    assert source.read_bytes()==original


def test_unknown_source_return_is_not_an_infinite_return_or_an_open(tmp_path):
    b,source,pad,point=fixture(tmp_path,mode='dogbone',observed=False)
    r=search.discover(source,board_hint='synthetic',expected_source_sha256=force._hash(source))
    assert r['unknown_source_return_count']>0
    assert all(a['terminal']['return_mm'] is not None for a in r['attempts'])
    assert all(a['terminal']['pad_uuid']!=force._uid(pad) for a in r['attempts'])
    assert not r['global_shortest_or_no_path_proof'] and not r['fab_ready']


def test_exhausted_attempt_bound_is_a_receipt_not_an_unroutability_claim(tmp_path,monkeypatch):
    b,source,pad,point=fixture(tmp_path,mode='vip',observed=True)
    calls=[]
    def blocked(*args,**kwargs):
        calls.append(kwargs);raise ValueError('synthetic_obstructed_all_layer_site')
    monkeypatch.setattr(search.entry,'plan',blocked)
    r=search.discover(source,board_hint='synthetic',expected_source_sha256=force._hash(source),max_attempts=1)
    assert r['ok'] and r['complete'] and not r['proposal'] and len(calls)==1
    assert len(r['attempts'])==1 and 'synthetic_obstructed_all_layer_site' in r['attempts'][0]['refusal']
    assert not r['global_shortest_or_no_path_proof'] and not r['release_authority']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_readonly_preflight_uses_actual_saved_pofv_context_in_native_frames(tmp_path,angle,face):
    b,source,pad=local_rule_case(tmp_path,angle,face)
    _,_,geometry=entry._existing_pad_rule(b,pad);original=source.read_bytes()
    first=search._preflight(b,pad,tuple(pad.GetPosition()),geometry,foreign_cache={})
    assert first['ok'] and first['source_local_rule_sha256']
    assert first['positive_preflight_does_not_authorize_construction']
    assert source.read_bytes()==original


def test_readonly_preflight_records_exact_foreign_inner_copper_blocker_without_waiver(tmp_path):
    b,source,pad=local_rule_case(tmp_path)
    xy=[v/1e6 for v in pad.GetPosition()]
    blocker=track(b,'+3V3',(xy[0]-1,xy[1]),(xy[0]+1,xy[1]),layer=pcbnew.In2_Cu,width=.2)
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    pad=next(p for f in b.GetFootprints() for p in f.Pads() if p.GetNumber()=='1')
    _,_,geometry=entry._existing_pad_rule(b,pad);cache={};original=source.read_bytes()
    first=search._preflight(b,pad,tuple(pad.GetPosition()),geometry,foreign_cache=cache)
    again=search._preflight(b,pad,tuple(pad.GetPosition()),geometry,foreign_cache=cache)
    assert first==again and not first['ok'] and not first['via_clear']
    assert first['native_via_report']['layer']=='In2.Cu'
    assert any(v.get('uuid')==force._uid(blocker) for v in first['native_via_report']['blockers'])
    assert source.read_bytes()==original

"""Native, renamed, rotated fixed-port pair transactions and hostile deltas."""
import json
import math
import time
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_pair_fixed_port_shortening as worker
from cec_native_items import discard_items
from test_pair_axis_miter import fixture
from test_field_proposals import track
from test_lastmile import _board


def kernel_groups(source,retired):
    b=pcbnew.LoadBoard(str(source));groups={}
    for t in b.GetTracks():
        if force._uid(t) in retired:groups.setdefault((t.GetNetname(),int(t.GetLayer())),[]).append(force._uid(t))
    return [sorted(v) for _,v in sorted(groups.items())]


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',['F.Cu','B.Cu','In2.Cu'])
def test_saved_native_shortening_has_fixed_ports_and_all_original_pair_gates(tmp_path,angle,mirror,face):
    source,child,made=fixture(tmp_path,angle,mirror,signal_face=face)
    groups=kernel_groups(source,made['retired_track_uuids'])
    frozen=[p.read_bytes() for p in (source,child)]
    r=worker.receive_literal_phase(source,child,board_hint='synthetic',pair_name='CAN',kernel_track_uuids=groups)
    assert r['ok'] and r['complete'],r
    assert r['geometry_goal']=='fixed_port_shortening' and r['shortened_centerline_mm']>.02
    assert len(r['fixed_port_kernel_receipts'])==2
    assert all(q['visible_native_material_removal']['ok'] for q in r['fixed_port_kernel_receipts'])
    assert r['exact_native_pair_completion']['connected']
    assert all(q['comparison']['ok'] for q in r['whole_pair_physical_samples'])
    assert not r['pair_qualified'] and not r['release_authority']
    assert [p.read_bytes() for p in (source,child)]==frozen


def four_kernels(tmp_path,*,crossface=False,quarter=0):
    source,child,made=fixture(tmp_path)
    boards=[pcbnew.LoadBoard(str(p)) for p in (source,child)]
    groups=kernel_groups(source,made['retired_track_uuids'])
    net='/renamed/cell/CAN_L';additional=[]
    for b in boards:
        t=next(t for t in b.GetTracks() if t.GetNetname()==net
            and sorted([tuple(t.GetStart()),tuple(t.GetEnd())])==[(12000000,12450000),(15000000,12450000)])
        discard_items(b,[t])
    for x,z in (((12,12.45),(12.4,12.45)),((12.8,12.45),(13.4,12.45)),((13.8,12.45),(15,12.45))):
        t=track(boards[0],net,x,z,width=.25);copy=t.Duplicate()
        copy.m_Uuid.Clone(pcbnew.KIID(force._uid(t)));boards[1].Add(copy)
    for x in (12.4,13.4):
        first=track(boards[0],net,(x,12.45),(x+.2,12.65),width=.25)
        last=track(boards[0],net,(x+.2,12.65),(x+.4,12.45),width=.25)
        additional.append([force._uid(first),force._uid(last)])
        track(boards[1],net,(x,12.45),(x+.4,12.45),width=.25)
    for b,path in zip(boards,(source,child)):
        if crossface:
            for t in b.GetTracks():
                if t.GetNetname()==net:t.SetLayer(pcbnew.B_Cu)
        if quarter:
            for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings(),*b.Zones()]:
                item.Rotate(pcbnew.VECTOR2I_MM(11,11),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        additive._ground_refill(b);field._save_field_snapshot(b,path)
    return source,child,groups+additional


@pytest.mark.parametrize('crossface',[False,True])
@pytest.mark.parametrize('quarter',[0,1,2,3])
def test_four_disconnected_source_kernels_are_received_once_as_complete_pair(tmp_path,crossface,quarter):
    source,child,groups=four_kernels(tmp_path,crossface=crossface,quarter=quarter)
    r=worker.receive_literal_phase(source,child,board_hint='synthetic',pair_name='CAN',kernel_track_uuids=groups)
    assert r['ok'] and r['complete'],r
    assert len(r['fixed_port_kernel_receipts'])==4
    assert r['independent_continuous_coupling_comparison']['ok']
    assert all(q['after']['skew_mm']<=q['before']['skew_mm'] for q in r['whole_pair_physical_samples'])
    assert not r['pair_qualified'] and not r['release_authority']


@pytest.mark.parametrize('fault',['duplicate','missing','merged','too_many','empty','non_string','unknown_mode',
    'implicit_mode','mode_in_default','missing_incoming','thin','pose','sidecar','new_via','new_face','new_lock','non45'])
def test_source_kernel_or_saved_delta_cannot_borrow_authority(tmp_path,fault):
    source,child,made=fixture(tmp_path);groups=kernel_groups(source,made['retired_track_uuids'])
    b=pcbnew.LoadBoard(str(child));fresh=[t for t in b.GetTracks() if force._uid(t) in made['incoming_track_uuids']]
    options=dict(geometry_goal='fixed_port_shortening',kernel_track_uuids=groups)
    if fault=='duplicate':groups[0].append(groups[0][0])
    elif fault=='missing':groups[0].pop()
    elif fault=='merged':options['kernel_track_uuids']=[sum(groups,[])]
    elif fault=='too_many':options['kernel_track_uuids']=groups*3
    elif fault=='empty':options['kernel_track_uuids']=[]
    elif fault=='non_string':groups[0][0]=True
    elif fault=='unknown_mode':options['geometry_goal']=True
    elif fault=='implicit_mode':options.pop('kernel_track_uuids')
    elif fault=='mode_in_default':options['geometry_goal']='craft'
    elif fault=='missing_incoming':discard_items(b,[fresh[0]])
    elif fault=='thin':fresh[0].SetWidth(200000)
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='sidecar':child.with_suffix('.kicad_pro').write_text('{}')
    elif fault=='new_face':fresh[0].SetLayer(pcbnew.In2_Cu)
    elif fault=='new_lock':fresh[0].SetLocked(True)
    elif fault=='non45':fresh[0].SetEnd(fresh[0].GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='new_via':
        v=pcbnew.PCB_VIA(b);v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetPosition(pcbnew.VECTOR2I_MM(18,18))
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetNet(b.FindNet(fresh[0].GetNetname()));b.Add(v)
    if fault in ('missing_incoming','thin','pose','new_face','new_lock','non45'):
        field._save_field_snapshot(b,child)
    elif fault=='new_via':pcbnew.SaveBoard(str(child),b)
    frozen=source.read_bytes()
    r=worker.owner.receive_literal_phase(source,child,made['retired_track_uuids'],board_hint='synthetic',pair_name='CAN',**options)
    assert not r['ok'] and not r['complete'] and r['errors'],r
    assert source.read_bytes()==frozen and not r['release_authority']


def test_one_nm_source_corner_is_not_a_new_geometry_tolerance(tmp_path):
    source,child,made=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    # A literal inherited 1nm perturbation removes the exact-hard90 catalog
    # witness. Ports and ALL new strokes still have to be exact 0/45 geometry.
    for t in b.GetTracks():
        if force._uid(t) not in made['retired_track_uuids'] or not t.GetNetname().endswith('CAN_H'):continue
        if tuple(t.GetStart())==(10000000,12000000):t.SetStart(pcbnew.VECTOR2I(10000001,12000000))
        if tuple(t.GetEnd())==(10000000,12000000):t.SetEnd(pcbnew.VECTOR2I(10000001,12000000))
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    groups=kernel_groups(source,made['retired_track_uuids'])
    r=worker.receive_literal_phase(source,child,board_hint='synthetic',pair_name='CAN',kernel_track_uuids=groups)
    assert r['ok'] and r['complete'],r
    assert r['eligible_hard90_before_after']==[0,0]
    old=worker.owner.receive_literal_phase(source,child,made['retired_track_uuids'],board_hint='synthetic',pair_name='CAN')
    assert not old['ok'] and any('strict_actual_acute_or_hard90_pair_gain_required' in e for e in old['errors']),old


def test_shortening_is_not_permission_to_cross_a_native_reference_gap(tmp_path):
    source,child,made=fixture(tmp_path,reference_hole=True)
    r=worker.receive_literal_phase(source,child,board_hint='synthetic',pair_name='CAN',
        kernel_track_uuids=kernel_groups(source,made['retired_track_uuids']))
    assert not r['ok'] and not r['complete'],r
    assert any('new_native_unreferenced_pair_copper' in e for e in r['errors']),r


def test_shorter_member_only_cannot_gain_authority_to_worsen_pair_skew(tmp_path):
    source,child,made=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));target=pcbnew.LoadBoard(str(child))
    before={force._uid(t):t for t in b.GetTracks()};groups=kernel_groups(source,made['retired_track_uuids'])
    selected=next(ids for ids in groups if before[ids[0]].GetNetname().endswith('CAN_H'))
    discard_items(b,[before[u] for u in selected])
    for t in target.GetTracks():
        if force._uid(t) in made['incoming_track_uuids'] and t.GetNetname().endswith('CAN_H'):
            copy=t.Duplicate();copy.m_Uuid.Clone(pcbnew.KIID(force._uid(t)));b.Add(copy)
    dest=force._copy_family(source,tmp_path/'one-member-only');additive._ground_refill(b);field._save_field_snapshot(b,dest)
    r=worker.receive_literal_phase(source,dest,board_hint='synthetic',pair_name='CAN',kernel_track_uuids=[selected])
    assert not r['ok'] and not r['complete'],r
    assert any('skew_mm' in e or 'coupling_regression' in e for e in r['errors']),r


def test_private_constructor_and_typed_chain_rederive_every_saved_kernel(tmp_path):
    import cec_source_cut_chain as chain
    source,child,groups=four_kernels(tmp_path,crossface=True)
    parent,target=[pcbnew.LoadBoard(str(p)) for p in (source,child)]
    old={force._uid(t):t for t in parent.GetTracks()};new={force._uid(t):t for t in target.GetTracks()}
    matched=worker.owner._fixed_port_kernels([old[u] for row in groups for u in row],
        [new[u] for u in new.keys()-old.keys()],groups)
    requests=[dict(source_track_uuids=[force._uid(t) for t in before],
                   points_nm=[list(p) for p in worker.owner._chain(after)]) for before,after in matched]
    made=worker.construct(parent,source,board_hint='synthetic',pair_name='CAN',requests=requests)
    dest=force._copy_family(source,tmp_path/'constructed');additive._ground_refill(parent);field._save_field_snapshot(parent,dest)
    phase=dict(kind='paired_fixed_port_shortening',candidate=str(dest),pair_name='CAN',kernel_track_uuids=made['kernel_track_uuids'])
    r=chain.receive(source,dest,board_hint='synthetic',phases=[phase],timeout_s=10.,per_phase_leases=True)
    assert r['ok'] and r['complete'],r
    assert len(r['phase_receiving'][0]['proof']['fixed_port_kernel_receipts'])==4
    assert len(r['retired_track_uuids'])==9 and not r['retired_via_uuids']
    assert not r['release_authority']


@pytest.mark.parametrize('fault',['unknown','missing','coerced_lock','duplicate','unbounded'])
def test_pipeline_does_not_infer_an_ambiguous_source_kernel_mode(tmp_path,fault):
    import cec_source_cut_chain as chain
    source,child,made=fixture(tmp_path)
    phase=dict(kind='paired_fixed_port_shortening',candidate=str(child),pair_name='CAN',
        kernel_track_uuids=kernel_groups(source,made['retired_track_uuids']))
    if fault=='unknown':phase['skip_skew']=True
    elif fault=='missing':del phase['kernel_track_uuids']
    elif fault=='coerced_lock':phase['allow_locked_source']=1
    elif fault=='duplicate':phase['kernel_track_uuids']*=2
    elif fault=='unbounded':phase['kernel_track_uuids']*=3
    r=chain.receive(source,child,board_hint='synthetic',phases=[phase],timeout_s=10.,per_phase_leases=True)
    assert not r['ok'] and not r['complete'] and r['errors'] and not r['release_authority'],r


def test_hidden_under_pad_bookkeeping_cannot_credit_physical_shortening():
    b=_board([(11,11.5,'/P')],edge=(0,0,22,22))
    pad=next(iter(next(iter(b.GetFootprints())).Pads()));pad.SetSize(pcbnew.VECTOR2I_MM(8,8))
    old=[track(b,'/P',(10,10),(10,12),width=.25),track(b,'/P',(10,12),(12,12),width=.25)]
    new=old[0].Duplicate();new.SetStart(pcbnew.VECTOR2I_MM(10,10));new.SetEnd(pcbnew.VECTOR2I_MM(12,12))
    with pytest.raises(ValueError,match='actual_visible_pair_kernel_shortening_required'):
        worker.owner._visible_kernel_shortening(b,old,[new],[force._uid(t) for t in old],pcbnew.F_Cu,time.monotonic()+10.)


def test_actual_native_closed_circle_contact_witness_is_not_modified():
    b=_board([(11,11,'/P')],edge=(0,0,22,22))
    v=pcbnew.PCB_VIA(b);v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetPosition(pcbnew.VECTOR2I_MM(11,11))
    v.SetWidth(500000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(b.FindNet('/P'));b.Add(v)
    poly=pcbnew.SHAPE_POLY_SET();v.TransformShapeToPolygon(poly,pcbnew.F_Cu,0,1000,pcbnew.ERROR_OUTSIDE)
    frozen=worker.owner._reference_identity(poly,time.monotonic()+10.)
    r=worker.owner._literal_native_contact_polygon_identity(poly,time.monotonic()+10.)
    assert r['literal_closed_ring_endpoint_aliases']==1 and not r['native_polygon_modified']
    assert r['identity']==frozen==worker.owner._reference_identity(poly,time.monotonic()+10.)


def test_a_repeated_interior_contact_vertex_is_not_a_closing_alias():
    # A literal native chain with a nontrivial bridge is NOT a circle's
    # zero-length final closure and cannot authorize this narrow witness.
    ring=pcbnew.SHAPE_LINE_CHAIN();ring.SetClosed(True)
    for x,y in ((0,0),(1000000,0),(1000000,1000000),(500000,500000),(0,1000000),(500000,500000)):
        ring.Append(x,y)
    poly=pcbnew.SHAPE_POLY_SET();poly.AddOutline(ring)
    with pytest.raises(ValueError,match='unsupported_repeated_native_contact_polygon_vertex'):
        worker.owner._literal_native_contact_polygon_identity(poly,time.monotonic()+10.)


def test_discovery_is_source_derived_and_has_no_copper_authority(tmp_path):
    source,child,made=fixture(tmp_path,angle=90,mirror=True,signal_face='B.Cu')
    b=pcbnew.LoadBoard(str(source));frozen=field._field_snapshot_inventory(b)
    menu=worker.discover(b,source,board_hint='synthetic',pair_name='CAN')
    assert menu['ok'] and menu['complete'] and menu['offers']
    assert menu['geometry_only_not_retirement_authority'] and not menu['release_authority']
    assert field._field_snapshot_inventory(b)==frozen
    portfolios=worker.portfolios(menu,maximum=4)
    assert 1<=len(portfolios)<=4
    assert all(q in menu['offers'] for rows in portfolios for q in rows)
    for q in menu['offers']:
        assert q['source_points_nm'][0]==q['replacement_points_nm'][0]
        assert q['source_points_nm'][-1]==q['replacement_points_nm'][-1] and q['gain_mm']>.01


@pytest.mark.parametrize('budget',[True,0,-1,10.1,float('nan')])
def test_phase_receiving_lease_is_not_widened_or_coerced(tmp_path,budget):
    source,child,made=fixture(tmp_path)
    r=worker.receive_literal_phase(source,child,board_hint='synthetic',pair_name='CAN',
        kernel_track_uuids=kernel_groups(source,made['retired_track_uuids']),timeout_s=budget)
    assert not r['ok'] and not r['complete'] and r['errors'],r


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('odd',[0,1])
def test_small_tip_alternatives_keep_literal_odd_nm_ports_and_exact_new_angles(quarter,mirror,odd):
    def transform(p):
        x,y=p
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [x+10000000,y+10000000]
    old=[transform(p) for p in ((0,odd),(-215900,215900),(0,431800))]
    rows=worker.source_tip_bevels(old,250000)
    assert len(rows)==5
    for points in rows:
        assert points[0]==old[0] and points[-1]==old[-1]
        assert all(worker.quality.is_canonical_stroke(a,b,tolerance_nm=0) for a,b in zip(points,points[1:]))
        assert sum(math.dist(a,b) for a,b in zip(points,points[1:]))<sum(math.dist(a,b) for a,b in zip(old,old[1:]))


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_hairpin_shortening_keeps_both_native_boundary_tangents_and_exact_gain(quarter,mirror,reverse):
    def transform(p):
        x,y=p
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [x+10000000,y+10000000]
    old=[transform(p) for p in ((0,0),(3000000,0),(3200000,200000),
        (3200000,600000),(3000000,800000),(2200000,800000))]
    if reverse:old.reverse()
    frames=worker.source_hairpin_frames(old);assert len(frames)==1
    rows=worker.source_hairpin_paths(old,250000);assert 5<=len(rows)<=40
    for made in rows:
        assert made[0]==old[0] and made[-1]==old[-1]
        for index in (0,-2):
            a=[old[index+1][i]-old[index][i] for i in (0,1)]
            b=[made[index+1][i]-made[index][i] for i in (0,1)]
            assert a[0]*b[1]==a[1]*b[0] and sum(x*y for x,y in zip(a,b))>0
        assert all(worker.quality.is_canonical_stroke(a,b,tolerance_nm=0) for a,b in zip(made,made[1:]))
        shift=abs(made[1][frames[0]['axis']]-old[1][frames[0]['axis']])
        growth=abs(made[2][frames[0]['normal_axis']]-old[2][frames[0]['normal_axis']])
        shift-=growth
        gain=sum(math.dist(a,b) for a,b in zip(old,old[1:]))-sum(math.dist(a,b) for a,b in zip(made,made[1:]))
        assert math.isclose(gain,2*shift+(4-2*math.sqrt(2))*growth,abs_tol=1e-8)


def test_extended_hairpin_windows_do_not_reconstruct_unchanged_source_edges(tmp_path):
    source,child,made=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));net='/renamed/cell/CAN_H'
    points=[[3000000,4000000],[4000000,4000000],[8000000,4000000],[8200000,4200000],
        [8200000,4800000],[8000000,5000000],[6000000,5000000],[5000000,6000000]]
    rows=[track(b,net,[v/1e6 for v in a],[v/1e6 for v in z],width=.25) for a,z in zip(points,points[1:])]
    for t,a,z in zip(rows,points,points[1:]):
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z))
    candidate=worker.source_hairpin_paths(points,250000)[0]
    trimmed,old,new=worker._trim_unchanged_boundary_edges(rows,points,candidate)
    assert len(trimmed)==5 and len(old)==len(new)==6
    assert {force._uid(t) for t in trimmed}=={force._uid(t) for t in rows[1:-1]}
    assert tuple(old[0])<tuple(old[-1]) and old[0]==new[0] and old[-1]==new[-1]
    backward=worker._trim_unchanged_boundary_edges(rows,list(reversed(points)),list(reversed(candidate)))
    assert backward[1:]==(old,new)
    assert [force._uid(t) for t in backward[0]]==[force._uid(t) for t in trimmed]


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_source_derived_hairpin_compensation_is_length_matched_not_grid_guessed(quarter,mirror,reverse):
    from decimal import Decimal,localcontext
    def transform(p):
        x,y=p
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [x+10000000,y+10000000]
    old=[transform(p) for p in ((0,0),(2800000,0),(2950000,150000),
        (2950000,410000),(2800000,560000),(2000000,560000))]
    tip=[[-218799,218800],[0,0],[-218799,-218800]]
    if reverse:old.reverse()
    with localcontext() as context:
        context.prec=56
        target=3*(worker._path_length_nm(tip)-worker._path_length_nm([tip[0],tip[-1]]))
        coarse=worker.source_hairpin_paths(old,250000)
        rows=worker.source_hairpin_paths(old,250000,compensation_targets_nm=[target])
        matched=[p for p in rows if Decimal(0)<=worker._path_length_nm(old)-worker._path_length_nm(p)-target<Decimal(2)]
        assert len(matched)==3 and all(p not in coarse for p in matched)
        assert all(worker.source_hairpin_frames(p) for p in matched)
        assert all(worker.quality.is_canonical_stroke(a,b,tolerance_nm=0) for p in matched for a,b in zip(p,p[1:]))
    assert len(rows)<=49


@pytest.mark.parametrize('targets',[[True],[float('nan')],[0],['1'],[],[None]])
def test_hairpin_compensation_target_types_cannot_coerce_an_unsafe_length(targets):
    points=[[0,0],[3000000,0],[3200000,200000],[3200000,600000],[3000000,800000],[2200000,800000]]
    if not targets:assert worker.source_hairpin_paths(points,250000,compensation_targets_nm=targets)
    else:
        with pytest.raises(ValueError,match='bounded_actual_source_hairpin_targets_required'):
            worker.source_hairpin_paths(points,250000,compensation_targets_nm=targets)


def test_coherent_tip_groups_include_bevels_without_reusing_a_source_cut():
    offers=[]
    for number in range(3):
        old=[[0,number*1000000],[-200000,number*1000000+200000],[0,number*1000000+400000]]
        for path in [[old[0],old[-1]],*worker.source_tip_bevels(old,250000)]:
            gain=float(worker._path_length_nm(old)-worker._path_length_nm(path))/1e6
            offers.append(dict(net='/renamed/shorter',track_uuids=[str(number)+'a',str(number)+'b'],
                source_points_nm=old,replacement_points_nm=path,gain_mm=gain))
    groups=worker._shorter_tip_groups(list(reversed(offers)),'/renamed/shorter')
    assert len(groups)==6 and all(len(group)==3 for group in groups)
    assert all(len({u for q in group for u in q['track_uuids']})==6 for group in groups)
    assert all(len(q['replacement_points_nm'])==2 for q in groups[0])
    assert all(len(q['replacement_points_nm'])==4 for group in groups[1:] for q in group)


def test_private_shortcut_cannot_create_a_hard90_at_a_retained_source_port(tmp_path):
    source,child,made=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));net='/renamed/cell/CAN_H'
    track(b,net,(6,5),(7,5),width=.25)
    first=track(b,net,(7,5),(7.5,5.5),width=.25)
    last=track(b,net,(7.5,5.5),(7,6),width=.25)
    track(b,net,(7,6),(7,7),width=.25)
    additive._ground_refill(b);field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    with pytest.raises(ValueError,match='fixed_port_replacement_creates_source_boundary_hard90'):
        worker.construct(b,source,board_hint='synthetic',pair_name='CAN',requests=[dict(
            source_track_uuids=sorted([force._uid(first),force._uid(last)]),points_nm=[[7000000,5000000],[7000000,6000000]])])


def test_same_corner_count_does_not_hide_a_new_pair_member_face_or_port_corner():
    def catalog(net='/P',layer=0,at=(1,2)):
        return dict(inventory_complete=True,selected=[dict(net=net,layer=layer,at_nm=list(at))])
    old=catalog()
    assert not worker.owner.new_bend_sites(old,catalog())
    for changed in (catalog('/N'),catalog(layer=2),catalog(at=(1,3))):
        assert len(old['selected'])==len(changed['selected'])
        assert worker.owner.new_bend_sites(old,changed)

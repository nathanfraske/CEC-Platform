"""Unequal native corridors and bounded atomic whole-pair repair scopes."""
import copy
import math
from decimal import Decimal
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_pair_fixed_port_shortening as worker
from cec_native_items import discard_items
from test_pair_axis_miter import fixture
from test_pair_fixed_port_shortening import kernel_groups
from test_field_proposals import track


def transform(point,quarter,mirror):
    x,y=point
    if mirror:x=-x
    for _ in range(quarter):x,y=-y,x
    return [x+11000000,y+11000000]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_unequal_native_chamfers_keep_both_literal_ports_and_tangents(quarter,mirror,reverse):
    points=[[0,0],[2000000,0],[2350000,350000],[2350000,950000],[2175000,1125000],[1600000,1125000]]
    old=[transform(p,quarter,mirror) for p in points]
    if reverse:old.reverse()
    frames=worker.source_hairpin_frames(old)
    assert len(frames)==1 and {frames[0]['chamfer_nm'],frames[0]['end_chamfer_nm']}=={175000,350000}
    paths=worker.source_hairpin_paths(old,250000)
    assert paths and len(paths)<=40
    for path in paths:
        assert path[0]==old[0] and path[-1]==old[-1]
        assert worker._path_length_nm(path)<worker._path_length_nm(old)
        assert all(worker.quality.is_canonical_stroke(a,z,tolerance_nm=0) for a,z in zip(path,path[1:]))
        for i in (0,-2):
            a=[old[i+1][j]-old[i][j] for j in (0,1)];b=[path[i+1][j]-path[i][j] for j in (0,1)]
            assert a[0]*b[1]==a[1]*b[0] and sum(x*y for x,y in zip(a,b))>0


def menu(quarter=0,mirror=False,reverse=False):
    p,n='/unrelated/long','/unrelated/short'
    kernels=[]
    for net,points in ((p,[[0,0],[2000000,0],[2200000,200000],[2200000,600000],[2000000,800000],[1400000,800000]]),
            (n,[[0,-450000],[2400000,-450000],[2750000,-100000],[2750000,950000],[2575000,1125000],[2000000,1125000]])):
        points=[transform(q,quarter,mirror) for q in points]
        if reverse:points.reverse()
        kernels.append(dict(net=net,layer=int(pcbnew.B_Cu),track_uuids=[net+str(i) for i in range(5)],
            source_points_nm=points,allow_locked_track_uuids=[]))
    offers=[]
    for i in range(3):
        points=[transform(q,quarter,mirror) for q in [[5000000+i*1000000,3000000],
            [5200000+i*1000000,3200000],[5000000+i*1000000,3400000]]]
        if reverse:points.reverse()
        for path in [[points[0],points[-1]],*worker.source_tip_bevels(points,250000)]:
            offers.append(dict(net=n,layer=int(pcbnew.In2_Cu),track_uuids=[str(i)+'a',str(i)+'b'],
                source_points_nm=points,replacement_points_nm=path,
                gain_mm=float(worker._path_length_nm(points)-worker._path_length_nm(path))/1e6,
                allow_locked_track_uuids=[]))
    return dict(ok=True,complete=True,pair=dict(p=p,n=n,width=.25,gap=.2),offers=offers,
        source_hairpin_kernels=kernels,source_continuous_pair=dict(member_lengths_mm={p:30.,n:29.}))


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_both_member_proposals_compensate_separated_tips_without_inventing_authority(quarter,mirror,reverse):
    m=menu(quarter,mirror,reverse);frozen=copy.deepcopy(m)
    rows=worker.coupled_hairpin_portfolios(m)
    assert rows and len(rows)<=128 and m==frozen
    for offers in rows:
        assert len(offers)==5 and len(worker.kernel_schema([q['track_uuids'] for q in offers]))==16
        assert len({q['layer'] for q in offers})==2
        gain={net:sum((worker._path_length_nm(q['source_points_nm'])-worker._path_length_nm(q['replacement_points_nm'])
            for q in offers if q['net']==net),Decimal(0)) for net in (m['pair']['p'],m['pair']['n'])}
        assert Decimal(0)<=gain[m['pair']['p']]-gain[m['pair']['n']]<Decimal(2)
        for q in offers:
            old,new=q['source_points_nm'],q['replacement_points_nm']
            assert old[0]==new[0] and old[-1]==new[-1] and q['gain_mm']>.01
            assert all(worker.quality.is_canonical_stroke(a,z,tolerance_nm=0) for a,z in zip(new,new[1:]))
    assert any(len(q)==5 for q in worker.portfolios(m,maximum=8))


@pytest.mark.parametrize('fault',['complete','width','gap','length','layer','duplicate','non_frame','oversize','boolean_max'])
def test_coupled_source_menu_cannot_coerce_or_forge_a_frame(fault):
    m=menu();maximum=128
    if fault=='complete':m['complete']=1
    elif fault=='width':m['pair']['width']=True
    elif fault=='gap':m['pair']['gap']=float('nan')
    elif fault=='length':m['source_continuous_pair']['member_lengths_mm'][m['pair']['p']]=float('inf')
    elif fault=='layer':m['source_hairpin_kernels'][0]['layer']=True
    elif fault=='duplicate':m['source_hairpin_kernels'][0]['track_uuids']*=2
    elif fault=='non_frame':m['source_hairpin_kernels'][0]['source_points_nm'][2][0]+=1
    elif fault=='oversize':m['source_hairpin_kernels']*=33
    elif fault=='boolean_max':maximum=True
    with pytest.raises(ValueError):worker.coupled_hairpin_portfolios(m,maximum=maximum)


def multi_kernel_fixture(tmp_path,*,tip_count=4,crossface=False,quarter=0,near_terminal_reference=False):
    source,child,made=fixture(tmp_path);boards=[pcbnew.LoadBoard(str(p)) for p in (source,child)]
    groups=kernel_groups(source,made['retired_track_uuids']);net='/renamed/cell/CAN_L'
    for b in boards:
        old=next(t for t in b.GetTracks() if t.GetNetname()==net
            and sorted([tuple(t.GetStart()),tuple(t.GetEnd())])==[(12000000,12450000),(15000000,12450000)])
        discard_items(b,[old])
    cursor=12.
    for i in range(tip_count):
        # Keep the final chord outside the unchanged terminal PTH's genuine
        # reference antipad. The four-tip variant otherwise introduces a
        # new 25 um reference deficit, correctly rejected by the receiver.
        start=(12.2 if near_terminal_reference else 12.1)+i*.6;end=start+.4
        t=track(boards[0],net,(cursor,12.45),(start,12.45),width=.25)
        twin=t.Duplicate();twin.m_Uuid.Clone(pcbnew.KIID(force._uid(t)));boards[1].Add(twin)
        a=track(boards[0],net,(start,12.45),(start+.2,12.65),width=.25)
        z=track(boards[0],net,(start+.2,12.65),(end,12.45),width=.25)
        groups.append([force._uid(a),force._uid(z)])
        track(boards[1],net,(start,12.45),(end,12.45),width=.25);cursor=end
    t=track(boards[0],net,(cursor,12.45),(15,12.45),width=.25)
    twin=t.Duplicate();twin.m_Uuid.Clone(pcbnew.KIID(force._uid(t)));boards[1].Add(twin)
    for b,path in zip(boards,(source,child)):
        if crossface:
            for t in b.GetTracks():
                if t.GetNetname()==net:t.SetLayer(pcbnew.B_Cu)
        if quarter:
            for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings(),*b.Zones()]:
                item.Rotate(pcbnew.VECTOR2I_MM(11,11),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        additive._ground_refill(b);field._save_field_snapshot(b,path)
    return source,child,groups


@pytest.mark.parametrize('tip_count',[3,4])
@pytest.mark.parametrize('crossface',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_five_and_six_native_kernels_keep_every_existing_whole_pair_gate(tmp_path,tip_count,crossface,quarter):
    source,child,groups=multi_kernel_fixture(tmp_path,tip_count=tip_count,crossface=crossface,quarter=quarter)
    frozen=[p.read_bytes() for p in (source,child)]
    r=worker.receive_literal_phase(source,child,board_hint='synthetic',pair_name='CAN',kernel_track_uuids=groups)
    assert r['ok'] and r['complete'],r
    assert len(r['fixed_port_kernel_receipts'])==2+tip_count and r['exact_native_pair_completion']['connected']
    assert r['independent_continuous_coupling_comparison']['ok']
    assert all(q['comparison']['ok'] for q in r['whole_pair_physical_samples'])
    assert [p.read_bytes() for p in (source,child)]==frozen and not r['release_authority']


def test_constructor_and_typed_chain_receive_six_native_kernels(tmp_path):
    import cec_source_cut_chain as chain
    source,child,groups=multi_kernel_fixture(tmp_path,crossface=True)
    parent,target=[pcbnew.LoadBoard(str(p)) for p in (source,child)]
    old={force._uid(t):t for t in parent.GetTracks()};new={force._uid(t):t for t in target.GetTracks()}
    matched=worker.owner._fixed_port_kernels([old[u] for row in groups for u in row],
        [new[u] for u in new.keys()-old.keys()],groups)
    requests=[dict(source_track_uuids=[force._uid(t) for t in before],points_nm=[list(p) for p in worker.owner._chain(after)])
        for before,after in matched]
    made=worker.construct(parent,source,board_hint='synthetic',pair_name='CAN',requests=requests)
    dest=force._copy_family(source,tmp_path/'constructed');additive._ground_refill(parent);field._save_field_snapshot(parent,dest)
    phase=dict(kind='paired_fixed_port_shortening',candidate=str(dest),pair_name='CAN',kernel_track_uuids=made['kernel_track_uuids'])
    r=chain.receive(source,dest,board_hint='synthetic',phases=[phase],timeout_s=10.,per_phase_leases=True)
    assert r['ok'] and r['complete'],r
    assert len(r['phase_receiving'][0]['proof']['fixed_port_kernel_receipts'])==6 and not r['release_authority']


def test_kernel_count_extension_does_not_expand_total_source_or_new_copper_bounds():
    with pytest.raises(ValueError):worker.kernel_schema([[str(i)+'a',str(i)+'b'] for i in range(7)])
    with pytest.raises(ValueError):worker.kernel_schema([[str(i)+str(j) for j in range(5)] for i in range(6)])
    assert len(worker.kernel_schema([[str(i)+'a',str(i)+'b'] for i in range(6)]))==12


def test_six_kernel_scope_cannot_borrow_a_real_terminal_reference_antipad(tmp_path):
    source,child,groups=multi_kernel_fixture(tmp_path,near_terminal_reference=True)
    r=worker.receive_literal_phase(source,child,board_hint='synthetic',pair_name='CAN',kernel_track_uuids=groups)
    assert not r['ok'] and any('new_native_unreferenced_pair_copper' in e for e in r['errors']),r


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_single_shoulder_growth_preserves_the_other_native_end_exactly(quarter,mirror,reverse):
    m=menu(quarter,mirror,reverse);old=m['source_hairpin_kernels'][0]['source_points_nm'];target=Decimal(35000)
    paths=worker.source_hairpin_end_growth_paths(old,250000,compensation_targets_nm=[target])
    assert len(paths)==2
    for path in paths:
        assert path[0]==old[0] and path[-1]==old[-1]
        assert (path[1:3]==old[1:3]) != (path[3:5]==old[3:5])
        gain=worker._path_length_nm(old)-worker._path_length_nm(path)
        assert Decimal(0)<=gain-target<Decimal(1)
        assert all(worker.quality.is_canonical_stroke(x,z,tolerance_nm=0) for x,z in zip(path,path[1:]))


@pytest.mark.parametrize('targets',[[True],[float('nan')],[0],['1'],[None],[Decimal(30000001)]])
def test_single_shoulder_cannot_coerce_nonphysical_compensation(targets):
    old=menu()['source_hairpin_kernels'][0]['source_points_nm']
    with pytest.raises(ValueError):worker.source_hairpin_end_growth_paths(old,250000,compensation_targets_nm=targets)


@pytest.mark.parametrize('maximum',[True,0,257,float('nan')])
def test_tip_portfolio_is_finite_and_type_strict(maximum):
    with pytest.raises(ValueError):worker.tip_compensation_portfolios(menu(),maximum=maximum)


def test_default_portfolio_keeps_tip_and_both_member_repair_queues_alive():
    m=menu();h=m['source_hairpin_kernels'][0];target=Decimal(35000)
    for path in worker.source_hairpin_end_growth_paths(h['source_points_nm'],250000,compensation_targets_nm=[target]):
        m['offers'].append(dict(h,replacement_points_nm=path,
            gain_mm=float(worker._path_length_nm(h['source_points_nm'])-worker._path_length_nm(path))/1e6))
    compensated=worker.tip_compensation_portfolios(m);coupled=worker.coupled_hairpin_portfolios(m)
    assert compensated and coupled
    rows=worker.portfolios(m,maximum=64)
    assert rows[0]==compensated[0] and rows[1]==coupled[0]
    assert any(len(row)==5 for row in rows) and any(len(row)==1 for row in rows)

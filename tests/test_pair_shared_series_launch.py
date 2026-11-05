"""Future series-cell access uses live geometry, never a board-specific nudge."""
import math
from unittest.mock import patch

import pcbnew
import pytest
import cec_precision_route as route
import cec_local_copper_cell as cell


def fixture(angle=0., offset=(0.,0.), prefix='SUP', back=False, directions=None):
    board=pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    current=dict(name='BEFORE',p='DATA_A',n='DATA_B',width=.2,gap=.2,clearance=.2)
    future=dict(name='AFTER',p='OTHER_A',n='OTHER_B',width=.2,gap=.2,clearance=.2)
    for name in ('DATA_A','DATA_B','OTHER_A','OTHER_B','BLOCKER'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    theta=math.radians(angle);c,s=math.cos(theta),math.sin(theta)
    def transform(point):
        x,y=point
        return (15+offset[0]+c*x-s*y,15+offset[1]+s*x+c*y)
    station=dict(kind='split-member-footprints',physical_refs=[],center=None)
    pads=[]
    for i,member in enumerate(('p','n')):
        fp=pcbnew.FOOTPRINT(board);ref=prefix+str(i+1);fp.SetReference(ref)
        layer=pcbnew.B_Cu if back else pcbnew.F_Cu
        fp.SetLayer(layer)
        direction=(directions or ((1.,0.),(1.,0.)))[i]
        dst=(1.2, i*2.0)
        src=(dst[0]-direction[0]*1.2,dst[1]-direction[1]*1.2)
        members=[]
        for number,point,net in ((1,src,current[member]),(2,dst,future[member])):
            pad=pcbnew.PAD(fp);pad.SetNumber(str(number));pad.SetPosition(pcbnew.VECTOR2I_MM(*transform(point)))
            pad.SetSize(pcbnew.VECTOR2I_MM(.6,.65));pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            mask=pcbnew.LSET();mask.AddLayer(layer);pad.SetLayerSet(mask)
            pad.SetOrientationDegrees(angle);pad.SetNetCode(board.GetNetcodeFromNetname(net))
            fp.Add(pad);members.append(pad)
        board.Add(fp);pads.append(members)
        station['physical_refs'].append(ref)
        dst=members[1].GetPosition()
        station[member+'_contacts']=[dict(ref=ref,pad='2',point_mm=[dst.x/1e6,dst.y/1e6])]
    points=[station[m+'_contacts'][0]['point_mm'] for m in ('p','n')]
    station['center']=[sum(p[i] for p in points)/2 for i in (0,1)]
    for a,b in (((0,0),(80,0)),((80,0),(80,80)),((80,80),(0,80)),((0,80),(0,0))):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    return board,current,future,station,pads


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('offset,prefix', [((0,0),'SUP'),((22,19),'RANDOM')])
def test_native_outward_reservations_rotate_translate_and_rename(angle,offset,prefix):
    board,current,future,station,pads=fixture(angle,offset,prefix)
    before=cell.copper_inventory(board)
    report=route._shared_series_launch_contract(board,current,future,station)
    assert report['ok'],report
    assert len(report['reservations'])==2
    for member in report['members']:
        assert route._crosses_avoid((member['start_mm'],member['finish_mm']),
            route._avoid_for_layer(report['reservations'],member['layer']),current['width'])
    for a,b in pads:
        point=(a.GetPosition().x/1e6,a.GetPosition().y/1e6)
        assert not route._crosses_avoid((point,point),
            route._avoid_for_layer(report['reservations'],'F.Cu'),current['width'])
    assert before==cell.copper_inventory(board)


def test_independent_orthogonal_member_rotations_and_back_layer():
    board,current,future,station,_=fixture(back=True,directions=((1,0),(0,-1)))
    report=route._shared_series_launch_contract(board,current,future,station)
    assert report['ok'],report
    assert {r[5] for r in report['reservations']}=={'B.Cu'}
    assert not route._avoid_for_layer(report['reservations'],'F.Cu')
    assert report['members'][0]['start_mm'][1]==report['members'][0]['finish_mm'][1]
    assert report['members'][1]['start_mm'][0]==report['members'][1]['finish_mm'][0]


@pytest.mark.parametrize('case',['extra_pad','wrong_net','npth','stale_point','duplicate_ref','same_contact','foreign_track','reserved_power','non_octilinear'])
def test_unproven_launch_never_becomes_a_contract(case):
    board,current,future,station,pads=fixture(angle=17 if case=='non_octilinear' else 0)
    avoid=()
    if case=='extra_pad':pads[0][0].GetParentFootprint().Add(pcbnew.PAD(pads[0][0].GetParentFootprint()))
    elif case=='wrong_net':pads[0][1].SetNetCode(board.GetNetcodeFromNetname('BLOCKER'))
    elif case=='npth':pads[1][1].SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    elif case=='stale_point':station['p_contacts'][0]['point_mm'][0]+=.001
    elif case=='duplicate_ref':
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(station['physical_refs'][0]);board.Add(fp)
    elif case=='same_contact':station['n_contacts']=station['p_contacts']
    elif case=='reserved_power':avoid=((16.5,14,17.5,18,'locked_power','F.Cu'),)
    elif case=='foreign_track':
        track=pcbnew.PCB_TRACK(board);track.SetStart(pcbnew.VECTOR2I_MM(16.8,14))
        track.SetEnd(pcbnew.VECTOR2I_MM(16.8,16));track.SetWidth(pcbnew.FromMM(.2))
        track.SetLayer(pcbnew.F_Cu);track.SetNetCode(board.GetNetcodeFromNetname('BLOCKER'));board.Add(track)
    before=cell.copper_inventory(board)
    report=route._shared_series_launch_contract(board,current,future,station,avoid=avoid)
    assert not report['ok'],report
    assert report['reason'] and not report['reservations']
    assert before==cell.copper_inventory(board)


def test_prospective_member_segments_cannot_cross():
    board,current,future,station,_=fixture(directions=((0,1),(0,-1)))
    report=route._shared_series_launch_contract(board,current,future,station)
    assert not report['ok'] and report['reason']=='prospective member escapes conflict'


@pytest.mark.parametrize('angle',[45,135,225,315])
def test_rotated_aabb_cannot_obstruct_current_lands(angle):
    board,current,future,station,pads=fixture(angle=angle)
    report=route._shared_series_launch_contract(board,current,future,station)
    if report['ok']:
        for a,b in pads:
            point=(a.GetPosition().x/1e6,a.GetPosition().y/1e6)
            assert not route._crosses_avoid((point,point),
                route._avoid_for_layer(report['reservations'],'F.Cu'),.2)
    else:
        assert report['reason'] in {'rectangular projection would obstruct a current launch','native outward escape is obstructed'}
        assert not report['reservations']


def test_compiler_replaces_only_actual_shared_endpoint_even_for_short_leg():
    board,current,future,station,_=fixture()
    pa,na=[tuple(station[m+'_contacts'][0]['point_mm']) for m in ('p','n')]
    # Both historical broad boxes contain the shared centre. Only source is shared.
    ends=(pa,(pa[0]+2,pa[1]),na,(na[0]+2,na[1]))
    diagnostics={}
    with patch.object(route,'_flow_through_pair_legs',return_value=([ends],[])), \
            patch.object(route,'_shared_split_support_centers',return_value=(tuple(station['center']),)), \
            patch.object(route,'_pair_endpoint_stations',return_value=[station]):
        rows=route._future_pair_launch_reservations(board,[future],current_pair=current,diagnostics=diagnostics)
    assert len(rows)==3
    assert sum(row[4].endswith(':target') for row in rows)==1
    assert diagnostics['suppressed_shared_support_count']==1
    assert diagnostics['shared_series_contracts'][0]['ok']


@pytest.mark.parametrize('reach',[0,-1,math.inf,math.nan,3.7])
def test_policy_is_finite_and_bounded(reach):
    board,current,future,station,_=fixture()
    with pytest.raises(ValueError):route._shared_series_launch_contract(board,current,future,station,launch_mm=reach)


def test_launch_diagnostics_survive_both_projection_boundaries():
    import json
    import cec_probe_evidence as evidence
    import cec_route_preflight as preflight
    board,current,future,station,_=fixture()
    contract=route._shared_series_launch_contract(board,current,future,station)
    contract.update(future_pair=future['name'],reservation='shared-native-test')
    schedule=[dict(name=current['name'],future_launch_reservation_policy=dict(shared_series_contracts=[contract]))]
    full=dict(pairs_ok=False,kelvin={},route_quality={},pairs=dict(schedule=schedule,
        routed=[dict(name=current['name'],p=current['p'],n=current['n'])],
        refused=[dict(name=future['name'],p=future['p'],n=future['n'],refused='unrelated remote blocker')]))
    with patch.object(route,'precision_route_board',return_value=full), \
            patch.object(route.cec_fr,'owned_locked_nets',return_value=set()):
        compact=preflight._probe_critical_pairs_on_board(board,'synthetic')
    final=preflight.compact_placement_evidence(json.loads(json.dumps(dict(critical_routes=compact))))
    assert final['critical_pair_launch_contracts']==evidence.compact_pair_launch_contracts(schedule)
    assert final['critical_pair_launch_contracts']['contracts'][0]['current_pair']==current['name']
    assert final['critical_pair_refused_count']==1
    assert final['critical_route_refused_count']==1


def test_launch_diagnostics_are_bounded_and_do_not_duplicate_raw_rectangles():
    import cec_probe_evidence as evidence
    contract=dict(ok=True,reason=None,members=[dict(pad_uuid=str(i)) for i in range(100)],
                  reservations=[(1,2,3,4,'large','F.Cu')]*100)
    report=evidence.compact_pair_launch_contracts([dict(name='EARLIER',future_launch_reservation_policy=dict(
        shared_series_contracts=[contract]*100))],limit=3)
    assert report['count']==100 and report['truncated'] and len(report['contracts'])==3
    assert all(len(row['members'])==2 and 'reservations' not in row and row['reservation_count']==100
               for row in report['contracts'])


def test_empty_diagnostics_do_not_change_legacy_control_projection():
    import cec_route_preflight as preflight
    report=preflight.compact_placement_evidence(dict(critical_routes={}))
    assert 'critical_pair_launch_contracts' not in report

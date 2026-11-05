"""Explicit source-width proposals do not become routing/current authority."""
import math
import time

import pcbnew
import pytest
from shapely import affinity
from shapely.geometry import box, MultiPolygon, Polygon

import cec_cell_row_rebuild as cells
import cec_crossface_bus_frontier as frontier
from test_native_layered_via_guard import fixture


def graph_fixture(rotation=0, mirror=False):
    def move(shape):
        if mirror: shape = affinity.scale(shape, -1, 1, origin=(0,0))
        return affinity.rotate(shape, rotation, origin=(0,0))
    def point(x,y):
        shape=move(box(x-.01,y-.01,x+.01,y+.01));p=shape.centroid
        return float(p.x),float(p.y)
    faces={0:move(MultiPolygon([box(0,0,4,4),box(8,0,12,4)])),2:move(box(0,0,12,4))}
    regions=move(MultiPolygon([box(1,1,2,2),box(9,1,10,2)]))
    return dict(faces=faces, source_points={0:point(.5,.5)},target_points={0:point(11,3)},
                transitions=regions,native_transition_clear=lambda at:True)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_complete_crossface_chain_is_only_a_native_screened_proposal(rotation,mirror):
    r=frontier.component_graph(**graph_fixture(rotation,mirror))
    assert r['proposed_face_path_found'] and len(r['proposed_transitions'])==2
    assert r['native_checked_count']==2
    assert not r['proposal_budget_exhausted']
    assert not any(r[k] for k in ('no_path_proof','native_planar_legs_received',
        'current_sharing_inferred','barrel_ampacity_qualified','routing_admitted','release_authority'))


@pytest.mark.parametrize('answer',[False,None,0,1,{'ok':False},{'ok':True}])
def test_native_callback_must_return_positive_boolean_not_truthy_metadata(answer):
    args=graph_fixture();args['native_transition_clear']=lambda at:answer
    r=frontier.component_graph(**args)
    assert not r['proposed_face_path_found'] and not r['native_checked_transition_centres']
    assert r['closest_unjoined_same_face_component_proposals']
    assert not r['no_path_proof']


def test_query_budget_never_becomes_no_path_authority():
    r=frontier.component_graph(**graph_fixture(),maximum_transitions=1)
    assert r['proposal_budget_exhausted'] and not r['proposed_face_path_found']
    assert not r['no_path_proof']


def test_deadline_never_calls_native_callback_or_grants_no_path():
    args=graph_fixture();args['native_transition_clear']=lambda at:pytest.fail('expired callback')
    r=frontier.component_graph(**args,deadline=time.monotonic()-1)
    assert r['proposal_budget_exhausted'] and r['native_checked_count']==0
    assert not r['no_path_proof']


@pytest.mark.parametrize('fault',['source_face','missing_source','bool_point','nan_point','budget',
    'outside_transition','self_crossing_polygon'])
def test_ambiguous_and_unbounded_geometry_refuses(fault):
    args=graph_fixture()
    if fault=='source_face': args['source_points']={6:(1,1)}
    elif fault=='missing_source': args['source_points']={}
    elif fault=='bool_point': args['source_points']={0:(True,1)}
    elif fault=='nan_point': args['source_points']={0:(math.nan,1)}
    elif fault=='budget': args['maximum_transitions']=257
    elif fault=='outside_transition': args['transitions']=box(20,20,21,21)
    elif fault=='self_crossing_polygon': args['faces'][0]=Polygon([(0,0),(2,2),(2,0),(0,2)])
    with pytest.raises(ValueError):frontier.component_graph(**args)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_native_real_all_face_padstack_snapshot_preserves_source(rotation,mirror):
    b,v=fixture(rotation)
    if mirror:
        for t in [v,*b.GetTracks()]:
            if t.GetClass()=='PCB_VIA':
                x,y=tuple(t.GetPosition());t.SetPosition(pcbnew.VECTOR2I(25000000-x,y))
            else:
                sx,sy=tuple(t.GetStart());ex,ey=tuple(t.GetEnd())
                t.SetStart(pcbnew.VECTOR2I(25000000-sx,sy));t.SetEnd(pcbnew.VECTOR2I(25000000-ex,ey))
    binding=cells._source_binding(b);pose=tuple(v.GetPosition())
    r,faces,regions=frontier.native_frontier(b,net_code=v.GetNetCode(),
        widths_nm={int(pcbnew.F_Cu):3300000,int(pcbnew.B_Cu):3300000},clearance_nm=200000,via=v,
        source_points_nm={int(pcbnew.F_Cu):(3000000,3000000)},
        target_points_nm={int(pcbnew.F_Cu):(22000000,22000000)},timeout_s=5.)
    assert r['proposed_face_path_found']
    assert len(r['native_obstacle_inventory'])==6
    assert sorted(row['native_land_diameter_nm'] for row in r['native_obstacle_inventory'])==[600000]*4+[3600000]*2
    assert len(faces)==2 and not regions.is_empty
    assert cells._source_binding(b)==binding and tuple(v.GetPosition())==pose
    assert not r['routing_admitted'] and not r['barrel_ampacity_qualified']


@pytest.mark.parametrize('fault',['live_via','wrong_net','inner_floor','blind','width','timeout'])
def test_native_source_and_factory_floors_cannot_be_bypassed(fault):
    b,v=fixture();args=dict(net_code=v.GetNetCode(),widths_nm={int(pcbnew.F_Cu):3300000,
        int(pcbnew.B_Cu):3300000},clearance_nm=200000,via=v,
        source_points_nm={int(pcbnew.F_Cu):(3000000,3000000)},
        target_points_nm={int(pcbnew.F_Cu):(22000000,22000000)},timeout_s=5.)
    if fault=='live_via':b.Add(v)
    elif fault=='wrong_net':args['net_code']=0
    elif fault=='inner_floor':b.GetDesignSettings().m_ViasMinSize=700000
    elif fault=='blind':v.SetViaType(pcbnew.VIATYPE_BLIND)
    elif fault=='width':args['widths_nm'][int(pcbnew.F_Cu)]=False
    elif fault=='timeout':args['timeout_s']=11
    with pytest.raises(ValueError):frontier.native_frontier(b,**args)

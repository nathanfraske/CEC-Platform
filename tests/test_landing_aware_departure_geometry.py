"""Whole-path source lead search does not inherit an arbitrary first-edge cap."""
import math
import pytest
import cec_landing_aware_route_geometry as geometry

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_exit_heading_and_both_fixed_ports_survive_whole_path_search(quarter,mirror):
    def transform(p):
        x,y=p
        for _ in range(quarter):x,y=-y,x
        if mirror:x=-x
        return [x,y]
    original=list(map(transform,[[0,287598],[0,0],[4500000,0],[4700000,-200000],[4700000,-1024901]]))
    start=original[0];exit=transform([0,62600]);direction=transform([0,-1])
    row=dict(departure_start_mm=[v/1e6 for v in start],contact_exit_mm=[v/1e6 for v in exit],inward_direction=direction)
    paths=geometry.source_departure_paths(original,row,250000)
    assert paths
    for path in paths:
        assert path[0]==original[0] and path[-1]==original[-1]
        geometry.capacity.geometry._points(path)
        before=sum(math.dist(a,z) for a,z in zip(original,original[1:]))
        assert sum(math.dist(a,z) for a,z in zip(path,path[1:]))+10000<before
        lead=path[1];delta=[lead[i]-start[i] for i in (0,1)]
        assert delta[0]*direction[1]-delta[1]*direction[0]==0
        assert math.dist(start,lead)>math.dist(original[0],original[1])
    assert geometry.source_departure_paths(list(reversed(original)),row,250000)==[list(reversed(p)) for p in paths]

@pytest.mark.parametrize('fault',['boolean_width','diagonal_heading','moved_port','transverse_exit','backward_exit'])
def test_unbound_or_non_cardinal_source_witness_cannot_fund_a_lead(fault):
    points=[[0,287598],[0,0],[4500000,0],[4700000,-200000],[4700000,-1024901]]
    row=dict(departure_start_mm=[0,.287598],contact_exit_mm=[0,.0626],inward_direction=[0,-1]);width=250000
    if fault=='boolean_width':width=True
    elif fault=='diagonal_heading':row['inward_direction']=[1,-1]
    elif fault=='moved_port':row['departure_start_mm'][0]=.1
    elif fault=='transverse_exit':row['contact_exit_mm'][0]=.1
    elif fault=='backward_exit':row['inward_direction']=[0,1]
    with pytest.raises(ValueError):geometry.source_departure_paths(points,row,width)

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_local_miter_retains_actual_exit_before_first_bend(quarter,mirror):
    def transform(p):
        x,y=p
        for _ in range(quarter):x,y=-y,x
        return [-x if mirror else x,y]
    original=list(map(transform,[[0,287598],[0,0],[4500000,0]]))
    start=original[0];exit=transform([0,62600]);direction=transform([0,-1])
    row=dict(departure_start_mm=[v/1e6 for v in start],contact_exit_mm=[v/1e6 for v in exit],inward_direction=direction)
    paths=geometry.source_exit_corner_paths(original,row,250000)
    assert len(paths)==2
    for path in paths:
        assert path[0]==original[0] and path[-1]==original[-1] and len(path)==4
        geometry.capacity.geometry._points(path)
        delta=[path[1][i]-start[i] for i in (0,1)]
        assert delta[0]*direction[1]-delta[1]*direction[0]==0
        assert sum(delta[i]*direction[i] for i in (0,1))>math.dist(start,exit)
        assert sum(math.dist(a,z) for a,z in zip(path,path[1:]))+10000<=4787598
    assert geometry.source_exit_corner_paths(list(reversed(original)),row,250000)==[list(reversed(p)) for p in paths]

@pytest.mark.parametrize('fault',['boolean_width','crosswise_heading','exit_after_corner','exit_not_on_line','not_right_angle'])
def test_local_miter_cannot_spend_source_exit_or_unbound_geometry(fault):
    points=[[0,287598],[0,0],[4500000,0]]
    row=dict(departure_start_mm=[0,.287598],contact_exit_mm=[0,.0626],inward_direction=[0,-1]);width=250000
    if fault=='boolean_width':width=True
    elif fault=='crosswise_heading':row.update(contact_exit_mm=[.05,.287598],inward_direction=[1,0])
    elif fault=='exit_after_corner':row['contact_exit_mm']=[0,-.1]
    elif fault=='exit_not_on_line':row['contact_exit_mm']=[.1,.0626]
    elif fault=='not_right_angle':points[-1][1]=1
    with pytest.raises(ValueError):geometry.source_exit_corner_paths(points,row,width)

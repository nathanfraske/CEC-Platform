import copy
import pytest
import cec_native_route_walk as walk


def validate(ops,**kwargs):
    args=dict(start=[0,0],end=[2000000,0],faces=[0,2],start_layers=[0],end_layers=[0],width_nm=200000)
    args.update(kwargs);return walk.validate(ops,**args)


def test_direct_source_face_walk_is_unchanged():
    r=validate([('trk',[0,0],[2000000,0],200000,0)])
    assert r['ok'] and r['via_count']==0 and not r['release_authority']


def test_endpoint_barrels_are_real_transitions_not_first_track_face_guesses():
    r=validate([('via',[0,0],.3,.6),('trk',[0,0],[2000000,0],200000,2),('via',[2000000,0],.3,.6)])
    assert r['starts_with_via'] and r['ends_with_via'] and r['via_count']==2
    assert not r['geometry_clearance_or_current_qualified']


@pytest.mark.parametrize('faces,first,last',[([0,2],0,2),([2,0],2,0),([0,6],0,6)])
def test_endpoint_transition_follows_declared_faces_not_board_or_layer_names(faces,first,last):
    ops=[('via',[0,0],.25,.5),('trk',[0,0],[2000000,0],200000,last)]
    assert validate(ops,faces=faces,start_layers=[first],end_layers=[last])['ok']


@pytest.mark.parametrize('bad',[
    [('trk',[0,0],[2000000,0],200000,2)],
    [('via',[0,0],.3,.6),('trk',[0,0],[2000000,0],200000,0)],
    [('via',[1,0],.3,.6),('trk',[0,0],[2000000,0],200000,2)],
    [('via',[0,0],.6,.3),('trk',[0,0],[2000000,0],200000,2)],
    [('via',[0,0],.3,.6),('via',[0,0],.3,.6),('trk',[0,0],[2000000,0],200000,0)],
    [('trk',[0,0],[2000000,0],100000,0)],
    [('trk',[1000,0],[2000000,0],200000,0)],
    [('trk',[0,0],[2000000,1000],200000,0)],
    [('trk',[0,0],[0,0],200000,0)],
    [('trk',[0,0],[1000000,0],200000,0)],
    [('via',[0,0],.3,.6)],
    [('invented',[0,0],[2000000,0],200000,0)],
])
def test_floating_wrong_face_dangling_or_noncanonical_walks_refuse(bad):
    with pytest.raises(ValueError):validate(bad)


@pytest.mark.parametrize('kwargs',[dict(width_nm=True),dict(faces=[0,0]),dict(faces=[0]),
    dict(start=[0.,0]),dict(end_layers=[99]),dict(start_layers=[False]),dict(end_layers=[False])])
def test_ambiguous_or_out_of_scope_inputs_refuse(kwargs):
    with pytest.raises(ValueError):validate([('via',[0,0],.3,.6),('trk',[0,0],[2000000,0],200000,2)],**kwargs)

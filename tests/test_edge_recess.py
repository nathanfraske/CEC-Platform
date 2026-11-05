import pytest
from cec_edge_recess import recessed_path

@pytest.mark.parametrize('start,end,n',[
    ((0,0),(20,0),(0,1)),((20,30),(0,30),(0,-1)),
    ((40,0),(40,20),(-1,0)),((12,8),(12,-12),(1,0))])
def test_preserves_frame_and_path_continuity(start,end,n):
    path=recessed_path(start,end,n,opening=(4,12),depth=5,radius=.5)
    assert path[0][0]==start and path[-1][-1]==end
    assert all(a[-1]==b[0] for a,b in zip(path,path[1:]))
    assert [len(p) for p in path].count(3)==2

def test_invalid_inward_and_zero_tool_radius_rejected():
    with pytest.raises(ValueError):recessed_path((0,0),(20,0),(1,0),opening=(4,12),depth=5,radius=.5)
    with pytest.raises(ValueError):recessed_path((0,0),(20,0),(0,1),opening=(4,12),depth=5,radius=0)

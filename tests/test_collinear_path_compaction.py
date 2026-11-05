"""Construction simplification never creates copper outside its input path."""
import pytest
from shapely.geometry import LineString
import cec_route_quality as quality


@pytest.mark.parametrize('points',[
    [[0,0],[0,6],[0,3],[5,3]],
    [[5,3],[0,3],[0,6],[0,0]],
    [[0,0],[4,4],[2,2],[7,2]],
    [[0,0],[2,0],[0,0],[0,4]],
    [[1,1],[1,1],[3,3],[5,5],[7,5]],
    [[0,0],[0,2],[3,2],[3,1],[4,1]],
])
def test_exact_collinear_compaction_preserves_turns_endpoints_and_subset(points):
    original=[list(p) for p in points];result=quality.compact_collinear_path(points)
    assert result[0]==points[0] and result[-1]==points[-1]
    # Exact centreline inclusion implies capsule inclusion for unchanged
    # width, without comparing two differently tessellated Shapely endcaps.
    assert LineString(points).covers(LineString(result))
    assert result==quality.compact_collinear_path(result) and points==original


@pytest.mark.parametrize('bad',[[],[[0,0]],[[0.,0],[1,1]],[[True,0],[1,1]],[[0,0],[1,1,2]]])
def test_non_native_or_unbounded_polyline_is_refused(bad):
    with pytest.raises(ValueError):quality.compact_collinear_path(bad)

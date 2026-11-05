import pytest
from cec_outline_compaction import bind_required_positions


@pytest.mark.parametrize('offset', [(0,0),(17,-8)])
def test_anchor_overlay_preserves_macro_spacing_and_unrelated_positions(offset):
    x,y=offset
    source={'one':(10+x,20+y,90),'two':(17+x,20+y,90),'cell':(4+x,7+y,0)}
    anchors={'one':(8+x,16+y,90),'two':(15+x,16+y,90),'cell':'mechanical lock'}
    result,evidence=bind_required_positions(source,anchors)
    assert result['two'][0]-result['one'][0]==7
    assert result['one']==anchors['one']
    assert result['cell']==source['cell']
    assert source['one']==(10+x,20+y,90)
    assert set(evidence['changed'])=={'one','two'}
    assert not bind_required_positions(result,anchors)[1]['changed']


@pytest.mark.parametrize('anchors', [
    {'missing':(1,2,3)}, {'one':(1,2)}, {'one':None},
    {'one':(1,float('nan'),3)}, {'one':(float('inf'),2,3)}, {'one':('bad',2,3)},
])
def test_invalid_required_pose_fails_before_changing_input(anchors):
    source={'one':(0,0,0)}
    with pytest.raises(ValueError): bind_required_positions(source,anchors)
    assert source=={'one':(0,0,0)}

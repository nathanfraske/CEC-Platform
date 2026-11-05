"""Copper reuse must improve construction, never waive craft or invent metal."""
import pytest
from cec_copper_reuse import RetainedCopper


def line(a,b,*,width=200000,net='/CONTROL',layer=0,uid='retained'):
    return dict(net=net,layer=layer,start_nm=list(a),end_nm=list(b),width_nm=width,uuid=uid)


@pytest.mark.parametrize('axis',[(1,0),(0,1),(1,1),(-1,1)])
@pytest.mark.parametrize('direction',[1,-1])
def test_reuse_exact_launch_prefix_in_all_octilinear_directions(axis,direction):
    x,y=axis[0]*direction,axis[1]*direction
    source=line((0,0),(x*175000,y*175000))
    trial=line((0,0),(x*875000,y*875000),uid='proposal')
    result,proof=RetainedCopper([source]).subtract([trial])
    assert result==[dict(trial,start_nm=[x*175000,y*175000])]
    assert proof['changed_segments']==1 and proof['reused_native_uuids']==['retained']
    assert source['start_nm']==[0,0] and source['end_nm']==[x*175000,y*175000]


def test_whole_covered_link_is_not_reemitted():
    result,proof=RetainedCopper([line((0,0),(1000000,0))]).subtract([
        line((100000,0),(500000,0),uid='proposal')])
    assert result==[] and proof['emitted_segments']==0


def test_interior_retained_interval_preserves_both_joining_ends():
    result,proof=RetainedCopper([line((200000,0),(700000,0))]).subtract([
        line((1000000,0),(0,0),uid='proposal')])
    assert [(row['start_nm'],row['end_nm']) for row in result]==[
        ([1000000,0],[700000,0]),([200000,0],[0,0])]


def test_union_of_overlapping_and_adjacent_source_segments():
    result,proof=RetainedCopper([line((0,0),(300000,0),uid='one'),
        line((200000,0),(500000,0),uid='two'),line((500000,0),(600000,0),uid='three')]).subtract([
        line((0,0),(1000000,0),uid='proposal')])
    assert result[0]['start_nm']==[600000,0]
    assert proof['reused_native_uuids']==['one','three','two']


@pytest.mark.parametrize('source',[
    line((0,1),(1000000,1)),
    line((0,0),(1000000,0),net='/OTHER'),
    line((0,0),(1000000,0),layer=2),
    line((0,0),(1000000,0),width=199999),
    line((0,0),(1000000,1)),
    line((0,0),(0,1000000)),
])
def test_no_tolerance_wrong_net_layer_skinny_or_nonlinear_reuse(source):
    trial=line((0,0),(1000000,0),uid='proposal')
    result,proof=RetainedCopper([source]).subtract([trial])
    assert result==[trial] and proof['changed_segments']==0


def test_coordinates_are_integer_not_float_or_boolean():
    for at in ((0.,0),(False,0)):
        with pytest.raises(ValueError):RetainedCopper([line(at,(1000,0))])


def test_inventory_and_intersection_budgets_fail_closed():
    source=[line((0,0),(1000000,0)),line((0,0),(500000,0))]
    with pytest.raises(ValueError):RetainedCopper(source,max_items=1)
    with pytest.raises(ValueError):RetainedCopper(source).subtract(source,max_checks=1)


def test_large_exact_native_coordinates_do_not_lose_integer_precision():
    origin=2**54
    trial=line((origin,origin),(origin+1000000,origin+1000000),uid='proposal')
    result,_=RetainedCopper([line((origin,origin),(origin+175000,origin+175000))]).subtract([trial])
    assert result==[dict(trial,start_nm=[origin+175000,origin+175000])]


def test_native_adapter_passes_vias_and_does_not_edit_retained_tracks():
    import pcbnew
    from cec_copper_reuse import normalize_native_ops
    import cec_route_quality as craft
    board=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(board,'/CONTROL',1);board.Add(net)
    retained=pcbnew.PCB_TRACK(board);retained.SetNet(net);retained.SetLayer(pcbnew.F_Cu)
    retained.SetStart(pcbnew.VECTOR2I(0,0));retained.SetEnd(pcbnew.VECTOR2I(175000,0))
    retained.SetWidth(200000);retained.SetLocked(True);board.Add(retained)
    uuid=str(retained.m_Uuid.AsString())
    trial=[('trk',pcbnew.VECTOR2I(0,0),pcbnew.VECTOR2I(875000,0),200000,pcbnew.F_Cu),
           ('via',pcbnew.VECTOR2I(875000,0),.3,.6)]
    bad=craft.assess_proposed_route(board,[dict(net='/CONTROL',layer=0,
        start_nm=[0,0],end_nm=[875000,0],width_nm=200000)])
    assert bad['ok'] is False and bad['issues'][0]['type']=='covered_backtrack'
    normalized,proof=normalize_native_ops(board,trial,'/CONTROL')
    assert list(normalized[0][1])==[175000,0] and normalized[1] is trial[1]
    good=craft.assess_proposed_route(board,[dict(net='/CONTROL',layer=0,
        start_nm=list(normalized[0][1]),end_nm=list(normalized[0][2]),width_nm=200000)])
    assert good['ok'] is True and good['complete'] is True
    assert retained.IsLocked() and str(retained.m_Uuid.AsString())==uuid
    assert list(retained.GetStart())==[0,0] and list(retained.GetEnd())==[175000,0]

"""No visual proximity, foreign net or fractional point may anchor a trim."""
import pcbnew
import pytest
import cec_native_supply_tail_trim as op
import cec_force_current as force
import cec_field_coupling as field
from test_lastmile import _board
from test_field_proposals import track


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('orientation',['vertical','horizontal'])
def test_real_integral_full_width_join_proposes_both_exact_retained_sides_without_mutation(face,orientation):
    b=_board([(2,2,'/OTHER/RAIL'),(8,8,'/OTHER/RAIL')],edge=(0,0,12,12));b.SetCopperLayerCount(6)
    points=((5,2),(5,8),(3,5),(7,5))
    if orientation=='horizontal':points=tuple((y,x) for x,y in points)
    t=track(b,'/OTHER/RAIL',points[0],points[1],layer=face);t.SetLocked(True)
    anchor=track(b,'/OTHER/RAIL',points[2],points[3],layer=face)
    before=field._field_snapshot_inventory(b)
    q=op.propose(b,force._uid(t),required_width_by_layer_nm={face:200000})
    assert q['complete'] and len(q['proposals'])==2
    assert all(r['literal_native_intersection_nm']==[5000000,5000000] for r in q['proposals'])
    assert all(r['source_anchor_track_uuid']==force._uid(anchor) for r in q['proposals'])
    assert before==field._field_snapshot_inventory(b) and not q['mutation_or_receiving_authority']


@pytest.mark.parametrize('mode',['foreign','other_face','narrow','retired','no_intersection'])
def test_non_source_full_width_join_produces_no_trim(mode):
    b=_board([(2,2,'/RAIL'),(8,8,'/RAIL')],edge=(0,0,12,12))
    t=track(b,'/RAIL',(5,2),(5,8));a=track(b,'/RAIL',(3,5),(7,5));retired=[]
    if mode=='foreign':a.SetNet(b.FindNet('/OTHER')) if b.FindNet('/OTHER') else a.SetNetCode(0)
    elif mode=='other_face':a.SetLayer(pcbnew.B_Cu)
    elif mode=='narrow':a.SetWidth(100000)
    elif mode=='retired':retired=[force._uid(a)]
    else:a.SetStart(pcbnew.VECTOR2I_MM(5.01,5));a.SetEnd(pcbnew.VECTOR2I_MM(7,5))
    q=op.propose(b,force._uid(t),required_width_by_layer_nm={pcbnew.F_Cu:200000},retired_track_uuids=retired)
    assert q['proposals']==[] and q['complete']


@pytest.mark.parametrize('args,expected',[
    (((0,0),(10,10),(0,10),(10,0)),[(5,5)]),
    (((0,0),(3,3),(0,2),(3,0)),[]),
    (((0,0),(10,0),(3,0),(7,0)),[(3,0),(7,0)]),
    (((0,0),(10,0),(10,0),(15,0)),[]),
    (((0,0),(10,0),(3,1),(7,1)),[]),
])
def test_exact_segment_math_never_rounds_an_intersection_into_electrical_authority(args,expected):
    assert op.intersections(*args)==expected

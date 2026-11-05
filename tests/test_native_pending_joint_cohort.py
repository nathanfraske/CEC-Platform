import pcbnew
import pytest
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track
from root_native_pending_joint_cohort_20261013 import coalesce


def row(t):
    return dict(uid=force._uid(t),net=str(t.GetNetname()),code=int(t.GetNetCode()),
        layer=int(t.GetLayer()),width=t.GetWidth(),start=tuple(t.GetStart()),end=tuple(t.GetEnd()),
        locked=t.IsLocked(),item=t,groups=[],typed_anchor_retained=False)


@pytest.mark.parametrize('quarter',range(4))
def test_exact_requested_free_joint_edges_form_one_rebuild_transaction_without_new_authority(quarter):
    b=_board([(10,20,'RENAMED'),(20,10,'RENAMED')]);a=track(b,'RENAMED',(10,20),(10,10));c=track(b,'RENAMED',(10,10),(20,10))
    for item in [*b.GetFootprints(),*b.GetTracks()]:item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    before=[(tuple(t.GetStart()),tuple(t.GetEnd())) for t in (a,c)]
    rows,retired,proof=coalesce(b,[row(a),row(c)])
    assert len(rows)==1 and len(retired)==1 and proof['joins']
    assert set(rows[0]['pending_member_uuids'])=={force._uid(a),force._uid(c)}
    assert before==[(tuple(t.GetStart()),tuple(t.GetEnd())) for t in (a,c)]
    assert not proof['automatic_retirement_authorized'] and not proof['release_authority']


@pytest.mark.parametrize('anchor',['pad','barrel','branch','width','typed','locked'])
def test_real_native_terminal_or_width_or_owner_boundaries_cannot_be_consumed(anchor):
    pads=[(10,20,'A'),(20,10,'A')]
    if anchor=='pad':pads.append((10,10,'A'))
    b=_board(pads);a=track(b,'A',(10,20),(10,10));c=track(b,'A',(10,10),(20,10))
    if anchor=='barrel':
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(10,10));v.SetWidth(600000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(b.FindNet('A'));b.Add(v)
    elif anchor=='branch':track(b,'A',(10,10),(5,10))
    elif anchor=='width':c.SetWidth(250000)
    elif anchor=='locked':c.SetLocked(True)
    rows=[row(a),row(c)]
    if anchor=='typed':rows[0]['typed_anchor_retained']=True
    result,retired,proof=coalesce(b,rows)
    assert len(result)==2 and not retired and not proof['joins']

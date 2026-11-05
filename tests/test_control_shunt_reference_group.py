"""Real native Source maps; only canonical schematic export is fixture-bound."""
import copy
import pcbnew
import pytest
import cec_control_shunt_placement as op
import cec_source_reference_group_transport as mapping
import cec_force_current as force
import cec_field_coupling as field
from test_control_shunt_placement import fixture as source_fixture


def fixture(tmp_path,monkeypatch,fault=None):
    b,owner,g,root,poses=source_fixture(tmp_path,monkeypatch)
    cap=g.GetParentFootprint();cap.SetOrientationDegrees(0)
    poses[cap.GetReference()][2]=0
    at=cap.GetPosition();x,y=at.x,at.y
    cap.Reference().SetVisible(False)
    points=[(x-8000000,y-3000000),(x+8000000,y-3000000),
        (x+8000000,y+3000000),(x-8000000,y+3000000)]
    for a,z in zip(points,points[1:]+points[:1]):
        s=pcbnew.PCB_SHAPE(cap);s.SetShape(pcbnew.SHAPE_T_SEGMENT);s.SetLayer(pcbnew.F_CrtYd)
        s.SetStart(pcbnew.VECTOR2I(*a));s.SetEnd(pcbnew.VECTOR2I(*z));s.SetWidth(50000);cap.Add(s)
    group=pcbnew.PCB_GROUP(b);group.SetName(mapping.PREFIX+cap.GetReference());b.Add(group);group.AddItem(cap)
    text=pcbnew.PCB_TEXT(b);text.SetText(cap.GetReference());text.SetLayer(pcbnew.B_SilkS)
    text.SetMirrored(True);text.SetTextSize(pcbnew.VECTOR2I_MM(.8,.8));text.SetTextThickness(120000)
    text.SetTextPos(at);text.SetKeepUpright(True)
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER);text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    b.Add(text);group.AddItem(text)
    # Native GetCourtyard is the same exact producer geometry used by inspect.
    chain=cap.GetCourtyard(cap.GetLayer()).COutline(0)
    corners=[(chain.CPoint(i).x,chain.CPoint(i).y)for i in range(chain.PointCount())]
    for a,z in zip(corners,corners[1:]+corners[:1]):
        s=pcbnew.PCB_SHAPE(b);s.SetShape(pcbnew.SHAPE_T_SEGMENT);s.SetLayer(pcbnew.B_SilkS)
        s.SetStart(pcbnew.VECTOR2I(*a));s.SetEnd(pcbnew.VECTOR2I(*z));s.SetWidth(120000);b.Add(s);group.AddItem(s)
    group.SetLocked(True);cap.SetLocked(False)
    if fault=='copper':
        t=pcbnew.PCB_TRACK(b);t.SetStart(at);t.SetEnd(at+pcbnew.VECTOR2I(1000000,0));t.SetWidth(200000)
        t.SetNetCode(g.GetNetCode());b.Add(t);group.AddItem(t)
    elif fault=='padmember':group.AddItem(g)
    elif fault=='hidden':text.SetText('wrong')
    elif fault=='nested':
        outer=pcbnew.PCB_GROUP(b);b.Add(outer);outer.AddItem(group)
    elif fault=='lockedcap':cap.SetLocked(True)
    field._save_field_snapshot(b,b.GetFileName())
    gid=force._uid(group);b=pcbnew.LoadBoard(b.GetFileName())
    return b,root,poses,gid


def test_real_map_optin_translation_and_source_replayed_request(tmp_path,monkeypatch):
    b,root,poses,gid=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='ungrouped'):op.plan(b,poses,board_hint=str(root))
    q=op.plan(b,poses,board_hint=str(root),reference_group_uuids=[gid])
    proof=next(iter(q.values()));authorization=proof['source_reference_group_authorization']
    assert authorization==mapping.inspect(b.GetFileName(),owner_uuid=proof['cap_uuid'],group_uuid=gid)
    assert authorization['group_locked'] and not proof['current_authority']
    child=pcbnew.LoadBoard(b.GetFileName())
    requests=op.requests(b,child,dict(poses=poses,selected_control_shunts=q,
        board_hint=str(root),reference_group_uuids=[gid]))
    assert len(requests)==1 and next(iter(child.Groups())).IsLocked()
    forged=copy.deepcopy(q);next(iter(forged.values()))['source_reference_group_authorization']['group_locked']=False
    with pytest.raises(ValueError,match='fresh_source'):
        op.requests(b,child,dict(poses=poses,selected_control_shunts=forged,
            board_hint=str(root),reference_group_uuids=[gid]))


@pytest.mark.parametrize('fault',['copper','padmember','hidden','nested','lockedcap'])
def test_explicit_uuid_does_not_authorize_arbitrary_group(tmp_path,monkeypatch,fault):
    b,root,poses,gid=fixture(tmp_path,monkeypatch,fault)
    with pytest.raises(ValueError):op.plan(b,poses,board_hint=str(root),reference_group_uuids=[gid])


@pytest.mark.parametrize('fault',['rotation','duplicate','unknown','native_mutation','native_unlock','missingoptin'])
def test_source_map_scope_cannot_be_forged_or_rotated(tmp_path,monkeypatch,fault):
    b,root,poses,gid=fixture(tmp_path,monkeypatch);ids=[gid]
    if fault=='rotation':next(iter(poses.values()))[2]=45
    elif fault=='duplicate':ids=[gid,gid]
    elif fault=='unknown':ids=['00000000-0000-0000-0000-000000000000']
    elif fault=='native_mutation':next(iter(b.GetDrawings())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='native_unlock':next(iter(b.Groups())).SetLocked(False)
    else:ids=[]
    with pytest.raises(ValueError):op.plan(b,poses,board_hint=str(root),reference_group_uuids=ids)

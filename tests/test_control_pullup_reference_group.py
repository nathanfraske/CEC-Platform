"""Complete canonical EN/BOOT passives can carry exact Source reference maps.

Actual KiCad groups, locks, ink, rotations, faces and pads are exercised.
Only the synthetic schematic exporter and synthetic supply authority are bound.
"""
import copy
from pathlib import Path
import pcbnew,pytest
import cec_control_pullup_placement as op
import cec_source_reference_group_transport as mapping
import cec_field_coupling as field


def fixture(tmp_path,monkeypatch,*,boot=False,turn=0,back=False):
    if boot:
        from test_boot_pullup_placement import fixture as original
    else:
        from test_control_pullup_placement import fixture as original
    b,m,c,r,s,root,tree,poses=original(tmp_path,monkeypatch,turn=turn,back=back)
    r.Reference().SetVisible(False);at=r.GetPosition();x,y=at.x,at.y
    points=[(x-1500000,y-1000000),(x+1500000,y-1000000),
        (x+1500000,y+1000000),(x-1500000,y+1000000)]
    court=pcbnew.B_CrtYd if r.IsFlipped()else pcbnew.F_CrtYd
    face=pcbnew.F_SilkS if r.IsFlipped()else pcbnew.B_SilkS
    for first,last in zip(points,points[1:]+points[:1]):
        shape=pcbnew.PCB_SHAPE(r);shape.SetShape(pcbnew.SHAPE_T_SEGMENT);shape.SetLayer(court)
        shape.SetStart(pcbnew.VECTOR2I(*first));shape.SetEnd(pcbnew.VECTOR2I(*last));shape.SetWidth(50000);r.Add(shape)
    group=pcbnew.PCB_GROUP(b);group.SetName(mapping.PREFIX+r.GetReference());b.Add(group);group.AddItem(r)
    text=pcbnew.PCB_TEXT(b);text.SetText(r.GetReference());text.SetLayer(face)
    text.SetMirrored(face==pcbnew.B_SilkS);text.SetTextSize(pcbnew.VECTOR2I_MM(.8,.8))
    text.SetTextThickness(120000);text.SetTextPos(at);text.SetKeepUpright(True)
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER);text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    b.Add(text);group.AddItem(text)
    chain=r.GetCourtyard(r.GetLayer()).COutline(0)
    corners=[(chain.CPoint(i).x,chain.CPoint(i).y)for i in range(chain.PointCount())]
    for first,last in zip(corners,corners[1:]+corners[:1]):
        shape=pcbnew.PCB_SHAPE(b);shape.SetShape(pcbnew.SHAPE_T_SEGMENT);shape.SetLayer(face)
        shape.SetStart(pcbnew.VECTOR2I(*first));shape.SetEnd(pcbnew.VECTOR2I(*last))
        shape.SetWidth(120000);b.Add(shape);group.AddItem(shape)
    group.SetLocked(True);r.SetLocked(False)
    field._save_field_snapshot(b,b.GetFileName());gid=op.force._uid(group);ref=r.GetReference()
    return pcbnew.LoadBoard(b.GetFileName()),root,poses,gid,ref


def authority(monkeypatch):
    import cec_decoupler_cell as cells
    monkeypatch.setattr(cells,'_supply_current_widths',lambda board,net:dict(
        required_by_layer_nm={int(l):800000 for l in board.GetEnabledLayers().CuStack()},
        current_authority={'synthetic_only':True}))


@pytest.mark.parametrize('boot',[False,True])
@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_exact_source_group_optin_keeps_both_pins_full_current_and_lock(tmp_path,monkeypatch,boot,turn,back):
    b,root,poses,gid,ref=fixture(tmp_path,monkeypatch,boot=boot,turn=turn,back=back)
    original=Path(b.GetFileName()).read_bytes();binding=op.row._source_binding(b)
    with pytest.raises(ValueError,match='ungrouped'):op.complete_plan(b,poses,board_hint=str(root))
    selected=op.complete_plan(b,poses,board_hint=str(root),reference_group_uuids=[gid]);item=selected[ref]
    proof=item['source_reference_group_authorization']
    assert proof==mapping.inspect(b.GetFileName(),owner_uuid=item['resistor_uuid'],group_uuid=gid)
    assert proof['group_locked']and not item['current_authority']and not item['source_trace_retirement_authority']
    child=pcbnew.LoadBoard(b.GetFileName());first=b.FindFootprintByReference(ref)
    delta=tuple(round(poses[ref][i]*1e6)-tuple(first.GetPosition())[i]for i in(0,1))
    rotation=int((poses[ref][2]-first.GetOrientationDegrees())%360)//90
    mapping.transform_cardinal(child,proof,quarter_turns=rotation,delta_nm=delta)
    authority(monkeypatch)
    requests=op.requests(b,child,dict(poses=poses,selected_control_pullups=selected,
        board_hint=str(root),reference_group_uuids=[gid]))
    assert len(requests)==2
    rail=next(q for q in requests.values()if q['role']=='nonload_pullup_supply')
    assert rail['width_nm']>=800000 and not rail['new_barrel_authority']and not rail['class_only_supply_prefix_authority']
    assert next(g for g in child.Groups()if op.force._uid(g)==gid).IsLocked()
    assert not child.FindFootprintByReference(ref).IsLocked()
    assert Path(b.GetFileName()).read_bytes()==original and binding==op.row._source_binding(b)


@pytest.mark.parametrize('fault',['copper','padmember','hidden','nested','locked_owner','dnp','duplicate',
    'unknown','native_ink','native_unlock','missing_optin','noncardinal','wrong_owner'])
def test_group_uuid_never_grants_arbitrary_or_changed_ownership(tmp_path,monkeypatch,fault):
    b,root,poses,gid,ref=fixture(tmp_path,monkeypatch);g=next(iter(b.Groups()));r=b.FindFootprintByReference(ref);ids=[gid]
    if fault=='copper':
        track=pcbnew.PCB_TRACK(b);track.SetStart(r.GetPosition());track.SetEnd(r.GetPosition()+pcbnew.VECTOR2I(1000000,0))
        track.SetWidth(200000);track.SetNetCode(r.FindPadByNumber('1').GetNetCode());b.Add(track);g.AddItem(track)
    elif fault=='padmember':g.AddItem(r.FindPadByNumber('1'))
    elif fault=='hidden':next(i for i in b.GetDrawings()if i.GetClass()=='PCB_TEXT').SetText('wrong')
    elif fault=='nested':outer=pcbnew.PCB_GROUP(b);b.Add(outer);outer.AddItem(g)
    elif fault=='locked_owner':r.SetLocked(True)
    elif fault=='dnp':r.SetDNP(True)
    elif fault=='duplicate':ids=[gid,gid]
    elif fault=='unknown':ids=['00000000-0000-0000-0000-000000000000']
    elif fault=='native_ink':next(iter(b.GetDrawings())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='native_unlock':g.SetLocked(False)
    elif fault=='missing_optin':ids=[]
    elif fault=='noncardinal':poses[ref][2]=45
    elif fault=='wrong_owner':poses.pop(ref);poses['not_an_owner']=[0,0,0]
    # Persistent malicious Source groups must also fail actual recognition.
    if fault in('copper','padmember','hidden','nested','locked_owner','dnp'):
        field._save_field_snapshot(b,b.GetFileName());b=pcbnew.LoadBoard(b.GetFileName())
    if fault=='wrong_owner':assert op.complete_plan(b,poses,board_hint=str(root),reference_group_uuids=ids)=={}
    else:
        with pytest.raises(ValueError):op.complete_plan(b,poses,board_hint=str(root),reference_group_uuids=ids)


@pytest.mark.parametrize('fault',['forged_source','child_unlock','missing_member','new_member','removed_owner','nested'])
def test_requests_rederive_source_and_reject_changed_projected_group(tmp_path,monkeypatch,fault):
    b,root,poses,gid,ref=fixture(tmp_path,monkeypatch);selected=op.complete_plan(b,poses,board_hint=str(root),reference_group_uuids=[gid])
    child=pcbnew.LoadBoard(b.GetFileName());g=next(iter(child.Groups()));r=child.FindFootprintByReference(ref)
    if fault=='forged_source':selected[ref]['source_reference_group_authorization']['group_locked']=False
    elif fault=='child_unlock':g.SetLocked(False)
    elif fault=='missing_member':g.RemoveItem(next(i for i in g.GetItems()if i.GetClass()=='PCB_TEXT'))
    elif fault=='new_member':
        ink=pcbnew.PCB_TEXT(child);ink.SetText('extra');child.Add(ink);g.AddItem(ink)
    elif fault=='removed_owner':g.RemoveItem(r)
    elif fault=='nested':outer=pcbnew.PCB_GROUP(child);child.Add(outer);outer.AddItem(g)
    authority(monkeypatch)
    with pytest.raises(ValueError):op.requests(b,child,dict(poses=poses,selected_control_pullups=selected,
        board_hint=str(root),reference_group_uuids=[gid]))


@pytest.mark.parametrize('boot',[False,True])
def test_complete_compiler_and_independent_saved_pose_receiver_use_map_scope(tmp_path,monkeypatch,boot):
    import cec_cell_escape_replan as escape
    import cec_complete_cell_receiving as saved
    b,root,poses,gid,ref=fixture(tmp_path,monkeypatch,boot=boot)
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**k:{'assigned':{}})
    proposal=escape.prepare(b,poses,board_hint=str(root),reference_group_uuids=[gid])
    proof=proposal['selected_control_pullups'][ref]['source_reference_group_authorization']
    assert proposal['row_plan']['source_reference_group_transports'][ref]==proof
    child=pcbnew.LoadBoard(b.GetFileName());old=b.FindFootprintByReference(ref)
    mapping.transform_cardinal(child,proof,quarter_turns=int((poses[ref][2]-old.GetOrientationDegrees())%360)//90,
        delta_nm=tuple(round(poses[ref][i]*1e6)-tuple(old.GetPosition())[i]for i in(0,1)))
    monkeypatch.setattr(saved,'_assignments',lambda *a:{})
    authority(monkeypatch)
    actual,moved=saved._poses(b,child,str(root),reference_group_uuids=[gid])
    assert actual==poses and moved==set(poses)

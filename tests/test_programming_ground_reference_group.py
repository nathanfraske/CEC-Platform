"""Native mapped resistor returns need two fresh, identical map authorities."""
import copy
from pathlib import Path
import pcbnew,pytest
import cec_source_reference_group_transport as mapping
import cec_control_shunt_ground_return_axes as axes
import cec_smd_macro_transport as transport
import cec_force_current as force
import cec_field_coupling as field
from test_programming_ground_return_axes import case


def mapped_case(tmp_path,monkeypatch,turn=0,back=False,monitor=False):
    b,old_child,proposal,request,via,tail,tree=case(tmp_path,monkeypatch,turn,back,monitor)
    fp=b.FindFootprintByReference('R_program');fp.Reference().SetVisible(False)
    at=fp.GetPosition();x,y=at.x,at.y
    points=[(x-8000000,y-4000000),(x+8000000,y-4000000),
        (x+8000000,y+4000000),(x-8000000,y+4000000)]
    face=pcbnew.F_SilkS if back else pcbnew.B_SilkS
    court=pcbnew.B_CrtYd if back else pcbnew.F_CrtYd
    for first,last in zip(points,points[1:]+points[:1]):
        shape=pcbnew.PCB_SHAPE(fp);shape.SetShape(pcbnew.SHAPE_T_SEGMENT);shape.SetLayer(court)
        shape.SetStart(pcbnew.VECTOR2I(*first));shape.SetEnd(pcbnew.VECTOR2I(*last));shape.SetWidth(50000);fp.Add(shape)
    group=pcbnew.PCB_GROUP(b);group.SetName(mapping.PREFIX+fp.GetReference());b.Add(group);group.AddItem(fp)
    text=pcbnew.PCB_TEXT(b);text.SetText(fp.GetReference());text.SetLayer(face)
    text.SetMirrored(face==pcbnew.B_SilkS);text.SetTextSize(pcbnew.VECTOR2I_MM(1.2,1.2))
    text.SetTextThickness(200000);text.SetTextPos(at);text.SetKeepUpright(True)
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER);text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    b.Add(text);group.AddItem(text)
    chain=fp.GetCourtyard(fp.GetLayer()).COutline(0)
    corners=[tuple(chain.CPoint(i))for i in range(chain.PointCount())]
    for first,last in zip(corners,corners[1:]+corners[:1]):
        shape=pcbnew.PCB_SHAPE(b);shape.SetShape(pcbnew.SHAPE_T_SEGMENT);shape.SetLayer(face)
        shape.SetStart(pcbnew.VECTOR2I(*first));shape.SetEnd(pcbnew.VECTOR2I(*last));shape.SetWidth(200000)
        b.Add(shape);group.AddItem(shape)
    group.SetLocked(True);fp.SetLocked(False);gid=force._uid(group)
    field._save_field_snapshot(b,b.GetFileName());b=pcbnew.LoadBoard(b.GetFileName())
    child=pcbnew.LoadBoard(b.GetFileName())
    proof=mapping.inspect(b.GetFileName(),owner_uuid=force._uid(fp),group_uuid=gid)
    pose=proposal['poses']['R_program'];origin=b.FindFootprintByReference('R_program').GetPosition()
    mapping.transform_cardinal(child,proof,quarter_turns=0,
        delta_nm=tuple(round(pose[k]*1e6)-origin[k]for k in(0,1)))
    proposal['reference_group_uuids']=[gid]
    return b,child,proposal,request,gid,force._uid(via),force._uid(tail)


@pytest.mark.parametrize('monitor',[False,True])
@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_source_mapped_return_preserves_every_map_and_barrel_member(tmp_path,monkeypatch,monitor,turn,back):
    b,child,p,r,gid,vid,tid=mapped_case(tmp_path,monkeypatch,turn,back,monitor)
    before=axes.row._source_binding(b);original=Path(b.GetFileName()).read_bytes()
    derived=axes.derive(b,child,p,[r],timeout_s=9.)
    role=derived[0]['source_programming_resistor']
    assert role['source_reference_group_authorization']==mapping.inspect(b.GetFileName(),
        owner_uuid=role['resistor_uuid'],group_uuid=gid)
    result=transport.apply(b,child,source_path=Path(b.GetFileName()),board_hint=p['board_hint'],
        reference_group_uuids=[gid],source_control_ground_return_axes=[r],timeout_s=9.)
    moved=next(q for q in result['source_process_barrel_motion']if q['uuid']==vid)
    assert moved['source_control_shunt_return_axis']==derived[0]
    assert result['explicitly_reproved_private_signal_return_reseats']==[]and result['new_barrels_created']==0
    group=next(g for g in child.Groups()if force._uid(g)==gid)
    assert group.IsLocked()and not child.FindFootprintByReference('R_program').IsLocked()
    assert len(list(group.GetItems()))==6
    live={force._uid(t):t for t in child.GetTracks()}
    assert list(live[vid].GetPosition())==r['position_nm']and live[tid].GetLength()==789000
    assert all(live[vid].GetWidth(l)==900000 for l in child.GetEnabledLayers().CuStack())
    assert original==Path(b.GetFileName()).read_bytes()and before==axes.row._source_binding(b)


@pytest.mark.parametrize('fault',['missing_optin','wrong_group','legacy_RC','changed_ink','unlocked_group',
    'removed_member','extra_member','nested','locked_owner','copper_member','wrong_owner','forged_axis'])
def test_group_membership_never_bypasses_exact_fresh_role_and_native_map(tmp_path,monkeypatch,fault):
    b,child,p,r,gid,vid,tid=mapped_case(tmp_path,monkeypatch)
    kw=dict(reference_group_uuids=[gid],source_control_ground_return_axes=[r])
    group=next(g for g in child.Groups()if force._uid(g)==gid)
    if fault=='missing_optin':kw['reference_group_uuids']=[]
    elif fault=='wrong_group':kw['reference_group_uuids']=['00000000-0000-0000-0000-000000000000']
    elif fault=='legacy_RC':kw.pop('source_control_ground_return_axes');kw['local_signal_return_via_poses']=[dict(r,uuid=vid)]
    elif fault=='changed_ink':next(i for i in group.GetItems()if i.GetClass()=='PCB_TEXT').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='unlocked_group':group.SetLocked(False)
    elif fault=='removed_member':group.RemoveItem(next(i for i in group.GetItems()if i.GetClass()=='PCB_TEXT'))
    elif fault=='extra_member':
        text=pcbnew.PCB_TEXT(child);text.SetText('extra');child.Add(text);group.AddItem(text)
    elif fault=='nested':outer=pcbnew.PCB_GROUP(child);child.Add(outer);outer.AddItem(group)
    elif fault=='locked_owner':child.FindFootprintByReference('R_program').SetLocked(True)
    elif fault=='copper_member':group.AddItem(next(t for t in child.GetTracks()if force._uid(t)==tid))
    elif fault=='wrong_owner':r['owner_pad_uuid']=force._uid(b.FindFootprintByReference('U_program').FindPadByNumber('12'))
    else:r['source_programming_resistor']={'source_reference_group_authorization':{'group_uuid':gid}}
    binding=axes.row._source_binding(child)
    with pytest.raises(ValueError):transport.apply(b,child,source_path=Path(b.GetFileName()),
        board_hint=p['board_hint'],timeout_s=9.,**kw)
    assert binding==axes.row._source_binding(child)


@pytest.mark.parametrize('monitor',[False,True])
@pytest.mark.parametrize('face_index',[1,3,5])
def test_actual_nonuniform_inner_and_back_lands_cannot_inherit_top_only_class_floor(tmp_path,monkeypatch,monitor,face_index):
    b,child,p,r,via,tail,_=case(tmp_path,monkeypatch,monitor=monitor)
    layers=list(b.GetEnabledLayers().CuStack());via.Padstack().SetMode(pcbnew.PADSTACK.MODE_CUSTOM)
    for layer in layers:via.SetWidth(layer,900000)
    via.SetWidth(layers[face_index],800000)
    assert via.GetWidth(pcbnew.F_Cu)==900000 and via.GetWidth(layers[face_index])==800000
    field._save_field_snapshot(b,b.GetFileName());b=pcbnew.LoadBoard(b.GetFileName())
    child=pcbnew.LoadBoard(b.GetFileName());fp=child.FindFootprintByReference('R_program')
    pose=p['poses']['R_program'];fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in pose[:2])))
    saved=next(t for t in b.GetTracks()if force._uid(t)==force._uid(via))
    assert saved.GetWidth(pcbnew.F_Cu)==900000 and saved.GetWidth(layers[face_index])==800000
    binding=axes.row._source_binding(child)
    with pytest.raises(ValueError,match='source_ground_barrel_below_exact_class_floor'):
        axes.derive(b,child,p,[r],timeout_s=9.)
    assert binding==axes.row._source_binding(child)

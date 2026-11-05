"""Stationary plated Ground reuse is exact material, never net proximity."""
import copy,json,math
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_force_current as force
import cec_projected_ground_contact as contact
import cec_smd_macro_transport as transport
from cec_native_items import discard_items
from test_native_ground_terminal_branch import fixture as base


def fixture(tmp_path,quarter=0,back=False,turn=0):
    b,source,ids,ports,owner,cap,via=base(tmp_path,quarter=quarter,layer=pcbnew.B_Cu if back else pcbnew.F_Cu)
    root=cap.FindPadByNumber('2');root.SetSize(pcbnew.VECTOR2I_MM(.9,.9))
    # A real former SMD owner makes naive rigid barrel transport WRONG.
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('RENAMED_OLD_GROUND_OWNER');fp.SetValue('unclassified_source_contact')
    fp.SetPosition(via.GetPosition());fp.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);b.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('7');pad.SetNet(b.FindNet('GND'))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(.9,.9));pad.SetPosition(via.GetPosition())
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);pad.SetLayerSet(layers);fp.Add(pad)
    angle=math.radians(turn);old=tuple(root.GetPosition());c,s=round(math.cos(angle)),round(math.sin(angle))
    origin=tuple(cap.GetPosition());offset=(old[0]-origin[0],old[1]-origin[1]);at=tuple(via.GetPosition())
    target=[(at[0]-c*offset[0]-s*offset[1])/1e6,(at[1]+s*offset[0]-c*offset[1])/1e6,
        cap.GetOrientationDegrees()+turn]
    additive._ground_refill(b);b.SetFileName(str(source));field._save_field_snapshot(b,source)
    return b,source,owner,cap,root,via,fp,target


def plan(b,root,via,target):
    return contact.plan_barrel_reuse(b,force._uid(root),force._uid(via),target,board_hint='synthetic')


def pose(fp,target):
    fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])));fp.SetOrientationDegrees(target[2])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',[0,90,180,270])
def test_full_stationary_source_barrel_reused_across_cardinal_and_back_faces(tmp_path,quarter,back,turn):
    b,source,owner,cap,root,via,former,target=fixture(tmp_path,quarter,back,turn)
    raw=source.read_bytes();binding=row._source_binding(b);q=json.loads(json.dumps(plan(b,root,via,target)))
    assert source.read_bytes()==raw and row._source_binding(b)==binding
    pose(cap,target);former.Move(pcbnew.VECTOR2I_MM(1,0))
    observed=contact.observe_barrel_reuse(b,root,q)
    assert observed and observed['saved_return_mm']==0.
    assert q['former_owner_connections_not_retired_or_waived'] and not q['current_qualified']
    assert observed['stationary_native_barrel_and_full_land_reproved']
    assert source.read_bytes()==raw and not observed['release_authority']


@pytest.mark.parametrize('fault',['sliver','foreign','tht','unknown','power','noncardinal','far',
    'unfilled','missing_plane','source_unsaved','missing_via','no_profile','no_source'])
def test_inexact_land_role_or_reference_never_grants_barrel_reuse(tmp_path,fault):
    b,source,owner,cap,root,via,former,target=fixture(tmp_path)
    via_uuid=force._uid(via)
    if fault=='sliver':target[0]+=.16
    elif fault=='foreign':via.SetNet(b.FindNet('+3V3'))
    elif fault=='tht':root.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='unknown':owner.SetValue('UNKNOWN')
    elif fault=='power':cap.SetValue('2200uF')
    elif fault=='noncardinal':target[2]+=1
    elif fault=='far':target[0]+=33
    elif fault=='unfilled':next(iter(b.Zones())).UnFill()
    elif fault=='missing_plane':b.Remove(next(iter(b.Zones())))
    elif fault=='source_unsaved':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='missing_via':discard_items(b,[via])
    elif fault=='no_profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='';b.SetProperties(props)
    else:b.SetFileName('')
    if fault not in ('source_unsaved','no_source'):
        # Hostile sources may contain a deliberate short or unsupported
        # plated land. Persist without normalizing that test evidence.
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source),b)
    before=row._source_binding(b)
    with pytest.raises((ValueError,RuntimeError)):
        contact.plan_barrel_reuse(b,force._uid(root),via_uuid,target,board_hint='synthetic')
    assert row._source_binding(b)==before


@pytest.mark.parametrize('fault',['via_pose','drill','width','lock','group','cut','land','pose','plane',
    'forged_width','forged_role','forged_return','forged_source'])
def test_reuse_is_rederived_and_never_trusts_cached_live_or_source_claims(tmp_path,fault):
    b,source,owner,cap,root,via,former,target=fixture(tmp_path);q=json.loads(json.dumps(plan(b,root,via,target)))
    pose(cap,target)
    if fault=='via_pose':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='drill':via.SetDrill(250000)
    elif fault=='width':via.SetWidth(599999)
    elif fault=='lock':via.SetLocked(not via.IsLocked())
    elif fault=='group':
        group=pcbnew.PCB_GROUP(b);group.SetName('FORGED_OWNER');b.Add(group);group.AddItem(via)
    elif fault=='cut':discard_items(b,[via])
    elif fault=='land':root.SetSize(pcbnew.VECTOR2I(899999,900000))
    elif fault=='pose':cap.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='plane':next(iter(b.Zones())).UnFill()
    elif fault=='forged_width':q['source_reference_via']['diameters_nm'][str(pcbnew.F_Cu)]+=1
    elif fault=='forged_role':q['source_ground_role']={'kind':'net_only'}
    elif fault=='forged_return':q['source_return_mm']+=1
    else:q['source_sha256']='forged'
    before=row._source_binding(b)
    try:result=contact.observe_barrel_reuse(b,root,q)
    except ValueError:result=None
    assert result is None and row._source_binding(b)==before


@pytest.mark.parametrize('fault',[None,'proof','duplicate','target','missing_context'])
def test_transport_keeps_barrel_axis_instead_of_dragging_it_with_former_owner(tmp_path,fault):
    b,source,owner,cap,root,via,former,target=fixture(tmp_path);q=json.loads(json.dumps(plan(b,root,via,target)))
    child=pcbnew.LoadBoard(str(source));pose(child.FindFootprintByReference(cap.GetReference()),target)
    child.FindFootprintByReference(former.GetReference()).Move(pcbnew.VECTOR2I_MM(1,0))
    proofs=[q];options=dict(source_path=source,board_hint='synthetic')
    if fault=='proof':q['source_return_mm']+=1
    elif fault=='duplicate':proofs.append(copy.deepcopy(q))
    elif fault=='target':child.FindFootprintByReference(cap.GetReference()).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='missing_context':options={}
    before={force._uid(t):force._item_key(t) for t in child.GetTracks()}
    if fault:
        with pytest.raises(ValueError):transport.apply(b,child,maximum_shift_mm=32.,
            reused_ground_barrel_contacts=proofs,**options)
        assert {force._uid(t):force._item_key(t) for t in child.GetTracks()}==before
    else:
        r=transport.apply(b,child,maximum_shift_mm=32.,reused_ground_barrel_contacts=proofs,**options)
        assert r['reused_stationary_ground_barrel_uuids']==[force._uid(via)]
        assert force._uid(via) not in {v['uuid'] for v in r['source_process_barrel_motion']}
        current=next(t for t in child.GetTracks() if force._uid(t)==force._uid(via))
        assert current.GetPosition()==via.GetPosition() and current.GetDrillValue()==via.GetDrillValue()
        assert not r['saved_candidate_authorized']


@pytest.mark.parametrize('timeout',[True,0,11,None,float('nan')])
def test_explicit_finite_barrel_reuse_work_bound(tmp_path,timeout):
    b,source,owner,cap,root,via,former,target=fixture(tmp_path)
    with pytest.raises(ValueError):contact.plan_barrel_reuse(b,force._uid(root),force._uid(via),target,
        board_hint='synthetic',timeout_s=timeout)

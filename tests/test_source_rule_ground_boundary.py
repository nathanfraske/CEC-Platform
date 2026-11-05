"""Source-rule-owned Ground events: native construction, not board admission."""
import time
from pathlib import Path
import pcbnew
import pytest
import cec_source_rule_ground_boundary as op
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_fab_profile as fab
import cec_existing_local_pofv_pad_rule as rule
from test_control_shunt_placement import fixture as control_fixture


def fixture(tmp_path,monkeypatch,turn=0,back=False):
    b,owner,g,root,_=control_fixture(tmp_path,monkeypatch,turn,back)
    b.SetCopperLayerCount(6);props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    enabled=b.GetEnabledLayers()
    for face in(pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.In2_Cu,pcbnew.In3_Cu,pcbnew.In4_Cu,pcbnew.B_Cu):enabled.AddLayer(face)
    b.SetEnabledLayers(enabled)
    g.GetNet().GetNetClassSlow().SetTrackWidth(500000)
    owner.Move(pcbnew.VECTOR2I_MM(20,20))
    cap=g.GetParentFootprint();cap.SetPosition(pcbnew.VECTOR2I(0,0))
    for p in cap.Pads():p.SetShape(pcbnew.PAD_SHAPE_RECT)
    g.SetPosition(pcbnew.VECTOR2I(0,0));signal=cap.FindPadByNumber('1')
    dx,dy=((-960000,0),(0,960000),(960000,0),(0,-960000))[turn//90]
    signal.SetPosition(pcbnew.VECTOR2I(dx,dy))
    for face in(pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetLayer(face);z.SetNet(g.GetNet());p=pcbnew.SHAPE_POLY_SET();p.NewOutline()
        for x,y in((-100,-100),(100,-100),(100,100),(-100,100)):p.Append(x*1000000,y*1000000)
        z.Outline().Append(p);z.SetFilledPolysList(face,p);z.SetIsFilled(True);b.Add(z)
    for a,z in[((-100,-100),(100,-100)),((100,-100),(100,100)),((100,100),(-100,100)),((-100,100),(-100,-100))]:
        line=pcbnew.PCB_SHAPE(b);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.Edge_Cuts)
        line.SetStart(pcbnew.VECTOR2I_MM(*a));line.SetEnd(pcbnew.VECTOR2I_MM(*z));line.SetWidth(50000);b.Add(line)
    seed=pcbnew.PCB_VIA(b);seed.SetPosition(owner.FindPadByNumber('1').GetPosition());seed.SetWidth(300000);seed.SetDrill(200000)
    seed.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);seed.SetNet(g.GetNet());b.Add(seed)
    evidence=fr.group_local_pofv_signal_vias(b,[seed]);source=Path(b.GetFileName());field._save_field_snapshot(b,source)
    fr.ensure_local_pofv_signal_via_rule(str(source),dict(local_pofv_signal_vias=evidence))
    return b,source,g,root


def run(b,g,root,**kw):
    detail={};result,error=op.construct(b,g,board_path=str(root),reach_mm=.8,timeout_s=5.,diagnostics=detail,**kw)
    return result,error,detail


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_native_source_control_shunt_events_construct_full_class_return(tmp_path,monkeypatch,turn,back):
    b,source,g,root=fixture(tmp_path,monkeypatch,turn,back);raw=source.read_bytes();floors=rule._floors(b)
    result,error,detail=run(b,g,root)
    assert result,error or detail
    assert len(result['items'])==2 and result['full_native_reference_annuli']
    assert result['diameter_mm']==.3 and result['drill_mm']==.2 and result['distance_mm']<=.8
    track,via=result['items'];assert track.GetWidth()==int(op.cells._netclass(b,'GND')['width'])
    assert track.GetLayer()==(pcbnew.B_Cu if back else pcbnew.F_Cu)
    assert fab.local_pofv_via_decision(b,via)[0]is True
    assert source.read_bytes()==raw and rule._floors(b)==floors
    group=next(g for g in b.Groups()if g.GetName()==rule.GROUP)
    assert force._uid(via)in{force._uid(i)for i in group.GetItems()}
    assert detail['source_role']['kind']=='source_control_shunt_ground'
    assert not detail['current_authority']and not result.get('release_authority',False)


def test_normal_ground_constructor_reaches_source_rule_tier_after_blocked_center(tmp_path,monkeypatch):
    b,source,g,root=fixture(tmp_path,monkeypatch);raw=source.read_bytes();floors=rule._floors(b)
    actual=fr._via_spot_clear
    def blocked_center(board,at,*args,**kwargs):
        return False if at==g.GetPosition()else actual(board,at,*args,**kwargs)
    monkeypatch.setattr(fr,'_via_spot_clear',blocked_center)
    detail={}
    result,error=op.cells._add_ground_return(b,g,board_path=str(root),reach_mm=.8,lock=False,diagnostics=detail)
    assert result,error or detail
    assert result['status']=='source-rule-ground-boundary-dogbone'
    assert result['diameter_mm']==.3 and result['drill_mm']==.2
    assert detail['source_rule_boundary_dogbone']['evidence']['consumed_events']>0
    assert source.read_bytes()==raw and rule._floors(b)==floors


@pytest.mark.parametrize('fault',['missingrule','missinggroup','unknownrole','sourcedrift','missingref','groundnet','lockedgroup'])
def test_refusals_never_mutate_native_items_groups_or_global_limits(tmp_path,monkeypatch,fault):
    b,source,g,root=fixture(tmp_path,monkeypatch)
    if fault=='missingrule':source.with_suffix('.kicad_dru').unlink()
    elif fault=='missinggroup':
        group=next(v for v in b.Groups()if v.GetName()==rule.GROUP)
        for item in list(group.GetItems()):group.RemoveItem(item)
        b.Remove(group)
    elif fault=='unknownrole':monkeypatch.setattr(op.source_leaf,'_candidates',lambda board:{})
    elif fault=='sourcedrift':root.write_text(root.read_text().replace('100nF','unknown'))
    elif fault=='missingref':
        from cec_native_items import discard_items
        discard_items(b,list(b.Zones()))
    elif fault=='groundnet':g.SetNetCode(0)
    else:next(v for v in b.Groups()if v.GetName()==rule.GROUP).SetLocked(True)
    before=field._field_snapshot_inventory(b);floors=rule._floors(b)
    result,error,detail=run(b,g,root)
    assert result is None
    assert field._field_snapshot_inventory(b)==before and rule._floors(b)==floors


def test_boundary_events_are_native_derived_not_fixed_radius(tmp_path,monkeypatch):
    b,source,g,root=fixture(tmp_path,monkeypatch)
    q=op.boundary_events(b,g,300000,200000,.8,deadline=time.monotonic()+3)
    assert q['events']and len(q['events'])<=64
    native_exit=[r for r in q['events']if r['origin']['kind']=='native_source_pad_face_exit']
    assert native_exit and any(abs(r['distance_mm']-.402)<.00001 for r in native_exit)
    # The actual VHP .56x.62 source land yields .432/.462 face exits.
    # This is a geometric fixture, not a board/refdes/coordinate exception.
    g.SetSize(pcbnew.VECTOR2I(560000,620000))
    q=op.boundary_events(b,g,300000,200000,.8,deadline=time.monotonic()+3)
    assert any(abs(r['distance_mm']-.462)<.00001 for r in q['events']if r['origin']['kind']=='native_source_pad_face_exit')


def test_event_truncation_is_explicit_and_expired_lease_is_not_a_path_claim(tmp_path,monkeypatch):
    b,source,g,root=fixture(tmp_path,monkeypatch)
    q=op.boundary_events(b,g,300000,200000,.8,deadline=time.monotonic()+3,max_events=2)
    assert len(q['events'])==2 and q['truncated']==q['generated']-2
    with pytest.raises(ValueError,match='deadline'):
        op.boundary_events(b,g,300000,200000,.8,deadline=time.monotonic()-1)


def test_source_control_shunt_reach_cannot_be_promoted_to_owner_reach(tmp_path,monkeypatch):
    b,source,g,root=fixture(tmp_path,monkeypatch);before=field._field_snapshot_inventory(b)
    result,error=op.construct(b,g,board_path=str(root),reach_mm=1.5)
    assert result is None and 'unchanged_control_shunt_ground_reach_required'in error
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.In2_Cu,pcbnew.In3_Cu,pcbnew.In4_Cu,pcbnew.B_Cu])
def test_native_foreign_barrier_cannot_be_waived_on_any_face(tmp_path,monkeypatch,layer):
    b,source,g,root=fixture(tmp_path,monkeypatch)
    net=pcbnew.NETINFO_ITEM(b,'foreign_renamed');b.Add(net)
    z=pcbnew.ZONE(b);z.SetLayer(layer);z.SetNet(net);p=pcbnew.SHAPE_POLY_SET();p.NewOutline()
    for x,y in((-2,-2),(2,-2),(2,2),(-2,2)):p.Append(x*1000000,y*1000000)
    z.Outline().Append(p);z.SetFilledPolysList(layer,p);z.SetIsFilled(True);b.Add(z)
    before=field._field_snapshot_inventory(b);result,error,detail=run(b,g,root)
    assert result is None and field._field_snapshot_inventory(b)==before


def test_actual_live_process_refusal_rolls_back_new_copper(tmp_path,monkeypatch):
    b,source,g,root=fixture(tmp_path,monkeypatch);before=field._field_snapshot_inventory(b)
    monkeypatch.setattr(op.fab,'local_pofv_via_decision',lambda *a,**k:(False,'negative fixture'))
    assert run(b,g,root)[0]is None
    assert field._field_snapshot_inventory(b)==before


def test_membership_failure_restores_all_new_native_items_and_groups(tmp_path,monkeypatch):
    b,source,g,root=fixture(tmp_path,monkeypatch);before=field._field_snapshot_inventory(b)
    monkeypatch.setattr(op.fr,'group_local_pofv_signal_vias',lambda *a,**k:[])
    assert run(b,g,root)[0]is None and field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('kw',[dict(timeout_s=0),dict(timeout_s=11),dict(reach_mm=.9),dict(lock=1)])
def test_invalid_or_extended_cap_parameters_do_not_create_items(tmp_path,monkeypatch,kw):
    b,source,g,root=fixture(tmp_path,monkeypatch);before=field._field_snapshot_inventory(b)
    args=dict(board_path=str(root),reach_mm=.8,timeout_s=5.);args.update(kw)
    try:result,error=op.construct(b,g,**args);assert result is None
    except ValueError:pass
    assert field._field_snapshot_inventory(b)==before

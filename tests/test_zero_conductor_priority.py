import pcbnew
import pytest
import cec_macro_priority_preflight as op
import cec_force_current as force
import cec_field_coupling as field
from test_lastmile import _board


def example(tmp_path,monkeypatch,turn=0,back=False):
    source=_board([(10,10,'/ground'),(22,22,'/hot')],edge=(0,0,30,30))
    fp=next(f for f in source.GetFootprints()if next(iter(f.Pads())).GetNetname()=='/ground')
    if back:fp.Flip(fp.GetPosition(),False)
    track=pcbnew.PCB_TRACK(source);track.SetStart(pcbnew.VECTOR2I_MM(23,20));track.SetEnd(pcbnew.VECTOR2I_MM(23,24))
    track.SetWidth(600000);track.SetLayer(pcbnew.B_Cu);track.SetNet(source.FindNet('/hot'));source.Add(track)
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(source,path)
    source=pcbnew.LoadBoard(str(path));child=pcbnew.LoadBoard(str(path))
    fp=next(f for f in child.GetFootprints()if next(iter(f.Pads())).GetNetname()=='/ground')
    fp.Move(pcbnew.VECTOR2I_MM(.5,0));fp.Rotate(fp.GetPosition(),pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    report=dict(scope='provisional_source_owned_smd_cohort_endpoint_transport',changes=[],
        moved_owner_footprint_uuids=[force._uid(fp)])
    monkeypatch.setattr(op.topology,'route_width_contracts',lambda *a,**kw:{'/hot':dict(current_authority=dict(source='board_design_basis'))})
    monkeypatch.setattr(op.fr,'locked_pour_authority_nets_board',lambda *a,**kw:set())
    return source,child,report


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_zero_conductors_still_checks_actual_moving_lands(tmp_path,monkeypatch,turn,back):
    a,b,report=example(tmp_path,monkeypatch,turn,back)
    before=field._field_snapshot_inventory(b)
    result=op.inspect(a,b,report,board_hint='synthetic')
    assert result['ok']and result['complete']and result['moving_land_or_barrel_count']==1
    assert result['zero_conductor_motion_receiving']['all_source_copper_and_groups_retained']
    assert not result['routing_admitted']and not result['current_or_clearance_qualified']
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',['position','width','layer','net','lock','missing_owner','stationary_owner','flip','unmoved_pad'])
def test_empty_report_cannot_hide_copper_or_owner_mutations(tmp_path,monkeypatch,fault):
    a,b,report=example(tmp_path,monkeypatch);track=next(iter(b.GetTracks()))
    if fault=='position':track.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='width':track.SetWidth(track.GetWidth()-1)
    elif fault=='layer':track.SetLayer(pcbnew.F_Cu)
    elif fault=='net':track.SetNet(b.FindNet('/ground'))
    elif fault=='lock':track.SetLocked(not track.IsLocked())
    elif fault=='missing_owner':report['moved_owner_footprint_uuids']=[]
    elif fault=='stationary_owner':report['moved_owner_footprint_uuids']=[force._uid(f)for f in b.GetFootprints()if force._uid(f)not in report['moved_owner_footprint_uuids']]
    elif fault=='flip':
        fp=next(f for f in b.GetFootprints()if force._uid(f)in report['moved_owner_footprint_uuids']);fp.Flip(fp.GetPosition(),False)
    else:
        fp=next(f for f in b.GetFootprints()if force._uid(f)not in report['moved_owner_footprint_uuids'])
        next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(2,2))
    with pytest.raises(ValueError):op.inspect(a,b,report,board_hint='synthetic')


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_zero_transport_does_not_waive_a_moved_land_priority_collision(tmp_path,monkeypatch,layer):
    a,b,report=example(tmp_path,monkeypatch,back=layer==pcbnew.B_Cu)
    pad=next(p for f in b.GetFootprints()if force._uid(f)in report['moved_owner_footprint_uuids']for p in f.Pads())
    at=tuple(pad.GetPosition())
    for board in(a,b):
        track=next(iter(board.GetTracks()));track.SetLayer(layer)
        # Positive physical gap (.05mm), but below the .2mm rule. A hard
        # short is separately refused by the non-normalizing save witness.
        track.SetStart(pcbnew.VECTOR2I(at[0]+750000,at[1]-2000000))
        track.SetEnd(pcbnew.VECTOR2I(at[0]+750000,at[1]+2000000))
    result=op.inspect(a,b,report,board_hint='synthetic')
    assert result['complete']and not result['ok']and result['conflicts']
    assert not result['routing_admitted']


@pytest.mark.parametrize('fault',['via_drill','arc_midpoint','zone_process','zone_fill','group_membership'])
def test_complete_native_retention_includes_process_arcs_fills_and_groups(tmp_path,monkeypatch,fault):
    a,b,report=example(tmp_path,monkeypatch)
    if fault=='via_drill':
        item=pcbnew.PCB_VIA(a);item.SetPosition(pcbnew.VECTOR2I_MM(20,15))
        item.SetWidth(600000);item.SetDrill(300000);item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);item.SetNet(a.FindNet('/hot'));a.Add(item)
    elif fault=='arc_midpoint':
        item=pcbnew.PCB_ARC(a);item.SetStart(pcbnew.VECTOR2I_MM(20,15));item.SetMid(pcbnew.VECTOR2I_MM(21,16));item.SetEnd(pcbnew.VECTOR2I_MM(22,15))
        item.SetWidth(200000);item.SetLayer(pcbnew.B_Cu);item.SetNet(a.FindNet('/hot'));a.Add(item)
    elif fault.startswith('zone'):
        item=pcbnew.ZONE(a);item.SetLayer(pcbnew.F_Cu);item.SetNet(a.FindNet('/hot'))
        item.Outline().NewOutline()
        for x,y in((24,14),(27,14),(27,17),(24,17)):item.Outline().Append(pcbnew.VECTOR2I_MM(x,y))
        item.SetFilledPolysList(pcbnew.F_Cu,item.Outline().CloneDropTriangulation());item.SetIsFilled(True);a.Add(item)
    else:
        item=pcbnew.PCB_GROUP(a);item.SetName('untouched-source-group');a.Add(item);item.AddItem(next(iter(a.GetTracks())))
    uid=force._uid(item);path=tmp_path/'material-source.kicad_pcb';field._save_field_snapshot(a,path)
    a=pcbnew.LoadBoard(str(path));b=pcbnew.LoadBoard(str(path))
    fp=next(f for f in b.GetFootprints()if force._uid(f)in report['moved_owner_footprint_uuids']);fp.Move(pcbnew.VECTOR2I_MM(.5,0))
    items=[*b.GetTracks(),*b.Zones(),*b.Groups()];changed=next(i for i in items if force._uid(i)==uid)
    if fault=='via_drill':changed.SetDrill(300001)
    elif fault=='arc_midpoint':changed.SetMid(changed.GetMid()+pcbnew.VECTOR2I(1,0))
    elif fault=='zone_process':changed.SetLocalClearance(int(changed.GetLocalClearance())+1)
    elif fault=='zone_fill':changed.SetIsFilled(False)
    else:changed.RemoveItem(next(iter(b.GetTracks())))
    with pytest.raises(ValueError):op.inspect(a,b,report,board_hint='synthetic')

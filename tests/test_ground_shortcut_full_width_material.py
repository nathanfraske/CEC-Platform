"""Real full-class corner material, not centerline or drilled-void credit."""
import time,json
import pcbnew
import pytest
import cec_ground_return_shortcut as op
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_lastmile import _board


def fixture(tmp_path,quarter=0,mirror=False,face=pcbnew.F_Cu,endpoint_aliases=False):
    board=_board([],edge=(0,0,30,30));board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    for net in('GND','foreign'):board.Add(pcbnew.NETINFO_ITEM(board,net))
    board.GetNetInfo().GetNetItem('GND').GetNetClassSlow().SetTrackWidth(500000)
    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return [round(x*1e6),round(y*1e6)]
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('RENAMED_OWNER');board.Add(fp)
    for number,net,x,y in[('2','GND',11.5948,8.5217),('5','GND',13.8698,8.5217),
        ('1','foreign',11.5948,7.5717),('6','foreign',13.8698,7.5717)]:
        pad=pcbnew.PAD(fp);pad.SetNumber(number);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetPosition(pcbnew.VECTOR2I(*point(x,y)))
        pad.SetSize(pcbnew.VECTOR2I_MM(1.325,.6));layers=pcbnew.LSET();layers.AddLayer(face)
        pad.SetLayerSet(layers);pad.SetNet(board.FindNet(net));fp.Add(pad);pad.SetOrientationDegrees(quarter*90)
    for a,b in[((11.5948,8.5217),(13.8698 if endpoint_aliases else 14.4,8.5217)),
        ((12.2513,8.5217),(12.7323,8.0407)),
        ((12.7323,8.0407),(12.7323,7.56 if endpoint_aliases else 7.1))]:
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I(*point(*a)));t.SetEnd(pcbnew.VECTOR2I(*point(*b)))
        t.SetLayer(face);t.SetWidth(500000);t.SetNet(board.FindNet('GND'));t.SetLocked(True);board.Add(t)
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I(*point(12.7323,7.56)))
    via.SetWidth(500000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNet(board.FindNet('GND'));board.Add(via)
    for layer in(pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(board);z.SetNet(board.FindNet('GND'));z.SetLayer(layer);z.SetLocalClearance(200000)
        z.SetMinThickness(100000);z.Outline().NewOutline()
        for x,y in((1,1),(29,1),(29,29),(1,29)):z.Outline().Append(x*1000000,y*1000000)
        board.Add(z)
    additive._ground_refill(board)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(
        classes=[dict(name='Default',track_width=.5,clearance=.2,via_diameter=.5,via_drill=.3)],netclass_assignments={'GND':'Default'}))))
    root=fp.FindPadByNumber('5')
    params=dict(board_hint='synthetic',pad_uuid=force._uid(root),target_via_uuid=force._uid(via),
        points_nm=[point(*p)for p in[(13.8698,8.5217),(13.05,8.5217),(12.7323,8.204),(12.7323,7.56)]])
    return board,source,params,root,via,point


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_covered_centerline_real_full_class_corner_saved_native_receive(tmp_path,quarter,mirror,face):
    board,source,params,root,via,point=fixture(tmp_path,quarter,mirror,face)
    original=source.read_bytes();proposal=op.plan(source,**params)
    assert proposal['width_nm']==500000
    child=op.construct(proposal);additive._ground_refill(child)
    candidate=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(child,candidate)
    result=op.receive(source,candidate,**params)
    assert result['ok']and result['complete'],result
    assert result['saved_return_witness_mm']<result['source_return_witness_mm']-.8
    assert result['new_holes']==0 and not result['retired_track_uuids']
    assert result['every_source_native_partition_identical']
    assert source.read_bytes()==original


def test_whole_capsule_already_covered_remains_a_duplicate(tmp_path):
    board,source,params,root,via,point=fixture(tmp_path)
    points=[point(11.5948,8.5217),point(13.8698,8.5217)]
    with pytest.raises(ValueError,match='already_covered_by_source_copper'):
        op._new_surface_material(board,points,0,time.monotonic()+10.)


@pytest.mark.parametrize('hole_kind',['round_npth','slotted_npth','foreign_via'])
def test_only_novelty_inside_actual_bore_never_counts_as_new_copper(tmp_path,hole_kind):
    board=_board([],edge=(0,0,20,20));board.Add(pcbnew.NETINFO_ITEM(board,'GND'))
    board.GetNetInfo().GetNetItem('GND').GetNetClassSlow().SetTrackWidth(500000)
    at=pcbnew.VECTOR2I_MM(6.5,8)
    if hole_kind=='foreign_via':
        hole=pcbnew.PCB_VIA(board);hole.SetPosition(at);hole.SetWidth(900000);hole.SetDrill(600000)
        hole.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(hole)
        bore=pcbnew.SHAPE_CIRCLE(at,300000)
    else:
        fp=pcbnew.FOOTPRINT(board);board.Add(fp);hole=pcbnew.PAD(fp)
        hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH);hole.SetPosition(at)
        hole.SetSize(pcbnew.VECTOR2I_MM(.9,.6));hole.SetDrillSize(pcbnew.VECTOR2I_MM(.9 if hole_kind=='slotted_npth'else .6,.6))
        if hole_kind=='slotted_npth':hole.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG)
        fp.Add(hole);bore=hole.GetEffectiveHoleShape()
    full=pcbnew.SHAPE_POLY_SET();full.NewOutline()
    for x,y in((4,7),(9,7),(9,9),(4,9)):full.Append(x*1000000,y*1000000)
    void=pcbnew.SHAPE_POLY_SET();bore.TransformToPolygon(void,1,pcbnew.ERROR_OUTSIDE);full.BooleanSubtract(void)
    z=pcbnew.ZONE(board);z.SetLayer(0);z.SetNet(board.FindNet('GND'))
    z.Outline().NewOutline()
    for x,y in((4,7),(9,7),(9,9),(4,9)):z.Outline().Append(x*1000000,y*1000000)
    z.SetFilledPolysList(0,full);z.SetIsFilled(True);board.Add(z)
    with pytest.raises(ValueError,match='already_covered_by_source_copper'):
        op._new_surface_material(board,[[5000000,8000000],[8000000,8000000]],0,time.monotonic()+10.)


def test_actual_source_width_is_not_a_caller_parameter_and_saved_wrong_width_refuses(tmp_path):
    board,source,params,root,via,point=fixture(tmp_path);proposal=op.plan(source,**params)
    child=op.construct(proposal)
    old={force._uid(t)for t in board.GetTracks()}
    next(t for t in child.GetTracks()if force._uid(t)not in old).SetWidth(499999)
    candidate=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(child,candidate)
    result=op.receive(source,candidate,**params)
    assert not result['ok']and not result['complete'],result
    with pytest.raises(TypeError):op._new_surface_material(board,params['points_nm'],0,time.monotonic()+10.,width_nm=1)


def test_material_deadline_is_not_extended(tmp_path):
    board,source,params,root,via,point=fixture(tmp_path)
    with pytest.raises(ValueError,match='source_sheet_deadline'):
        op._new_surface_material(board,params['points_nm'],0,time.monotonic()-1.)


def test_capsule_novelty_never_waives_existing_covered_backtrack_craft_guard(tmp_path):
    board,source,params,root,via,point=fixture(tmp_path,endpoint_aliases=True)
    proposal=op.plan(source,**params);child=op.construct(proposal);additive._ground_refill(child)
    candidate=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(child,candidate)
    result=op.receive(source,candidate,**params)
    assert not result['ok']and any('worsened_whole_native_trace_craft'in e for e in result['errors']),result


def test_saved_replay_preserves_literal_ordered_nested_source_groups(tmp_path):
    import cec_additive_pair_repair as saving
    board,source,params,root,via,point=fixture(tmp_path)
    tracks=list(board.GetTracks())
    inner=pcbnew.PCB_GROUP(board);inner.SetName('existing inner');board.Add(inner)
    inner.AddItem(tracks[-1]);inner.AddItem(tracks[0])
    outer=pcbnew.PCB_GROUP(board);outer.SetName('existing outer');board.Add(outer)
    outer.AddItem(inner);outer.AddItem(root.GetParentFootprint())
    field._save_field_snapshot(board,source)
    original=source.read_bytes()
    proposal=op.plan(source,**params);child=op.construct(proposal)
    old={force._uid(t)for t in board.GetTracks()}
    added=[force._uid(t)for t in child.GetTracks()if force._uid(t)not in old]
    candidate=force._copy_family(source,tmp_path/'literal-candidate')
    saving.save_native_additions(candidate,child,dict(created_uuids=added),old,board_hint='synthetic')
    result=op.receive(source,candidate,**params)
    assert result['ok']and result['complete'],result
    assert source.read_bytes()==original
    source_groups=[n for n in additive._nodes(source)[1].values()if n[0]=='group']
    candidate_groups=[n for n in additive._nodes(candidate)[1].values()if n[0]=='group']
    assert source_groups==candidate_groups
    altered=candidate.read_text().replace('existing outer','unrelated group mutation')
    candidate.write_text(altered)
    refused=op.receive(source,candidate,**params)
    assert not refused['ok']and not refused['complete'],refused

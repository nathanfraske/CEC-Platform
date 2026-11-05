"""Real native reserved copper rejects one causal pose, not every cap combination."""
import copy
from pathlib import Path
import pcbnew
import pytest
from shapely.geometry import box
import cec_field_coupling as field
import cec_force_current as force
import cec_native_cell_pose_domains as poses
import cec_escape_pose_frontier as surface
from test_lastmile import _board


def fixture(tmp_path,quarter=0,back=False):
    board=_board([],edge=(0,0,30,30));face=pcbnew.B_Cu if back else pcbnew.F_Cu
    for name in ('GND','/renamed/force_bus'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    for ref,at in (('Q83',(5,5)),('C71',(5,8))):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue('opaque-package')
        fp.SetFPID(pcbnew.LIB_ID('synthetic','NativeSurface'))
        board.Add(fp);fp.SetPosition(pcbnew.VECTOR2I_MM(*at));fp.SetLayer(face)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
        layer_set=pcbnew.LSET();layer_set.AddLayer(face);pad.SetLayerSet(layer_set)
        pad.SetNetCode(board.GetNetcodeFromNetname('GND'));pad.SetPosition(fp.GetPosition());fp.Add(pad)
    zone=pcbnew.ZONE(board);zone.SetLayer(face)
    zone.SetNetCode(board.GetNetcodeFromNetname('/renamed/force_bus'))
    zone.SetLocalClearance(pcbnew.FromMM(.2))
    poly=zone.Outline();poly.NewOutline()
    for x,y in ((10,10),(12,10),(12,12),(10,12)):
        poly.Append(round(x*1e6),round(y*1e6))
    zone.SetFilledPolysList(face,poly);zone.SetIsFilled(True);board.Add(zone)
    angle=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
    for fp in board.GetFootprints():fp.Rotate(pcbnew.VECTOR2I_MM(15,15),angle)
    zone.Rotate(pcbnew.VECTOR2I_MM(15,15),angle)
    source=Path(tmp_path)/'source.kicad_pcb';field._save_field_snapshot(board,source)
    parent=pcbnew.LoadBoard(str(source));private=pcbnew.LoadBoard(str(source))
    foreign=next(iter(private.Zones()));bounds=foreign.GetBoundingBox()
    owner=private.FindFootprintByReference('Q83')
    owner.SetPosition(pcbnew.VECTOR2I((bounds.GetLeft()+bounds.GetRight())//2,
        (bounds.GetTop()+bounds.GetBottom())//2))
    selected={ref:dict(id='blocked'if ref=='Q83'else'stay',ref=ref,cost=0.,
        pose=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()])
        for ref in ('Q83','C71')for fp in [private.FindFootprintByReference(ref)]}
    report=surface.surface_screen(private,['Q83'],selected_refs=tuple(selected),timeout_s=10.)
    assert report['ok']is False and report['conflicts']
    return source,parent,private,selected,report,force._uid(foreign)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_saved_reserved_zone_yields_only_the_blocked_owner_pose(tmp_path,quarter,back):
    source,parent,private,selected,report,zone=fixture(tmp_path,quarter,back)
    before=source.read_bytes();native=field._field_snapshot_inventory(private)
    result=poses._immutable_surface_pose_feedback(parent,private,selected,report)
    assert result['complete']and len(result['clauses'])==1
    row=result['clauses'][0]
    assert(row['ref'],row['choice_id'],row['foreign_zone_uuid'])==('Q83','blocked',zone)
    assert row['actual_native_land_rechecked']and row['zone_outline_and_fill_and_rule_unchanged']
    assert row['other_owner_choices_not_rejected']and not result['routing_admitted']
    assert not result['release_authority']and not result['no_path_proof']
    assert source.read_bytes()==before and field._field_snapshot_inventory(private)==native


@pytest.mark.parametrize('mutation',['outline','fill','clearance','Ground','missing_zone',
    'wrong_pad','wrong_pin','wrong_pose','wrong_layer','fake_collision','incomplete','fixed_owner'])
def test_changed_or_unproved_foreign_context_cannot_become_a_unary_constraint(tmp_path,mutation):
    source,parent,private,selected,report,zone=fixture(tmp_path)
    old=next(iter(parent.Zones()));child=next(iter(private.Zones()));options={}
    if mutation=='outline':child.Outline().Append(13000000,12000000)
    elif mutation=='fill':child.SetFilledPolysList(pcbnew.F_Cu,pcbnew.SHAPE_POLY_SET())
    elif mutation=='clearance':child.SetLocalClearance(pcbnew.FromMM(.3))
    elif mutation=='Ground':
        for board,z in ((parent,old),(private,child)):z.SetNetCode(board.GetNetcodeFromNetname('GND'))
    elif mutation=='missing_zone':private.Remove(child)
    elif mutation=='wrong_pad':report['conflicts'][0]['pad_uuid']='not-a-native-land'
    elif mutation=='wrong_pin':report['conflicts'][0]['pin']='7'
    elif mutation=='wrong_pose':selected['Q83']['pose'][0]+=.001
    elif mutation=='wrong_layer':report['conflicts'][0]['layer']='not-a-real-layer'
    elif mutation=='fake_collision':
        fp=private.FindFootprintByReference('Q83');fp.SetPosition(pcbnew.VECTOR2I_MM(4,4))
        selected['Q83']['pose'][:2]=[4,4]
    elif mutation=='incomplete':report['source_unchanged']=False
    elif mutation=='fixed_owner':options['fixed_refs']=['Q83']
    result=poses._immutable_surface_pose_feedback(parent,private,selected,report,**options)
    assert result['clauses']==[]and not result['routing_admitted']and not result['no_path_proof']


def test_native_causal_feedback_avoids_repeating_one_owner_with_every_cap_choice(tmp_path):
    source,parent,private,selected,report,zone=fixture(tmp_path)
    feedback=poses._immutable_surface_pose_feedback(parent,private,selected,report)
    rejected={(q['ref'],q['choice_id'])for q in feedback['clauses']}
    domains={'Q83':[dict(selected['Q83']),dict(selected['Q83'],id='other-owner-pose',cost=1.)],
        'C71':[dict(selected['C71'],id=str(i),cost=i*.01)for i in range(32)]}
    original=copy.deepcopy(domains)
    filtered=poses._pose_domains_without_unary_refusals(domains,rejected)
    members={(ref,q['id']):[dict(kind='court',face=0,
        geometry=box(0,0,1,1)if ref=='Q83'else box(5,5,6,6))]
        for ref,choices in domains.items()for q in choices}
    result=poses.solve(filtered,members)
    assert result['complete']and result['selected']['Q83']['id']=='other-owner-pose'
    assert len(filtered['C71'])==32 and domains==original
    assert not result['routing_admitted']and not result['construction_authority']


def test_pruned_finite_domain_does_not_claim_global_infeasibility(tmp_path):
    source,parent,private,selected,report,zone=fixture(tmp_path)
    filtered=poses._pose_domains_without_unary_refusals({'Q83':[selected['Q83']]},{('Q83','blocked')})
    result=poses.solve(filtered,{})
    assert not result['complete']and not result['no_path_proof']and not result['routing_admitted']

"""Same-land dominance is actual copper evidence, never same-net proximity."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_redundant_ground_dogbone as op
from cec_native_items import discard_items
from test_field_proposals import track
from test_redundant_local_ground_return import fixture as original_fixture


def fixture(tmp_path,angle=0,layer=pcbnew.F_Cu):
    source,b,old_uid=original_fixture(tmp_path)
    discard_items(b,[t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND'])
    old=next(v for v in b.GetTracks() if force._uid(v)==old_uid)
    root=next(v for v in b.GetTracks() if v.GetClass()=='PCB_VIA' and tuple(v.GetPosition())==(10000000,15000000))
    old.SetPosition(pcbnew.VECTOR2I_MM(11.125,15));root.SetPosition(pcbnew.VECTOR2I_MM(10,14.1))
    next(g for g in b.Groups() if g.ContainsItem(old)).AddItem(root)
    lead=track(b,'GND',(10,15),(11.125,15),width=.2,layer=layer)
    keep=track(b,'GND',(10,15),(10,14.1),width=.2,layer=layer)
    cap=b.FindFootprintByReference('C173');cap.SetLayer(layer)
    for pad in cap.Pads():
        ls=pcbnew.LSET();ls.AddLayer(layer);pad.SetLayerSet(ls)
    if angle:
        for item in [*b.GetFootprints(),*b.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    return source,pcbnew.LoadBoard(str(source)),old_uid,force._uid(root),force._uid(lead),force._uid(keep)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_deletion_reuses_same_land_dogbone_and_actual_two_plane_bridge(tmp_path,angle,layer):
    source,b,old,root,lead,keep=fixture(tmp_path,angle,layer);before=source.read_bytes()
    q=op.plan(b,source,old,root,allow_source_locked=True)
    assert q['retired_track_uuids']==sorted([old,lead])
    assert q['source_kernel_length_mm']==pytest.approx(1.125)
    assert q['retained_departure_length_mm']==pytest.approx(.9)
    target=force._copy_family(source,tmp_path/'candidate');op.subtract(b,q)
    additive._ground_refill(b);field._save_field_snapshot(b,target)
    r=op.receive(source,target,q,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert r['all_surviving_native_partitions_preserved'] and r['all_known_ground_returns']['ok']
    assert r['no_new_copper_holes_or_poses'] and len(r['actual_saved_reference_plane_bridges'])==2
    assert {force._uid(t) for t in b.GetTracks()}=={
        force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}-{old,lead}
    assert root in {force._uid(t) for t in b.GetTracks()} and keep in {force._uid(t) for t in b.GetTracks()}
    assert source.read_bytes()==before and not r['release_authority'] and not r['current_qualified']


@pytest.mark.parametrize('fault',['group_locked','group_renamed','ungrouped','ordinary_barrel',
    'new_route_missing','new_route_longer','old_inner_departure','old_surface_branch',
    'grouped_lead','masked_lead','thin_lead','off_axis','new_partial_overlap',
    'another_ground_land','external_join','unfilled','no_lock_authority','unsaved_source'])
def test_only_the_exact_dominated_generated_departure_can_be_retired(tmp_path,fault):
    source,b,old_uid,root_uid,lead_uid,keep_uid=fixture(tmp_path)
    live={force._uid(t):t for t in b.GetTracks()};old,root,lead,keep=[live[u] for u in (old_uid,root_uid,lead_uid,keep_uid)]
    group=next(g for g in b.Groups() if g.ContainsItem(old))
    if fault=='group_locked':group.SetLocked(True)
    elif fault=='group_renamed':group.SetName('STRUCTURAL_RETURN')
    elif fault=='ungrouped':group.RemoveItem(old)
    elif fault=='ordinary_barrel':old.SetWidth(600000);old.SetDrill(300000)
    elif fault=='new_route_missing':discard_items(b,[keep])
    elif fault=='new_route_longer':root.Move(pcbnew.VECTOR2I_MM(0,-.65));keep.SetEnd(root.GetPosition())
    elif fault=='old_inner_departure':track(b,'GND',(11.125,15),(12,15),width=.2,layer=pcbnew.In2_Cu)
    elif fault=='old_surface_branch':track(b,'GND',(11.125,15),(11.125,16),width=.2)
    elif fault=='grouped_lead':group.AddItem(lead)
    elif fault=='masked_lead':lead.SetHasSolderMask(True)
    elif fault=='thin_lead':lead.SetWidth(199999)
    elif fault=='off_axis':old.Move(pcbnew.VECTOR2I(0,10000));lead.SetEnd(old.GetPosition())
    elif fault=='new_partial_overlap':root.Move(pcbnew.VECTOR2I_MM(0,.2));keep.SetEnd(root.GetPosition())
    elif fault=='another_ground_land':
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('OTHER_OWNER');b.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetNet(b.FindNet('GND'));pad.SetPosition(pcbnew.VECTOR2I_MM(10.7,15));pad.SetSize(pcbnew.VECTOR2I_MM(.25,.25))
        ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(ls);fp.Add(pad)
    elif fault=='external_join':b.FindFootprintByReference('C173').FindPadByNumber('2').SetSize(pcbnew.VECTOR2I_MM(.1,.1))
    elif fault=='unfilled':next(iter(b.Zones())).UnFill()
    elif fault=='unsaved_source':b.FindFootprintByReference('C173').SetValue('2.2uF')
    if fault!='unsaved_source':field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.plan(b,source,old_uid,root_uid,allow_source_locked=fault!='no_lock_authority')
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['extra_cut','keep_cut','lead_width','component_value','outline','group','source_plan'])
def test_saved_receiver_cannot_hide_unowned_edits_or_forged_worker_lists(tmp_path,fault):
    source,b,old,root,lead,keep=fixture(tmp_path);q=op.plan(b,source,old,root,allow_source_locked=True)
    op.subtract(b,q);target=force._copy_family(source,tmp_path/'candidate')
    if fault=='extra_cut':discard_items(b,[next(t for t in b.GetTracks() if force._uid(t) not in {root,keep})])
    elif fault=='keep_cut':discard_items(b,[next(t for t in b.GetTracks() if force._uid(t)==keep)])
    elif fault=='lead_width':next(t for t in b.GetTracks() if force._uid(t)==keep).SetWidth(199999)
    elif fault=='component_value':b.FindFootprintByReference('C173').SetValue('another_part')
    elif fault=='outline':next(d for d in b.GetDrawings() if d.GetLayer()==pcbnew.Edge_Cuts).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='group':next(iter(b.Groups())).SetName('ANOTHER_PROCESS')
    else:q=copy.deepcopy(q);q['retired_track_uuids'].append(root)
    additive._ground_refill(b);field._save_field_snapshot(b,target)
    r=op.receive(source,target,q,board_hint='synthetic')
    assert not r['ok'] and not r['complete'] and r['errors'] and not r['release_authority'],r


def test_discovery_is_native_and_does_not_require_named_components_or_a_drc_error(tmp_path):
    source,b,old,root,*_=fixture(tmp_path);fp=b.FindFootprintByReference('C173')
    fp.SetReference('C_FROM_ANOTHER_BOARD');field._save_field_snapshot(b,source)
    before=source.read_bytes();r=op.discover(b,source,allow_source_locked=True)
    assert r['complete'] and r['candidate_inventory_complete'] and len(r['plans'])==1
    assert r['plans'][0]['via_uuid']==old and r['plans'][0]['retained_via_uuid']==root
    assert not r['source_mutated'] and source.read_bytes()==before


def test_native_serialization_of_an_exactly_emptied_process_group_is_replayed(tmp_path):
    source,b,old,root,*_=fixture(tmp_path)
    next(g for g in b.Groups() if any(force._uid(i)==old for i in g.GetItems())).RemoveItem(
        next(t for t in b.GetTracks() if force._uid(t)==root))
    field._save_field_snapshot(b,source);q=op.plan(b,source,old,root,allow_source_locked=True)
    op.subtract(b,q);target=force._copy_family(source,tmp_path/'candidate')
    additive._ground_refill(b);field._save_field_snapshot(b,target)
    r=op.receive(source,target,q,board_hint='synthetic')
    assert r['ok'] and r['complete'],r


@pytest.mark.parametrize('options',[dict(allow_source_locked=1),dict(maximum_candidates=True),
    dict(maximum_candidates=0),dict(maximum_candidates=9),dict(timeout_s=True),dict(timeout_s=11)])
def test_untyped_or_unbounded_discovery_is_not_cut_authority(tmp_path,options):
    source,b,*_=fixture(tmp_path)
    with pytest.raises(ValueError):op.discover(b,source,**options)

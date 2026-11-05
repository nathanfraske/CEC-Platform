"""Batch selection is geometric, bounded, source-local and never a rating."""
import copy
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_rectilinear_copper as native
import cec_regional_fill as regional
import cec_reentrant_pocket_geometry as geometry
import cec_shallow_copper_pocket_cover as shallow
import cec_source_retaining_boundary_batch as batch
import cec_native_copper_delta as delta
import cec_field_coupling as field
from test_shallow_copper_pocket_cover import SOURCE,orient
from test_source_retaining_boundary_pocket import fixture

@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_reentrant_selection_and_native_merge_rotate_and_mirror(turn,back):
    points=orient(SOURCE,turn,back)
    offers=[o for o in shallow.candidates(points) if geometry.reentrant(o)]
    assert offers
    for offer in offers:
        merged=geometry.merged(points,offer['points_nm'])
        assert len(merged)<len(points)
        lost=native._poly(points);lost.BooleanSubtract(native._poly(merged))
        assert not lost.OutlineCount()

def test_convex_purposeful_chamfer_is_not_a_reentrant_defect():
    points=[[200000,0],[3800000,0],[4000000,200000],[4000000,3800000],
        [3800000,4000000],[200000,4000000],[0,3800000],[0,200000]]
    offers=shallow.candidates(points)
    assert offers and not any(geometry.reentrant(o) for o in offers)

@pytest.mark.parametrize('legacy',[False,True])
@pytest.mark.parametrize('mode',['local_overlap','inset_copy'])
def test_actual_native_batch_keeps_source_and_is_local_with_real_joined_progress(tmp_path,legacy,mode):
    source,uid=fixture(tmp_path,legacy)
    proposal=batch.plan(source,board_hint='synthetic_not_hardware',support_mode=mode)
    assert [r['zone_uuid'] for r in proposal['records']]==[uid]
    old=pcbnew.LoadBoard(str(source));new=batch.construct(source,proposal)
    original=next(z for z in old.Zones() if force._uid(z)==uid)
    child=next(z for z in new.Zones() if force._uid(z)==uid)
    before=original.GetFilledPolysList(pcbnew.F_Cu);after=child.GetFilledPolysList(pcbnew.F_Cu)
    assert regional.exact_source_contour_present(after,before,time.monotonic()+10.)
    row=proposal['records'][0]
    permitted=geometry.local_mask(before,row['source_points_nm'],row['points_nm'],row['source_configuration']['min_thickness_nm'])
    fresh=after.CloneDropTriangulation();fresh.BooleanSubtract(before)
    spill=fresh.CloneDropTriangulation();spill.BooleanSubtract(permitted)
    assert not spill.OutlineCount()
    material=delta.compare(old,new,net='SYNTH_POCKET',layer_ids=[pcbnew.F_Cu])
    assert material['ok'] and material['complete'],material['errors']
    assert material['faces'][0]['definitely_added_area_mm2']>=.0025
    if legacy:
        strong=next(z for z in old.Zones() if z.GetAssignedPriority()==10)
        void=strong.Outline().CloneDropTriangulation();void.BooleanSubtract(strong.GetFilledPolysList(pcbnew.F_Cu))
        fresh.BooleanIntersection(void);assert not fresh.OutlineCount()

@pytest.mark.parametrize('key,value',[('maximum_zones',0),('maximum_zones',9),('maximum_pockets_per_zone',9),
    ('maximum_guarded_offers',65),('start_zone_rank',129),('maximum_zones',True)])
def test_batch_search_domain_is_finite(tmp_path,key,value):
    source,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='finite_source_pocket_batch_required'):
        batch.plan(source,board_hint='synthetic_not_hardware',**{key:value})

@pytest.mark.parametrize('fault',['local_profile','source_process','owner'])
def test_batch_profile_process_and_owner_forgery_cannot_construct(tmp_path,fault):
    source,_=fixture(tmp_path)
    proposal=batch.plan(source,board_hint='synthetic_not_hardware');bad=copy.deepcopy(proposal)
    if fault=='local_profile':bad['records'][0]['points_nm'][0][0]+=100
    elif fault=='source_process':bad['records'][0]['source_configuration']['min_thickness_nm']=1
    else:bad['records'][0]['zone_uuid']='not-the-source-owner'
    with pytest.raises(ValueError,match='stale_or_forged'):batch.construct(source,bad)

def test_merged_must_improve_not_duplicate_an_existing_profile():
    with pytest.raises(ValueError,match='strict_batch_boundary_vertex_improvement_required'):
        geometry.merged(SOURCE,SOURCE)

def test_native_refilled_round_edges_cannot_emit_remote_boolean_scraps(tmp_path):
    source,uid=fixture(tmp_path);board=pcbnew.LoadBoard(str(source))
    zone=next(z for z in board.Zones() if force._uid(z)==uid);selected=pcbnew.ZONES();selected.append(zone)
    import cec_zone_fill
    cec_zone_fill.compile_selected(board,selected,timeout_s=10.)
    assert zone.GetFilledPolysList(pcbnew.F_Cu).Outline(0).PointCount()>8
    field._save_field_snapshot(board,source)
    proposal=batch.plan(source,board_hint='synthetic_not_hardware');child=batch.construct(source,proposal)
    old=pcbnew.LoadBoard(str(source));original=next(z for z in old.Zones() if force._uid(z)==uid)
    result=next(z for z in child.Zones() if force._uid(z)==uid).GetFilledPolysList(pcbnew.F_Cu)
    assert regional.exact_source_contour_present(result,original.GetFilledPolysList(pcbnew.F_Cu),time.monotonic()+10.)
    fresh=result.CloneDropTriangulation();count=original.GetFilledPolysList(pcbnew.F_Cu).OutlineCount()
    for i in reversed(range(fresh.OutlineCount()-count,fresh.OutlineCount())):fresh.RemoveOutline(i)
    fresh.BooleanSubtract(original.GetFilledPolysList(pcbnew.F_Cu))
    row=proposal['records'][0];window=geometry.addition_window(row['source_points_nm'],row['points_nm'],row['source_configuration']['min_thickness_nm'])
    fresh.BooleanSubtract(window);assert not fresh.OutlineCount()

def test_authored_outline_improvement_hidden_by_existing_copper_is_not_progress(tmp_path):
    source,_=fixture(tmp_path);board=pcbnew.LoadBoard(str(source))
    z=pcbnew.ZONE(board);z.SetNet(next(iter(board.GetPads())).GetNet());z.SetLayer(pcbnew.F_Cu)
    z.SetZoneName('SYNTHETIC_EXISTING_FULL_COVER');z.SetAssignedPriority(10);z.SetMinThickness(100000)
    points=[[2000000,2000000],[8000000,2000000],[8000000,6000000],[2000000,6000000]]
    z.Outline().Append(native._poly(points));z.SetFilledPolysList(pcbnew.F_Cu,native._poly(points));z.SetIsFilled(True);board.Add(z)
    field._save_field_snapshot(board,source)
    proposal=batch.plan(source,board_hint='synthetic_not_hardware');child=force._copy_family(source,tmp_path/'hidden-child')
    field._save_field_snapshot(batch.construct(source,proposal),child)
    proof=batch.receive(source,child,proposal,board_hint='synthetic_not_hardware')
    assert not proof['ok'] and any('authored_outline_only_or_insufficient_visible_native_progress' in e for e in proof['errors'])

@pytest.mark.parametrize('fault',['field','extra_track'])
def test_batch_saved_child_cannot_smuggle_unowned_changes(tmp_path,fault):
    source,_=fixture(tmp_path);proposal=batch.plan(source,board_hint='synthetic_not_hardware')
    child=force._copy_family(source,tmp_path/'forged-child');board=batch.construct(source,proposal)
    if fault=='field':next(iter(board.GetFootprints())).SetReference('FORGED')
    else:
        t=pcbnew.PCB_TRACK(board);t.SetNet(next(iter(board.GetPads())).GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(100000)
        t.SetStart(pcbnew.VECTOR2I(3000000,3000000));t.SetEnd(pcbnew.VECTOR2I(4000000,3000000));board.Add(t)
    field._save_field_snapshot(board,child)
    proof=batch.receive(source,child,proposal,board_hint='synthetic_not_hardware')
    assert not proof['ok'] and any('changed_unowned_saved_native_evidence' in e for e in proof['errors'])

def test_authored_pocket_cannot_create_a_new_exterior_spur_past_actual_source_support(tmp_path):
    source,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));z=next(z for z in b.Zones() if force._uid(z)==uid)
    # Nominal outline still reaches y=6mm; actual saved source metal stops
    # at5.8mm. Filling that nominal "notch" would grow an exterior lip.
    z.SetFilledPolysList(pcbnew.F_Cu,native._poly([[2000000,2000000],[8000000,2000000],[8000000,5800000],[2000000,5800000]]))
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError,match='no_guarded_reentrant_source_pockets'):
        batch.plan(source,board_hint='synthetic_not_hardware')

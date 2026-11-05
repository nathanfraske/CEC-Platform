"""Exact native covers for integer-quantized inputs, not route tolerances."""
import copy
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_native_keeper_extension_receiving as extension
import cec_rectilinear_copper as owner
import cec_additive_route_receiving as additive
from cec_native_fill_geometry import identity
from test_signed_native_keeper_extension import native_fixture


def save_trial(tmp_path,angle=0,mirror=False,layer=pcbnew.F_Cu,retained=False):
    b,_,extra,z=native_fixture(angle,mirror,layer)
    extra.SetEnd(extra.GetEnd()+pcbnew.VECTOR2I(1,0));uid=force._uid(z);tid=force._uid(extra)
    before_row=owner._track_row(extra)
    assert not owner._centerline_allowed(before_row['start_nm'],before_row['end_nm'],'chamfer45')
    with pytest.raises(owner.Refused,match='native_manhattan_centerline_required'):
        extension.plan(b,[tid],required_width_nm=1000000,allow_signed_native_keeper=True)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    original=pcbnew.LoadBoard(str(source));c=pcbnew.LoadBoard(str(source))
    plan=extension.plan(c,[tid],required_width_nm=1000000,allow_signed_native_keeper=True,
        source_diagonal_quantum_nm=1,retained_native_track_material=retained)
    emitted=owner.materialize(c,plan);owner.fill(c,plan,uid,regional_source=original)
    additive._ground_refill(c);child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(c,child)
    return source,child,plan,emitted,before_row


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('retained',[False,True])
def test_quantized_input_never_moves_and_all_actual_capsule_material_is_in_canonical_fill(tmp_path,angle,mirror,layer,retained):
    source,child,plan,emitted,before=save_trial(tmp_path,angle,mirror,layer,retained)
    original=pcbnew.LoadBoard(str(source));saved=pcbnew.LoadBoard(str(child));old_bytes=source.read_bytes()
    proof=owner.receive(saved,plan,emitted['zone_uuid'],regional_source=original,timeout_s=10.)
    assert proof['ok'] and proof['complete'],proof
    assert proof['quantized_source_diagonal_track_uuids']==[before['uuid']]
    actual=next(t for t in saved.GetTracks() if force._uid(t)==before['uuid'])
    assert owner._track_row(actual)==before
    assert all(owner._centerline_allowed(a,b,'chamfer45') for a,b in
        zip(plan['polygon_nm'],plan['polygon_nm'][1:]+plan['polygon_nm'][:1]))
    witnesses,_=owner.enclosed_track_witnesses(saved,plan,emitted['zone_uuid'],regional_source=original,timeout_s=10.)
    assert witnesses==[]
    literal=extension.receive_literal_phase(source,child,[dict(plan=plan,materialized=emitted)],board_hint='synthetic')
    assert literal['ok'] and literal['complete'],literal
    assert source.read_bytes()==old_bytes and not proof['new_capacity_credited'] and not proof['release_authority']


@pytest.mark.parametrize('fault',['two_nm','bad_quantum','bool','retire','no_keeper','native_fill','recompile','square'])
def test_quantum_policy_cannot_authorize_arbitrary_angles_or_mutations(fault):
    b,_,extra,z=native_fixture();extra.SetEnd(extra.GetEnd()+pcbnew.VECTOR2I(1,0))
    kw=dict(required_width_nm=1000000,clearance_nm=200000,min_thickness_nm=100000,
        replace_native_zone_uuid=force._uid(z),enclosing_native_zone_uuids=[force._uid(z)],
        retire_source_tracks=False,fill_policy='source_preserving_regions',allow_signed_native_keeper=True,
        contour_style='chamfer45',source_diagonal_quantum_nm=1)
    if fault=='two_nm':extra.SetEnd(extra.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='bad_quantum':kw['source_diagonal_quantum_nm']=2
    elif fault=='bool':kw['source_diagonal_quantum_nm']=True
    elif fault=='retire':kw['retire_source_tracks']=True
    elif fault=='no_keeper':kw['replace_native_zone_uuid']=None
    elif fault=='native_fill':kw['fill_policy']='native'
    elif fault=='recompile':kw['rebuild_keeper_from_tracks']=True
    else:kw['contour_style']='square'
    with pytest.raises(owner.Refused):owner.plan(b,[force._uid(extra)],**kw)


def test_retained_real_track_cannot_launder_missing_quantized_fill(tmp_path):
    source,child,plan,emitted,row=save_trial(tmp_path,retained=True)
    before=pcbnew.LoadBoard(str(source));c=pcbnew.LoadBoard(str(child))
    z=next(z for z in c.Zones() if force._uid(z)==emitted['zone_uuid'])
    x,y=row['end_nm'];hole=owner._poly([(x-50000,y-50000),(x+50000,y-50000),
        (x+50000,y+50000),(x-50000,y+50000)])
    filled=z.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation();filled.BooleanSubtract(hole)
    z.SetFilledPolysList(pcbnew.F_Cu,filled)
    proof=owner.receive(c,plan,emitted['zone_uuid'],regional_source=before,timeout_s=10.)
    assert not proof['ok'] and not proof['complete']
    assert proof['reason']=='quantized_native_diagonal_requires_complete_actual_fill_cover',proof


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_foreign_fill_hole_bridges_are_exact_not_simplified_or_ignored(tmp_path,layer):
    b,_,extra,z=native_fixture(layer=layer)
    foreign=pcbnew.ZONE(b);foreign.SetNet(b.FindNet('/RENAMED_FOREIGN'));foreign.SetLayer(layer)
    outline=owner._poly([(60000000,60000000),(66000000,60000000),(66000000,66000000),(60000000,66000000)])
    foreign.Outline().Append(outline);b.Add(foreign)
    filled=outline.CloneDropTriangulation();filled.NewHole(0)
    for p in [(61000000,61000000),(61000000,62000000),(62000000,62000000),(62000000,61000000)]:
        filled.Append(*p,0,0)
    filled.Fracture(False);foreign.SetFilledPolysList(layer,filled);foreign.SetIsFilled(True)
    # Authored simple outlines still refuse a fractured ring. Native FILLS
    # now additionally prove exact bridge topology and zero loss/spill, then
    # preserve/hash their literal representation instead of blanket refusal.
    with pytest.raises(owner.Refused,match='unsupported_supporting_native_ring'):
        owner._shape_identity(filled,time.monotonic()+2.)
    validated=owner._support_row(foreign,int(layer),time.monotonic()+2.)
    native=owner._support_row(foreign,int(layer),time.monotonic()+2.,allow_native_hole_bridges=True)
    assert validated==native
    assert native['fill_sha256']==identity(filled,time.monotonic()+2.)[0]
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    before=pcbnew.LoadBoard(str(source));c=pcbnew.LoadBoard(str(source));foreign_id=force._uid(foreign)
    old=next(q for q in before.Zones() if force._uid(q)==foreign_id)
    old_identity=identity(old.GetFilledPolysList(layer),time.monotonic()+2.)
    plan=extension.plan(c,[force._uid(extra)],required_width_nm=1000000,allow_signed_native_keeper=True)
    emitted=owner.materialize(c,plan);owner.fill(c,plan,emitted['zone_uuid'],regional_source=before)
    additive._ground_refill(c);child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(c,child)
    proof=extension.receive_literal_phase(source,child,[dict(plan=plan,materialized=emitted)],board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    saved=pcbnew.LoadBoard(str(child));actual=next(q for q in saved.Zones() if force._uid(q)==foreign_id)
    assert identity(actual.GetFilledPolysList(layer),time.monotonic()+2.)==old_identity
    # The native representation policy grants no occupied-space permission.
    shifted=actual.GetFilledPolysList(layer).CloneDropTriangulation();shifted.Move(pcbnew.VECTOR2I_MM(-28,-30))
    actual.SetFilledPolysList(layer,shifted)
    with pytest.raises(owner.Refused,match='foreign_native_zone_'):
        owner._require_unoccupied_outline(saved,owner._poly(plan['polygon_nm']),plan['net'],int(layer),
            time.monotonic()+2.,allow_native_hole_bridges=True)

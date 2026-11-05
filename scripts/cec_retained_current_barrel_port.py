"""A fixed circular source-via entry, not new barrel/current authority.

A single straight radial launch through a concentric circular through barrel
has congruent annular contact metal under rotation about the unchanged bore.
Both old and new launches must reach beyond the outer land by half a trace
width; no other changed stroke may contact that annulus. Whole-covered lands
also have an exact rotation-independent full-annulus witness. Segmented
escapes instead require literal preservation of every native stroke touching
the annulus. This geometric equivalence does NOT qualify plating, ampacity,
temperature or fabrication.
"""
import time
import pcbnew
import cec_force_current as force
import cec_kelvin_copper_cut as native

POLICY='source_circular_barrels'


def contact_strokes(via,face,points,width,deadline):
    """Literal same-width stroke geometry touching the actual native land."""
    result=[];outer=via.GetEffectiveShape(face)
    for a,b in zip(points,points[1:]):
        if time.monotonic()>=deadline:raise ValueError('retained_current_barrel_contact_deadline')
        if outer.Collide(pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width),1):
            result.append(sorted([list(a),list(b)]))
    return sorted(result)


def _entry(via,face,points,width,at,deadline):
    if time.monotonic()>=deadline:raise ValueError('retained_current_barrel_contact_deadline')
    if tuple(points[0])==at:ordered=points
    elif tuple(points[-1])==at:ordered=list(reversed(points))
    else:raise ValueError('retained_current_barrel_must_be_a_literal_fixed_port')
    diameter=int(via.GetWidth(face));outer=via.GetEffectiveShape(face)
    if width>=diameter:
        # The endpoint's disk covers the whole native outer circle; subtract
        # the same unchanged bore, never count that bore itself as copper.
        return dict(method='fixed_endpoint_disk_covers_entire_annulus',diameter_nm=diameter)
    if 4*sum((ordered[1][i]-at[i])**2 for i in (0,1))<(diameter+width)**2:
        raise ValueError('source_or_candidate_barrel_radial_launch_is_too_short')
    for a,b in zip(ordered[1:],ordered[2:]):
        if time.monotonic()>=deadline:raise ValueError('retained_current_barrel_contact_deadline')
        shape=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width)
        if outer.Collide(shape,1):raise ValueError('multiple_changed_strokes_touch_source_barrel_annulus')
    return dict(method='single_full_width_straight_radial_annular_entry',diameter_nm=diameter,
        radial_launch_vector_nm=[ordered[1][i]-at[i] for i in (0,1)],
        required_straight_launch_extent_twice_nm=diameter+width)


def contact(board,via,face,source_points,candidate_points,width,deadline):
    at=tuple(via.GetPosition());layers=tuple(board.GetEnabledLayers().CuStack())
    size=via.GetPrimaryDrillSize()
    drill_ok=(size.x==size.y==via.GetDrillValue()) if hasattr(size,'x') else size==via.GetDrillValue()
    if (via.GetClass()!='PCB_VIA' or via.GetParentGroup() or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
            or {int(via.TopLayer()),int(via.BottomLayer())}!={pcbnew.F_Cu,pcbnew.B_Cu}
            or not via.IsOnLayer(face) or via.GetEffectiveShape(face).Type()!=pcbnew.SH_CIRCLE
            or via.GetPrimaryDrillShape()!=pcbnew.PAD_DRILL_SHAPE_CIRCLE or not drill_ok
            or not 0<via.GetDrillValue()<via.GetWidth(face) or not native._simple_drill(via,layers)):
        raise ValueError('simple_unchanged_concentric_source_current_barrel_required')
    if at not in (tuple(source_points[0]),tuple(source_points[-1])) or at not in (tuple(candidate_points[0]),tuple(candidate_points[-1])):
        raise ValueError('retained_current_barrel_must_be_a_literal_fixed_port')
    try:
        old=_entry(via,face,source_points,width,at,deadline)
        new=_entry(via,face,candidate_points,width,at,deadline)
        if old['method']!=new['method']:raise ValueError('source_barrel_contact_witness_method_changed')
    except ValueError as exc:
        if time.monotonic()>=deadline:raise
        first=contact_strokes(via,face,source_points,width,deadline)
        last=contact_strokes(via,face,candidate_points,width,deadline)
        if not first or first!=last:raise ValueError('source_annular_escape_fragments_not_identically_preserved:'+str(exc)) from exc
        reach=max(sum((p[i]-at[i])**2 for i in (0,1)) for segment in first for p in segment)
        if width<=via.GetDrillValue() and 4*reach<=(via.GetDrillValue()-width)**2:
            raise ValueError('source_escape_has_no_positive_physical_annular_metal_contact')
        old=new=dict(method='identical_actual_native_annular_escape_fragments',stroke_geometry_nm=first,
            source_and_candidate_annular_contact_copper_exactly_equal=True)
    return dict(uuid=force._uid(via),kind='PCB_VIA',fixed_port_nm=list(at),layer=face,
        actual_outer_diameter_nm=int(via.GetWidth(face)),actual_bore_diameter_nm=int(via.GetDrillValue()),
        annular_web_diameter_difference_nm=int(via.GetWidth(face)-via.GetDrillValue()),
        source_contact=old,candidate_contact=new,physical_annular_entry_congruent_under_centered_rotation=True,
        unchanged_bore_is_void_not_copper=True,source_barrel_capacity_debt_not_qualified=True,
        plating_current_thermal_and_fabrication_authority=False,release_authority=False)

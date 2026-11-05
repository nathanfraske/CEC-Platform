"""Source-owned readable reference maps, with explicit opposite-face fallback.

Only visible references implicated by an exact source native silk report are
eligible. A finite nearby miniature courtyard map is tried first. Otherwise
the actual projected courtyards and references may be printed on the opposite
surface. Native references remain authoritative and are only hidden after a
replacement is constructed. Parts, copper, BOM, values, MPNs and rules cannot
change. This is optional annotation tooling, not routing or fab admission.
"""
import argparse
import copy
from collections import Counter
from contextvars import ContextVar
import json
import hashlib
import math
import os
from pathlib import Path
import tempfile
import time
import uuid

import pcbnew
from shapely import affinity
from shapely.geometry import box
from shapely.ops import unary_union
from shapely.ops import nearest_points
import cec_additive_route_receiving as additive
import cec_assembly_envelope as assembly
import cec_board_geometry as geometry
import cec_copper_echo as syntax
import cec_fab_check as fab
import cec_fab_profile as profile
import cec_field_coupling as field
import cec_force_current as force
import cec_native_drc_runner as native
import cec_stage_admission as admission

POLICY = 'nearby-reference-map-else-opposite-face-projected-courtyard-v1'
GROUP = 'CEC_READABLE_COMPONENT_REFERENCE_MAPPING'


class _ConstructPlanMaterial:
    """One constructor's fresh Source, never a proposal or reusable verdict.

    The ordinary public planner and its mask-search wrapper still run in
    full. Only that invocation may transfer its own unmodified native Source
    and parsed UUID inventory to the immediately following materialization.
    Independent saved receiving always starts a separate fresh invocation.
    """
    __slots__ = ('source', 'board', 'source_ids', 'source_sha256', 'native_epoch')

    def __init__(self, source):
        self.source = Path(source).resolve()
        self.board = self.source_ids = self.source_sha256 = self.native_epoch = None


_CONSTRUCT_PLAN_MATERIAL = ContextVar('cec_reference_construct_plan_material', default=None)


def _plan_material_epoch(board):
    # The obstacle identity includes native footprint/root artwork, fields,
    # via settings and mask defaults. The independent field inventory also
    # covers every actual track and filled zone, not just annotation inputs.
    return (_obstacle_epoch(board), tuple(sorted(field._field_snapshot_inventory(board).items())))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def polygon(item, layer):
    p = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(p, layer, 0, 1000, pcbnew.ERROR_OUTSIDE, False)
    p.Simplify()
    s = assembly.polygon_from_native(p)
    require(s.is_valid, 'valid_native_legend_material_required')
    return s


def court(fp):
    p = fp.GetCourtyard(fp.GetLayer())
    require(p.OutlineCount() == 1 and p.HoleCount(0) == 0,
        'one_literal_closed_source_courtyard_required')
    shape = assembly.polygon_from_native(p)
    require(shape.is_valid and not shape.is_empty, 'valid_source_courtyard_required')
    return shape


def guide_body(fp, project_native_fab_body=False):
    """A body legend can project a Source Fab rectangle, never shrink a court.

    Deliberately recognize only one exact unfilled cardinal native Fab
    rectangle. Extra functional shapes, ambiguous bodies and other geometry
    fail closed. The actual manufacturing courtyard remains a separate,
    unchanged assembly/placement obstacle and is never replaced by this ink.
    """
    if not project_native_fab_body:return court(fp)
    face=pcbnew.B_Fab if fp.IsFlipped()else pcbnew.F_Fab
    art=[g for g in fp.GraphicalItems()if g.GetLayer()==face and g.GetClass()!='PCB_TEXT']
    require(len(art)==1 and art[0].GetClass()=='PCB_SHAPE'
        and art[0].GetShape()==pcbnew.SHAPE_T_RECT and not art[0].IsAnyFill()
        and fp.GetOrientationDegrees()%90==0,'one_exact_cardinal_source_fab_body_rectangle_required')
    a,z=art[0].GetStart(),art[0].GetEnd()
    shape=box(min(a.x,z.x)/1e6,min(a.y,z.y)/1e6,max(a.x,z.x)/1e6,max(a.y,z.y)/1e6)
    require(shape.is_valid and not shape.is_empty and shape.area>0
        and court(fp).covers(shape),'source_fab_body_must_be_inside_unchanged_manufacturing_courtyard')
    return shape


def make_text(board, text, at, layer, height, stroke, angle=0):
    t = pcbnew.PCB_TEXT(board); t.SetText(text)
    t.SetLayer(layer); t.SetMirrored(layer == pcbnew.B_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(round(height*1e6), round(height*1e6)))
    t.SetTextThickness(round(stroke*1e6))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    t.SetTextPos(pcbnew.VECTOR2I(round(at[0]*1e6), round(at[1]*1e6)))
    t.SetTextAngle(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T)); t.SetKeepUpright(True)
    return t


def make_outline(board, shape, layer, stroke):
    require(shape.geom_type == 'Polygon' and not shape.interiors,
        'one_closed_projected_legend_courtyard_required')
    points = list(shape.exterior.coords); result = []
    require(4 <= len(points) <= 257, 'bounded_projected_courtyard_outline_required')
    for a,z in zip(points,points[1:]):
        t = pcbnew.PCB_SHAPE(board); t.SetShape(pcbnew.SHAPE_T_SEGMENT)
        t.SetStart(pcbnew.VECTOR2I(round(a[0]*1e6),round(a[1]*1e6)))
        t.SetEnd(pcbnew.VECTOR2I(round(z[0]*1e6),round(z[1]*1e6)))
        require(t.GetStart() != t.GetEnd(), 'positive_native_projected_courtyard_edge_required')
        t.SetLayer(layer); t.SetWidth(round(stroke*1e6)); result.append(t)
    return result


def floors(board, source):
    declared = profile.board_profile_name(board)
    require(declared is not None, 'declared_source_factory_profile_required_for_legend')
    # source_context has just loaded this exact Source. Use the identical
    # declared-profile resolver without loading the same native file again.
    resolved = profile.active_profile_name(board, hint=source)
    require(resolved == declared, 'source_factory_profile_resolution_changed')
    rules = fab.profile_rules(fab.PROFILES['jlcpcb'], profile.stackup_oz(resolved)['F.Cu'], declared)
    settings = board.GetDesignSettings()
    return dict(height=max(rules['silk_height'],settings.m_MinSilkTextHeight/1e6),
        stroke=max(rules['silk'],settings.m_MinSilkTextThickness/1e6),
        clearance=max(rules['silk_clearance'],settings.m_SilkClearance/1e6),
        edge=max(rules['edge'],rules['silk_clearance']),profile=declared)


def source_context(source, grade, board_hint):
    source = Path(source).resolve(); grade = Path(grade).resolve()
    j = json.loads(grade.read_text()); epoch = force._code_identity()
    require(j['code_identity'] == epoch, 'source_native_legend_grade_epoch_changed')
    matching=[k for k in ('candidate','source') if k in j['boards'] and j['boards'][k]['sha256']==force._hash(source)]
    if matching:
        produced=j['boards'][matching[0]]['native_producer']
    else:
        # Read the real completed suite receipt directly. Never relabel an
        # old producer, copy a current code hash onto stale evidence or choose
        # a board by its latest filename. All original producer checks below
        # apply identically to this explicitly named, exact source row.
        require(j.get('kind')=='fresh-native-parity-and-early-intake'
            and j.get('code_unchanged')is True and j.get('plan_unchanged')is True,
            'actual_saved_source_reference_grade_binding_required')
        row=j['boards'].get(board_hint,{})
        require(row.get('sha256')==force._hash(source)
            and Path(row.get('path','')).resolve()==source
            and all(row.get(k)is True for k in('source_unchanged','source_family_unchanged',
                'source_inputs_unchanged','source_intake_ok')),
            'exact_completed_suite_reference_source_binding_required')
        produced=row['producer']
    require(produced['ok'] and produced['complete'] and not produced['native_inventory']['potentially_truncated'],
        'complete_uncapped_source_silk_report_required')
    report = Path(produced['report']); require(force._hash(report) == produced['report_sha256'],
        'source_native_silk_report_changed')
    require(any(p.endswith('.kicad_pcb') and h == force._hash(source)
        for p,h in produced['source_files'].items()), 'source_native_legend_board_binding_required')
    b = pcbnew.LoadBoard(str(source)); f = floors(b, source)
    # KiCad drops unresolved/empty board groups on a subsequent save. In
    # particular, a board group cannot durably own footprint-child graphics.
    # Do not let an unrelated annotation transaction silently retire such
    # Source metadata. The separately received legacy-group repair owns it.
    require(all(list(g.GetItems()) for g in b.Groups()),
        'source_contains_nonroundtrip_group_requires_separate_repair')
    return b,f,json.loads(report.read_text()),dict(source=str(source),source_sha256=force._hash(source),
        source_family=force._family(source,board_hint),grade=str(grade),grade_sha256=force._hash(grade),
        native_report=str(report),native_report_sha256=force._hash(report),code_identity=epoch,
        authority_sha256=force._hash(Path(__file__).resolve()),factory_legend=f)


def _obstacle_epoch(board):
    """Read live native inputs without saving/normalizing the Source board."""
    fps=list(board.GetFootprints());drawings=list(board.GetDrawings())
    vias=[i for i in board.GetTracks()if i.GetClass()=='PCB_VIA']
    require(len(fps)+len(drawings)+len(vias)<=16384,'bounded_reference_obstacle_epoch_required')
    writer=pcbnew.PCB_IO_KICAD_SEXPR();digest=hashlib.sha256();total=0
    for item in [*fps,*drawings,*vias]:
        writer.Format(item);text=writer.GetStringOutput(True);total+=len(text)
        require(total<=32*1024*1024,'bounded_reference_obstacle_serialization_required')
        digest.update(text.encode());digest.update(b'\0')
    # Native pad apertures and via tenting may resolve board defaults that
    # are not explicit in an individual item's serialized record.
    resolved=[]
    for fp in fps:
        for pad in fp.Pads():
            resolved.append((force._uid(pad),pad.GetSolderMaskExpansion(pcbnew.F_Mask),
                pad.GetSolderMaskExpansion(pcbnew.B_Mask)))
    for via in vias:
        resolved.append((force._uid(via),via.IsTented(pcbnew.F_SilkS),via.IsTented(pcbnew.B_SilkS),
            via.GetSolderMaskExpansion(),via.GetLocalSolderMaskMargin(),
            via.GetFrontTentingMode(),via.GetBackTentingMode(),
            via.IsOnLayer(pcbnew.F_Mask),via.IsOnLayer(pcbnew.B_Mask)))
    settings=board.GetDesignSettings()
    mask_defaults=(settings.m_SolderMaskExpansion,settings.m_SolderMaskMinWidth,
        settings.m_SolderMaskToCopperClearance,settings.m_TentViasFront,settings.m_TentViasBack)
    digest.update(repr((resolved,mask_defaults,str(board.GetFileName()),board.GetProperties().asdict(),
        sorted(os.environ.items()))).encode())
    return digest.hexdigest()


class _ObstaclePreparation:
    """One planner's immutable negative geometry, never verdict authority."""
    def __init__(self,board):
        self.board=board;self.epoch=_obstacle_epoch(board);self.base={};self.artwork={};self._aperture_bytes={}

    def check(self,board):
        require(board is self.board and self.epoch==_obstacle_epoch(board),
            'reference_obstacle_native_inputs_changed')

    def material(self,board,face,excluded,policy):
        self.check(board);key=(int(face),frozenset(excluded),policy)
        if key not in self.base:
            ink,openings=_obstacle_material(board,face,excluded,policy,self)
            self.check(board);self.base[key]=(tuple(ink),tuple(openings))
        return self.base[key]

    def apertures(self,board,face,policy):
        """Same-plan native apertures, copied from immutable private WKB.

        Source-native epoch checks bracket extraction and precede every reuse.
        No mutable native polygon or caller-owned Shapely object enters the
        cache; independent plans and saved reconstruction own separate caches.
        """
        from shapely.wkb import loads
        import cec_rectangular_field_silk_clearance as native_mask
        self.check(board)
        require(face in(pcbnew.F_SilkS,pcbnew.B_SilkS)and policy in
            ('reserve_native_lands','native_mask_and_bore'),'exact_reference_aperture_face_policy_required')
        key=(int(face),policy)
        if key not in self._aperture_bytes:
            rows=native_mask._mask_openings(board,face,policy)
            converted=tuple((uid,assembly.polygon_from_native(poly).wkb)for uid,poly in rows)
            self.check(board);self._aperture_bytes[key]=converted
        return tuple((uid,loads(data))for uid,data in self._aperture_bytes[key])

    def mask_artwork(self,board,face,provider):
        self.check(board);key=int(face)
        if key not in self.artwork:
            shape,_=provider(board,face);self.check(board);self.artwork[key]=shape
        return self.artwork[key]


def _obstacle_material(board,face,excluded_fields,via_ink_policy,prepared=None):
    require(type(via_ink_policy)is str and via_ink_policy in
        ('reserve_native_lands','native_mask_and_bore'),'explicit_reference_native_mask_policy_required')
    ink = []; openings = []
    cu = pcbnew.F_Cu if face == pcbnew.F_SilkS else pcbnew.B_Cu
    for item in board.GetDrawings():
        if item.GetLayer() == face:
            ink.append(polygon(item, face))
    for fp in board.GetFootprints():
        for item in [*fp.GraphicalItems(),*fp.GetFields()]:
            if (item.GetLayer() == face and force._uid(item) not in excluded_fields
                    and (not hasattr(item,'IsVisible') or item.IsVisible())):
                ink.append(polygon(item,face))
        for pad in fp.Pads() if via_ink_policy=='reserve_native_lands'else ():
            if pad.IsOnLayer(cu):
                openings.append(assembly.polygon_from_native(pad.GetEffectivePolygon(cu,pcbnew.ERROR_OUTSIDE)))
            if pad.HasHole():
                p = pcbnew.SHAPE_POLY_SET(); pad.GetEffectiveHoleShape().TransformToPolygon(p,1000,pcbnew.ERROR_OUTSIDE)
                openings.append(assembly.polygon_from_native(p))
    for via in board.GetTracks() if via_ink_policy=='reserve_native_lands'else ():
        if via.GetClass() == 'PCB_VIA' and via.IsOnLayer(cu):
            # Conservatively reserve every land, even a potentially tented
            # one. No inferred mask exception is needed for this annotation.
            p = pcbnew.SHAPE_POLY_SET(); via.TransformShapeToPolygon(p,cu,0,1000,pcbnew.ERROR_OUTSIDE,False)
            openings.append(assembly.polygon_from_native(p))
    if via_ink_policy=='native_mask_and_bore':
        import cec_rectangular_field_silk_clearance as mask_geometry
        require(prepared is None or type(prepared)is _ObstaclePreparation,
            'planner_owned_reference_aperture_preparation_required')
        if prepared is not None:openings.extend(p for _,p in prepared.apertures(board,face,via_ink_policy))
        else:openings.extend(assembly.polygon_from_native(p)
            for _,p in mask_geometry._mask_openings(board,face,via_ink_policy))
    return ink,openings


def obstacles(board, face, excluded_fields, clearance, *, assembled_bodies,
              via_ink_policy='reserve_native_lands',reviewed_body_shapes=None,_prepared=None):
    require(_prepared is None or type(_prepared)is _ObstaclePreparation,
        'planner_owned_reference_obstacle_preparation_required')
    ink,openings=(_obstacle_material(board,face,excluded_fields,via_ink_policy)if _prepared is None
        else _prepared.material(board,face,excluded_fields,via_ink_policy))
    bodies=[];cu=pcbnew.F_Cu if face==pcbnew.F_SilkS else pcbnew.B_Cu
    if assembled_bodies:
        for fp in board.GetFootprints():
            if fp.GetLayer()!=cu:continue
            artwork_only=(not list(fp.Pads())and not list(fp.Models())
                and bool(fp.GetAttributes()&pcbnew.FP_BOARD_ONLY)
                and bool(fp.GetAttributes()&pcbnew.FP_EXCLUDE_FROM_BOM)
                and bool(fp.GetAttributes()&pcbnew.FP_EXCLUDE_FROM_POS_FILES))
            if not artwork_only:
                uid=force._uid(fp)
                bodies.append(reviewed_body_shapes[uid]if reviewed_body_shapes is not None
                    and uid in reviewed_body_shapes else court(fp))
    raw=unary_union([*ink,*openings,*bodies])
    return raw.buffer(clearance+0.002,join_style=2)


def shapes(board, models, face, f, *, positions=None, scale=1., origin=(0.,0.)):
    items = []; record = []
    for fp,original in models:
        shape = affinity.scale(original,xfact=scale,yfact=scale,origin=origin)
        if positions is not None:
            shape = affinity.translate(shape,positions[0],positions[1])
        center = shape.centroid; chosen = None
        inner = shape.buffer(-(f['stroke']/2+f['clearance']+0.002),join_style=2)
        for angle in (0,90):
            t = make_text(board,fp.GetReference(),(center.x,center.y),face,f['height'],f['stroke'],angle)
            ink = polygon(t,face)
            if inner.covers(ink):
                chosen = t; break
        require(chosen is not None, 'readable_reference_does_not_fit_projected_courtyard')
        outlines = make_outline(board,shape,face,f['stroke'])
        items.extend([*outlines,chosen])
        record.append(dict(footprint_uuid=force._uid(fp),reference_field_uuid=force._uid(fp.Reference()),
            reference=fp.GetReference(),courtyard_xy_mm=[list(p) for p in shape.exterior.coords],
            text_xy_mm=[center.x,center.y],text_angle_degrees=angle,
            actual_back_view_readable=face == pcbnew.B_SilkS,text_mirrored=face == pcbnew.B_SilkS))
    ink = unary_union([polygon(i,face) for i in items])
    return items,ink,record


def _native_readable_chart_scales(board,models,face,f):
    """Add at most one glyph-derived rectangle scale to the old finite menu.

    Only the NEW explanatory picture grows. Actual Fab/courtyards, readable
    ink floors, the 18 mm work envelope, leaders and all obstacles are still
    authoritative. Nonrectangular or oversized domains retain the old menu;
    that refusal is not a claim that no board-level arrangement exists.
    """
    legacy=(1.5,2.,3.)
    evidence=dict(legacy_scales_unchanged=True,native_glyph_and_factory_floors_unchanged=True,
        extra_scale_added=False,scale_quantum=.0625,maximum_scale=12.,maximum_work_extent_mm=18.)
    try:
        require(1<=len(models)<=8 and face in(pcbnew.F_SilkS,pcbnew.B_SilkS),
            'bounded_native_readable_chart_models_required')
        require(all(type(f[k])in(int,float)and math.isfinite(f[k])and f[k]>0
            for k in('height','stroke','clearance')),'positive_native_readable_chart_floors_required')
        margin=f['stroke']/2+f['clearance']+.002;required=[]
        for fp,shape in models:
            require(shape.geom_type=='Polygon'and shape.is_valid and not shape.is_empty
                and not shape.interiors and shape.equals(box(*shape.bounds)),
                'adaptive_chart_requires_exact_rectangular_body_guide')
            x0,y0,x1,y1=shape.bounds;w,h=x1-x0,y1-y0
            require(w>0 and h>0,'positive_native_rectangular_body_required')
            angles=[]
            for angle in(0,90):
                glyph=polygon(make_text(board,fp.GetReference(),(0,0),face,
                    f['height'],f['stroke'],angle),face)
                require(not glyph.is_empty and glyph.is_valid,'complete_native_reference_glyph_required')
                a,b,c,d=glyph.bounds
                # Native text is centred by make_text, but use its ACTUAL
                # asymmetric extents rather than assuming glyph symmetry.
                angles.append(max((2*max(abs(a),abs(c))+2*margin)/w,
                    (2*max(abs(b),abs(d))+2*margin)/h))
            required.append(min(angles))
        raw=max(required);evidence['necessary_rectangular_scale']=raw
        if raw<=3.:
            # The old largest menu entry already has enough room. No new
            # default rendering, packing objective or chart size is implied.
            return legacy,evidence
        scale=math.ceil(raw*16)/16
        require(3.<scale<=12.,'readable_chart_exceeds_bounded_scale')
        body=unary_union([p for _,p in models]);bounds=body.bounds
        require(max(bounds[2]-bounds[0],bounds[3]-bounds[1])*scale<=18.,
            'local_mapping_chart_work_extent_exceeded')
        # Bounds supply a proposal, not fit authority. The identical native
        # polygons/inner-guide covers test used by construction must pass.
        shapes(board,models,face,f,scale=scale,origin=(body.centroid.x,body.centroid.y))
        evidence.update(extra_scale_added=True,extra_scale=scale,
            actual_native_glyph_inside_each_unchanged_scaled_guide=True)
        return (*legacy,scale),evidence
    except ValueError as exc:
        evidence['refusal']=str(exc)
        return legacy,evidence


def _native_readable_polygon_chart_scales(board,models,face,f,*,deadline=None):
    """Opt-in bounded sizing against actual nonrectangular guide material.

    Bounding boxes provide only a necessary lower bound. Every offered scale
    must contain real native glyph polygons in the SAME inset guide used by
    construction. No manufacturing body grows, and old rectangle recipes are
    unchanged unless this separately replayed policy is explicitly requested.
    """
    legacy=(1.5,2.,3.)
    evidence=dict(legacy_scales_unchanged=True,native_glyph_and_factory_floors_unchanged=True,
        extra_scale_added=False,scale_quantum=.0625,maximum_scale=12.,maximum_work_extent_mm=18.,
        policy='actual_native_polygon_guide_and_glyph_containment-v1',
        bounding_box_is_fit_authority=False,maximum_scale_probes=145,
        scale_probes=0,no_path_proof=False,release_authority=False)
    try:
        now=time.monotonic()
        require(deadline is None or type(deadline)in(int,float)and math.isfinite(deadline),
            'finite_native_polygon_chart_deadline_required')
        stop=min(now+2.,deadline if deadline is not None else now+2.)
        require(now<stop,'native_polygon_chart_scale_deadline')
        require(1<=len(models)<=8 and face in(pcbnew.F_SilkS,pcbnew.B_SilkS),
            'bounded_native_polygon_chart_models_required')
        require(all(type(f[k])in(int,float)and math.isfinite(f[k])and f[k]>0
            for k in('height','stroke','clearance')),'positive_native_readable_chart_floors_required')
        margin=f['stroke']/2+f['clearance']+.002;prepared=[];required=[]
        for fp,guide in models:
            require(time.monotonic()<stop,'native_polygon_chart_scale_deadline')
            require(guide.geom_type=='Polygon'and guide.is_valid and not guide.is_empty
                and not guide.interiors and 4<=len(guide.exterior.coords)<=257,
                'bounded_actual_simple_polygon_body_guide_required')
            x0,y0,x1,y1=guide.bounds;w,h=x1-x0,y1-y0;center=guide.centroid
            require(w>0 and h>0 and guide.contains(center),'positive_centred_actual_body_guide_required')
            glyphs=[];lower=[]
            for angle in(0,90):
                glyph=polygon(make_text(board,fp.GetReference(),(0,0),face,f['height'],f['stroke'],angle),face)
                require(not glyph.is_empty and glyph.is_valid,'complete_native_reference_glyph_required')
                a,b,c,d=glyph.bounds
                # Total glyph spans are necessary bounds even for an
                # asymmetric guide/glyph. They are never sufficient fit.
                lower.append(max((c-a+2*margin)/w,(d-b+2*margin)/h))
                glyphs.append(affinity.translate(glyph,center.x,center.y))
            prepared.append((guide,center,glyphs));required.append(min(lower))
        raw=max(required);evidence['necessary_bounding_box_scale']=raw
        body=unary_union([p for _,p in models]);bounds=body.bounds
        extent=max(bounds[2]-bounds[0],bounds[3]-bounds[1])
        require(math.isfinite(raw)and math.isfinite(extent)and extent>0,
            'finite_native_polygon_chart_scale_and_extent_required')
        def fits(scale):
            require(time.monotonic()<stop,'native_polygon_chart_scale_deadline')
            evidence['scale_probes']+=1
            for guide,center,glyphs in prepared:
                actual=affinity.scale(guide,xfact=scale,yfact=scale,origin=(center.x,center.y))
                inner=actual.buffer(-margin,join_style=2)
                if not any(inner.covers(glyph) for glyph in glyphs):return False
            return True
        if raw<=3. and extent*3.<=18. and fits(3.):return legacy,evidence
        first=max(49,math.ceil(raw*16));last=min(192,math.floor(18./extent*16))
        require(first<=last,'native_polygon_chart_scale_or_work_extent_exceeded')
        for tick in range(first,last+1):
            scale=tick/16
            if not fits(scale):continue
            # Final native rendering is independent of the cached search
            # glyphs. It repeats all actual inset/outline/glyph tests.
            shapes(board,models,face,f,scale=scale,origin=(body.centroid.x,body.centroid.y))
            require(time.monotonic()<stop,'native_polygon_chart_scale_deadline')
            evidence.update(extra_scale_added=True,extra_scale=scale,
                actual_native_glyph_inside_each_unchanged_scaled_guide=True)
            return (*legacy,scale),evidence
        evidence['refusal']='finite_native_polygon_guide_scales_do_not_contain_readable_glyphs'
    except ValueError as exc:
        evidence['refusal']=str(exc)
    return legacy,evidence


def chart_decoration(board, records, models, face, f):
    """A miniature diagram must look like a callout, not a phantom component."""
    from shapely.geometry import Polygon
    mapped=unary_union([Polygon(r['courtyard_xy_mm']) for r in records])
    x0,y0,x1,y1=mapped.bounds;cx=(x0+x1)/2
    title=make_text(board,'REF MAP',(cx,y0-f['clearance']-f['height']),face,f['height'],f['stroke'])
    combined=unary_union([mapped,polygon(title,face)]).bounds
    frame=box(*combined).buffer(f['clearance']+f['stroke']/2,join_style=2)
    border=make_outline(board,frame,face,f['stroke'])
    actual=unary_union([p for _,p in models]).convex_hull
    a,z=nearest_points(actual,frame)
    leader=pcbnew.PCB_SHAPE(board);leader.SetShape(pcbnew.SHAPE_T_SEGMENT)
    leader.SetLayer(face);leader.SetWidth(round(f['stroke']*1e6))
    leader.SetStart(pcbnew.VECTOR2I(round(a.x*1e6),round(a.y*1e6)))
    leader.SetEnd(pcbnew.VECTOR2I(round(z.x*1e6),round(z.y*1e6)))
    require(leader.GetStart()!=leader.GetEnd(),'separate_identifiable_reference_callout_required')
    return [*border,title,leader],frame,leader


def record_items(board,row,face,f):
    result=[]
    if 'outline_segments_xy_mm' in row:
        for a,z in row['outline_segments_xy_mm']:
            line=pcbnew.PCB_SHAPE(board);line.SetShape(pcbnew.SHAPE_T_SEGMENT)
            line.SetStart(pcbnew.VECTOR2I(round(a[0]*1e6),round(a[1]*1e6)))
            line.SetEnd(pcbnew.VECTOR2I(round(z[0]*1e6),round(z[1]*1e6)))
            line.SetLayer(face);line.SetWidth(round(f['stroke']*1e6));result.append(line)
    else:
        from shapely.geometry import Polygon
        result=make_outline(board,Polygon(row['courtyard_xy_mm']),face,f['stroke'])
    text=make_text(board,row['reference'],row['text_xy_mm'],face,f['height'],f['stroke'],row['text_angle_degrees'])
    result.append(text)
    if row.get('leader_xy_mm'):
        a,z=row['leader_xy_mm'];line=pcbnew.PCB_SHAPE(board);line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetStart(pcbnew.VECTOR2I(round(a[0]*1e6),round(a[1]*1e6)))
        line.SetEnd(pcbnew.VECTOR2I(round(z[0]*1e6),round(z[1]*1e6)))
        line.SetLayer(face);line.SetWidth(round(f['stroke']*1e6));result.append(line)
    return result


def _interrupted_body_guides(board, shape, face, f, *, _prepared=None):
    """Subtract actual apertures from a NEW nonfunctional projected guide.

    This never edits a Source graphic. Full Fab/courtyard/pin/key/orientation
    art stays opaque and literal. Other ink and assembled bodies cannot grant
    clipping permission. Native glyph, leader, mask and saved gates still own
    acceptance; these strokes are not closed assembly-body authority.
    """
    from shapely.geometry import LineString
    import cec_rectangular_field_silk_clearance as native_mask
    require(face in (pcbnew.F_SilkS, pcbnew.B_SilkS)
        and shape.geom_type == 'Polygon' and shape.is_valid and not shape.interiors,
        'actual_projected_body_guide_and_silk_face_required')
    points = list(shape.exterior.coords)
    require(4 <= len(points) <= 257, 'bounded_projected_body_guide_required')
    # Actual mask and effective holes, including tented drills. Never use a
    # pad bbox, copper-plane bbox, nearby text or caller obstacle as authority.
    require(_prepared is None or type(_prepared)is _ObstaclePreparation,
        'planner_owned_reference_aperture_preparation_required')
    rows = (_prepared.apertures(board,face,'native_mask_and_bore')if _prepared is not None else
        tuple((uid,assembly.polygon_from_native(poly))for uid,poly in
            native_mask._mask_openings(board,face,'native_mask_and_bore')))
    margin = f['clearance'] + f['stroke']/2 + .003
    opened = []; touched = []
    for uid, aperture in rows:
        require(aperture.is_valid and not aperture.is_empty,
            'complete_native_body_guide_opening_required')
        keepout = aperture.buffer(margin, join_style=2)
        if keepout.intersects(shape.boundary):
            opened.append(keepout); touched.append(uid)
    blocked = unary_union(opened)
    segments = []
    for a, z in zip(points, points[1:]):
        original = LineString([a, z]); kept = original.difference(blocked)
        pieces = ([kept] if kept.geom_type == 'LineString' else list(kept.geoms))
        pieces.sort(key=lambda line: original.project(line.centroid))
        for line in pieces:
            if line.is_empty: continue
            require(line.geom_type == 'LineString' and len(line.coords) == 2,
                'only_original_straight_body_guide_intervals_required')
            start, end = list(line.coords)
            if original.project(line.interpolate(0)) > original.project(line.interpolate(line.length)):
                start, end = end, start
            start, end = [[round(v*1e6)/1e6 for v in p] for p in (start, end)]
            require(math.dist(start, end) >= f['stroke'],
                'usable_interrupted_body_guide_strokes_required')
            require(LineString([start, end]).difference(original.buffer(.000002)).is_empty,
                'interrupted_guide_must_stay_on_exact_source_projection')
            segments.append([start, end])
    # At least two separated sides must still describe the projected body;
    # a lone dash or an invisible outline cannot provide the association.
    directions = {round(math.atan2(z[1]-a[1], z[0]-a[0]) % math.pi, 8) for a, z in segments}
    require(2 <= len(segments) <= 24 and len(directions) >= 2,
        'usable_interrupted_body_guide_association_required')
    retained = sum(math.dist(a, z) for a, z in segments)
    return segments, dict(policy='actual_native_opening_difference_of_new_projected_body_guide_v1',
        native_opening_uuids=sorted(set(touched)), factory_clearance_mm=f['clearance'],
        stroke_mm=f['stroke'], clip_margin_mm=margin, retained_length_mm=retained,
        removed_length_mm=max(0., shape.length-retained),
        only_new_nonfunctional_body_guide_strokes=True,
        complete_fab_courtyard_and_functional_marks_unchanged=True,
        closed_assembly_body_authority=False)


def reverse_component(board, model, face, f, blocked, material, other_courts, *, peripheral_seats=False,
                      interrupt_projected_body_guides=False,positive_leaders_only=False,_prepared=None):
    """Keep tiny courtyards at their real scale; seat readable text beside them.

    An exact rectangular courtyard may use all four corner brackets when
    its full lines conflict with openings. No corner moves and no text is
    shrunk. A short leader makes an outside reference unambiguous.
    """
    fp,shape=model;points=list(shape.exterior.coords)
    styles=[('complete',[[list(a),list(z)] for a,z in zip(points,points[1:])])]
    require(type(interrupt_projected_body_guides) is bool,
        'explicit_projected_body_guide_interruption_required')
    interruption = None
    if interrupt_projected_body_guides:
        segments, interruption = _interrupted_body_guides(board, shape, face, f,_prepared=_prepared)
        # Opt-in removes ONLY opening-obstructed intervals, never arbitrary
        # clear middle strokes as a four-corner fallback would do.
        if interruption['native_opening_uuids']:
            styles = [('native_opening_interrupted_body_guide', segments)]
    elif len(points)==5:
        corners=[]
        for i,a in enumerate(points[:-1]):
            for z in (points[(i-1)%4],points[(i+1)%4]):
                length=math.dist(a,z);leg=min(.35,length/3)
                require(leg>=f['stroke'],'readable_source_courtyard_corner_feature_required')
                end=[a[k]+(z[k]-a[k])*leg/length for k in (0,1)]
                corners.append([list(a),end])
        styles.append(('four_exact_corner_brackets',corners))
    x0,y0,x1,y1=shape.bounds;center=shape.centroid
    for style,segments in styles:
        base=dict(footprint_uuid=force._uid(fp),reference_field_uuid=force._uid(fp.Reference()),
            reference=fp.GetReference(),courtyard_xy_mm=[list(p) for p in points],
            outline_style=style,outline_segments_xy_mm=segments,
            actual_back_view_readable=face==pcbnew.B_SilkS,text_mirrored=face==pcbnew.B_SilkS)
        if style == 'native_opening_interrupted_body_guide':
            base['body_guide_interruption'] = interruption
        for angle in (0,90):
            probe=make_text(board,fp.GetReference(),(center.x,center.y),face,f['height'],f['stroke'],angle)
            pb=polygon(probe,face).bounds;half_x=(pb[2]-pb[0])/2;half_y=(pb[3]-pb[1])/2
            gap=f['clearance']+f['stroke']+.03
            seats=[(center.x,center.y),(center.x,y0-gap-half_y),(x1+gap+half_x,center.y),
                (center.x,y1+gap+half_y),(x0-gap-half_x,center.y)]
            if peripheral_seats:
                # Preserve the old five-seat recipe unless explicitly
                # requested. An outside glyph need not be centre-aligned:
                # actual body/glyph bounds give finite cardinal offsets,
                # still with the SAME outline, nearest leader, readable
                # floor, native openings and independent saved receiver.
                import cec_reference_field_seating as field_seats
                glyph=polygon(make_text(board,fp.GetReference(),(0,0),face,
                    f['height'],f['stroke'],angle),face)
                for reach in (.5,1.,1.5):
                    for at in field_seats._centers(shape,glyph,f,reach):
                        if at not in seats:seats.append(at)
            for at in seats:
                row=dict(base,text_xy_mm=list(at),text_angle_degrees=angle)
                text=make_text(board,fp.GetReference(),at,face,f['height'],f['stroke'],angle)
                text_shape=polygon(text,face)
                inside=shape.buffer(-(f['stroke']/2+f['clearance']+.002),join_style=2).covers(text_shape)
                if not inside:
                    if shape.intersects(text_shape.buffer(f['clearance']+.002)):
                        continue
                    a,z=nearest_points(shape,text_shape.envelope.buffer(f['clearance']+f['stroke']/2+.002,join_style=2))
                    # Envelope inflation can meet a tiny body even when the
                    # glyph itself is clear. That is not a leader: reject
                    # collapsed native segments before saving. Do not invent
                    # a minimum leader length beyond the native geometry.
                    if positive_leaders_only and tuple(round(v*1e6)for v in(a.x,a.y)) == tuple(round(v*1e6)for v in(z.x,z.y)):
                        continue
                    row['leader_xy_mm']=[[a.x,a.y],[z.x,z.y]]
                if not text_shape.intersection(other_courts).is_empty:
                    continue
                made=record_items(board,row,face,f)
                ink=unary_union([polygon(item,face) for item in made])
                if not material.covers(ink) or ink.intersects(blocked):
                    continue
                # Native DRC remains responsible for glyph/leader overlap;
                # don't accept a tiny hard-to-read mark merely because the
                # neighbouring board surface is empty.
                return made,ink,[row]
    raise ValueError('no_readable_clear_projected_courtyard_and_reference_seat')


def plan(source, *, grade, board_hint, maximum_components=6, seed_index=0,
         reverse_ownership='footprint_children',via_ink_policy='reserve_native_lands',
         owner_uuid_scope=(),reviewed_courtyard_contract_ids=(),peripheral_reverse_seats=False,
         interrupt_projected_body_guides=False,opposite_face_chart=False,project_native_fab_body=False,
         positive_leaders_only=False,adaptive_chart_scale=False,polygon_chart_scale=False):
    require(type(maximum_components) is int and 1 <= maximum_components <= 8
        and type(seed_index) is int and 0 <= seed_index < 32 and type(board_hint) is str
        and bool(board_hint),'finite_dense_reference_mapping_domain_required')
    require(type(reverse_ownership)is str and reverse_ownership in
        ('footprint_children','rigid_root_group_per_component'),'explicit_reverse_annotation_ownership_required')
    require(type(peripheral_reverse_seats)is bool,'explicit_finite_reverse_reference_periphery_required')
    require(type(interrupt_projected_body_guides)is bool,
        'explicit_projected_body_guide_interruption_required')
    require(not interrupt_projected_body_guides or reverse_ownership=='rigid_root_group_per_component',
        'interrupted_guides_must_not_modify_library_footprint_artwork')
    require(type(opposite_face_chart)is bool,'explicit_opposite_face_reference_chart_required')
    require(not opposite_face_chart or reverse_ownership=='rigid_root_group_per_component',
        'opposite_reference_chart_requires_root_owned_native_group')
    require(type(project_native_fab_body)is bool,'explicit_native_fab_body_projection_required')
    require(type(positive_leaders_only)is bool,'explicit_positive_reference_leader_policy_required')
    require(type(adaptive_chart_scale)is bool,'explicit_native_readable_chart_scale_required')
    require(type(polygon_chart_scale)is bool and (not polygon_chart_scale or adaptive_chart_scale),
        'explicit_polygon_chart_scale_requires_adaptive_policy')
    require(not project_native_fab_body or reverse_ownership=='rigid_root_group_per_component',
        'fab_body_guide_requires_root_owned_native_annotation')
    require(type(via_ink_policy)is str and via_ink_policy in
        ('reserve_native_lands','native_mask_and_bore'),'explicit_reference_native_mask_policy_required')
    require(type(owner_uuid_scope)in(list,tuple)and len(owner_uuid_scope)<=8
        and all(type(u)is str and u for u in owner_uuid_scope)
        and len(set(owner_uuid_scope))==len(owner_uuid_scope),
        'bounded_exact_native_reference_owner_scope_required')
    require(type(reviewed_courtyard_contract_ids)in(list,tuple)
        and len(reviewed_courtyard_contract_ids)<=8
        and all(type(k)is str and k for k in reviewed_courtyard_contract_ids)
        and len(set(reviewed_courtyard_contract_ids))==len(reviewed_courtyard_contract_ids),
        'bounded_explicit_reviewed_reference_body_contracts_required')
    started = time.monotonic(); b,f,raw,binding = source_context(source,grade,board_hint)
    retained_material = _CONSTRUCT_PLAN_MATERIAL.get()
    if retained_material is not None:
        require(type(retained_material) is _ConstructPlanMaterial
            and retained_material.source == Path(source).resolve()
            and retained_material.board is None, 'constructor_owned_fresh_plan_material_required')
        initial_material_epoch = _plan_material_epoch(b)
    reviewed_shapes=None;reviewed_proofs=[];reviewed_dependencies={}
    if reviewed_courtyard_contract_ids:
        # This exact-package context is a conservative obstacle only. It
        # does not add a Source courtyard or receive any assembly overlap.
        import cec_reference_field_seating as reference_bodies
        reviewed_dependencies=reference_bodies.dependencies()
        reviewed_shapes,reviewed_proofs,_=reference_bodies._reviewed_body_shapes(source,b,board_hint,
            reviewed_courtyard_contract_ids,started+10.)
    fps = {force._uid(fp):fp for fp in b.GetFootprints()}
    by_field = {force._uid(fp.Reference()):uid for uid,fp in fps.items()}
    count = Counter()
    for fault in raw['violations']:
        if fault['type'] not in ('silk_overlap','silk_over_copper','silk_edge_clearance'):
            continue
        for item in fault['items']:
            if item.get('uuid') in by_field:
                count[by_field[item['uuid']]] += 1
    source_nodes = additive._nodes(source)[1]
    grouped = {force._uid(i) for g in b.Groups() for i in g.GetItems()}
    grouped.update(u for node in source_nodes.values() if node[0]=='group'
        for u in additive._members(node))
    eligible = []
    for uid in sorted(count,key=lambda u:(-count[u],u)):
        fp = fps[uid]; ref = fp.Reference()
        if (not ref.IsVisible() or ref.IsLocked() or force._uid(ref) in grouped
                or uid in grouped or fp.GetParentGroup() or ref.GetLayer() not in (pcbnew.F_SilkS,pcbnew.B_SilkS)):
            continue
        expected = pcbnew.B_SilkS if fp.IsFlipped() else pcbnew.F_SilkS
        if ref.GetLayer() != expected:
            continue
        try:
            native = (reviewed_shapes[uid]if reviewed_shapes is not None and uid in reviewed_shapes
                else court(fp))
            if project_native_fab_body:native=guide_body(fp,True)
        except ValueError:
            continue
        eligible.append((fp,native))
    if owner_uuid_scope:
        # Target an actual reported moved-owner conflict without wasting
        # every earlier seed on inherited, unrelated warnings. This narrows
        # existing eligibility; it never hides an unreported/locked owner or
        # supplies a caller's annotation/geometry waiver.
        require(set(owner_uuid_scope)<={force._uid(fp)for fp,_ in eligible},
            'requested_reference_owner_not_source_native_fault_eligible')
        eligible=[m for m in eligible if force._uid(m[0])in owner_uuid_scope]
    require(seed_index < len(eligible),'no_eligible_source_dense_reference_seed')
    root = eligible[seed_index]; source_face = root[0].Reference().GetLayer()
    candidates = sorted([m for m in eligible if m[0].Reference().GetLayer() == source_face
        and m[1].distance(root[1]) <= 2.],key=lambda m:(m[1].distance(root[1]),-count[force._uid(m[0])],force._uid(m[0])))
    models = candidates[:maximum_components]
    excluded = {force._uid(fp.Reference()) for fp,_ in models}
    material = assembly.polygon_from_native(geometry.outline_material(b)).buffer(-f['edge'],join_style=2)
    body = unary_union([p for _,p in models]); center = body.centroid
    preparation=_ObstaclePreparation(b)
    front=None;front_refusal=None
    try:
        front = obstacles(b,source_face,excluded,f['clearance'],assembled_bodies=True,
            via_ink_policy=via_ink_policy,reviewed_body_shapes=reviewed_shapes,_prepared=preparation)
    except ValueError as exc:
        # Unknown same-face bodies disqualify the front chart, NOT the
        # independently checked opposite face. Never invent their envelope
        # or silently treat them as an empty body merely to fit a chart.
        front_refusal=str(exc)
    front_hard = obstacles(b,source_face,excluded,f['clearance'],assembled_bodies=False,
        via_ink_policy=via_ink_policy,_prepared=preparation)
    front_attempts = []; selected = None
    scale_discovery={};front_scales=(1.5,2.,3.)
    if adaptive_chart_scale:
        front_scales,scale_discovery['front']=(
            _native_readable_polygon_chart_scales(b,models,source_face,f,deadline=started+10.) if polygon_chart_scale
            else _native_readable_chart_scales(b,models,source_face,f))
    # A modest nearby map, not a global claim that no arrangement exists.
    # Layout is the actual relative component geometry, uniformly enlarged.
    for scale in front_scales:
        trial = affinity.scale(body,xfact=scale,yfact=scale,origin=(center.x,center.y))
        x0,y0,x1,y1 = trial.bounds; a0,b0,a1,b1 = body.bounds
        gap=3*f['height']+f['clearance']
        shifts = [(a1+gap-x0,center.y-(y0+y1)/2),
            (a0-gap-x1,center.y-(y0+y1)/2),
            (center.x-(x0+x1)/2,b1+gap-y0),
            (center.x-(x0+x1)/2,b0-gap-y1)]
        for shift in shifts:
            row = dict(scale=scale,translation_mm=list(shift)); front_attempts.append(row)
            try:
                require(front is not None,'front_mapping_body_inventory_refused:'+str(front_refusal))
                items,ink,records = shapes(b,models,source_face,f,positions=shift,scale=scale,origin=(center.x,center.y))
                decor,frame,leader=chart_decoration(b,records,models,source_face,f)
                items.extend(decor);ink=unary_union([ink,*[polygon(item,source_face) for item in decor]])
                require(max(trial.bounds[2]-trial.bounds[0],trial.bounds[3]-trial.bounds[1])<=18.,'local_mapping_chart_work_extent_exceeded')
                require(material.covers(ink),'mapping_chart_not_supported_by_actual_substrate')
                # Reserve the complete mini-map, including blank interiors;
                # no component can sit inside its explanatory picture.
                envelope = frame.buffer(f['stroke']/2)
                require(not envelope.intersects(front),'nearby_mapping_chart_space_occupied')
                require(not polygon(leader,source_face).intersects(front_hard),'reference_callout_leader_hits_native_ink_or_opening')
                outside_owner=polygon(leader,source_face).difference(body.convex_hull.buffer(f['clearance']+.01,join_style=2))
                require(not outside_owner.intersects(front),'reference_callout_leader_crosses_other_assembly_body')
                selected = (source_face,items,records,'nearby_front_mapping_chart'); row['fits'] = True
                break
            except ValueError as exc:
                row.update(fits=False,reason=str(exc))
        if selected:
            break
    rear_chart_attempts=[]
    if not selected and opposite_face_chart:
        target=pcbnew.B_SilkS if source_face==pcbnew.F_SilkS else pcbnew.F_SilkS
        rear=obstacles(b,target,set(),f['clearance'],assembled_bodies=True,
            via_ink_policy=via_ink_policy,reviewed_body_shapes=reviewed_shapes,_prepared=preparation)
        rear_hard=obstacles(b,target,set(),f['clearance'],assembled_bodies=False,
            via_ink_policy=via_ink_policy,_prepared=preparation)
        rear_scales=(1.5,2.,3.)
        if adaptive_chart_scale:
            rear_scales,scale_discovery['opposite']=(
                _native_readable_polygon_chart_scales(b,models,target,f,deadline=started+10.) if polygon_chart_scale
                else _native_readable_chart_scales(b,models,target,f))
        for scale in rear_scales:
            trial=affinity.scale(body,xfact=scale,yfact=scale,origin=(center.x,center.y))
            x0,y0,x1,y1=trial.bounds;a0,b0,a1,b1=body.bounds
            # A chart is a labeled callout, not a footprint relocation.
            # Finite cardinal gap/tangent seats can use nearby free legend
            # space without moving circuitry or deleting existing maps.
            shifts=[]
            for reach in (3.,5.,7.):
                gap=reach*f['height']+f['clearance']
                for tangent in (0.,-2.,2.,-4.,4.):
                    slide=tangent*f['height']
                    shifts.extend([(a1+gap-x0,center.y-(y0+y1)/2+slide),
                        (a0-gap-x1,center.y-(y0+y1)/2+slide),
                        (center.x-(x0+x1)/2+slide,b1+gap-y0),
                        (center.x-(x0+x1)/2+slide,b0-gap-y1)])
            for shift in shifts:
                require(time.monotonic()-started<10.,'dense_reference_mapping_plan_deadline')
                row=dict(scale=scale,translation_mm=list(shift));rear_chart_attempts.append(row)
                try:
                    items,ink,records=shapes(b,models,target,f,positions=shift,scale=scale,origin=(center.x,center.y))
                    decor,frame,leader=chart_decoration(b,records,models,target,f)
                    items.extend(decor);ink=unary_union([ink,*[polygon(item,target)for item in decor]])
                    require(max(trial.bounds[2]-trial.bounds[0],trial.bounds[3]-trial.bounds[1])<=18.,
                        'local_mapping_chart_work_extent_exceeded')
                    require(material.covers(ink),'mapping_chart_not_supported_by_actual_substrate')
                    require(body.convex_hull.buffer(18.,join_style=2).covers(frame),
                        'local_rear_reference_chart_reach_exceeded')
                    require(not frame.buffer(f['stroke']/2).intersects(rear),
                        'nearby_mapping_chart_space_occupied')
                    require(not polygon(leader,target).intersects(rear_hard),
                        'reference_callout_leader_hits_native_ink_or_opening')
                    outside_owner=polygon(leader,target).difference(body.convex_hull.buffer(f['clearance']+.01,join_style=2))
                    require(not outside_owner.intersects(rear),
                        'reference_callout_leader_crosses_other_assembly_body')
                    row['fits']=True
                    selected=(target,items,records,'nearby_opposite_face_mapping_chart')
                    break
                except ValueError as exc:row.update(fits=False,reason=str(exc))
            if selected:break
    rejected = []
    if not selected:
        target = pcbnew.B_SilkS if source_face == pcbnew.F_SilkS else pcbnew.F_SilkS
        blocked = obstacles(b,target,set(),f['clearance'],assembled_bodies=True,
            via_ink_policy=via_ink_policy,reviewed_body_shapes=reviewed_shapes,_prepared=preparation)
        items = []; records = []
        for model in models:
            try:
                other_courts=unary_union([p for fp,p in models if force._uid(fp)!=force._uid(model[0])]).buffer(f['clearance'])
                made,ink,rows = reverse_component(b,model,target,f,blocked,material,other_courts,
                    peripheral_seats=peripheral_reverse_seats,
                    interrupt_projected_body_guides=interrupt_projected_body_guides,
                    _prepared=preparation,
                    positive_leaders_only=positive_leaders_only or project_native_fab_body or interrupt_projected_body_guides)
                require(material.covers(ink),'reverse_legend_not_supported_by_substrate')
                require(not ink.intersects(blocked),'reverse_legend_native_ink_or_opening_conflict')
                blocked = unary_union([blocked,ink.buffer(f['clearance']+0.002)])
                items.extend(made);records.extend(rows)
            except ValueError as exc:
                rejected.append(dict(footprint_uuid=force._uid(model[0]),reason=str(exc)))
        require(bool(records),'no_readable_clear_opposite_face_mapping_in_bounded_domain')
        selected = (target,items,records,'opposite_face_projected_courtyard')
    face,items,records,mode = selected
    if project_native_fab_body:
        for row in records:
            owner=fps[row['footprint_uuid']]
            row.update(projection_geometry='exact_source_fab_body_not_manufacturing_courtyard',
                actual_manufacturing_courtyard_xy_mm=[list(p)for p in court(owner).exterior.coords],
                full_fab_and_actual_courtyard_and_functional_marks_unchanged=True)
    preparation.check(b)
    require(time.monotonic()-started < 10.,'dense_reference_mapping_plan_deadline')
    require(binding['source_family']==force._family(source,board_hint),'dense_reference_source_family_changed')
    result=dict(schema=1,policy=POLICY,binding=binding,board_hint=board_hint,grade=str(Path(grade).resolve()),
        maximum_components=maximum_components,seed_index=seed_index,mode=mode,target_layer_id=int(face),
        records=records,front_mapping_trials=front_attempts,reverse_refusals=rejected,
        added_item_count=len(items),source_current_or_copper_authority=False,
        finite_map_search_is_not_global_impossibility_proof=True,fab_ready=False,release_authority=False)
    if reverse_ownership!='footprint_children':result['reverse_ownership']=reverse_ownership
    if owner_uuid_scope:result['owner_uuid_scope']=sorted(owner_uuid_scope)
    if peripheral_reverse_seats:result['peripheral_reverse_seats']=True
    if opposite_face_chart:
        result.update(opposite_face_chart=True,opposite_face_chart_trials=rear_chart_attempts)
    if project_native_fab_body:result['project_native_fab_body']=True
    if positive_leaders_only:result['positive_leaders_only']=True
    if adaptive_chart_scale:
        result.update(adaptive_chart_scale=True,chart_scale_discovery=scale_discovery)
    if polygon_chart_scale:result['polygon_chart_scale']=True
    if interrupt_projected_body_guides:
        import cec_rectangular_field_silk_clearance as native_mask
        result.update(interrupt_projected_body_guides=True,
            interrupted_guide_authority_sha256=force._hash(Path(native_mask.__file__).resolve()))
    if via_ink_policy!='reserve_native_lands':
        import cec_rectangular_field_silk_clearance as ink
        result.update(via_ink_policy=via_ink_policy,native_mask_authority_sha256=force._hash(Path(ink.__file__).resolve()))
    if reviewed_courtyard_contract_ids:
        require(reviewed_dependencies==reference_bodies.dependencies(),
            'reviewed_reference_body_helper_changed_during_plan')
        result.update(reviewed_courtyard_contract_ids=list(reviewed_courtyard_contract_ids),
            reviewed_body_reservations=reviewed_proofs,reviewed_body_helper_dependencies=reviewed_dependencies,
            reviewed_bodies_are_obstacles_only_not_source_courtyard_or_overlap_admission=True)
    if retained_material is not None:
        require(initial_material_epoch == _plan_material_epoch(b),
            'fresh_reference_plan_changed_its_native_source')
        retained_material.board = b
        retained_material.source_ids = frozenset(source_nodes)
        retained_material.source_sha256 = binding['source_sha256']
        retained_material.native_epoch = initial_material_epoch
        require(time.monotonic()-started < 10., 'dense_reference_mapping_plan_deadline')
    return result


def construct(source, proposal):
    retained_material = _ConstructPlanMaterial(source)
    token = _CONSTRUCT_PLAN_MATERIAL.set(retained_material)
    try:
        fresh = plan(source,reverse_ownership=proposal.get('reverse_ownership','footprint_children'),
            via_ink_policy=proposal.get('via_ink_policy','reserve_native_lands'),
            owner_uuid_scope=proposal.get('owner_uuid_scope',()),
            reviewed_courtyard_contract_ids=proposal.get('reviewed_courtyard_contract_ids',()),
            peripheral_reverse_seats=proposal.get('peripheral_reverse_seats',False),
            interrupt_projected_body_guides=proposal.get('interrupt_projected_body_guides',False),
            opposite_face_chart=proposal.get('opposite_face_chart',False),
            project_native_fab_body=proposal.get('project_native_fab_body',False),
            positive_leaders_only=proposal.get('positive_leaders_only',False),
            adaptive_chart_scale=proposal.get('adaptive_chart_scale',False),
            polygon_chart_scale=proposal.get('polygon_chart_scale',False),
            **{k:proposal[k] for k in ('grade','board_hint','maximum_components','seed_index')})
    finally:
        _CONSTRUCT_PLAN_MATERIAL.reset(token)
    require(fresh == proposal,'stale_or_forged_dense_reference_mapping_plan')
    b = retained_material.board
    require(b is not None and retained_material.source_ids is not None
        and retained_material.source_sha256 == force._hash(Path(source).resolve())
        and retained_material.native_epoch == _plan_material_epoch(b),
        'fresh_constructor_source_material_changed')
    f = proposal['binding']['factory_legend']; face = proposal['target_layer_id']
    source_locks={force._uid(fp):bool(fp.IsLocked())for fp in b.GetFootprints()}
    token = proposal['binding']['source_sha256']+':'+str(proposal['seed_index'])
    # The Source is immutable during this invocation. Read its complete root UUID
    # inventory once, retaining collision checks for every generated identity
    # as well as uniqueness among this invocation's new native items.
    source_ids=retained_material.source_ids;generated_ids=set()
    def ident(kind,index):
        uid=str(uuid.uuid5(uuid.NAMESPACE_URL,token+':'+kind+':'+str(index)))
        require(uid not in source_ids and uid not in generated_ids,'legend_generated_uuid_collision')
        generated_ids.add(uid)
        return pcbnew.KIID(uid)
    group = None
    chart=proposal['mode']in('nearby_front_mapping_chart','nearby_opposite_face_mapping_chart')
    if chart:
        group = pcbnew.PCB_GROUP(b); group.SetName(GROUP)
        group.m_Uuid.Clone(ident('group',0))
        b.Add(group)
    added = [];root_added=[];reverse_groups=[]
    for n,row in enumerate(proposal['records']):
        fp = next(fp for fp in b.GetFootprints() if force._uid(fp) == row['footprint_uuid'])
        fp.Reference().SetVisible(False)
        reverse=proposal['mode']=='opposite_face_projected_courtyard'
        attached=reverse and proposal.get('reverse_ownership','footprint_children')=='footprint_children'
        local_group=None
        if reverse and not attached:
            local_group=pcbnew.PCB_GROUP(b);local_group.SetName(GROUP+':'+row['reference'])
            local_group.m_Uuid.Clone(ident('reverse-group',n))
            b.Add(local_group);local_group.AddItem(fp);reverse_groups.append(force._uid(local_group))
        owner=fp if attached else b
        for k,item in enumerate(record_items(owner,row,face,f)):
            item.m_Uuid.Clone(ident('record-'+str(n),k));item.SetLocked(True);owner.Add(item)
            if group is not None:group.AddItem(item)
            if local_group is not None:local_group.AddItem(item)
            added.append(force._uid(item))
            if not attached:root_added.append(force._uid(item))
        if local_group is not None:local_group.SetLocked(True)
    if chart:
        models=[(next(fp for fp in b.GetFootprints() if force._uid(fp)==r['footprint_uuid']),None) for r in proposal['records']]
        models=[(fp,guide_body(fp,proposal.get('project_native_fab_body',False))) for fp,_ in models]
        decor,_,_=chart_decoration(b,proposal['records'],models,face,f)
        for k,item in enumerate(decor):
            item.m_Uuid.Clone(ident('chart-decoration',k));item.SetLocked(True);b.Add(item);group.AddItem(item);added.append(force._uid(item));root_added.append(force._uid(item))
        # A side callout encodes a relationship among several footprints.
        # Keep it rigid with those members rather than letting a later placer
        # silently move a part away from its map. Opposite-face labels are
        # native footprint children and follow normal moves/rotations/flips.
        for row in proposal['records']:
            group.AddItem(next(fp for fp in b.GetFootprints() if force._uid(fp)==row['footprint_uuid']))
    if group is not None:group.SetLocked(True)
    if proposal.get('reverse_ownership')=='rigid_root_group_per_component':
        # Native GROUP.SetLocked propagates into member footprints. Rigid
        # mapping ownership is not permission to change their authored lock.
        for fp in b.GetFootprints():fp.SetLocked(source_locks[force._uid(fp)])
    require(len(added)==proposal['added_item_count'],'complete_saved_reference_mapping_required')
    return b,dict(added_annotation_uuids=sorted(added),added_group_uuid=force._uid(group) if group is not None else None,
        added_root_annotation_uuids=sorted(root_added),
        added_reverse_group_uuids=reverse_groups,
        reverse_annotations_are_native_footprint_children=proposal['mode']=='opposite_face_projected_courtyard'
            and proposal.get('reverse_ownership','footprint_children')=='footprint_children',
        reverse_annotations_and_owner_rigid_root_group=bool(reverse_groups),
        front_map_and_members_form_one_rigid_native_group=proposal['mode']=='nearby_front_mapping_chart',
        modified_footprint_uuids=sorted(row['footprint_uuid'] for row in proposal['records']))


def _reference_literal(source_text,native_text,proposal,manifest):
    """Preserve all source bytes except the replaced reference visibility.

    Root-owned ink is rigidly grouped with its physical owner, not inserted
    into the library footprint's artwork. No footprint-library mismatch is
    manufactured just to make its board-specific reference readable.
    """
    import cec_source_retaining_ses_import as raw
    require(proposal.get('reverse_ownership')=='rigid_root_group_per_component',
        'explicit_root_owned_reference_literal_policy_required')
    old,new=raw.inventory(source_text),raw.inventory(native_text);text=source_text
    for row in sorted(proposal['records'],key=lambda r:old[r['footprint_uuid']][0],reverse=True):
        uid=row['footprint_uuid'];a,z=old[uid];x,y=new[uid];before=source_text[a:z];after=native_text[x:y]
        def refs(node):
            return [(i,j,node[i:j])for i,j in raw.children(node)
                if raw.kind(node[i:j])=='property'and raw.node_uuid(node[i:j])==row['reference_field_uuid']]
        left,right=refs(before),refs(after);require(len(left)==len(right)==1,'exact_source_native_reference_property_required')
        i,j,field_text=left[0];hidden=[right[0][2][u:v]for u,v in raw.children(right[0][2])
            if raw.kind(right[0][2][u:v])=='hide']
        require(len(hidden)==1 and hidden[0].split()==['(hide','yes)'],'replaced_reference_must_be_hidden_only_after_readable_mapping')
        spans=[(u,v)for u,v in raw.children(field_text)if raw.kind(field_text[u:v])=='hide']
        require(len(spans)<=1,'unique_source_reference_visibility_required')
        if spans:
            u,v=spans[0];field_text=field_text[:u]+hidden[0]+field_text[v:]
        else:
            at=raw.children(field_text,root_end=True);field_text=field_text[:at]+'\n'+hidden[0]+'\n'+field_text[at:]
        before=before[:i]+field_text+before[j:];text=text[:a]+before+text[z:]
    ids=set(manifest['added_root_annotation_uuids'])|set(manifest['added_reverse_group_uuids'])
    if manifest['added_group_uuid']:ids.add(manifest['added_group_uuid'])
    require(not ids&old.keys()and ids<=new.keys(),'exact_new_root_reference_annotation_identity_required')
    additions='\n'.join(native_text[new[u][0]:new[u][1]]for u in sorted(ids))
    at=raw.children(text,root_end=True)
    return text[:at]+'\n'+additions+'\n'+text[at:]


def write_private(source,candidate,proposal):
    import cec_source_retaining_ses_import as raw
    source,candidate=[Path(p).resolve()for p in(source,candidate)]
    require(source!=candidate and force._hash(source)==force._hash(candidate),
        'exact_private_root_reference_source_copy_required')
    board,manifest=construct(source,proposal)
    with tempfile.TemporaryDirectory(prefix='cec-root-reference-')as work:
        projected=Path(work)/'native.kicad_pcb';field._save_field_snapshot(board,projected)
        text=_reference_literal(raw.raw_text(source),raw.raw_text(projected),proposal,manifest)
    raw.write_raw(candidate,text);return manifest


def _root_annotation_order(tree):
    """Native annotation vectors are unordered, not an item-order contract.

    Their complete UUID, text, pose, art, lock and membership trees compare.
    Literal receiving already preserves every source byte and exact generated
    annotation. Only the native serializer's root drawing/group order differs
    when a literal-retaining second prefix is loaded into a fresh board.
    """
    def is_annotation(n):return isinstance(n,list)and n and n[0]in(
        'group','gr_text','gr_text_box','gr_line','gr_rect','gr_poly','gr_arc','gr_circle','gr_curve')
    nodes=iter(sorted((n for n in tree if is_annotation(n)),key=repr))
    return [next(nodes)if is_annotation(n)else n for n in tree]


def _saved_replay_clock():
    return time.monotonic()


def _saved_replay_family(path):
    files=[]
    for item in path.parent.rglob('*'):
        require(not item.is_symlink(),'saved_reference_family_symlink_refused')
        if item.is_file():files.append(item)
    return force._family_file_hashes(files)


def _saved_replay_digest(value):
    return hashlib.sha256(repr(value).encode()).hexdigest()


class _SavedReplay:
    """Fresh expected native material, NOT a saved-candidate verdict.

    No mutable native board or serialized prepared state crosses this seam.
    Comparison owes the actual literal and TWO independently saved candidate
    trees. A failed, expired or consumed stage cannot be resumed.
    """
    def __init__(self,source,candidate,proposal,timeout_s):
        require(type(timeout_s)in(int,float)and math.isfinite(timeout_s)
            and 0<timeout_s<=10.,'bounded_saved_reference_stage_required')
        self._paths=tuple(Path(p).resolve(strict=True)for p in(source,candidate))
        require(self._paths[0]!=self._paths[1]and not self._paths[0].samefile(self._paths[1]),
            'distinct_saved_reference_mapping_candidate_required')
        self._proposal=copy.deepcopy(proposal);self._limit=timeout_s
        self._state='new';self._timings={};self._identity=None
        self._expected_tree=self._expected_literal=self._manifest=self._seal=None

    def _snapshot(self):
        import _pcbnew
        q=self._proposal;binding=q['binding']
        files=[Path(q['grade']).resolve(strict=True),Path(binding['native_report']).resolve(strict=True)]
        modules=(pcbnew,_pcbnew,field,additive,syntax)
        return dict(paths=[str(p)for p in self._paths],
            families=[force._family(p,q['board_hint'])for p in self._paths],
            complete_families=[_saved_replay_family(p)for p in self._paths],
            evidence={str(p):force._hash(p)for p in files},
            code_identity=force._code_identity(),
            implementation={str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))for m in modules},
            owner_sha256=force._hash(Path(__file__).resolve()),
            environment=sorted((k,v)for k,v in os.environ.items()if k.startswith(('CEC_','KICAD'))or k=='PATH'),
            proposal_sha256=_saved_replay_digest(q))

    def _material_seal(self):
        return _saved_replay_digest((self._expected_tree,self._expected_literal,self._manifest))

    def _stage(self,name,required,next_state,fn):
        require(self._state==required,'saved_reference_'+name+'_stage_order_required')
        self._state='failed';started=_saved_replay_clock()
        try:
            result=fn()
            require(_saved_replay_clock()-started<self._limit,'saved_reference_'+name+'_deadline')
            self._state=next_state
            return result
        finally:
            self._timings[name]=_saved_replay_clock()-started
            if self._state==next_state and not self._timings[name]<self._limit:
                self._state='failed'
                raise ValueError('saved_reference_'+name+'_deadline')

    def reconstruct(self):
        def run():
            self._identity=self._snapshot()
            source,candidate=self._paths;q=self._proposal
            # Existing construct independently replans and requires fresh==q.
            # Discovery board material or an old positive receipt is not used.
            board,manifest=construct(source,q)
            with tempfile.TemporaryDirectory(prefix='cec-reference-expected-')as work:
                expected=Path(work)/'board.kicad_pcb';field._save_field_snapshot(board,expected)
                normalize=(_root_annotation_order if q.get('reverse_ownership')=='rigid_root_group_per_component'else lambda tree:tree)
                self._expected_tree=syntax._freeze(normalize(additive._nodes(expected)[0]))
                if q.get('reverse_ownership')=='rigid_root_group_per_component':
                    import cec_source_retaining_ses_import as literal
                    self._expected_literal=_reference_literal(literal.raw_text(source),literal.raw_text(expected),q,manifest)
                expected_hash=force._hash(expected)
            # Retain no SWIG board and expose no mutable material to the caller.
            self._manifest=copy.deepcopy(manifest);self._seal=self._material_seal()
            require(self._snapshot()==self._identity,'saved_reference_inputs_changed_during_reconstruction')
            return dict(complete=True,reconstruction_only=True,saved_candidate_received=False,
                expected_native_sha256=expected_hash,private_material_sha256=self._seal,
                release_authority=False)
        return self._stage('reconstruct','new','reconstructed',run)

    def receive(self):
        def run():
            require(self._snapshot()==self._identity,'saved_reference_inputs_changed_before_comparison')
            require(self._material_seal()==self._seal,'saved_reference_expected_material_changed')
            source,candidate=self._paths;q=self._proposal
            with tempfile.TemporaryDirectory(prefix='cec-reference-compare-')as work:
                compared=candidate
                if q.get('reverse_ownership')=='rigid_root_group_per_component':
                    import cec_source_retaining_ses_import as literal
                    require(self._expected_literal==literal.raw_text(candidate),
                        'reference_mapping_changed_unowned_literal_source_evidence')
                    compared=Path(work)/'normalized-candidate.kicad_pcb'
                    field._save_field_snapshot(pcbnew.LoadBoard(str(candidate)),compared)
                normalize=(_root_annotation_order if q.get('reverse_ownership')=='rigid_root_group_per_component'else lambda tree:tree)
                require(self._expected_tree==syntax._freeze(normalize(additive._nodes(compared)[0])),
                    'reference_mapping_changed_unowned_board_evidence')
                second=Path(work)/'second-save.kicad_pcb'
                field._save_field_snapshot(pcbnew.LoadBoard(str(candidate)),second)
                require(self._expected_tree==syntax._freeze(normalize(additive._nodes(second)[0])),
                    'reference_mapping_is_not_stable_under_a_second_native_save')
            require(force._sidecars(source)==force._sidecars(candidate),'reference_mapping_changed_companions_or_factory_rules')
            require(q['binding']['source_family']==force._family(source,q['board_hint']),
                'reference_mapping_original_family_changed')
            require(self._snapshot()==self._identity,'reference_mapping_family_or_runtime_changed_during_saved_receiving')
            require(self._material_seal()==self._seal,'saved_reference_expected_material_changed')
            return dict(ok=True,complete=True,errors=[],fab_ready=False,release_authority=False,
                source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
                code_identity=force._code_identity(),source_bound_projection_exact=True,
                all_copper_parts_pads_poses_outlines_models_bom_values_mpns_and_rules_exact=True,
                reference_identity_preserved=True,actual_reverse_text_mirroring_proved=True,
                manifest=copy.deepcopy(self._manifest),whole_saved_second_native_roundtrip_stable=True,
                source_candidate_families_and_code_unchanged=True,
                fresh_native_drc_and_actual_front_back_visual_review_still_required=True)
        return self._stage('compare','reconstructed','received',run)

    def observation(self):
        return dict(state=self._state,phase_timings_s=copy.deepcopy(self._timings),
            constituent_timeout_s=self._limit,identity=copy.deepcopy(self._identity),
            no_saved_verdict_or_new_construction_authority=True)


def saved_replay(source,candidate,proposal,*,timeout_s=10.):
    """Two real finite stages: independent reconstruction then saved comparison."""
    return _SavedReplay(source,candidate,proposal,timeout_s)


def receive(source,candidate,proposal):
    # Compatibility composition, not a new aggregate ten-second permission.
    # Explicit composed callers must consume the two constituent stages.
    result=dict(ok=False,complete=False,errors=[],fab_ready=False,release_authority=False)
    try:
        replay=saved_replay(source,candidate,proposal)
        replay.reconstruct()
        return replay.receive()
    except (ValueError,RuntimeError,KeyError,TypeError,OSError)as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def main():
    import cec_swig_guard;cec_swig_guard.pin()
    import wx
    quiet=wx.LogNull()
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','grade','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--hint',required=True);p.add_argument('--maximum-components',type=int,default=6)
    p.add_argument('--seed-index',type=int)
    p.add_argument('--max-seeds',type=int,default=16)
    a=p.parse_args();require(not a.out.exists(),'fresh_reference_mapping_work_required')
    require(1<=a.max_seeds<=32,'bounded_reference_mapping_seed_search_required')
    failed=[];proposal=None
    for index in ([a.seed_index] if a.seed_index is not None else range(a.max_seeds)):
        try:
            proposal=plan(a.source,grade=a.grade,board_hint=a.hint,maximum_components=a.maximum_components,seed_index=index)
            break
        except ValueError as exc:
            failed.append(dict(seed_index=index,reason=str(exc)))
    require(proposal is not None,'finite_reference_mapping_search_exhausted:'+str(failed))
    b,manifest=construct(a.source,proposal);child=force._copy_family(a.source,a.out/'UNADMITTED-reference-map')
    field._save_field_snapshot(b,child);proof=receive(a.source,child,proposal)
    require(proof['ok'] and proof['complete'],str(proof['errors']))
    report=a.out/'native.json';shadow=force._copy_family(child,a.out/'native-input')
    produced=native.run(shadow,report,reporting_build=a.reporting_build,timeout_s=10.,board_hint=a.hint)
    require(produced['ok'] and produced['complete'] and not produced['native_inventory']['potentially_truncated'],
        'complete_reference_mapping_native_drc_required')
    after=json.loads(report.read_text());before=json.loads(Path(proposal['binding']['native_report']).read_text())
    known={admission._canonical_identity(v) for v in before['violations']}
    fresh=[v for v in after['violations'] if admission._canonical_identity(v) not in known]
    result=dict(ok=not fresh and not after['unconnected_items'],complete=True,changed=True,
        source=str(a.source.resolve()),source_sha256=force._hash(a.source),candidate=str(child),candidate_sha256=force._hash(child),
        code_identity=force._code_identity(),proposal=proposal,manifest=manifest,independent_annotation_receiving=proof,
        native_producer=produced,new_native_faults=fresh,opens=len(after['unconnected_items']),
        source_raw_native_count=len(before['violations']),candidate_raw_native_count=len(after['violations']),
        prior_seed_refusals=failed,source_seed_domain_exhaustive=False,
        errors=[] if not fresh and not after['unconnected_items'] else ['native_reference_mapping_refused'],
        records=[dict(plan=dict(proposal=proposal),materialized=manifest)],
        source_family_and_code_unchanged=proof['source_candidate_families_and_code_unchanged'],
        input_sha256={str(Path(__file__).resolve()):force._hash(Path(__file__)),
            str(a.grade.resolve()):force._hash(a.grade),
            proposal['binding']['native_report']:proposal['binding']['native_report_sha256']},
        routing_admitted=False,fab_ready=False,release_authority=False)
    force._write(a.out/'stage.json',result)
    print(json.dumps(dict(stage=str(a.out/'stage.json'),ok=result['ok'],mode=proposal['mode'],
        references=[r['reference'] for r in proposal['records']],raw_native=[result['source_raw_native_count'],result['candidate_raw_native_count']],new_native=fresh)),flush=True)


if __name__=='__main__':main()

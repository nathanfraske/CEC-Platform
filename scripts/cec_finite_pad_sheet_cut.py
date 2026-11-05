"""Necessary finite-pad sheet-exit bounds, never a passing route certificate.

A closed cut enclosing one terminal and excluding the opposite terminal bank
must pass the entire current, in either direction. Its length, thickness and a
specified local J limit bounds that flux from above. Only exact inscribed
rectangles of actual foreign cardinal copper are subtracted. Endcaps, curved
copper, outline, rule areas and same-net Kelvin restrictions are deliberately
NOT credited as obstructions: omitting them makes the ceiling optimistic,
never a false impossibility proof caused by raster/outer polygon inflation.

The J limit is an explicitly conditional diagnostic input. This module cannot
promote an advisory threshold, replace IPC trace widths, authorize sharing,
qualify contact/heating or grant a route/current/fabrication exemption.
"""
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import time

MM=1_000_000


def _positive(value, name):
    if type(value) is Fraction:
        if (0<value<=1_000_000 and value.numerator.bit_length()<=4096
                and value.denominator.bit_length()<=4096):return value
        raise ValueError('bounded_positive_rational_'+name+'_required')
    if (type(value) not in (int,float) or not 0 < value <= 1_000_000
            or not math.isfinite(value)):
        raise ValueError('finite_positive_'+name+'_required')
    return Fraction(str(value))


def _box(box):
    if (type(box) not in (tuple,list) or len(box)!=4
            or any(type(v) is not int or abs(v)>2_000_000_000 for v in box)
            or not box[0]<box[2] or not box[1]<box[3]):
        raise ValueError('bounded_nonempty_integer_rectangle_required')
    return tuple(box)


def _ratio(value):
    return dict(numerator=value.numerator,denominator=value.denominator,
                approximate=float(value))


def _union_length(rows):
    merged=[]
    for lo,hi in sorted(rows):
        if lo>=hi:continue
        if merged and lo<=merged[-1][1]:merged[-1][1]=max(hi,merged[-1][1])
        else:merged.append([lo,hi])
    return sum(hi-lo for lo,hi in merged),merged


def _bound(bounds, obstructions, *, current, copper, jlimit, deadline):
    x0,y0,x1,y1=_box(bounds)
    edges=[];blocked=0
    for name,axis,at,lo,hi in (('left',0,x0,y0,y1),('right',0,x1,y0,y1),
                              ('top',1,y0,x0,x1),('bottom',1,y1,x0,x1)):
        hits=[]
        for row in obstructions:
            if time.monotonic()>=deadline:raise ValueError('finite_sheet_cut_deadline')
            a,b,c,d=row['rectangle_nm']
            # A cut exactly on the boundary gets NO blocked-length credit.
            # This is conservative even when native manufacturing equality
            # would forbid contact there.
            low,high=(b,d) if axis==0 else (a,c)
            amin,amax=(a,c) if axis==0 else (b,d)
            start,end=max(lo,low),min(hi,high)
            if amin<at<amax and start<end:
                hits.append(dict(uuid=row['uuid'],kind=row['kind'],
                    interval_nm=[start,end],rectangle_nm=row['rectangle_nm']))
        size,merged=_union_length(row['interval_nm'] for row in hits)
        blocked+=size
        edges.append(dict(edge=name,axis=axis,coordinate_nm=at,interval_nm=[lo,hi],
            blocked_length_lower_nm=size,blocked_intervals_nm=merged,contributors=hits))
    perimeter=2*(x1-x0+y1-y0);available=perimeter-blocked
    capacity=Fraction(available,MM)*copper*jlimit
    return dict(bounds_nm=list(bounds),perimeter_nm=perimeter,
        blocked_length_lower_nm=blocked,available_length_upper_nm=available,
        sheet_capacity_upper_A=_ratio(capacity),required_current_A=_ratio(current),
        conditional_front_sheet_obstruction=capacity<current,edges=edges)


def _pad_rectangle(pad):
    import pcbnew
    if (pad.GetShape()!=pcbnew.PAD_SHAPE_RECT or tuple(pad.GetOffset())!=(0,0)
            or pad.Padstack().Mode()!=pcbnew.PADSTACK.MODE_NORMAL
            or float(pad.GetOrientationDegrees())%90!=0):
        return None
    b=pad.GetBoundingBox()
    return _box([int(b.GetX()),int(b.GetY()),int(b.GetRight()),int(b.GetBottom())])


def analyze(board,pad_uuid,remote_pad_uuids,*,current_A,copper_mm,j_limit_A_mm2,
            clearance_nm,cut_offsets_nm,timeout_s=2.):
    """Read-only conditional cuts of one actual single-surface rectangular pad.

    A positive obstruction applies ONLY if all current crosses between the
    inside terminal and exact outside bank, without any vertical bypass. This
    is a necessary geometry screen, not a constructive or physical verdict.
    """
    import pcbnew
    current=_positive(current_A,'current');copper=_positive(copper_mm,'copper')
    jlimit=_positive(j_limit_A_mm2,'conditional_J_limit')
    if (type(timeout_s) not in (int,float) or not 0<timeout_s<=9.1 or not math.isfinite(timeout_s)
            or type(clearance_nm) is not int or not 0<=clearance_nm<=5_000_000
            or type(cut_offsets_nm) not in (list,tuple) or not 1<=len(cut_offsets_nm)<=32
            or any(type(v) is not int or not 1<=v<=5_000_000 for v in cut_offsets_nm)
            or len(set(cut_offsets_nm))!=len(cut_offsets_nm)
            or type(pad_uuid) is not str or not pad_uuid
            or type(remote_pad_uuids) not in (list,tuple) or not 1<=len(remote_pad_uuids)<=64
            or any(type(v) is not str or not v or v==pad_uuid for v in remote_pad_uuids)
            or len(set(remote_pad_uuids))!=len(remote_pad_uuids)):
        raise ValueError('bounded_explicit_finite_sheet_cut_context_required')
    deadline=time.monotonic()+timeout_s
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    tracks=list(board.GetTracks())
    if len(pads)+len(tracks)>16384:raise ValueError('finite_sheet_native_inventory_bound')
    def uid(item):return str(item.m_Uuid.AsString())
    selected=[p for p in pads if uid(p)==pad_uuid]
    receivers=[p for p in pads if uid(p) in remote_pad_uuids]
    if len(selected)!=1 or len(receivers)!=len(remote_pad_uuids) or len({uid(p) for p in receivers})!=len(receivers):
        raise ValueError('unique_actual_finite_sheet_terminals_required')
    pad=selected[0]
    face=tuple(map(int,pad.GetLayerSet().CuStack()))
    bounds=_pad_rectangle(pad)
    if (pad.HasHole() or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or bounds is None
            or len(face)!=1 or face[0] not in (pcbnew.F_Cu,pcbnew.B_Cu)
            or face[0] not in set(map(int,board.GetEnabledLayers().CuStack()))
            or pad.GetNetCode()<=0
            or any(pad.GetNetCode()!=sink.GetNetCode() or not sink.IsOnLayer(face[0]) for sink in receivers)):
        raise ValueError('actual_single_surface_rectangular_injection_and_same_net_sink_required')
    sink_boxes=[]
    for sink in receivers:
        sb=sink.GetBoundingBox()
        sink_boxes.append(dict(uuid=uid(sink),bounds_nm=list(_box(
            [int(sb.GetX()),int(sb.GetY()),int(sb.GetRight()),int(sb.GetBottom())]))))
    obstructions=[];omitted={};seen=set()
    for item in [*pads,*tracks]:
        if time.monotonic()>=deadline:raise ValueError('finite_sheet_cut_deadline')
        if not item.IsOnLayer(face[0]) or item.GetNetCode()==pad.GetNetCode():continue
        key=uid(item)
        if key in seen:raise ValueError('ambiguous_foreign_native_uuid')
        seen.add(key)
        kind=item.GetClass();rectangles=[]
        if kind=='PAD':
            rect=(_pad_rectangle(item) if item.GetAttribute()==pcbnew.PAD_ATTRIB_SMD
                  and not item.HasHole() else None)
            if rect is not None:
                a,b,c,d=rect
                # Native bounding boxes may include integer rounding at the
                # edge. Credit only a strictly inset actual rectangle.
                a+=1;b+=1;c-=1;d-=1
                if a>=c or b>=d:
                    omitted[kind]=omitted.get(kind,0)+1
                    continue
                # Orthogonal strips are INSIDE the true Euclidean clearance
                # expansion. Do not substitute an oversized corner square.
                rectangles=[(a-clearance_nm,b,c+clearance_nm,d),
                            (a,b-clearance_nm,c,d+clearance_nm)]
        elif kind=='PCB_TRACK':
            a,b=map(int,item.GetStart());c,d=map(int,item.GetEnd())
            width=int(item.GetWidth())
            if width<=0:raise ValueError('positive_actual_foreign_track_width_required')
            radius=width//2+clearance_nm
            if radius>0 and a==c and b!=d:
                rectangles=[(a-radius,min(b,d),a+radius,max(b,d))]
            elif radius>0 and b==d and a!=c:
                rectangles=[(min(a,c),b-radius,max(a,c),b+radius)]
        if not rectangles:omitted[kind]=omitted.get(kind,0)+1
        for rect in rectangles:
            obstructions.append(dict(uuid=key,kind=kind,net=str(item.GetNetname()),
                rectangle_nm=list(_box(rect)),basis='exact_inscribed_foreign_body_clearance_rectangle'))
    cuts=[]
    for delta in sorted(cut_offsets_nm):
        x0,y0,x1,y1=bounds;cut=_box([x0-delta,y0-delta,x1+delta,y1+delta])
        for row in sink_boxes:
            sink_box=row['bounds_nm']
            if not (sink_box[2]<cut[0] or sink_box[0]>cut[2]
                    or sink_box[3]<cut[1] or sink_box[1]>cut[3]):
                raise ValueError('every_actual_sink_must_be_strictly_outside_every_cut')
        cuts.append(_bound(cut,obstructions,current=current,copper=copper,jlimit=jlimit,deadline=deadline))
    minimum=min(cuts,key=lambda r:Fraction(r['sheet_capacity_upper_A']['numerator'],r['sheet_capacity_upper_A']['denominator']))
    return dict(schema=1,complete=True,scope='conditional_necessary_single_surface_cut_flux_upper_bound',
        actual_pad_uuid=pad_uuid,actual_remote_pad_uuids=sorted(remote_pad_uuids),net=str(pad.GetNetname()),
        face=board.GetLayerName(face[0]),actual_pad_bounds_nm=list(bounds),sink_bounds=sink_boxes,
        model=dict(current_A=_ratio(current),copper_mm=_ratio(copper),j_limit_A_mm2=_ratio(jlimit),
                   clearance_nm=clearance_nm,J_limit_not_promoted_or_ratified_by_this_observer=True),
        cuts=cuts,minimum_cut=minimum,conditional_front_sheet_obstruction=minimum['conditional_front_sheet_obstruction'],
        omitted_foreign_native_classes=omitted,obstructions=obstructions,
        ignored_other_restrictions='outline_rule_areas_zones_holes_curved_copper_same_net_Kelvin_and_collector_connectivity',
        omission_only_increases_optimistic_capacity=True,conditional_geometry_only=True,
        assumptions=['all_required_unsigned_current_crosses_inside_terminal_cut','every_opposite_terminal_outside_cut',
                     'zero_vertical_current_exits_inside_cut','specified_local_sheet_J_and_thickness_model'],
        no_obstruction_is_not_a_route_or_capacity_pass=True,actual_network_or_current_sharing_not_inferred=True,
        board_mutated=False,qualified=False,current_qualified=False,release_authority=False)


def diagnose(source,*,expected_sha256,board_hint,net,pad_uuid,cut_offsets_nm,
             j_limit_A_mm2,timeout_s=9.1):
    """Bind a diagnostic to the actual complete Source current/terminal domain.

    The single finite land and EVERY opposite bank land are rederived, not
    chosen from a favorable path. Current/margin and modeled copper come from
    the existing Source contract/profile. The explicit J argument remains a
    conditional screen; no new replacement authority is emitted.
    """
    import pcbnew
    import cec_current_topology as topology
    import cec_fab_profile as fab
    import cec_force_current as force
    import cec_route_dimensions as dimensions
    _positive(j_limit_A_mm2,'conditional_J_limit')
    if (type(timeout_s) not in (int,float) or not 0<timeout_s<=9.1
            or type(expected_sha256) is not str or len(expected_sha256)!=64
            or any(c not in '0123456789abcdef' for c in expected_sha256)
            or type(board_hint) is not str or not board_hint or type(net) is not str or not net):
        raise ValueError('exact_saved_finite_sheet_diagnostic_identity_required')
    deadline=time.monotonic()+timeout_s
    source=str(Path(source).resolve())
    if force._hash(source)!=expected_sha256:raise ValueError('finite_sheet_Source_saved_hash_mismatch')
    family=force._family(source,board_hint);code=force._code_identity()
    board=pcbnew.LoadBoard(source)
    with force._thermal_hint(board_hint):
        domains=topology.board_current_domains(board,board_hint=board_hint)
        domain=domains.get(net) or {}
        if (domain.get('complete') is not True or domain.get('missing_refs')
                or not domain.get('source_refs') or not domain.get('sink_refs')):
            raise ValueError('complete_actual_finite_sheet_current_domain_required')
        authority=topology.current_contract_for_net(net,board_hint,domains)
        if (type(authority) is not dict or type(authority.get('margin_included')) is not bool):
            raise ValueError('unchanged_Source_current_and_margin_authority_required')
        amps=_positive(authority.get('amps'),'Source_current')
        margin=_positive(authority.get('geometry_margin'),'Source_geometry_margin')
        current=amps if authority['margin_included'] else amps*margin
        sources=[p for fp in board.GetFootprints() if fp.GetReference() in domain['source_refs']
            for p in fp.Pads() if str(p.GetNetname())==net]
        sinks=[p for fp in board.GetFootprints() if fp.GetReference() in domain['sink_refs']
            for p in fp.Pads() if str(p.GetNetname())==net]
        if len(sources)==1 and force._uid(sources[0])==pad_uuid and sinks:
            terminal,remote,role=sources[0],sinks,'declared_source'
        elif len(sinks)==1 and force._uid(sinks[0])==pad_uuid and sources:
            terminal,remote,role=sinks[0],sources,'declared_sink'
        else:raise ValueError('one_actual_finite_terminal_and_all_opposite_terminals_required')
        face=tuple(map(int,terminal.GetLayerSet().CuStack()))
        if len(face)!=1:raise ValueError('one_actual_finite_sheet_face_required')
        layer=board.GetLayerName(face[0])
        profile=fab.active_profile_name(board,hint=board_hint)
        if not profile:raise ValueError('Source_declared_copper_profile_required')
        copper=fab.copper_thickness_mm(profile,layer)
        spec=dimensions.project_resolver(source,board=board)(net) or {}
        own_clearance=spec.get('clearance')
        if (type(own_clearance) not in (int,float) or not 0<=own_clearance<=5
                or not math.isfinite(own_clearance)):
            raise ValueError('Source_project_native_clearance_required')
        # The dimension compiler publishes mm. Round its diagnostic exclusion
        # DOWN to integer nm, never inflate a blockage through float rounding.
        clearance=max(int(Fraction(str(own_clearance))*MM),int(board.GetDesignSettings().m_MinClearance))
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('finite_sheet_diagnostic_deadline')
        result=analyze(board,pad_uuid,[force._uid(p) for p in remote],current_A=current,
            copper_mm=copper,j_limit_A_mm2=j_limit_A_mm2,clearance_nm=clearance,
            cut_offsets_nm=cut_offsets_nm,timeout_s=min(9.1,remaining))
    family_after=force._family(source,board_hint);code_after=force._code_identity()
    if family!=family_after or code!=code_after or force._hash(source)!=expected_sha256:
        raise ValueError('finite_sheet_Source_or_code_changed_during_observation')
    if time.monotonic()>=deadline:raise ValueError('finite_sheet_diagnostic_deadline')
    result.update(source=source,source_sha256=expected_sha256,board_hint=board_hint,
        source_family=family,source_family_unchanged=True,
        code_digest=hashlib.sha256(json.dumps(code,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        code_file_count=len(code),code_unchanged=True,current_authority=authority,current_domain=domain,
        all_declared_opposite_lands_rederived=True,one_actual_declared_finite_terminal_rederived=True,
        declared_finite_terminal_role=role,unsigned_cut_not_dependent_on_current_direction=True,
        modeled_copper_profile=profile,model_copper_not_finished_order_minimum_or_maximum_qualification=True,
        Source_project_and_factory_clearance_floor_preserved=True,
        independent_native_DRC_Kelvin_field_current_and_thermal_gates_not_replaced=True)
    return result

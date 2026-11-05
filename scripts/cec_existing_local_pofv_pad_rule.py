"""Existing native local POFV rule for a literal saved SMD-owned entry.

This does not create a rule, lower board setup, qualify a remote field,
or bypass native geometry. The default inspector is centre-only; separate
explicit inspectors prove a fully contained Source-owned land, a direct
canonical bounded Source SMD dogbone, or an actual straight SMD-track body.
Unsupported/missing/dimension-overriding
rules fall back to the ordinary limits. Explicit non-barrel constraints may
coexist with the exact existing local rule; they are not evaluated or waived.
Actual group membership and saved native DRC still
have to be received after construction. Native KiCad's group-only control
proves that this existing custom rule overrides its board-setup defaults.
"""
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path

GROUP = 'CEC_LOCAL_POFV_SIGNAL_VIA'
CONDITION = "A.Type == 'Via' && A.memberOfGroup('CEC_LOCAL_POFV_SIGNAL_VIA')"
RULE_NAME = 'CEC local POFV signal via'
NON_BARREL_CONSTRAINTS = frozenset(('track_width','diff_pair_gap',
    'edge_clearance','hole_clearance'))
BARREL_CONSTRAINTS = frozenset(('via_diameter','hole_size','annular_width'))


def _unrelated_rule(node):
    """Prove syntax cannot alter a barrel-size floor, not native applicability.

    No generic rule-engine emulation: unknown constraints, disallow rules,
    severities, layer selectors, expressions or mixed dimension constraints
    refuse the context. All actual clearances remain separately guarded.
    """
    if (type(node) is not list or not 4<=len(node)<=8 or node[0]!='rule'
            or type(node[1]) is not str or not node[1] or node[1]=='"'+RULE_NAME+'"'):
        return False
    conditions=[r for r in node[2:] if type(r) is list and r and r[0]=='condition']
    if (len(conditions)!=1 or len(conditions[0])!=2
            or type(conditions[0][1]) is not str or not conditions[0][1].startswith('"')
            or not conditions[0][1].endswith('"') or len(conditions[0][1])<=2):return False
    constraints=[r for r in node[2:] if type(r) is list and r and r[0]=='constraint']
    if not constraints or len(constraints)+1!=len(node)-2:return False
    seen=set()
    for row in constraints:
        if (not 3<=len(row)<=4 or row[1] not in NON_BARREL_CONSTRAINTS
                or row[1] in seen):return False
        seen.add(row[1]);limits={}
        for bound in row[2:]:
            if (type(bound) is not list or len(bound)!=2 or bound[0] not in ('min','max')
                    or bound[0] in limits or type(bound[1]) is not str
                    or not bound[1].endswith('mm')):return False
            value=Decimal(bound[1][:-2])*1000000
            if not value.is_finite() or value!=int(value) or not 0<=value<=100000000:return False
            limits[bound[0]]=int(value)
        if limits.get('min',0)>limits.get('max',100000000):return False
    return True


def _shadowed_barrel_rule(node):
    """Only earlier min-only barrel constraints shadowed by the exact rule.

    KiCad evaluates constraints in reverse source order. The later literal
    local rule supplies ALL three barrel dimensions for its actual members,
    so an earlier rule of these types cannot change those dimensions. This
    is not a condition evaluator: no other constraint, max, layer selector,
    severity, disallow, duplicate or malformed field earns permission.
    https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#custom_design_rules
    """
    if (type(node) is not list or not 4<=len(node)<=6 or node[0]!='rule'
            or type(node[1]) is not str or not node[1]
            or node[1]=='"'+RULE_NAME+'"'):
        return False
    conditions=[r for r in node[2:] if type(r) is list and r and r[0]=='condition']
    if len(conditions)!=1:return False
    condition=conditions[0]
    if (len(condition)!=2
            or type(condition[1]) is not str or not condition[1].startswith('"')
            or not condition[1].endswith('"') or len(condition[1])<=2):return False
    seen=set()
    try:
        for constraint in node[2:]:
            if constraint is condition:continue
            if (type(constraint) is not list or len(constraint)!=3
                    or constraint[0]!='constraint' or constraint[1] not in BARREL_CONSTRAINTS
                    or constraint[1] in seen):return False
            seen.add(constraint[1]);bound=constraint[2]
            if (type(bound) is not list or len(bound)!=2 or bound[0]!='min'
                    or type(bound[1]) is not str or not bound[1].endswith('mm')):return False
            nm=Decimal(bound[1][:-2])*1000000
            if not nm.is_finite() or nm!=int(nm) or not 0<nm<=100000000:return False
    except (InvalidOperation,ValueError,TypeError):return False
    return bool(seen)


def _local_rule(root):
    if (type(root) is not list or not 2<=len(root)<=65 or root[0]!=['version','1']):return None
    local=[r for r in root[1:] if type(r) is list and len(r)>=2
        and r[:2]==['rule','"'+RULE_NAME+'"']]
    if len(local)!=1:return None
    local_index=next(i for i,row in enumerate(root) if row is local[0])
    for index,row in enumerate(root[1:],1):
        if row is local[0] or _unrelated_rule(row):continue
        if index<local_index and _shadowed_barrel_rule(row):continue
        return None
    return local[0]


def _pad(p):
    return (p.m_Uuid.AsString(), p.GetParentFootprint().m_Uuid.AsString(),
        str(p.GetNumber()), str(p.GetNetname()), int(p.GetAttribute()), int(p.GetShape()),
        tuple(p.GetPosition()), tuple(p.GetSize()), tuple(p.GetOffset()),
        tuple(p.GetDrillSize()), float(p.GetOrientationDegrees()),
        float(p.GetRoundRectRadiusRatio()), tuple(map(int,p.GetLayerSet().CuStack())))


def _floors(board):
    s=board.GetDesignSettings()
    return tuple(int(getattr(s,k)) for k in
        ('m_ViasMinSize','m_MinThroughDrill','m_ViasMinAnnularWidth','m_MinClearance','m_HoleToHoleMin'))


def bind_projected_source_poses(board,poses,*,allow_octilinear_rotations=False):
    """Explicit proposal context; resolve independently rederives every pad.

    This attribute grants no placement/route admission or native rule. The
    literal saved Source, original rule, whole rigid package and candidate
    pad must all independently match on each lookup. Default callers still
    require an unchanged saved pad, exactly as before.
    """
    import json,math
    if (type(poses) is not dict or not 1<=len(poses)<=32 or type(allow_octilinear_rotations) is not bool
            or any(type(r) is not str or type(p) not in (list,tuple) or len(p)!=3
                or any(type(n) not in (int,float) or not math.isfinite(n) for n in p)
                for r,p in poses.items())):
        raise ValueError('bounded_explicit_source_pad_rule_pose_context_required')
    board._cec_projected_saved_pad_rule_poses=json.loads(json.dumps(poses,allow_nan=False))
    board._cec_projected_saved_pad_rule_allow_octilinear_rotations=allow_octilinear_rotations


def _projected_package(board,source,pad):
    """A whole exact explicitly permitted package, not a resized candidate land."""
    import math,pcbnew
    poses=getattr(board,'_cec_projected_saved_pad_rule_poses',None)
    octilinear=getattr(board,'_cec_projected_saved_pad_rule_allow_octilinear_rotations',False)
    fp=pad.GetParentFootprint();ref=fp.GetReference()
    if type(poses) is not dict or ref not in poses or type(octilinear) is not bool:return None
    old=source.FindFootprintByReference(ref);pose=poses[ref]
    if old is None or old.IsLocked() or old.GetParentGroup() is not None:return None
    if (old.m_Uuid!=fp.m_Uuid or old.GetValue()!=fp.GetValue() or old.GetFPIDAsString()!=fp.GetFPIDAsString()
            or old.IsLocked()!=fp.IsLocked() or old.GetAttributes()!=fp.GetAttributes()
            or old.IsFlipped()!=fp.IsFlipped()
            or {f.GetName():f.GetText() for f in old.GetFields()}!={f.GetName():f.GetText() for f in fp.GetFields()}
            or list(fp.GetPosition())!=[round(n*1e6) for n in pose[:2]]
            or abs((fp.GetOrientationDegrees()-pose[2]+180)%360-180)>1e-9
            or (pose[2]-old.GetOrientationDegrees())%360 not in range(0,360,45 if octilinear else 90)
            or math.dist(tuple(old.GetPosition()),tuple(fp.GetPosition()))>32000000):return None
    projected=pcbnew.FOOTPRINT(old);projected.SetPosition(fp.GetPosition());projected.SetOrientationDegrees(pose[2])
    actual={p.m_Uuid.AsString():p for p in fp.Pads()};expected={p.m_Uuid.AsString():p for p in projected.Pads()}
    if (actual.keys()!=expected.keys() or len(actual)>256
            or any(_pad(actual[u])!=_pad(expected[u]) for u in expected)):return None
    # Compare actual native polygons too; a custom/chamfered pad cannot hide
    # altered geometry behind equal nominal size/shape/position fields.
    if any(actual[u].GetEffectivePolygon(l).Format()!=expected[u].GetEffectivePolygon(l).Format()
            for u in expected for l in expected[u].GetLayerSet().CuStack()):return None
    return dict(owner_uuid=fp.m_Uuid.AsString(),target_pose=list(pose),
        entire_source_native_package_rederived=True,placement_authority=False)


def resolve(board,pad):
    """Read-only source-derived context; no filename/profile alone grants it."""
    import pcbnew
    import cec_fab_profile as fab
    import cec_copper_echo as syntax
    try:
        path=Path(board.GetFileName())
        if not path.is_file() or path.suffix!='.kicad_pcb':return None
        rule_path=path.with_suffix('.kicad_dru')
        if not rule_path.is_file() or rule_path.stat().st_size>65536:return None
        text=rule_path.read_text(encoding='utf-8')
        # Only the exact local dimension rule is understood. Separate types
        # cannot override it; earlier min-only barrel constraints are proven
        # shadowed by that later literal rule, as in native KiCad. Later
        # dimensions and all unknown rule kinds still refuse. Conditions,
        # effects and clearances are never guessed or relaxed; actual saved
        # group membership and native DRC remain mandatory.
        content='\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))
        root=syntax._parse(syntax._TOKEN.findall('('+content+')'))
        rule=_local_rule(root)
        if rule is None or len(rule)!=6 or rule[2]!=['condition','"'+CONDITION+'"']:
            return None
        limits={}
        for node in rule[3:]:
            if (len(node)!=3 or node[0]!='constraint' or node[1] not in
                    ('via_diameter','hole_size','annular_width') or node[1] in limits
                    or type(node[2]) is not list or len(node[2])!=2 or node[2][0]!='min'
                    or not node[2][1].endswith('mm')):return None
            nm=Decimal(node[2][1][:-2])*1000000
            if not nm.is_finite() or nm!=int(nm) or not 1<=nm<=1000000:return None
            limits[node[1]]=int(nm)
        if len(limits)!=3:return None
        profile_name=fab.board_profile_name(board);profile=fab.PROFILES.get(profile_name)
        if not profile or not profile.get('pofv'):return None
        if (limits['hole_size']<round(profile['pofv_drill_min_mm']*1e6)
                or limits['annular_width']<round(profile['pofv_annular_min_mm']*1e6)):
            return None
        source=pcbnew.LoadBoard(str(path))
        if fab.board_profile_name(source)!=profile_name or _floors(source)!=_floors(board):return None
        groups=[g for g in source.Groups() if g.GetName()==GROUP]
        if len(groups)!=1 or not list(groups[0].GetItems()):return None
        members=list(groups[0].GetItems())
        if len(members)>1024 or any(v.GetClass()!='PCB_VIA'
                or v.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or not fab.pofv_dimensions(profile,v.GetWidth(v.TopLayer())/1e6,v.GetDrillValue()/1e6)[0]
                for v in members):return None
        ordinary=_floors(source)
        stricter_than_setup=(limits['via_diameter']>=ordinary[0]
            and limits['hole_size']>=ordinary[1] and limits['annular_width']>=ordinary[2])
        if not stricter_than_setup and not any(v.GetWidth(v.TopLayer())<ordinary[0]
                and fab.local_pofv_via_decision(source,v)[0] for v in members):return None
        actual=[p for fp in board.GetFootprints() for p in fp.Pads() if p.m_Uuid==pad.m_Uuid]
        original=[p for fp in source.GetFootprints() for p in fp.Pads() if p.m_Uuid==pad.m_Uuid]
        if len(actual)!=1 or len(original)!=1 or _pad(actual[0])!=_pad(pad):return None
        projected=None
        if _pad(original[0])!=_pad(pad):
            projected=_projected_package(board,source,pad)
            if projected is None:return None
        if (pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.HasHole() or pad.GetNetCode()<=0
                or tuple(pad.GetLayerSet().CuStack()) not in ((pcbnew.F_Cu,),(pcbnew.B_Cu,))
                or pad.GetShape() not in (pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_CIRCLE,
                    pcbnew.PAD_SHAPE_OVAL,pcbnew.PAD_SHAPE_ROUNDRECT)):
            return None
        result=dict(source=str(path.resolve()),source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            rule=str(rule_path.resolve()),rule_sha256=hashlib.sha256(rule_path.read_bytes()).hexdigest(),
            profile=profile_name,group=GROUP,pad_uuid=pad.m_Uuid.AsString(),
            minimum_nm=limits,ordinary_board_limits_nm=_floors(board)[:3],
            existing_native_rule_not_new_floor_waiver=True,native_saved_membership_and_DRC_required=True,
            fabrication_or_current_or_release_qualified=False)
        if projected is not None:result['projected_native_source_package']=projected
        if stricter_than_setup:result['all_local_dimensions_at_or_above_ordinary_setup']=True
        return result
    except (ValueError,TypeError,AttributeError,RuntimeError,OSError,InvalidOperation):
        return None


def geometry(context,requested):
    """Actual local rule and selected-process dimensions, not ordinary ones."""
    import cec_fab_profile as fab
    diameter,drill=map(float,requested);limits=context['minimum_nm']
    drill=max(round(drill*1e6),limits['hole_size'])
    diameter=max(round(diameter*1e6),limits['via_diameter'],drill+2*limits['annular_width'])
    result=diameter/1e6,drill/1e6
    if not fab.pofv_dimensions(fab.PROFILES[context['profile']],*result)[0]:
        raise ValueError('saved_local_pad_rule_geometry_outside_selected_process')
    return result


def inspect(board,pad,at,diameter_nm,drill_nm,net_code):
    import cec_fab_profile as fab
    context=resolve(board,pad)
    if (context is None or type(diameter_nm) is not int or type(drill_nm) is not int
            or int(pad.GetNetCode())!=net_code or pad.GetPosition()!=at):
        return None
    if geometry(context,(diameter_nm/1e6,drill_nm/1e6))!=(diameter_nm/1e6,drill_nm/1e6):return None
    if not fab._pad_contains_circle(pad,at,(diameter_nm+1)//2,tolerance_nm=0):return None
    return context


def inspect_contained(board,pad,at,diameter_nm,drill_nm,net_code):
    """Explicit off-centre entry, not a change to the centre-only inspector.

    The unchanged saved Source package and literal native group rule remain
    the authority. Strict pad containment and the existing assembly policy
    must independently hold; proposed free-interval metadata grants nothing.
    All-layer copper, hole, edge, live group and saved DRC checks are external.
    """
    import pcbnew
    import cec_fab_profile as fab
    import cec_native_contained_via_events as contained
    context=resolve(board,pad)
    if (context is None or type(diameter_nm)is not int or type(drill_nm)is not int
            or type(net_code)is not int or not isinstance(at,pcbnew.VECTOR2I)
            or int(pad.GetNetCode())!=net_code):return None
    if geometry(context,(diameter_nm/1e6,drill_nm/1e6))!=(diameter_nm/1e6,drill_nm/1e6):return None
    if (not fab._pad_contains_circle(pad,at,(diameter_nm+1)//2,tolerance_nm=0)
            or not contained.contains(pad,at,diameter_nm)
            or not fab.via_pad_decision(board,pad,at,diameter_nm,drill_nm,net_code)[0]):return None
    # Do not infer ownership from a coincident/partially overlapping second
    # native land, even on the same net or opposite surface.
    circle=pcbnew.SHAPE_CIRCLE(at,(diameter_nm+1)//2)
    owners=[p for f in board.GetFootprints()for p in f.Pads()
        if any(p.GetEffectiveShape(l).Collide(circle,0)for l in p.GetLayerSet().CuStack())]
    if len(owners)!=1 or owners[0].m_Uuid!=pad.m_Uuid:return None
    return context


def inspect_dogbone(board,proposal,at,diameter_nm,drill_nm,net_code):
    """Prove proposed local ownership under the SAME existing native rule.

    No automatic nearest-pad inference, arbitrary field, partial overlap,
    multi-leg ownership, profile-only floor waiver or Source rule edit. The
    literal Source SMD must own the start of one exact 0/45-degree segment,
    and both its length and the pad-to-via reach are process bounded. This
    preflight does not grant route/current admission: construction must add
    that real copper, re-prove live ownership and existing group membership,
    and independently receive the saved native DRC and all Source deltas.
    """
    import pcbnew
    import cec_fab_profile as fab
    try:
        if (type(proposal) is not dict or set(proposal)!={'pad','start','layer'}
                or type(diameter_nm) is not int or type(drill_nm) is not int
                or type(net_code) is not int or type(proposal['layer']) is not int
                or not isinstance(proposal['start'],pcbnew.VECTOR2I)):
            return None
        pad,start,layer=proposal['pad'],proposal['start'],proposal['layer']
        context=resolve(board,pad)
        if context is None or int(pad.GetNetCode())!=net_code:return None
        groups=[g for g in board.Groups() if g.GetName()==GROUP]
        if len(groups)!=1 or groups[0].IsLocked() or not list(groups[0].GetItems()):return None
        if geometry(context,(diameter_nm/1e6,drill_nm/1e6))!=(diameter_nm/1e6,drill_nm/1e6):return None
        if (pad.GetParentFootprint().IsDNP() or tuple(map(int,pad.GetLayerSet().CuStack()))!=(layer,)
                or layer not in (pcbnew.F_Cu,pcbnew.B_Cu)):
            return None
        dx,dy=int(at.x-start.x),int(at.y-start.y)
        if (not (dx or dy) or not (dx==0 or dy==0 or abs(dx)==abs(dy))
                or not fab.local_pofv_dogbone_matches(pad,start,at,layer,net_code)):
            return None
        blocked,overlaps=fab.via_at_pad_conflicts(board,at,diameter_nm,drill_nm,net_code)
        # A fully contained land belongs to the original centre-only API;
        # this exact new context must be a genuine external dogbone seat.
        if blocked is not None or overlaps:return None
        return dict(context,bounded_source_smd_dogbone=dict(
            start_nm=list(start),end_nm=list(at),layer_id=layer,
            maximum_reach_mm=fab.LOCAL_POFV_REACH_MM,
            live_copper_group_membership_and_saved_native_DRC_still_required=True))
    except (ValueError,TypeError,AttributeError,RuntimeError,OverflowError):
        return None


def inspect_polyline(board,proposal,at,diameter_nm,drill_nm,net_code):
    """Existing literal rule on exactly two proposed canonical SMD limbs.

    This does not create a floor or recognize an arbitrary nearby net. The
    same saved Source SMD/group/process proof as the direct dogbone remains
    mandatory, as do real new copper, live two-leg ownership and saved DRC.
    """
    import pcbnew
    import cec_fab_profile as fab
    try:
        if (type(proposal) is not dict or set(proposal)!={'pad','points','layer'}
                or type(diameter_nm) is not int or type(drill_nm) is not int
                or type(net_code) is not int or type(proposal['layer']) is not int
                or not isinstance(at,pcbnew.VECTOR2I)):
            return None
        pad,points,layer=proposal['pad'],proposal['points'],proposal['layer']
        context=resolve(board,pad)
        if context is None:return None
        groups=[g for g in board.Groups() if g.GetName()==GROUP]
        if len(groups)!=1 or groups[0].IsLocked() or not list(groups[0].GetItems()):return None
        if geometry(context,(diameter_nm/1e6,drill_nm/1e6))!=(diameter_nm/1e6,drill_nm/1e6):return None
        if (not fab.local_pofv_polyline_matches(pad,points,layer,net_code)
                or points[-1]!=at):return None
        blocked,overlaps=fab.via_at_pad_conflicts(board,at,diameter_nm,drill_nm,net_code)
        if blocked is not None or overlaps:return None
        return dict(context,bounded_source_smd_two_leg_dogbone=dict(
            points_nm=[list(p)for p in points],layer_id=layer,
            maximum_reach_mm=fab.LOCAL_POFV_REACH_MM,
            live_copper_group_membership_and_saved_native_DRC_still_required=True))
    except (ValueError,TypeError,AttributeError,RuntimeError,OverflowError):
        return None


def inspect_source_track_body(board,proposal,at,diameter_nm,drill_nm,net_code):
    """Prove an existing local rule on real, already constructed SMD copper.

    This is the same exact native subinterval accepted by factory and saved
    additive receiving, not proximity, a proposed multi-leg path or an alias
    for the direct dogbone inspector. The complete straight track must really
    exist on this board. Only its bounded Source-SMD-owned subinterval earns
    the existing local dimensions; every physical guard, saved group and DRC
    check remains mandatory. No current or retirement authority is implied.
    """
    import pcbnew
    import cec_fab_profile as fab
    try:
        if (type(proposal) is not dict or set(proposal)!={'pad','track'}
                or type(diameter_nm) is not int or type(drill_nm) is not int
                or type(net_code) is not int or not isinstance(at,pcbnew.VECTOR2I)):
            return None
        pad,track=proposal['pad'],proposal['track']
        context=resolve(board,pad)
        if (context is None or pad.GetParentFootprint().IsDNP()
                or int(pad.GetNetCode())!=net_code or track.GetClass()!='PCB_TRACK'
                or int(track.GetNetCode())!=net_code
                or tuple(map(int,pad.GetLayerSet().CuStack()))!=(int(track.GetLayer()),)
                or track.GetLayer() not in (pcbnew.F_Cu,pcbnew.B_Cu)):
            return None
        groups=[g for g in board.Groups() if g.GetName()==GROUP]
        if len(groups)!=1 or groups[0].IsLocked() or not list(groups[0].GetItems()):return None
        if geometry(context,(diameter_nm/1e6,drill_nm/1e6))!=(diameter_nm/1e6,drill_nm/1e6):return None
        def signature(item):
            return (item.GetClass(),item.m_Uuid.AsString(),int(item.GetNetCode()),
                int(item.GetLayer()),tuple(item.GetStart()),tuple(item.GetEnd()),int(item.GetWidth()))
        actual=[t for t in board.GetTracks() if t.m_Uuid==track.m_Uuid]
        if len(actual)!=1 or signature(actual[0])!=signature(track):return None
        track=actual[0]
        via=pcbnew.PCB_VIA(board);via.SetPosition(at);via.SetNetCode(net_code)
        via.SetWidth(diameter_nm);via.SetDrill(drill_nm)
        via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        if not fab.local_pofv_body_contact_matches(pad,track,via):return None
        blocked,overlaps=fab.via_at_pad_conflicts(board,at,diameter_nm,drill_nm,net_code)
        # Fully contained pads use their separate explicit inspector. A body
        # context cannot disguise any partial or second-land overlap either.
        if blocked is not None or overlaps:return None
        return dict(context,bounded_source_smd_track_body=dict(
            track_uuid=track.m_Uuid.AsString(),start_nm=list(track.GetStart()),
            end_nm=list(track.GetEnd()),layer_id=int(track.GetLayer()),via_axis_nm=list(at),
            maximum_reach_mm=fab.LOCAL_POFV_REACH_MM,
            actual_native_track_required=True,
            live_copper_group_membership_and_saved_native_DRC_still_required=True))
    except (ValueError,TypeError,AttributeError,RuntimeError,OverflowError):
        return None
